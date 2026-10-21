import pytest

from cashflow_api.app import create_app

VALID_LOAN = {
    "reference": "loan-001",
    "principal_cents": 120_000,
    "annual_rate_bps": 525,
    "term_months": 12,
    "first_payment_date": "2026-11-01",
}


@pytest.fixture
def client(db, monkeypatch):
    # Route repository calls through the test transaction
    monkeypatch.setattr(
        "cashflow_api.app.get_db", lambda: db
    )

    app = create_app({"TESTING": True})
    return app.test_client()


@pytest.fixture
def portfolio_id(client):
    response = client.post(
        "/portfolios",
        json={
            "code": "negative-tests",
            "name": "Negative Path Tests",
        },
    )
    assert response.status_code == 201
    return response.get_json()["id"]


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


def test_create_loan_api(client, db):
    portfolio = client.post(
        "/portfolios",
        json={"code": "loans-test", "name": "Loans Test"},
    ).get_json()

    response = client.post(
        f"/portfolios/{portfolio['id']}/loans",
        json={
            "reference": "loan-001",
            "principal_cents": 120_000,
            "annual_rate_bps": 525,
            "term_months": 12,
            "first_payment_date": "2026-11-01",
        },
    )

    assert response.status_code == 201
    loan_id = response.get_json()["id"]

    rows = db.execute(
        """
        SELECT payment_number, principal_cents,
               interest_cents, remaining_balance_cents
        FROM scheduled_cashflows
        WHERE loan_id = %s
        ORDER BY payment_number
        """,
        (loan_id,),
    ).fetchall()

    assert len(rows) == 12
    assert rows[0] == (1, 9762, 525, 110238)
    assert sum(row[1] for row in rows) == 120_000
    assert rows[-1][3] == 0


def test_create_loan_missing_portfolio(client):
    response = client.post(
        "/portfolios/999999999/loans",
        json={
            "reference": "loan-001",
            "principal_cents": 120_000,
            "annual_rate_bps": 525,
            "term_months": 12,
            "first_payment_date": "2026-11-01",
        },
    )

    assert response.status_code == 404


def test_get_loan_schedule(client):
    portfolio = client.post(
        "/portfolios",
        json={"code": "schedule-test", "name": "Schedule Test"},
    ).get_json()

    loan = client.post(
        f"/portfolios/{portfolio['id']}/loans",
        json={
            "reference": "loan-001",
            "principal_cents": 120_000,
            "annual_rate_bps": 525,
            "term_months": 12,
            "first_payment_date": "2026-11-01",
        },
    ).get_json()

    response = client.get(
        f"/loans/{loan['id']}/schedule"
    )

    assert response.status_code == 200

    cashflows = response.get_json()["cashflows"]

    assert len(cashflows) == 12
    assert cashflows[0]["principal_cents"] == 9762
    assert cashflows[0]["interest_cents"] == 525
    assert cashflows[-1]["remaining_balance_cents"] == 0
    assert sum(
        row["principal_cents"] for row in cashflows
    ) == 120_000


def test_get_missing_loan_schedule(client):
    response = client.get(
        "/loans/999999999/schedule"
    )
    assert response.status_code == 404


def test_portfolio_cashflow_aggregation(client):
    portfolio_response = client.post(
        "/portfolios",
        json={"code": "aggregate", "name": "Aggregation Test"},
    )
    assert portfolio_response.status_code == 201
    portfolio_id = portfolio_response.get_json()["id"]

    loans = [
        {
            "reference": "loan-a",
            "principal_cents": 120_000,
            "annual_rate_bps": 525,
            "term_months": 12,
            "first_payment_date": "2026-11-01",
        },
        {
            "reference": "loan-b",
            "principal_cents": 60_000,
            "annual_rate_bps": 0,
            "term_months": 3,
            "first_payment_date": "2026-11-15",
        },
    ]

    for loan in loans:
        response = client.post(
            f"/portfolios/{portfolio_id}/loans",
            json=loan,
        )
        assert response.status_code == 201

    response = client.get(
        f"/portfolios/{portfolio_id}/cashflows"
    )
    assert response.status_code == 200

    cashflows = response.get_json()["cashflows"]

    assert len(cashflows) == 12

    november = cashflows[0]
    assert november == {
        "month": "2026-11-01",
        "principal_cents": 29_762,
        "interest_cents": 525,
        "total_cents": 30_287,
    }

    assert sum(
        row["principal_cents"] for row in cashflows
    ) == 180_000

    assert sum(
        row["interest_cents"] for row in cashflows
    ) == 3_439


