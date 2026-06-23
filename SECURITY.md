# Security Policy

## Supported Versions

surreal-basics is pre-1.0; security fixes are applied to the latest released
minor version on PyPI. Please upgrade to the most recent version before
reporting an issue.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, report privately via one of:

- GitHub's [private vulnerability reporting](https://github.com/lfnovo/surreal-basics/security/advisories/new)
- Email: lfnovo@gmail.com

Include a description, affected versions, and reproduction steps where possible.
You can expect an initial acknowledgement within a few business days. Once a fix
is available, a new release will be published and the advisory disclosed.

## Scope

surreal-basics is a connection/query abstraction over the official SurrealDB SDK.
Record/table identifiers passed to `repo_upsert`, `repo_update`, and
`repo_relate` (and their `_sync` counterparts) are **bound as query
parameters / `RecordID` objects** rather than interpolated into SurrealQL, so a
malicious identifier cannot alter query structure. A lightweight
`validate_identifier` guard runs as defense-in-depth.

When you build raw SurrealQL yourself via `repo_query` / `repo_query_sync`,
always parameterize user-supplied **values** through the `vars` argument rather
than formatting them into the query string. A basic guard rejects obvious injection markers, but full
parameterization of identifiers is tracked as a hardening task.
