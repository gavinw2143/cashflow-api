import pytest

from cashflow_api.app import create_app


@pytest.fixture
def client(db, monkeypatch):
    # Route repository calls through the test transaction
    monkeypatch.setattr(
        "cashflow_api.app.get_db", lambda: db
    )

    app = create_app({"TESTING": True})
    return app.test_client()


def test_create_portfolio(client, db):
    response = client.post(
        "/portfolios",
        json={
            "code": "test-portfolio",
            "name": "Test Portfolio",
        },
    )

    assert response.status_code == 201

    data = response.get_json()
    assert data["code"] == "test-portfolio"
    assert data["name"] == "Test Portfolio"
    assert isinstance(data["id"], int)

    row = db.execute(
        "SELECT code, name FROM portfolios WHERE id = %s",
        (data["id"],),
    ).fetchone()

    assert row == ("test-portfolio", "Test Portfolio")


def test_duplicate_portfolio_code(client, db):
    payload = {
        "code": "duplicate",
        "name": "First Portfolio",
    }

    assert client.post(
        "/portfolios", json=payload
    ).status_code == 201

    response = client.post(
        "/portfolios",
        json={**payload, "name": "Second Portfolio"},
    )

    assert response.status_code == 409

    count = db.execute(
        "SELECT COUNT(*) FROM portfolios WHERE code = %s",
        ("duplicate",),
    ).fetchone()[0]

    assert count == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"code": "", "name": "Test"},
        {"code": "test", "name": " "},
        {"code": 123, "name": "Test"},
        {"name": "Missing Code"},
    ],
)
def test_invalid_portfolio(client, payload):
    response = client.post("/portfolios", json=payload)
    assert response.status_code == 400


def test_requires_json(client):
    response = client.post(
        "/portfolios",
        data="not JSON",
        content_type="text/plain",
    )
    assert response.status_code == 415
