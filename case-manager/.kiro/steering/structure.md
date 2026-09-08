# Project Structure & Conventions

## Layout

```
case-manager/
├── manage.py                 # Django entrypoint (default settings: app.settings.local)
├── Makefile                  # dev/build/test commands
├── pyproject.toml            # deps managed by uv
├── compose.yml               # includes shared/mock-db.yml
├── handler/                  # AWS Lambda entrypoints
│   ├── api.py                # serverless-wsgi handler for the REST API
│   ├── sequence_run_linking.py
│   ├── workflow_run_linking.py
│   ├── metadata_manager_linking.py
│   ├── redcap_import.py
│   └── migrate.py
├── shared/                   # shared docker/db assets (init-db.sql, mock-db.yml)
├── docs/                     # schema diagram(s)
└── app/                      # the Django app
    ├── settings/             # base, local, aws, it (integration test)
    ├── urls/                 # base, local URL configs
    ├── models/               # one model (group) per file, re-exported in __init__.py
    ├── serializers/          # DRF serializers, mirrors models
    ├── viewsets/             # DRF viewsets, mirrors models
    ├── service/              # business logic / orchestration (the "service layer")
    ├── schemas/events/       # event JSON Schemas + generated pydantic models
    ├── management/commands/  # custom manage.py commands (import_redcap, insert_mock, ...)
    ├── migrations/
    ├── tests/                # test_*.py + factories.py
    ├── aws/                  # AWS integrations (event_bridge.py)
    ├── fields.py             # custom model fields (OrcaBusIdField / ULID)
    ├── pagination.py, renderers.py, routers.py
    └── wsgi.py
```

## Layering & where code goes

- **Viewsets** (`app/viewsets/`) handle HTTP: request parsing, permissions,
  serialization, and response shaping. Keep them thin.
- **Services** (`app/service/`) hold business logic and orchestration —
  especially anything that touches multiple models, emits events, or wraps a
  transaction. Prefer putting non-trivial logic here rather than in viewsets or
  handlers.
- **Lambda handlers** (`handler/`) are thin adapters that call `django.setup()`,
  parse the EventBridge event, and delegate to a service function.
- **Models** (`app/models/`) own persistence rules and invariants (e.g. link
  blocking on terminal statuses is enforced in `Case`-related models so every
  code path respects it).

## Conventions

- **Models per file:** each model (or tightly related group) lives in its own file
  under `app/models/` and is re-exported from `app/models/__init__.py`. Import
  models from `app.models`, not from the submodule.
- **Base classes:** models extend `BaseModel` (calls `full_clean()` on save and
  refreshes from DB) and use `BaseManager` for shared query helpers. Viewsets
  extend `BaseViewSet` / `BaseViewSetWithHistory`.
- **IDs:** primary keys use `OrcaBusIdField` (ULID-based, with a type prefix such
  as `cas` for Case). The stored value is the bare 26-char ULID; the prefix is
  added on read via `from_db_value`.
- **API casing:** the API is camelCase on the wire (djangorestframework-camel-case);
  Python code stays snake_case. Serializers/models use snake_case field names.
- **Read-only by default:** for `Case`, any field not in `API_WRITABLE_FIELDS` is
  read-only via `get_read_only_fields()`. Add a field name to `API_WRITABLE_FIELDS`
  only when it should be writable through the API.
- **History/audit:** use `BaseHistoricalRecords`. Set `instance._history_user`
  (the requester email, via `get_email_from_jwt`) before saving so the audit
  trail records the actor. Do NOT use `m2m .add()/.remove()` on `user_set` /
  `external_entity_set` — those bypass `save()` and skip history. Create/delete the
  through-model instances (`CaseUserLink`, `CaseExternalEntityLink`) directly.
- **Events:** emit via `app.aws.event_bridge.emit_event` with a generated pydantic
  event model. Emit only after the DB transaction commits using
  `transaction.on_commit(...)`, as the service layer does today.
- **Migrations:** after changing a model, run `make makemigrations` and commit the
  generated migration alongside the model change.
- **Formatting:** `black` (py312). Run `make lint-fix` before wrapping up.
