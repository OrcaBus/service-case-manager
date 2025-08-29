.PHONY: *

DB_HOSTNAME ?= localhost
DB_PORT ?= 5432

# installation
install:
	@pip install -r deps/requirements-dev.txt

check: lint

lint:
	@black -t py312 --check . --exclude .venv

lint-fix:
	@black -t py312 . --exclude .venv

# docker compose shortcut
up:
	@docker compose up --wait -d

down:
	@docker compose down

ps:
	@docker compose ps

## docker - psql
reset-db:
	@docker exec -e PGPASSWORD=orcabus -it orcabus_db psql -h $(DB_HOSTNAME) -U orcabus -d orcabus -c "DROP DATABASE IF EXISTS case_manager;"
	@docker exec -e PGPASSWORD=orcabus -it orcabus_db psql -h $(DB_HOSTNAME) -U orcabus -d orcabus -c "CREATE DATABASE case_manager;"

psql:
	@docker exec -e PGPASSWORD=orcabus -it orcabus_db psql -h $(DB_HOSTNAME) -U orcabus -d case_manager

# application

start: migrate
	@python manage.py runserver

docker-start: migrate
	@python manage.py runserver 0.0.0.0:8000

stop: down

makemigrations:
	@python manage.py makemigrations

migrate:
	@python manage.py migrate

mock: reset-db migrate
	@python manage.py insert_mock

suite:
	@python manage.py test --parallel

coverage:
	@coverage run manage.py test
	@coverage report -m

# full mock suite test pipeline - install deps, bring up compose stack, run suite, bring down compose stack
test: install up suite down
