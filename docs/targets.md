# Targets

By default every operation runs against the namespace, database and user from
the global configuration (`init()` or the `SURREAL_*` variables). A **target**
overrides any of those for a single call or for a block of code, so one process
can serve several namespaces, or several users, at the same time.

Typical cases:

- A multi-tenant service with one namespace per tenant, picking the namespace
  from each incoming request.
- A tenant whose namespace has its own scoped user, so requests run with that
  user's permissions instead of a shared root login.
- Forwarding the end user's own access token to the database.
- Migrating many namespaces from one process.

## Per call: `using=`

Every `repo_*` function takes a keyword-only `using=` argument:

```python
from surreal_basics import Target, repo_query, repo_create

await repo_query("SELECT * FROM item", using=Target(namespace="tenant_a"))
await repo_create("item", {"name": "x"}, using=Target(namespace="tenant_b", database="app"))
```

## Per block: `use_target()`

`use_target()` binds a target for everything inside the block, including
functions it calls that don't know about targets:

```python
from surreal_basics import use_target, repo_query

async def handler(request):
    async with use_target(namespace=tenant_of(request), database="app"):
        return await repo_query("SELECT * FROM item")
```

It works with both `with` and `async with`. The binding is stored in a
`contextvars.ContextVar`, so:

- concurrent asyncio tasks each see their own target;
- tasks created inside the block inherit it;
- threads start without one, so each thread binds its own.

`use_target(None)` does nothing, which lets you pass an optional target
straight through. `current_target()` returns what is bound right now.

## Which settings apply

Each layer overrides only the fields it sets:

1. `using=` on the call
2. the innermost `use_target()` block, layered over any outer blocks
3. the global configuration

```python
init(namespace="default", database="app")

with use_target(namespace="tenant_a"):
    await repo_query("...")                                  # tenant_a / app
    await repo_query("...", using=Target(database="audit"))  # tenant_a / audit
```

The credential fields (`username`/`password` and `token`) count as one group:
a layer that sets any of them replaces the whole credential from the layers
below. A token bound for a block is never combined with a username from an
outer block.

## Credentials

### Scoped users

```python
tenant = Target(
    namespace="tenant_a",
    username="tenant_user",
    password=secret,
    auth_scope="namespace",   # or "database", or "root"
)
await repo_query("SELECT * FROM item", using=tenant)
```

With a namespace or database scope, the signin is bound to the target's own
namespace (and database), which is what `DEFINE USER ... ON NAMESPACE` and
`ON DATABASE` users need. The same user cannot sign in to another tenant's
namespace, so a wrong namespace fails instead of reading someone else's data.

### Tokens

```python
await repo_query("SELECT * FROM item", using=Target(namespace="tenant_a", token=jwt))
```

The connection authenticates with the token instead of signing in. A token
cannot be refreshed by the library. Once it expires, queries fail with an
authentication error, and a new target needs a new token.

`Target` refuses a token combined with a username, and a username without a
password. Secrets are left out of `repr()`.

## Connections

In the persistent network modes (WebSocket, and HTTP with `persistent=True`),
each distinct target gets its own connection, keyed by URL, namespace,
database and credential. The key holds a hash of the credential, not the
credential itself. The default target keeps using a single connection, as
before. Async connections also belong to the event loop that opened them, so
the same target on two loops means two connections.

HTTP with `persistent=False` opens a new connection for every operation, target
or not. Memory and embedded modes are covered [below](#memory-and-embedded-modes).

Idle connections are capped at `ConnectionManager.max_connections` (32 by
default). Past that, the least recently used idle connection is closed, on the
event loop that owns it. A connection that a query is using is never closed
under it:

- eviction skips it, so under load the limit can be exceeded briefly;
- when it has to be replaced (a rejected or unrefreshable token), it leaves the
  pool at once, so new operations get a fresh connection, and is closed when
  its last user finishes.

`reset_connections()` is the exception: it closes everything immediately.

```python
from surreal_basics import ConnectionManager

ConnectionManager.max_connections = 128
```

Connections also pick up configuration changes: calling `init(namespace=...)`
after a connection is open makes later operations use the new namespace. Before
0.9.0 the change was ignored until `reset_connections()` was called.

### Memory and embedded modes

These modes run the database inside the process, and a second `mem://` handle
would be a separate, empty database. So all targets share one engine, and the
engine switches namespace and database when a different target asks for it.

"One engine" means one per API: the sync functions and the async functions
each have their own, as they did before targets. In `memory` mode they are two
separate databases.

The engine holds one namespace and database at a time. Asking for a different
target while a connection to another is still in use raises
`SurrealDBConnectionError`. Sequential switching, and concurrent use of the
same target, both work. Credentials are ignored in these modes, as before.

## Migrating several namespaces

```python
import asyncio

from surreal_basics import Target
from surreal_basics.migrate import MigrationRunner, AsyncMigrationRunner

for tenant in tenants:
    MigrationRunner("migrations", using=Target(namespace=tenant)).run_up()

# or concurrently (server modes only; see the memory/embedded note above)
await asyncio.gather(*(
    AsyncMigrationRunner("migrations", using=Target(namespace=t)).run_up()
    for t in tenants
))
```

See [Migrations](migrations.md#several-namespaces).
