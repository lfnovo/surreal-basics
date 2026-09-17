"""Tests for per-call and per-context targets (#34)."""

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from surreal_basics import (
    Target,
    current_target,
    init,
    repo_create,
    repo_query,
    repo_query_sync,
    repo_select,
    use_target,
)
from surreal_basics.connection import ConnectionManager
from surreal_basics.exceptions import SurrealDBConnectionError, SurrealDBQueryError
from surreal_basics.migrate import AsyncMigrationRunner, MigrationRunner
from surreal_basics.target import resolve_target

from .conftest import TEST_DB, TEST_NS


def _ns(label: str) -> str:
    """A namespace no other test (or earlier run) uses."""
    return f"sbl_{label}_{uuid.uuid4().hex[:8]}"


class TestTargetValidation:
    def test_token_and_username_are_exclusive(self):
        with pytest.raises(ValueError, match="either token or username"):
            Target(username="u", password="p", token="t")

    def test_username_requires_password(self):
        with pytest.raises(ValueError, match="together"):
            Target(username="u")
        with pytest.raises(ValueError, match="together"):
            Target(password="p")

    def test_rejects_unknown_auth_scope(self):
        with pytest.raises(ValueError, match="auth_scope"):
            Target(auth_scope="tenant")  # type: ignore[arg-type]

    def test_repr_hides_secrets(self):
        text = repr(Target(username="u", password="hunter2"))
        text += repr(Target(token="sekrit-token"))
        text += repr(resolve_target(Target(token="sekrit-token")))
        assert "hunter2" not in text
        assert "sekrit-token" not in text


class TestLayering:
    def test_fields_fall_through(self):
        merged = Target(database="app").over(Target(namespace="t1", database="old"))
        assert (merged.namespace, merged.database) == ("t1", "app")

    def test_credential_is_replaced_as_a_group(self):
        outer = Target(username="svc", password="pw")
        merged = Target(token="jwt").over(outer)
        assert merged.token == "jwt"
        assert merged.username is None and merged.password is None

    def test_credential_survives_a_namespace_only_layer(self):
        outer = Target(username="svc", password="pw")
        merged = Target(namespace="t2").over(outer)
        assert (merged.username, merged.password) == ("svc", "pw")


class TestResolve:
    def test_config_is_the_default(self, reset_config):
        init(namespace="ns", database="db", user="u", password="p")
        resolved = resolve_target()
        assert (resolved.namespace, resolved.database) == ("ns", "db")
        assert resolved.credentials == {"username": "u", "password": "p"}

    def test_context_over_config_and_explicit_over_context(self, reset_config):
        init(namespace="ns", database="db")
        with use_target(namespace="ctx"):
            assert resolve_target().namespace == "ctx"
            explicit = resolve_target(Target(namespace="arg"))
            assert (explicit.namespace, explicit.database) == ("arg", "db")

    def test_scoped_signin_binds_to_the_target_namespace(self, reset_config):
        init(namespace="ns", database="db")
        resolved = resolve_target(
            Target(
                namespace="t1",
                username="u",
                password="p",
                auth_scope="namespace",
            )
        )
        assert resolved.credentials == {
            "username": "u",
            "password": "p",
            "namespace": "t1",
        }

    def test_token_skips_signin_credentials(self, reset_config):
        resolved = resolve_target(Target(token="jwt"))
        assert resolved.token == "jwt"
        assert resolved.credentials is None

    def test_key_changes_with_the_credential_only(self, reset_config):
        a = resolve_target(Target(username="u", password="one"))
        b = resolve_target(Target(username="u", password="two"))
        same = resolve_target(Target(username="u", password="one"))
        assert a.key != b.key
        assert a.key == same.key
        assert "one" not in repr(a.key)


