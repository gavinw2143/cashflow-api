# cashflow-api

[![CI](https://github.com/gavinw2143/cashflow-api/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gavinw2143/cashflow-api/actions/workflows/ci.yml)

A Flask REST service that stores fixed-rate loans, generates amortization schedules, and aggregates projected cashflows across portfolios. Built with Python 3.14, Psycopg 3, PostgreSQL 17, Flyway, uv, and pytest.

## Features

- Portfolio creation with unique portfolio codes
- Loan creation with a transactionally persisted monthly amortization schedule
- Integer-cent storage and Decimal-based calculations, with explicit HALF_UP rounding
- Monthly portfolio-level principal and interest aggregation in PostgreSQL
- Input validation and HTTP responses for invalid inputs, missing records, and uniqueness conflicts
- Unit and PostgreSQL-backed integration tests, including a rollback regression test

## Quick start

Prerequisites: Docker with Compose, [uv](https://docs.astral.sh/uv/), and Make.

```sh
cp .env.example .env
# Edit .env to set a local POSTGRES_PASSWORD and matching URLs.
make migrate
make serve
```

The development API listens on `http://127.0.0.1:5000`. The PostgreSQL container binds to host loopback only (`127.0.0.1:5432`). Flask's built-in server is for development, not production.

## API

| Method | Path | Description |
| --- | --- | --- |
| POST | `/portfolios` | Create a portfolio |
| POST | `/portfolios/{portfolio_id}/loans` | Create a loan and its schedule |
| GET | `/loans/{loan_id}/schedule` | Retrieve scheduled installments |
| GET | `/portfolios/{portfolio_id}/cashflows` | Aggregate projected cashflows by month |

Create a portfolio:

```sh
curl -i http://127.0.0.1:5000/portfolios \
  -H 'Content-Type: application/json' \
  -d '{"code":"fixed-income","name":"Fixed Income Portfolio"}'
```

Create a fixed-rate loan (replace `1` with the returned portfolio ID):

```sh
curl -i http://127.0.0.1:5000/portfolios/1/loans \
  -H 'Content-Type: application/json' \
  -d '{
    "reference": "loan-001",
    "principal_cents": 120000,
    "annual_rate_bps": 525,
    "term_months": 12,
    "first_payment_date": "2026-11-01"
  }'
```

A successful POST returns HTTP 201 and the created record's ID. Loan creation validates the reference, principal, rate, term, and date. Relevant error statuses include 400 (invalid request), 404 (missing portfolio or loan), 409 (duplicate reference/code), and 415 (non-JSON content type).

Retrieve results:

```sh
curl http://127.0.0.1:5000/loans/1/schedule
curl http://127.0.0.1:5000/portfolios/1/cashflows
```

The cashflow endpoint groups installments by calendar month and returns totals for scheduled principal, interest, and combined payments.

## Data model

```text
portfolios (id PK, code UNIQUE, name)
    |
    +-- loans (id PK, portfolio_id FK, reference,
    |          principal_cents, annual_rate_bps,
    |          term_months, first_payment_date)
    |       |
    |       +-- scheduled_cashflows (
    |             loan_id FK, payment_number,
    |             due_date, principal_cents,
    |             interest_cents, remaining_balance_cents)
```

`loans` has a unique `(portfolio_id, reference)` constraint. Installments use `(loan_id, payment_number)` as a composite primary key and require unique `(loan_id, due_date)`. Foreign keys and CHECK constraints enforce basic referential integrity and nonnegative scheduled amounts. The Python repository inserts each loan and all its installments inside one explicit Psycopg transaction.

Schema changes are tracked in `migrations/V1__initial_schema.sql` by Flyway. Applied migrations are not edited; future changes should be added as new versions.

## Financial conventions

- All amounts are represented as integer **USD cents** in PostgreSQL.
- The annual fixed interest rate is stored in **basis points** (e.g., `525` means 5.25%), converted to a nominal monthly rate by dividing by 120,000.
- The amortization formula uses `Decimal` at precision 40; monthly interest and payment cents are rounded with `ROUND_HALF_UP`.
- The final installment repays the exact remaining balance to avoid residual rounding drift.
- Payment dates advance by calendar month and preserve month-end placement.
- The schedules are **projections**, not records of actual receipts, settlements, or delinquency. The model does not implement day-count conventions, prepayments, fees, variable rates, or production-grade financial validation.

## Tests and migrations

```sh
make up
docker compose exec -T db createdb -U cashflow cashflow_test
docker compose run --rm \
  -e FLYWAY_URL=jdbc:postgresql://db:5432/cashflow_test \
  flyway migrate

make test
make lint
uv run ruff format --check .
make validate
```

Create `cashflow_test` only once on a local PostgreSQL volume; if it already exists, skip the `createdb` command. `make test` loads `.env`; integration tests use `TEST_DATABASE_URL` and roll back their own changes. The CI workflow provisions a fresh test database, applies Flyway migrations, runs Ruff checks, and executes the full pytest suite. Missing test database configuration fails CI.

## Developer commands

| Command | Effect |
| --- | --- |
| `make migrate` | Start PostgreSQL and apply pending Flyway migrations |
| `make validate` | Validate applied Flyway migrations |
| `make info` | Inspect migration history |
| `make psql` | Open PostgreSQL's interactive shell |
| `make serve` | Launch Flask's local development server |
| `make test` | Run pytest with local environment |
| `make lint` | Run Ruff lint |
| `make down` | Stop Compose services without deleting database volumes |

The repository's Compose network uses a stable host-side bridge name (`br-cashflow`) to support restrictive local firewall configurations. Most environments do not need custom firewall rules; rules are host-specific and are not installed by this project.
