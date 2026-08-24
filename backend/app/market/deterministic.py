"""A market simulator that is a pure function of time.

The shipped GBM simulator (`simulator.py`) carries its price state in memory and
advances it from a background task. That is the right design for the container
deployment and the wrong one for a serverless deployment, where nothing runs
between requests and two concurrent instances would walk apart immediately.

This module produces the same process — geometric Brownian motion with the same
per-ticker drift and volatility, the same tick-scaled dt, and the same
correlation structure — as a closed-form function of the clock. Every instance,
every SSE connection and every request therefore agrees on the price without
sharing any state.

Two ideas make that possible:

**Lévy construction.** A Brownian path is normally built by summing increments,
which costs one draw per tick — 172,800 of them for a day at 500ms. Instead the
path is defined top-down: W(T) is drawn first, then the midpoint W(T/2)
conditioned on the endpoints, then the midpoints of each half, and so on. Any
W(t) is reachable in `_BRIDGE_DEPTH` steps, and each node's draw comes from a
hash of its coordinates rather than from a stateful generator. The result is
distributed exactly like the increment-summed path.

**A factor model instead of a Cholesky factorisation.** The shipped simulator
correlates tickers by decomposing the correlation matrix, which needs the whole
matrix and therefore numpy. The same matrix is reproduced here by writing each
ticker's motion as a market component, a sector component and an idiosyncratic
one — see `_displacement`.
"""

from __future__ import annotations

import hashlib
import math
from functools import lru_cache

from .seed_prices import (
    CORRELATION_GROUPS,
    CROSS_GROUP_CORR,
    DEFAULT_PARAMS,
    INTRA_FINANCE_CORR,
    INTRA_TECH_CORR,
    SEED_PRICES,
    TICKER_PARAMS,
)
from .tickers import canonicalize_ticker

#: Matches GBMSimulator: 252 trading days * 6.5 hours. Time runs ~5.3x faster
#: than the calendar, which is what makes a 500ms tick move a visible amount.
TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600

#: One session is one UTC day. The walk restarts from the seed price at
#: midnight, which is what makes the seed price an exact session baseline for
#: `daily_change_percent` — and what stops months of drift from carrying AAPL
#: somewhere unrecognisable.
SESSION_SECONDS = 86_400

#: The session's length measured in trading years — the domain of the walk.
SESSION_TAU = SESSION_SECONDS / TRADING_SECONDS_PER_YEAR

#: Subdivisions of the session. 2^22 nodes resolves to ~0.02s, comfortably
#: finer than the 500ms tick, so consecutive ticks never share a leaf cell.
_BRIDGE_DEPTH = 22

#: Share of each ticker's variance carried by the whole-market factor. Equal to
#: the cross-sector correlation by construction: two tickers with nothing else
#: in common correlate exactly this much.
_MARKET_SHARE = CROSS_GROUP_CORR

#: Shocks are drawn per minute rather than per tick, at roughly one per ticker
#: per ten minutes — the rate the shipped simulator's 0.001-per-tick produces
#: over the few minutes anyone actually watches it.
_SHOCK_BUCKET_SECONDS = 60
_SHOCK_PROB = 0.1
_SHOCK_MIN, _SHOCK_MAX = 0.02, 0.05

#: A shock decays away instead of persisting. The shipped simulator multiplies
#: the price permanently, which is harmless over a few minutes but compounds
#: into a second random walk over a full session — 144 shocks a day, whose
#: variance would bury the GBM and, being drawn per ticker, would flatten every
#: correlation to zero. A dislocation that reverts over minutes is both better
#: behaved and closer to what a real news spike looks like.
_SHOCK_DECAY_SECONDS = 300.0

#: exp(-6) — beyond this a shock contributes less than a tenth of a cent.
_SHOCK_LOOKBACK_BUCKETS = 30

_TWO_32 = float(1 << 32)


def _digest(parts: tuple) -> int:
    """A 64-bit integer keyed by the node's coordinates.

    blake2b rather than Python's `hash()`: the latter is salted per process, so
    two instances would disagree on every price.
    """
    h = hashlib.blake2b(digest_size=8)
    for part in parts:
        h.update(str(part).encode())
        h.update(b"\x1f")
    return int.from_bytes(h.digest(), "big")


@lru_cache(maxsize=1 << 17)
def _standard_normal(parts: tuple) -> float:
    """One standard normal deviate, determined entirely by `parts`.

    Cached because descending the bridge to two nearby times shares every node
    but the last few — history rendering asks for 600 consecutive ticks, and
    without this each would pay for the whole descent.
    """
    n = _digest(parts)
    # Box-Muller over two halves of the digest. The +0.5 keeps u1 off zero,
    # where the logarithm would diverge.
    u1 = ((n >> 32) + 0.5) / _TWO_32
    u2 = ((n & 0xFFFF_FFFF) + 0.5) / _TWO_32
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def _brownian(key: tuple, t: float, total: float = SESSION_TAU) -> float:
    """Standard Brownian motion on [0, total] evaluated at t.

    W(0) = 0 and Var(W(s)) = s. Built by binary subdivision: at each level the
    midpoint of the bracketing interval is drawn from its conditional
    distribution — mean the average of the endpoints, variance a quarter of the
    span — and the half containing t becomes the new bracket.
    """
    if t <= 0.0:
        return 0.0
    t = min(t, total)

    lo, hi = 0.0, total
    w_lo = 0.0
    w_hi = _standard_normal((*key, 0, 0)) * math.sqrt(total)

    # Identifies the bracket among all cells at the current level, so every
    # midpoint in the tree gets its own draw.
    cell = 0
    for level in range(1, _BRIDGE_DEPTH + 1):
        mid = 0.5 * (lo + hi)
        w_mid = 0.5 * (w_lo + w_hi) + _standard_normal((*key, level, cell)) * math.sqrt(
            (hi - lo) * 0.25
        )
        if t < mid:
            hi, w_hi = mid, w_mid
            cell *= 2
        else:
            lo, w_lo = mid, w_mid
            cell = cell * 2 + 1

    span = hi - lo
    return w_lo if span <= 0.0 else w_lo + (w_hi - w_lo) * (t - lo) / span