class TestUseTarget:
    def test_binds_and_restores(self):
        assert current_target() is None
        with use_target(namespace="t1") as bound:
            assert current_target() == bound == Target(namespace="t1")
            with use_target(database="app"):
                assert current_target() == Target(namespace="t1", database="app")
            assert current_target() == Target(namespace="t1")
        assert current_target() is None

    def test_restores_after_an_exception(self):
        with pytest.raises(RuntimeError):
            with use_target(namespace="t1"):
                raise RuntimeError
        assert current_target() is None

    def test_none_is_a_no_op(self):
        with use_target(None):
            assert current_target() is None

    def test_target_and_fields_are_exclusive(self):
        with pytest.raises(TypeError):
            use_target(Target(namespace="a"), database="b")

    @pytest.mark.asyncio
    async def test_async_with(self):
        async with use_target(namespace="t1"):
            assert current_target() == Target(namespace="t1")
        assert current_target() is None

    @pytest.mark.asyncio
    async def test_concurrent_tasks_do_not_see_each_other(self):
        started = asyncio.Event()

        async def bound(ns):
            async with use_target(namespace=ns):
                started.set()
                await asyncio.sleep(0.01)
                return current_target().namespace

        async def unbound():
            await started.wait()
            return current_target()

        results = await asyncio.gather(bound("t1"), bound("t2"), unbound())
        assert results == ["t1", "t2", None]


class _FakeSync:
    """Records what the manager does to a connection."""

    def __init__(self, url):
        self.url = url
        self.closed = False
        self.signed_in_with = None
        self.token = None
        self.ns_db = None

    def signin(self, credentials):
        self.signed_in_with = credentials

    def authenticate(self, token):
        self.token = token

    def use(self, ns, db):
        self.ns_db = (ns, db)

    def close(self):
        self.closed = True


class _FakeAsync(_FakeSync):
    async def signin(self, credentials):  # type: ignore[override]
        self.signed_in_with = credentials

    async def authenticate(self, token):  # type: ignore[override]
        self.token = token

    async def use(self, ns, db):  # type: ignore[override]
        self.ns_db = (ns, db)

    async def close(self):  # type: ignore[override]
        self.closed = True


@pytest.fixture
def fake_server(reset_config, monkeypatch):
    """A ws config whose connections are fakes, with a cap of two."""
    monkeypatch.setattr("surreal_basics.connection.Surreal", _FakeSync)
    monkeypatch.setattr("surreal_basics.connection.AsyncSurreal", _FakeAsync)
    monkeypatch.setattr(ConnectionManager, "max_connections", 2)
    init(host="localhost", port=8000, mode="ws", namespace="base", database="app")
    ConnectionManager.reset()
    yield
    ConnectionManager.reset()


class TestPoolSync:
    def _open(self, ns):
        with ConnectionManager.get_sync_connection(Target(namespace=ns)) as conn:
            return conn

    def test_one_connection_per_target(self, fake_server):
        first = self._open("t1")
        assert self._open("t1") is first
        assert self._open("t2") is not first
        assert first.ns_db == ("t1", "app")

    def test_evicts_the_least_recently_used(self, fake_server):
        t1, t2 = self._open("t1"), self._open("t2")
        self._open("t1")  # t2 is now the oldest
        t3 = self._open("t3")
        assert t2.closed
        assert not t1.closed and not t3.closed
        assert len(ConnectionManager._sync_slots) == 2

    def test_never_evicts_a_connection_in_use(self, fake_server):
        with ConnectionManager.get_sync_connection(Target(namespace="t1")) as held:
            self._open("t2")
            self._open("t3")
            assert not held.closed
        assert not held.closed

    def test_token_authenticates_instead_of_signing_in(self, fake_server):
        with ConnectionManager.get_sync_connection(Target(token="jwt")) as conn:
            assert conn.token == "jwt"
            assert conn.signed_in_with is None

    def test_separate_credentials_get_separate_connections(self, fake_server):
        a = Target(namespace="t1", username="a", password="pa")
        b = Target(namespace="t1", username="b", password="pb")
        with ConnectionManager.get_sync_connection(a) as conn_a:
            pass
        with ConnectionManager.get_sync_connection(b) as conn_b:
            pass
        assert conn_a is not conn_b
        assert conn_b.signed_in_with == {"username": "b", "password": "pb"}

    def test_config_change_reaches_the_connection(self, fake_server):
        """#33: changing the configured namespace used to be silently ignored."""
        with ConnectionManager.get_sync_connection() as before:
            pass
        init(namespace="other")
        with ConnectionManager.get_sync_connection() as after:
            pass
        assert after is not before
        assert after.ns_db == ("other", "app")


