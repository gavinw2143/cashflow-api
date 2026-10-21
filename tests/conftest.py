import os

import psycopg
import pytest


@pytest.fixture
def db():
    dsn = os.environ.get("TEST_DATABASE_URL")

    if not dsn:
        if os.environ.get("CI") == "true":
            pytest.fail("TEST_DATABASE_URL is required in CI")
        pytest.skip("TEST_DATABASE_URL not configured")

    with psycopg.connect(
        dsn,
        autocommit=True,
        connect_timeout=5,
    ) as conn:
        conn.execute("BEGIN")
        try:
            yield conn
        finally:
            conn.execute("ROLLBACK")