def test_empty_portfolio_cashflows(client):
    portfolio = client.post(
        "/portfolios",
        json={"code": "empty", "name": "Empty Portfolio"},
    ).get_json()

    response = client.get(
        f"/portfolios/{portfolio['id']}/cashflows"
    )

    assert response.status_code == 200
    assert response.get_json()["cashflows"] == []


def test_missing_portfolio_cashflows(client):
    response = client.get(
        "/portfolios/999999999/cashflows"
    )
    assert response.status_code == 404


def test_duplicate_loan_reference(client, db, portfolio_id):
    url = f"/portfolios/{portfolio_id}/loans"

    first = client.post(url, json=VALID_LOAN)
    assert first.status_code == 201
    loan_id = first.get_json()["id"]

    duplicate = client.post(url, json=VALID_LOAN)
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"] == (
        "Loan reference already exists in portfolio"
    )

    # The rejected request must not create another loan.
    count = db.execute(
        """
        SELECT COUNT(*)
        FROM loans
        WHERE portfolio_id = %s AND reference = %s
        """,
        (portfolio_id, "loan-001"),
    ).fetchone()[0]
    assert count == 1

    # The existing loan's schedule must remain intact.
    count = db.execute(
        """
        SELECT COUNT(*)
        FROM scheduled_cashflows
        WHERE loan_id = %s
        """,
        (loan_id,),
    ).fetchone()[0]
    assert count == 12

    # The database transaction must remain usable.
    recovered = client.post(
        url,
        json={**VALID_LOAN, "reference": "loan-002"},
    )
    assert recovered.status_code == 201


def test_loan_reference_unique_per_portfolio(client, portfolio_id):
    second_portfolio = client.post(
        "/portfolios",
        json={
            "code": "second-portfolio",
            "name": "Second Portfolio",
        },
    )
    assert second_portfolio.status_code == 201
    second_id = second_portfolio.get_json()["id"]

    for pid in (portfolio_id, second_id):
        response = client.post(
            f"/portfolios/{pid}/loans",
            json=VALID_LOAN,
        )
        assert response.status_code == 201


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param(
            {"reference": ""}, id="blank-reference"
        ),
        pytest.param(
            {"reference": 123}, id="numeric-reference"
        ),
        pytest.param(
            {"principal_cents": 0}, id="zero-principal"
        ),
        pytest.param(
            {"principal_cents": -1}, id="negative-principal"
        ),
        pytest.param(
            {"principal_cents": True}, id="boolean-principal"
        ),
        pytest.param(
            {"principal_cents": 1.5}, id="fractional-cents"
        ),
        pytest.param(
            {"principal_cents": 2**63}, id="principal-overflow"
        ),
        pytest.param(
            {"annual_rate_bps": -1}, id="negative-rate"
        ),
        pytest.param(
            {"annual_rate_bps": True}, id="boolean-rate"
        ),
        pytest.param(
            {"annual_rate_bps": 100_001}, id="rate-too-large"
        ),
        pytest.param(
            {"term_months": 0}, id="zero-term"
        ),
        pytest.param(
            {"term_months": True}, id="boolean-term"
        ),
        pytest.param(
            {"term_months": 601}, id="term-too-large"
        ),
        pytest.param(
            {"first_payment_date": "2026-02-30"},
            id="invalid-calendar-date",
        ),
        pytest.param(
            {"first_payment_date": "2026-11-1"},
            id="noncanonical-date",
        ),
        pytest.param(
            {"first_payment_date": None},
            id="missing-date",
        ),
    ],
)
def test_invalid_loan_inputs(client, db, portfolio_id, changes):
    response = client.post(
        f"/portfolios/{portfolio_id}/loans",
        json={**VALID_LOAN, **changes},
    )

    assert response.status_code == 400
    assert "error" in response.get_json()

    count = db.execute(
        """
        SELECT COUNT(*)
        FROM loans
        WHERE portfolio_id = %s
        """,
        (portfolio_id,),
    ).fetchone()[0]

    assert count == 0


def test_invalid_loan_request_formats(client, portfolio_id):
    url = f"/portfolios/{portfolio_id}/loans"

    malformed = client.post(
        url,
        data='{"reference":',
        content_type="application/json",
    )
    assert malformed.status_code == 400

    wrong_shape = client.post(url, json=[1, 2, 3])
    assert wrong_shape.status_code == 400

    wrong_media_type = client.post(
        url,
        data="not JSON",
        content_type="text/plain",
    )
    assert wrong_media_type.status_code == 415