class TestPoolAsync:
    async def _open(self, ns):
        async with ConnectionManager.get_async_connection(Target(namespace=ns)) as c:
            return c

    @pytest.mark.asyncio
    async def test_evicts_the_least_recently_used(self, fake_server):
        t1, t2 = await self._open("t1"), await self._open("t2")
        await self._open("t1")
        t3 = await self._open("t3")
        assert t2.closed
        assert not t1.closed and not t3.closed

    @pytest.mark.asyncio
    async def test_never_evicts_a_connection_in_use(self, fake_server):
        async with ConnectionManager.get_async_connection(
            Target(namespace="t1")
        ) as held:
            await self._open("t2")
            await self._open("t3")
            assert not held.closed

    @pytest.mark.asyncio
    async def test_concurrent_first_use_shares_one_connection(self, fake_server):
        conns = await asyncio.gather(*(self._open("t1") for _ in range(5)))
        assert len({id(c) for c in conns}) == 1
        assert not conns[0].closed


class TestMemoryEngine:
    def test_targets_switch_the_engine(self, surreal_config_memory):
        a, b = Target(namespace="mem_a"), Target(namespace="mem_b")
        repo_query_sync("CREATE item SET n = 1", using=a)
        assert repo_query_sync("SELECT * FROM item", using=b) == []
        assert len(repo_query_sync("SELECT * FROM item", using=a)) == 1

    def test_refuses_a_second_target_while_one_is_held(self, surreal_config_memory):
        with ConnectionManager.get_sync_connection(Target(namespace="mem_a")):
            with pytest.raises(SurrealDBConnectionError, match="one target at a time"):
                repo_query_sync("RETURN 1", using=Target(namespace="mem_b"))
            # The same target nests fine.
            assert repo_query_sync("RETURN 1", using=Target(namespace="mem_a")) == 1

    @pytest.mark.asyncio
    async def test_async_targets_switch_the_engine(
        self, surreal_config_memory, async_cleanup
    ):
        async with use_target(namespace="mem_async_a"):
            await repo_query("CREATE item SET n = 1")
        async with use_target(namespace="mem_async_b"):
            assert await repo_query("SELECT * FROM item") == []

    @pytest.mark.asyncio
    async def test_async_same_target_runs_concurrently(
        self, surreal_config_memory, async_cleanup
    ):
        async def work(i):
            async with use_target(namespace="mem_async_c"):
                return await repo_query("RETURN $i", {"i": i})

        assert await asyncio.gather(*(work(i) for i in range(5))) == list(range(5))


@pytest.fixture
def namespaces(surreal_config_ws):
    """Two fresh namespaces, removed afterwards."""
    created = [_ns("a"), _ns("b")]
    yield created
    for ns in created:
        repo_query_sync(f"REMOVE NAMESPACE IF EXISTS {ns}")
    init(namespace=TEST_NS, database=TEST_DB, user="root", password="root")


