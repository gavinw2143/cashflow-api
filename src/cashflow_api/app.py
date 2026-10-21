import os

import psycopg
from flask import Flask, current_app, g, jsonify, request
from psycopg.errors import UniqueViolation

from cashflow_api.repository import create_portfolio


def get_db() -> psycopg.Connection:
    if "db" not in g:
        dsn = current_app.config["DATABASE_URL"]
        if not dsn:
            raise RuntimeError("DATABASE_URL is not configured")

        g.db = psycopg.connect(dsn, autocommit=True)

    return g.db


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DATABASE_URL"] = os.getenv("DATABASE_URL")

    if test_config:
        app.config.update(test_config)

    @app.teardown_appcontext
    def close_db(_exception):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    @app.post("/portfolios")
    def post_portfolio():
        if not request.is_json:
            return jsonify(
                error="Content-Type must be application/json"
            ), 415

        payload = request.get_json(silent=True)

        if not isinstance(payload, dict):
            return jsonify(error="Expected a JSON object"), 400

        code = payload.get("code")
        name = payload.get("name")

        if not isinstance(code, str) or not isinstance(name, str):
            return jsonify(
                error="code and name must be strings"
            ), 400

        code, name = code.strip(), name.strip()

        if not code or not name:
            return jsonify(
                error="code and name cannot be empty"
            ), 400

        try:
            portfolio_id = create_portfolio(
                get_db(), code=code, name=name
            )
        except UniqueViolation:
            return jsonify(
                error="Portfolio code already exists"
            ), 409

        return jsonify(
            id=portfolio_id,
            code=code,
            name=name,
        ), 201

    return app
