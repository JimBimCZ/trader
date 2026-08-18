"""Tests for the error envelope and exception handlers."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import (
    AppError,
    InsufficientCashError,
    InvalidTickerError,
    PriceUnavailableError,
    register_exception_handlers,
)


class Body(BaseModel):
    quantity: float


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/invalid-ticker")
    async def invalid_ticker():
        raise InvalidTickerError("Invalid ticker: 'ZZZZZZ'")

    @app.get("/no-price")
    async def no_price():
        raise PriceUnavailableError("No price yet for AAPL.")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("internal detail that must not leak")

    @app.post("/validated")
    async def validated(body: Body):
        return {"ok": body.quantity}

    return TestClient(app, raise_server_exceptions=False)


class TestErrorEnvelope:
    def test_app_error_uses_its_own_code_and_status(self, client: TestClient):
        """An AppError subclass maps to its declared code and status."""
        response = client.get("/invalid-ticker")
        assert response.status_code == 400
        assert response.json() == {
            "error": {"code": "INVALID_TICKER", "message": "Invalid ticker: 'ZZZZZZ'"}
        }

    def test_price_unavailable_is_a_conflict(self, client: TestClient):
        """A missing price is 409, not 400 — the request was well-formed."""
        response = client.get("/no-price")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "PRICE_UNAVAILABLE"

    def test_validation_error_is_422_in_the_same_shape(self, client: TestClient):
        """Schema failures use the same envelope, not FastAPI's default detail."""
        response = client.post("/validated", json={"quantity": "abc"})
        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        assert "quantity" in body["error"]["message"]

    def test_unexpected_error_does_not_leak_internals(self, client: TestClient):
        """An uncaught exception returns a generic 500 with no internal detail."""
        response = client.get("/boom")
        assert response.status_code == 500
        body = response.json()
        assert body["error"]["code"] == "INTERNAL_ERROR"
        assert "internal detail" not in body["error"]["message"]

    def test_every_response_has_only_the_error_key(self, client: TestClient):
        """The envelope has no sibling keys."""
        assert list(client.get("/no-price").json()) == ["error"]


class TestErrorClasses:
    def test_message_is_preserved(self):
        """The message passed in is available on the exception."""
        assert InsufficientCashError("need more").message == "need more"

    def test_subclasses_carry_distinct_codes(self):
        """Each error type has its own machine-readable code."""
        codes = {InvalidTickerError.code, InsufficientCashError.code, PriceUnavailableError.code}
        assert len(codes) == 3

    def test_base_class_defaults(self):
        """The base class is a 400 with a generic code."""
        assert AppError.status_code == 400
        assert AppError.code == "ERROR"