@pytest.mark.integration
class TestTargetsIntegration:
    @pytest.mark.asyncio
    async def test_concurrent_requests_land_in_their_own_namespace(
        self, namespaces, async_cleanup
    ):
        async def handler(ns):
            async with use_target(namespace=ns):
                for _ in range(20):
                    await repo_query("CREATE item SET ns = $ns", {"ns": ns})
                    assert await repo_query("RETURN session::ns()") == ns

        await asyncio.gather(*(handler(ns) for ns in namespaces))

        for ns in namespaces:
            rows = await repo_query(
                "SELECT VALUE ns FROM item", using=Target(namespace=ns)
            )
            assert rows == [ns] * 20

    @pytest.mark.asyncio
    async def test_using_on_crud_helpers(self, namespaces, async_cleanup):
        a, b = (Target(namespace=ns) for ns in namespaces)
        created = await repo_create("item", {"name": "only-in-a"}, using=a)
        if isinstance(created, list):
            created = created[0]
        assert (await repo_select(created["id"], using=a))["name"] == "only-in-a"
        try:
            rows = await repo_select("item", using=b)
        except SurrealDBQueryError as e:
            # SurrealDB 3 rejects selecting a table that was never defined.
            assert "does not exist" in str(e)
        else:
            assert rows == []

    def test_threads_use_their_own_target(self, namespaces):
        def handler(ns):
            with use_target(namespace=ns):
                for _ in range(10):
                    repo_query_sync("CREATE item SET ns = $ns", {"ns": ns})
                return repo_query_sync("RETURN session::ns()")

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(handler, namespaces)) == namespaces

        for ns in namespaces:
            rows = repo_query_sync(
                "SELECT VALUE ns FROM item", using=Target(namespace=ns)
            )
            assert rows == [ns] * 10

    def test_http_uses_the_target(self, namespaces, surreal_config_http):
        ns = namespaces[0]
        assert repo_query_sync("RETURN session::ns()", using=Target(namespace=ns)) == ns
        assert repo_query_sync("RETURN session::ns()") == TEST_NS

    @pytest.mark.asyncio
    async def test_per_target_credentials(self, namespaces, async_cleanup):
        own, other = namespaces
        await repo_query(
            "DEFINE USER tenant ON NAMESPACE PASSWORD 'pw' ROLES OWNER",
            using=Target(namespace=own),
        )
        tenant = dict(username="tenant", password="pw", auth_scope="namespace")

        result = await repo_query(
            "RETURN session::ns()", using=Target(namespace=own, **tenant)
        )
        assert result == own

        # The user exists only in its own namespace.
        with pytest.raises(SurrealDBConnectionError):
            await repo_query("RETURN 1", using=Target(namespace=other, **tenant))

    @pytest.mark.asyncio
    async def test_token_target(self, namespaces, async_cleanup):
        from surrealdb import AsyncSurreal

        from .conftest import TEST_HOST, TEST_PORT

        own = namespaces[0]
        await repo_query(
            "DEFINE USER tenant ON NAMESPACE PASSWORD 'pw' ROLES OWNER",
            using=Target(namespace=own),
        )
        raw = AsyncSurreal(f"ws://{TEST_HOST}:{TEST_PORT}/rpc")
        try:
            tokens = await raw.signin(
                {"username": "tenant", "password": "pw", "namespace": own}
            )
        finally:
            await raw.close()
        token = getattr(tokens, "access", tokens)

        result = await repo_query(
            "RETURN session::ns()",
            using=Target(namespace=own, token=token),
        )
        assert result == own


@pytest.fixture
def migrations_dir(tmp_path):
    (tmp_path / "001_widgets.surrealql").write_text(
        "DEFINE TABLE IF NOT EXISTS widget SCHEMALESS;\n"
    )
    return tmp_path


@pytest.mark.integration
class TestMigrationFanOut:
    def test_changing_the_configured_namespace_between_runs(
        self, namespaces, migrations_dir
    ):
        """#33: every iteration used to migrate the first namespace."""
        for ns in namespaces:
            init(namespace=ns)
            MigrationRunner(migrations_dir).run_up()

        for ns in namespaces:
            runner = MigrationRunner(migrations_dir, using=Target(namespace=ns))
            assert runner.status()["current_version"] == 1

    def test_runner_with_an_explicit_target(self, namespaces, migrations_dir):
        own, other = namespaces
        MigrationRunner(migrations_dir, using=Target(namespace=own)).run_up()

        assert (
            MigrationRunner(migrations_dir, using=Target(namespace=own)).status()[
                "current_version"
            ]
            == 1
        )
        assert (
            MigrationRunner(migrations_dir, using=Target(namespace=other)).status()[
                "current_version"
            ]
            == 0
        )

    @pytest.mark.asyncio
    async def test_async_runners_in_parallel(
        self, namespaces, migrations_dir, async_cleanup
    ):
        await asyncio.gather(
            *(
                AsyncMigrationRunner(
                    migrations_dir, using=Target(namespace=ns)
                ).run_up()
                for ns in namespaces
            )
        )
        for ns in namespaces:
            status = await AsyncMigrationRunner(
                migrations_dir, using=Target(namespace=ns)
            ).status()
            assert status["current_version"] == 1
