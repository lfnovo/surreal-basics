# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-07-05

### Added

- Namespace/database-scoped signin (#17). New `auth_scope` config
  (`init(auth_scope=...)` or `SURREAL_AUTH_SCOPE`, default `"root"`):
  `"namespace"`/`"database"` bind the signin to the configured namespace (and
  database), enabling users defined with `DEFINE USER ... ON NAMESPACE` /
  `ON DATABASE`. Previously the signin was always root-level, so scoped users
  failed with an authentication error. The scope applies to every signin the
  library performs, including token refresh and reconnects. An invalid scope
  raises `ValueError` at config time.

### Fixed

- Persistent async singletons (WS and HTTP) now survive event-loop turnover
  (#20). The connection is bound to the loop it was created on; reusing it
  from a new loop — e.g. Streamlit's one-`asyncio.run()`-per-interaction
  pattern — failed with `RuntimeError: ... attached to a different loop`, and
  the error wasn't recognized by the self-heal machinery, so every subsequent
  call failed too. The manager now tracks the owning loop per async singleton
  and transparently rebuilds the connection when checked out from a different
  loop (the stale reference is dropped without close, since closing needs the
  original — usually already closed — loop).

## [0.5.0] - 2026-07-05

### Changed

- **Breaking:** `repo_create`/`repo_create_sync` no longer inject `created` and
  `updated` timestamps into the payload by default (#18). SurrealDB 3.x
  SCHEMAFULL tables reject undefined fields, so the unconditional injection
  broke inserts into tables that don't define both (e.g. append-only tables
  with only `created`). Timestamps should be owned by the schema
  (`DEFINE FIELD created ... DEFAULT time::now()`); the old behavior is
  available opt-in via `add_timestamps=True`.
- **Breaking:** `repo_update`/`repo_update_sync` no longer inject `updated`
  by default, for the same reason. Opt back in with `add_timestamp=True`
  (mirroring `repo_upsert`).
- `repo_create`/`repo_create_sync` now strip an `id` key from `data` before
  insert (as `repo_upsert` already did), keeping create-without-id semantics
  consistent across the family.

## [0.4.1] - 2026-06-23

### Fixed

- The expired-token self-heal from 0.4.0 now also covers callers that use the
  connection **directly** (`async with get_async_connection() as db:
  await db.query(...)`), not just the `repo_*` helpers (#15). Two changes:
  - **Proactive refresh:** persistent `ws`/HTTP connections track the JWT `exp`
    and re-`signin()` in place before the token lapses, so every checkout hands
    out a valid-auth connection regardless of how it's used.
  - **Reactive fallback:** the auth-rejection guard now also catches the *raw*
    `surrealdb` error a direct caller sees (previously only the translated
    `SurrealDBQueryError` from the `repo_*` path was caught), so the singleton
    is reset and the next call reconnects even without the retry decorator.

## [0.4.0] - 2026-06-23

### Added

- Record/table identifiers in `repo_upsert`, `repo_update`, and `repo_relate`
  (sync and async) are now **bound as query parameters / `RecordID` objects**
  instead of being interpolated into SurrealQL, closing the injection surface
  (#10). `repo_update`/`repo_relate` use the SDK's native `merge` /
  `insert_relation`; `repo_upsert` uses a parameterized `UPSERT $what MERGE`.
  A lightweight `validate_identifier` guard remains as defense-in-depth.
- Configuration now fails fast: a non-integer `SURREAL_PORT` or an unsupported
  `SURREAL_URL` scheme raises `ValueError` at config time instead of silently
  defaulting.
- Project tooling: ruff (lint + format), mypy, pre-commit, a `Makefile`,
  `.env.example`, `docker-compose.yml`, `CONTRIBUTING.md`, and `SECURITY.md`.
- The integration test suite now starts/stops SurrealDB via `docker compose`
  automatically (override with `SBL_TEST_DOCKER=0`) and runs against both a
  **SurrealDB v2 and v3** server (`SBL_TEST_SURREAL_VERSION`). CI gained
  lint/type-check and a v2/v3 integration matrix, and measures coverage.

### Fixed

- Restored transparent WebSocket reconnect on the 2.x SDK. A dropped persistent
  socket surfaces in 2.x as a bare `KeyError(<request-uuid>)` (the in-flight
  request's future map is cleared on close), which the previous drop-detection
  set did not catch — the first call after a drop leaked a raw `KeyError`
  instead of reconnecting. `KeyError` is now treated as a WS-drop on the WS
  path, so the singleton is rebuilt and the operation retried transparently.
- Persistent connections now self-heal an expired/rejected auth token (#14). A
  `ws`/HTTP-persistent singleton signs in once and caches the token; against a
  backend with a time-limited token (e.g. SurrealDB Cloud's 60-minute JWT),
  queries began failing with `IAM error: Not enough permissions` once it lapsed,
  *without* the socket dropping, and stayed wedged until process restart. Such
  auth errors are now treated as "singleton is dead": the connection is rebuilt
  with a fresh `signin()` and the operation retried transparently. (Genuine
  permission denials are retried before surfacing, since they're textually
  indistinguishable from an expired token.)

### Changed

- **Upgraded to the `surrealdb` 2.x SDK** (`surrealdb>=2.0.0`), which supports
  SurrealDB servers v2.0.0–v3.x. The 2.x SDK raises typed exceptions instead of
  returning error strings inline; surreal-basics now translates those into its
  own `SurrealDBTransientError` / `SurrealDBQueryError` so the public exception
  contract and retry behavior are unchanged.
- Empty-string auth env vars (`SURREAL_PASS`/`PASSWORD`, `SURREAL_NS`/etc.) now
  fall back to defaults, matching how an unset variable is treated.

### Removed

- The vestigial `pydantic-core<2.44` constraint — the 2.x SDK no longer pulls in
  full `pydantic`.

### Notes

- **SurrealDB v3 behavior:** v3 is stricter than v2 — reading from a table that
  was never defined raises an error instead of returning an empty list.
  surreal-basics surfaces this rather than masking it; define the table or
  insert a record before selecting.

## [0.3.2] - 2026-05-13

### Fixed

- Persistent WebSocket singleton now detects a dropped underlying socket
  (idle timeout, network blip, server-side close) and rebuilds itself on the
  next call. Previously, the `_ws_*_connected` flag was set once at signin
  and never cleared on a runtime drop, so every operation after the drop
  failed with `websockets.exceptions.ConnectionClosedError: no close frame
  received or sent`. The fix wraps the WS yield in `get_async_connection` /
  `get_sync_connection`, catches `ConnectionClosed`, resets the singleton,
  and re-raises as `SurrealDBTransientError` — letting `surreal_retry_async`
  / `surreal_retry` reconnect transparently
  ([#7](https://github.com/lfnovo/surreal-basics/issues/7)).

## [0.3.1] - 2026-05-12

### Fixed

- `SURREAL_URL` with `wss://` or `https://` scheme no longer silently downgrades
  to plaintext `ws://` / `http://`. The TLS information is preserved end-to-end
  through `SurrealConfig.get_url()`, unblocking Surreal Cloud and any
  TLS-fronted SurrealDB deployment ([#5](https://github.com/lfnovo/surreal-basics/issues/5)).
- When `SURREAL_URL` has no explicit port and uses a TLS scheme, the default
  port is now `443` (was `8000`).

### Changed

- `SURREAL_URL` is now authoritative for the port when set. A leftover
  `SURREAL_PORT=8018` from a local `.env` no longer leaks into a
  `SURREAL_URL=wss://...` cloud run — the URL's explicit port (or its
  scheme default) wins. `SURREAL_PORT` continues to work unchanged in
  the "no URL, build from parts" mode. To override a URL's port, set
  the port explicitly in `SURREAL_URL` itself.

### Added

- `tls` field on `SurrealConfig` and `tls` argument on `init()` to force TLS
  on/off independently of the URL scheme.
- `SURREAL_TLS` environment variable to override TLS at runtime.

## [0.3.0] - 2026-03-28

### Added

- Embedded/file-based connection mode (`mode="embedded"`, `path="./data.db"`)
- In-memory connection mode (`mode="memory"`) - no server required
- `path` parameter in `init()` and `SurrealConfig` for embedded file path
- `SURREAL_PATH` environment variable for embedded mode
- Auto-detection of `file://`, `mem://`, `memory://`, `surrealkv://` schemes in `SURREAL_URL`
- GitHub Actions workflows for tag creation and PyPI publishing

### Changed

- Bumped `surrealdb` dependency to `>=1.0.7` (required for embedded support)
- Bumped minimum Python version to `>=3.11`
- `parse_record_ids()` now uses `table_name:id` format instead of `str()` to avoid `⟨⟩` escaping in SDK v1.0.8
- `repo_select()` with a specific record ID returns a `dict` again (SDK v1.0.8 changed to returning a list)

## [0.2.0] - 2026-03-19

### Added

- Migration system for managing SurrealDB schema changes
  - `MigrationRunner` (sync) and `AsyncMigrationRunner` (async) for programmatic usage
  - `sbl-migrate` CLI with `up`, `down`, `status`, and `create` commands
  - Auto-discovery of `.surrealql` migration files with numeric prefix ordering
  - Rollback support via `_down.surrealql` files
  - Migration tracking via `_sbl_migrations` table
  - `python -m surreal_basics.migrate` entry point
- `SurrealDBMigrationError` exception
- `SURREAL_MIGRATIONS_DIR` environment variable for default migrations directory
- Migration documentation (`docs/migrations.md`)

## [0.1.2] - Initial release

### Added

- Async and sync repository functions (`repo_query`, `repo_create`, `repo_select`, etc.)
- WebSocket and HTTP connection management with persistent (singleton) connections
- Automatic retry for transient errors (lock conflicts) via tenacity
- Environment-based configuration (`SURREAL_HOST`, `SURREAL_PORT`, etc.)
- `parse_record_ids` and `ensure_record_id` utilities
- Custom exception hierarchy (`SurrealDBError`, `SurrealDBQueryError`, etc.)
