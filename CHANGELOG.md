# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/). Until 1.0, minor versions may
change the API.

## [Unreleased]

## [0.1.0] - 2026-09-25

First release, a rewrite of the original prototype.

### Added

- `Client`: token from `ACTIVITYINFO_TOKEN`, configurable server URL for
  self-managed servers, retries with backoff, and typed errors
  (`AuthenticationError`, `NotFoundError`, `PermissionDeniedError`, ...).
- Databases: list, get, find, create, delete, billing account; folders
  (create, nest, rename, move, delete); printable resource tree; batched
  changes with `DatabaseChanges`.
- Roles and permissions modelled on the R package (`Role`, `Grant`,
  `resource_permissions()`, `database_permissions()`, role parameters,
  record-level formulas, optional grants); database users (invite, change
  role, grants, remove, unlock, restore); read-only billing accounts.
- Forms: one class per field type, `FormSchema` (lossless round trip of the
  API's JSON), create forms and subforms, add, delete and recover fields,
  relocate and duplicate forms.
- Records: get, add, update, delete, recover, history; bulk writes in batches
  of 200; values keyed by field code, id or label and converted with the
  form's schema; lookups by key values (`find`, `ref`, `find_all`).
- Tables: lazy queries (`select`, `where`, `filter`, `sort`, `offset`,
  `limit`) with R-style default columns; pandas support as an optional extra
  (`to_pandas`, `FormSchema.from_data`, `add_many(df)`).
- Jobs: bulk import through the server's import pipeline (updating records
  that match on key fields), form and database exports, XLSForm import,
  database duplication, audit log.

### Removed

- The prototype's object API (`Manager`, `Field`, `Record` and its
  `Database`/`Folder`/`Form` classes).

[Unreleased]: https://github.com/pvernier/activipyinfo/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/pvernier/activipyinfo/releases/tag/v0.1.0
