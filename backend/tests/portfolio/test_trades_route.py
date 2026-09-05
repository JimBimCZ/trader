"""GET /api/portfolio/trades."""

import pytest


@pytest.mark.asyncio
async def test_trades_route_returns_newest_first_with_realized_pnl(api_client):
    api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 10})
    api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 4})

    body = api_client.get("/api/portfolio/trades").json()
    trades = body["trades"]

    assert [t["side"] for t in trades] == ["sell", "buy"]
    assert trades[1]["realized_pnl"] is None, (
        "a buy realizes nothing, and 0 would read as break-even"
    )
    assert trades[0]["realized_pnl"] is not None
    assert trades[0]["value"] == round(trades[0]["quantity"] * trades[0]["price"], 2)


@pytest.mark.asyncio
async def test_trades_route_limit_does_not_change_the_realized_figures(api_client):
    """The replay runs over the whole log, so paging cannot move a number."""
    for _ in range(3):
        api_client.post(
            "/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 2}
        )
    api_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 5})

    full = api_client.get("/api/portfolio/trades").json()["trades"]
    paged = api_client.get("/api/portfolio/trades?limit=1").json()["trades"]

    assert len(paged) == 1
    assert paged[0]["realized_pnl"] == full[0]["realized_pnl"]


@pytest.mark.asyncio
async def test_trades_route_rejects_an_out_of_range_limit(api_client):
    assert api_client.get("/api/portfolio/trades?limit=0").status_code == 422
    assert api_client.get("/api/portfolio/trades?limit=501").status_code == 422
