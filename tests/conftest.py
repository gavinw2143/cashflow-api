import os

import psycopg
import pytest


@pytest.fixture
def db():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("TEST_DATABASE_URL not configured")

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("BEGIN")
        try:
            yield conn
        finally:
            conn.execute("ROLLBACK")
