# Tech Stack & Commands

## Stack

- **Language:** Python 3.13 (`>=3.13`, pinned via `.python-version`)
- **Framework:** Django 5.2 + Django REST Framework
- **API schema:** drf-spectacular (OpenAPI), Swagger UI at `/schema/swagger-ui/`
- **Database:** PostgreSQL (via `psycopg[binary]`), run locally through Docker Compose
- **Package/dependency manager:** `uv` (with `uv.lock`); dependency groups `dev` and `test`
- **Formatter:** `black` (target `py312`)
- **History/audit:** `django-simple-history`
- **Events:** AWS EventBridge via `boto3`; observability via `aws-xray-sdk`
- **Deployment:** AWS Lambda using `serverless-wsgi` (see `handler/api.py`)
- **Validation/models for events:** `pydantic` v2; event models generated from JSON Schema

## Common commands (via Makefile)

Run these from the `case-manager` directory.

```bash
make install        # uv python install + uv sync --group dev
make start          # migrate then run dev server at http://localhost:8000
make up / make down # start / stop the docker compose DB stack
make migrate        # apply migrations
make makemigrations # create migrations after model changes
make mock           # reset db, migrate, insert mock data
make psql           # open psql against the case_manager database
make reset-db       # drop and recreate the case_manager database
```

## Linting & formatting

```bash
make lint      # black --check (py312), excludes .venv
make lint-fix  # black auto-format
```

Always run `make lint-fix` (or `black`) before finishing a change. Do not
reformat unrelated files.

## Testing

```bash
make test      # full pipeline: install, bring up compose, run suite, bring down
make suite     # run the Django test suite against a running database
make coverage  # coverage run + report
```

- Tests use Django's `TestCase`, `factory-boy` factories (`app/tests/factories.py`),
  and `unittest.mock` / `mockito`.
- Test files live in `app/tests/` and are named `test_*.py`.
- Do NOT add tests unless they are requested or clearly part of the task.

## Event model generation

Event payload models are generated from JSON Schema with `datamodel-code-generator`.
When editing an event contract, update the `*.schema.json` under
`app/schemas/events/` and regenerate:

```bash
make -C app/schemas generate-event-models
```

Do not hand-edit the generated `*_model.py` files.

## Long-running processes

`make start` and any `runserver` command are long-running. Do not launch them in
a blocking terminal call; ask the user to run them in their own terminal instead.
