"""Per-call and per-context connection targets.

A ``Target`` names the namespace, database and credential an operation should
run against. It can be passed to a single call (``using=``) or bound for a
block with ``use_target()``. Fields left as ``None`` fall through to the layer
below: an explicit ``using=`` over the bound context, the bound context over
the global config.

The binding lives in a ``ContextVar``, so concurrent asyncio tasks and threads
each see their own target.
"""

import hashlib
from contextvars import ContextVar, Token
from dataclasses import dataclass, field, replace
from typing import Any, Optional

from .config import _AUTH_SCOPES, AuthScope, SurrealConfig, get_config


@dataclass(frozen=True)
class Target:
    """Where, and as whom, an operation runs.

    Every field is optional. The credential fields form one group: a layer that
    sets any of ``username``, ``password`` or ``token`` replaces the whole
    credential of the layers below it, so a token bound for a block never
    signs in alongside an outer username.

    Args:
        namespace: Namespace to use.
        database: Database to use.
        username: User to sign in as. Requires ``password``.
        password: Password for ``username``.
        auth_scope: Signin scope for ``username``: ``"root"``, ``"namespace"``
            or ``"database"``, as in ``init()``. Scoped signins bind to this
            target's namespace (and database).
        token: An access token to authenticate with instead of signing in, e.g.
            the end user's own JWT. Mutually exclusive with ``username``.
    """

    namespace: Optional[str] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = field(default=None, repr=False)
    auth_scope: Optional[AuthScope] = None
    token: Optional[str] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.token is not None and (
            self.username is not None or self.password is not None
        ):
            raise ValueError(
                "Target takes either token or username/password, not both."
            )
        if (self.username is None) != (self.password is None):
            raise ValueError("Target username and password must be given together.")
        if self.auth_scope is not None and self.auth_scope not in _AUTH_SCOPES:
            raise ValueError(
                f"auth_scope must be one of {_AUTH_SCOPES}, got {self.auth_scope!r}."
            )

    def _sets_credential(self) -> bool:
        return self.username is not None or self.token is not None

    def over(self, below: Optional["Target"]) -> "Target":
        """This target's fields layered over ``below``'s."""
        if below is None:
            return self
        merged = replace(
            below,
            namespace=self.namespace if self.namespace is not None else below.namespace,
            database=self.database if self.database is not None else below.database,
            auth_scope=(
                self.auth_scope if self.auth_scope is not None else below.auth_scope
            ),
        )
        if self._sets_credential():
            merged = replace(
                merged,
                username=self.username,
                password=self.password,
                token=self.token,
            )
        return merged


_current: ContextVar[Optional[Target]] = ContextVar(
    "surreal_basics_target", default=None
)


def current_target() -> Optional[Target]:
    """The target bound by the innermost active ``use_target()``, if any."""
    return _current.get()


class use_target:
    """Bind a target for the enclosed block.

    Usable as ``with`` or ``async with``. Nested blocks layer over the outer
    one field by field (see ``Target``). ``use_target(None)`` is a no-op, so a
    caller can pass an optional target straight through.

    Example:
        async with use_target(namespace=tenant, database="app"):
            await repo_query("SELECT * FROM item")

    The binding is a ``ContextVar``: tasks created inside the block inherit it,
    and concurrent tasks or threads outside it never observe it.
    """

    def __init__(self, target: Optional[Target] = None, **fields: Any) -> None:
        if target is not None and fields:
            raise TypeError("use_target() takes a Target or keyword fields, not both.")
        self._target = Target(**fields) if fields else target
        self._token: Optional[Token[Optional[Target]]] = None

    def __enter__(self) -> Optional[Target]:
        if self._target is None:
            return _current.get()
        bound = self._target.over(_current.get())
        self._token = _current.set(bound)
        return bound

    def __exit__(self, *exc: object) -> None:
        if self._token is not None:
            _current.reset(self._token)
            self._token = None

    async def __aenter__(self) -> Optional[Target]:
        return self.__enter__()

    async def __aexit__(self, *exc: object) -> None:
        self.__exit__()


@dataclass(frozen=True)
class ResolvedTarget:
    """A target with every field filled in, ready to connect with.

    Internal. ``key`` identifies the connection it maps to; it carries a digest
    of the credential rather than the secret itself.
    """

    url: str
    namespace: str
    database: str
    credentials: Optional[dict] = field(default=None, repr=False)
    token: Optional[str] = field(default=None, repr=False)

    @property
    def key(self) -> tuple:
        secret: tuple
        if self.token is not None:
            secret = ("token", self.token)
        elif self.credentials is not None:
            secret = ("signin", tuple(sorted(self.credentials.items())))
        else:
            secret = ("none",)
        digest = hashlib.sha256(repr(secret).encode()).hexdigest()
        return (self.url, self.namespace, self.database, digest)


def _credentials_for(
    username: str, password: str, scope: AuthScope, namespace: str, database: str
) -> dict:
    """Signin payload for a scope. Scoped signins bind to the namespace/database,
    as required for DEFINE USER ... ON NAMESPACE/DATABASE."""
    credentials = {"username": username, "password": password}
    if scope in ("namespace", "database"):
        credentials["namespace"] = namespace
    if scope == "database":
        credentials["database"] = database
    return credentials


def resolve_target(
    using: Optional[Target] = None, config: Optional[SurrealConfig] = None
) -> ResolvedTarget:
    """Fill in a target: ``using`` over the bound context over the config."""
    config = config or get_config()
    layered = using.over(_current.get()) if using is not None else _current.get()
    t = layered or Target()

    namespace = t.namespace if t.namespace is not None else config.namespace
    database = t.database if t.database is not None else config.database

    if t.token is not None:
        return ResolvedTarget(config.get_url(), namespace, database, token=t.token)

    if t.username is not None:
        username, password = t.username, t.password or ""
    else:
        username, password = config.user, config.password
    scope = t.auth_scope if t.auth_scope is not None else config.auth_scope
    credentials = _credentials_for(username, password, scope, namespace, database)
    return ResolvedTarget(
        config.get_url(), namespace, database, credentials=credentials
    )
