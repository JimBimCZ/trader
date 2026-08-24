"""Vercel entrypoint: the FastAPI application as a single serverless function.

Vercel bundles the project directory around this file and looks for an ASGI
`app`. The backend is not installed as a package here — the container build owns
that — so its directory joins the import path first.

Only `/api/*` reaches this function. The exported frontend is served straight
from Vercel's CDN, so no static asset is ever rendered through Python; see
`vercel.json` for the rewrite that splits them.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402

__all__ = ["app"]
