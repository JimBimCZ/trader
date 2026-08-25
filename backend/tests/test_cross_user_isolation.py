"""User A must not read or mutate user B's rows.

The highest-value tests in this suite. Every other test checks that a feature
works; these check that it does not work on someone else's data. A regression
here is not a bug report, it is a privacy incident -- so they drive two real
HTTP sessions rather than two hand-built repositories, because the scoping has
to hold through the whole dependency chain.
"""

from __future__ import annotations

from app.identity import COOKIE_NAME


class TestTheClientsAreActuallyTwoUsers:
    """The guard the rest of this file depends on.

    Every other test here reads "A cannot see B's rows", and each of them is
    also satisfied by "neither client has any rows at all". A session that
    fails to round-trip -- a Secure cookie on a plain-http request was the
    real instance of this -- mints a fresh guest per request and makes four of
    them pass while proving nothing. This one fails in that mode instead.
    """

    def test_the_two_clients_hold_different_stable_identities(self, api_client, second_client):
        api_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 5, "side": "buy"},
        )
        second_client.post(
            "/api/portfolio/trade",
            json={"ticker": "NVDA", "quantity": 2, "side": "buy"},
        )

        mine = api_client.cookies.get(COOKIE_NAME)
        theirs = second_client.cookies.get(COOKIE_NAME)
        assert mine, "the first client holds no session cookie"
        assert theirs, "the second client holds no session cookie"
        assert mine != theirs, "both clients are the same user, so nothing here is isolated"

        # Stable, not just distinct: a later request must resolve to the same
        # user, which is only observable through rows that request did not
        # write.
        assert [p["ticker"] for p in api_client.get("/api/portfolio").json()["positions"]] == [
            "AAPL"
        ]
        assert [p["ticker"] for p in second_client.get("/api/portfolio").json()["positions"]] == [
            "NVDA"
        ]


class TestPortfolioIsolation:
    def test_a_trade_by_one_user_is_invisible_to_another(self, api_client, second_client):
        api_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 5, "side": "buy"},
        )

        other = second_client.get("/api/portfolio").json()

        assert other["positions"] == []
        assert other["cash_balance"] == 10000.0

    def test_spending_cash_does_not_spend_anyone_else_s(self, api_client, second_client):
        api_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 1, "side": "buy"},
        )

        assert api_client.get("/api/portfolio").json()["cash_balance"] < 10000.0
        assert second_client.get("/api/portfolio").json()["cash_balance"] == 10000.0


class TestWatchlistIsolation:
    """Both of these establish the second session *before* the mutation.

    `second_client`'s guest is minted by its first request, and minting
    re-seeds the ten defaults. Reading it only afterwards made
    `test_a_removed_ticker_stays_for_another_user` vacuous: AAPL came back
    from the seed no matter what the DELETE had done, and the whole suite
    passed with `WatchlistRepository.remove` deleting that ticker for every
    user in the database -- the one cross-user destructive write, with no
    coverage anywhere.
    """

    def test_an_added_ticker_does_not_appear_for_another_user(self, api_client, second_client):
        before = second_client.get("/api/watchlist").json()["tickers"]
        assert "PYPL" not in before

        api_client.post("/api/watchlist", json={"ticker": "PYPL"})

        assert "PYPL" not in second_client.get("/api/watchlist").json()["tickers"]

    def test_a_removed_ticker_stays_for_another_user(self, api_client, second_client):
        assert "AAPL" in second_client.get("/api/watchlist").json()["tickers"]

        api_client.delete("/api/watchlist/AAPL")

        assert "AAPL" in second_client.get("/api/watchlist").json()["tickers"], (
            "the DELETE reached another user's row"
        )


class TestChatIsolation:
    def test_chat_history_is_not_shared(self, api_client, second_client):
        api_client.post("/api/chat", json={"message": "isolation probe"})

        theirs = second_client.get("/api/chat").json()

        assert all("isolation probe" not in m["content"] for m in theirs["messages"])


class TestResetIsolation:
    def test_a_reset_does_not_wipe_another_user(self, api_client, second_client):
        second_client.post(
            "/api/portfolio/trade",
            json={"ticker": "AAPL", "quantity": 3, "side": "buy"},
        )

        api_client.post("/api/reset")

        survivor = second_client.get("/api/portfolio").json()
        assert len(survivor["positions"]) == 1
        assert survivor["positions"][0]["ticker"] == "AAPL"

    def test_a_reset_does_not_blank_the_shared_price_history(self, api_client):
        """The ring buffer holds market data per ticker, shared by everyone.

        Clearing it on reset blanked the main chart for every other user, who
        had asked for nothing. Asserted on a ticker the market source does not
        track, because the collector refills a real one within a poll interval
        -- which would make this pass whether the bug was there or not.
        """
        store = api_client.app.state.history_store
        store.track("ZZZZ")
        store.append("ZZZZ", 1.0, 100.0)

        api_client.post("/api/reset")

        assert store.get("ZZZZ") == [(1.0, 100.0)]
