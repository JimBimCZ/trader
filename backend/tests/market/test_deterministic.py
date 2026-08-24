"""The market model that is a pure function of time.

These tests hold the two properties the serverless deployment depends on —
that the price is reproducible and that it is still the process PLAN.md
describes — rather than pinning particular numbers, which would only restate
the hash.
"""

from __future__ import annotations

import math
import statistics

import pytest

from app.market import deterministic as det
from app.market.seed_prices import SEED_PRICES, TICKER_PARAMS

#: An arbitrary session, far from any boundary.
DAY = 20_324
OPEN = DAY * det.SESSION_SECONDS


def price(ticker: str, offset: float, seed: int = 0) -> float:
    return det.price_at(ticker, OPEN + offset, seed)


def log_return(ticker: str, day: int, seed: int = 0) -> float:
    """The session's total log return — dominated by the diffusion term."""
    close = det.price_at(ticker, day * det.SESSION_SECONDS + det.SESSION_SECONDS - 1, seed)
    return math.log(close / det.seed_price(ticker))


def correlation(xs: list[float], ys: list[float]) -> float:
    mx, my = statistics.mean(xs), statistics.mean(ys)
    covariance = sum((a - mx) * (b - my) for a, b in zip(xs, ys, strict=True))
    spread = math.sqrt(sum((a - mx) ** 2 for a in xs) * sum((b - my) ** 2 for b in ys))
    return covariance / spread


class TestDeterminism:
    """The whole point: no shared state, so every caller must agree."""

    def test_the_same_moment_gives_the_same_price(self):
        assert price("AAPL", 12_345.5) == price("AAPL", 12_345.5)

    def test_a_different_seed_gives_a_different_path(self):
        assert price("AAPL", 12_345.5, seed=1) != price("AAPL", 12_345.5, seed=2)

    def test_the_hash_is_not_salted_per_process(self):
        """Python's hash() is; using it would desynchronise two instances."""
        assert det._digest(("AAPL", 1)) == det._digest(("AAPL", 1))
        assert det._digest(("AAPL", 1)) != det._digest(("AAPL", 2))

    def test_an_unknown_ticker_gets_a_stable_opening_price(self):
        assert det.seed_price("SHOP") == det.seed_price("SHOP")
        assert 50.0 <= det.seed_price("SHOP") <= 300.0

    def test_unknown_tickers_do_not_collide(self):
        assert det.seed_price("SHOP") != det.seed_price("SQ")


class TestSession:
    def test_the_session_opens_at_the_seed_price(self):
        """session_open is this number, so daily change % depends on it exactly."""
        for ticker, seed in SEED_PRICES.items():
            assert price(ticker, 0.0) == seed

    def test_the_session_restarts_each_utc_day(self):
        assert det.price_at("AAPL", (DAY + 1) * det.SESSION_SECONDS) == SEED_PRICES["AAPL"]

    def test_session_bounds_split_a_timestamp(self):
        day, elapsed = det.session_bounds(OPEN + 90.0)
        assert (day, elapsed) == (DAY, 90.0)


class TestBrownianMotion:
    def test_the_walk_starts_at_zero(self):
        assert det._brownian(("k",), 0.0) == 0.0

    def test_variance_grows_with_time(self):
        """Var(W(t)) = t, which is what ties sigma to a real volatility."""
        for fraction in (0.25, 1.0):
            t = det.SESSION_TAU * fraction
            spread = statistics.pstdev([det._brownian((seed, "k"), t) for seed in range(600)])
            assert spread == pytest.approx(math.sqrt(t), rel=0.1)

    def test_the_path_is_continuous(self):
        """Neighbouring times must not land on unrelated draws."""
        t = det.SESSION_TAU * 0.5
        step = det.SESSION_TAU / 1e6
        assert det._brownian(("k",), t + step) == pytest.approx(det._brownian(("k",), t), abs=1e-3)


class TestVolatility:
    def test_realised_volatility_matches_the_configured_sigma(self):
        """A session is SESSION_TAU trading years, so sigma scales by its root."""
        days = range(DAY - 400, DAY)
        for ticker in ("AAPL", "TSLA"):
            realised = statistics.stdev([log_return(ticker, day) for day in days])
            expected = TICKER_PARAMS[ticker]["sigma"] * math.sqrt(det.SESSION_TAU)
            # Loose: the transient shocks add variance on top of the diffusion.
            assert expected <= realised <= expected * 1.6

    def test_a_typical_tick_moves_by_cents(self):
        """Sub-cent drift per 500ms tick is what the flash animation is sized for.

        The median rather than the maximum: a shock landing between two ticks
        is supposed to jump, and that is the drama the model is asked for.
        """
        ticks = [price("AAPL", 40_000 + i * 0.5) for i in range(400)]
        moves = [abs(b - a) for a, b in zip(ticks[:-1], ticks[1:], strict=True)]
        assert statistics.median(moves) < 0.10

    def test_the_volatility_multiplier_widens_the_range(self):
        calm = [det.price_at("AAPL", OPEN + s, 0, 1.0) for s in range(0, 86_400, 600)]
        wild = [det.price_at("AAPL", OPEN + s, 0, 4.0) for s in range(0, 86_400, 600)]
        assert max(wild) - min(wild) > max(calm) - min(calm)


class TestCorrelation:
    """The factor model has to reproduce seed_prices.py's correlation matrix.

    Measured on the diffusion component: the shocks are drawn per ticker and
    are deliberately uncorrelated, so they dilute — but do not shape — what the
    finished price series shows.
    """

    DAYS = range(19_000, 19_800)

    def displacements(self, ticker: str) -> list[float]:
        return [det._displacement(ticker, det.SESSION_TAU, day, 0) for day in self.DAYS]

    @pytest.mark.parametrize(
        ("first", "second", "expected"),
        [
            ("AAPL", "MSFT", 0.6),
            ("GOOGL", "NVDA", 0.6),
            ("JPM", "V", 0.5),
            ("AAPL", "JPM", 0.3),
            ("AAPL", "TSLA", 0.3),
            ("TSLA", "JPM", 0.3),
        ],
    )
    def test_pairwise_correlation(self, first: str, second: str, expected: float):
        measured = correlation(self.displacements(first), self.displacements(second))
        assert measured == pytest.approx(expected, abs=0.1)

    def test_each_ticker_keeps_unit_variance(self):
        """The three factor weights sum to one, so sigma is not rescaled."""
        for ticker in ("AAPL", "JPM", "TSLA"):
            spread = statistics.pstdev(self.displacements(ticker))
            assert spread == pytest.approx(math.sqrt(det.SESSION_TAU), rel=0.12)


class TestShocks:
    def test_a_shock_decays_instead_of_persisting(self):
        """Permanent shocks would compound into a second, louder random walk."""
        far_past = det._log_shock("AAPL", 80_000.0, DAY, 0)
        assert abs(far_past) < 0.06

    def test_shocks_are_reproducible(self):
        assert det._log_shock("AAPL", 12_000.0, DAY, 0) == det._log_shock("AAPL", 12_000.0, DAY, 0)

    def test_some_shock_lands_over_a_session(self):
        magnitudes = [abs(det._log_shock("AAPL", s, DAY, 0)) for s in range(0, 86_400, 60)]
        assert max(magnitudes) > 0.01
