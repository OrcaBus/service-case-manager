# Case Manager

One of the microservices in the OrcaBus that handles all the case information.

The case manager uses the Django framework.


## Running Locally

Requirement:

- Python
- Docker

```bash
docker -v
Docker version 27.3.1, build ce12230

python3 --version
Python 3.13.5
```

You would need to go to this microservice app directory from the root project

### Setup

You would need to set up the Python environment (conda or venv)

```bash
conda create -n orcabus_cm python=3.13
conda activate orcabus_cm
```

or with venv as an alternative

```bash
python3 -mvenv .venv
source .venv/bin/activate
```

Before starting the app we need to install the dependencies

```bash
make install
```
### Start

To start the application run the start command. This will run the server at `http://localhost:8000/`

```bash
make start
```

### Stop

To stop the running server, simply use the `make stop` command

### Testing

To run the test from scratch use `make test`, but if you want to test with a running database you could use `make suite`
.

Coverage test

```bash
make coverage
```

### Development

#### Migrations

From time to time the model of the app will need to change and apply the migrations. The following command will create
the migration changes and apply the migration respectively.

```bash
make makemigrations
make migrate
```

#### SQL Queries

To quickly run raw sql queries to the database, `make psql` will log in to the psql server.