def _sector(ticker: str) -> str | None:
    """The correlation group a ticker belongs to, or None if it moves alone.

    TSLA sits inside the tech set in `seed_prices` but is documented as
    correlating at the cross-sector level with everything, so it is given no
    sector factor at all — which produces exactly that.
    """
    if ticker == "TSLA":
        return None
    if ticker in CORRELATION_GROUPS["tech"]:
        return "tech"
    if ticker in CORRELATION_GROUPS["finance"]:
        return "finance"
    return None


def _rho(ticker: str) -> float:
    """Total correlation this ticker shares with others in its sector."""
    sector = _sector(ticker)
    if sector == "tech":
        return INTRA_TECH_CORR
    if sector == "finance":
        return INTRA_FINANCE_CORR
    return CROSS_GROUP_CORR


def _displacement(ticker: str, tau: float, day: int, seed: int) -> float:
    """The ticker's Brownian displacement at tau, with unit variance per unit time.

    Three independent motions are blended so the pairwise correlations come out
    at the documented values:

        W_i = sqrt(0.3)·M + sqrt(rho_i - 0.3)·S_sector + sqrt(1 - rho_i)·I_i

    Two tech names share M and S_tech, giving 0.3 + 0.3 = 0.6. Two finance names
    give 0.3 + 0.2 = 0.5. Anything across sectors — and anything involving TSLA,
    which has no sector term — shares only M, giving 0.3. The weights sum to 1
    in every case, so each ticker keeps exactly its own volatility.
    """
    rho = _rho(ticker)
    total = math.sqrt(_MARKET_SHARE) * _brownian((seed, day, "M"), tau)

    sector = _sector(ticker)
    if sector is not None and rho > _MARKET_SHARE:
        total += math.sqrt(rho - _MARKET_SHARE) * _brownian((seed, day, "S", sector), tau)

    total += math.sqrt(1.0 - rho) * _brownian((seed, day, "I", ticker), tau)
    return total


def _log_shock(ticker: str, elapsed: float, day: int, seed: int) -> float:
    """Log-price dislocation from recent shocks, summed over the lookback window.

    The shipped simulator's sudden 2-5% moves, made replayable and transient:
    each minute either fires or does not according to its own hash, and a fired
    shock decays exponentially from the minute it landed.
    """
    current = int(elapsed // _SHOCK_BUCKET_SECONDS)
    total = 0.0
    for bucket in range(max(0, current - _SHOCK_LOOKBACK_BUCKETS), current + 1):
        n = _digest((seed, day, "E", ticker, bucket))
        if ((n >> 40) + 0.5) / float(1 << 24) >= _SHOCK_PROB:
            continue
        magnitude = _SHOCK_MIN + ((n >> 16) & 0xFFFF) / 0x1_0000 * (_SHOCK_MAX - _SHOCK_MIN)
        age = elapsed - bucket * _SHOCK_BUCKET_SECONDS
        if age < 0.0:
            continue
        total += magnitude * (1 if n & 1 else -1) * math.exp(-age / _SHOCK_DECAY_SECONDS)
    return total


@lru_cache(maxsize=1024)
def seed_price(ticker: str) -> float:
    """The session's opening price: the documented seed, or a stable stand-in.

    An unknown ticker gets a price derived from its own name rather than from a
    random draw, so adding SHOP to the watchlist gives the same opening price on
    every instance and after every restart.
    """
    known = SEED_PRICES.get(ticker)
    if known is not None:
        return known
    return round(50.0 + (_digest(("seed", ticker)) % 25_000) / 100.0, 2)


def _params(ticker: str) -> tuple[float, float]:
    params = TICKER_PARAMS.get(ticker, DEFAULT_PARAMS)
    return params["mu"], params["sigma"]


def session_bounds(timestamp: float) -> tuple[int, float]:
    """The session index and seconds elapsed within it, for a Unix timestamp."""
    day = int(timestamp // SESSION_SECONDS)
    return day, timestamp - day * SESSION_SECONDS


def price_at(
    ticker: str,
    timestamp: float,
    seed: int = 0,
    vol_multiplier: float = 1.0,
) -> float:
    """The price of `ticker` at a Unix timestamp.

        S(t) = S0 · exp((mu - sigma^2/2)·tau + sigma·W(tau)) · shocks

    Identical in form to GBMSimulator's step, with tau the elapsed fraction of a
    trading year since the session opened rather than a single tick.
    """
    ticker = canonicalize_ticker(ticker)
    day, elapsed = session_bounds(timestamp)
    if elapsed <= 0.0:
        return seed_price(ticker)

    tau = elapsed / TRADING_SECONDS_PER_YEAR
    mu, sigma = _params(ticker)
    sigma *= vol_multiplier

    drift = (mu - 0.5 * sigma * sigma) * tau
    diffusion = sigma * _displacement(ticker, tau, day, seed)
    shock = _log_shock(ticker, elapsed, day, seed)

    return round(seed_price(ticker) * math.exp(drift + diffusion + shock), 2)
