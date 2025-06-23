# Case Manager Service

```
Namespace: orcabus.casemanager
```

## CDK

See [README.md](../README.md)

## How to run Case Manager locally

### Ready Check

- Go to the Django project root

```
cd app
```

_If you use PyCharm then annotate this `app/` directory as "source" directory in the project structure dialog._

### Python

- Setup Python environment (conda or venv)

```
conda create -n case-manager python=3.12
conda activate case-manager
```

### Make

- At app root, perform

```
make install
make up
make ps
```

### Migration

```
python manage.py help
python manage.py showmigrations
python manage.py makemigrations
python manage.py migrate
```

### Mock Data

_^^^ please make sure to run `python manage.py migrate` first! ^^^_

#### Generate Case Record

```
python manage.py help generate_mock_case
    > Generate mock Case data into database for local development and testing
```

```
python manage.py generate_mock_case
```

#### Generate domain model for event schema

```
# generate models for all schemas
make schema-gen

# generate model for a specific schema
# CaseStateChange
schema-gen-csc

```

#### Generate Hello Event

TODO

#### Generate Domain Event

TODO

### Run API

```
python manage.py runserver_plus
```

```
curl -s http://localhost:8000/api/v1/case | jq
```

Or visit in browser:

- http://localhost:8000/api/v1

### API Doc

#### Swagger

- http://localhost:8000/schema/swagger-ui/

#### OpenAPI v3

- http://localhost:8000/schema/openapi.json

## Local DB

```
make psql
```

```
case_manager# \l
case_manager# \c case_manager
case_manager# \dt
case_manager# \d
case_manager# \d case_manager_case
case_manager# select count(1) from case_manager_case;
case_manager# select * from case_manager_case;
case_manager# \q
```

## Testing

### Coverage report

```
make coverage report
```

_The HTML report is in `htmlcov/index.html`._

### Run test suite

```
make suite
```

### Unit test

```
python manage.py test case_manager.tests.test_case.CaseModelTests.test_minimal_case
```


## Tear Down

```
make down
```
