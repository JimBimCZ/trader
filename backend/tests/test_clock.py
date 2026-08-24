"""Tests for the time seam, notably the format `iso_seconds_ago` must share
with `utcnow_iso` -- callers compare these as strings, so any drift in the
format breaks ordering silently rather than raising."""

from __future__ import annotations

import re

from app.clock import iso_seconds_ago, utcnow_iso

#: `utcnow_iso`'s exact shape: "YYYY-MM-DDTHH:MM:SSZ".
_ISO_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class TestIsoSecondsAgo:
    def test_matches_utcnow_isos_shape(self):
        assert _ISO_SHAPE.match(utcnow_iso())
        assert _ISO_SHAPE.match(iso_seconds_ago(0))

    def test_zero_seconds_ago_has_identical_shape_to_utcnow(self):
        """String comparison against `last_seen_at` only orders correctly if
        both producers emit byte-identical formats -- same suffix, same
        precision."""
        now = utcnow_iso()
        zero_ago = iso_seconds_ago(0)
        assert len(now) == len(zero_ago)
        assert now[-1] == zero_ago[-1] == "Z"
        assert now[10] == zero_ago[10] == "T"

    def test_is_in_the_past(self):
        assert iso_seconds_ago(3600) < utcnow_iso()

    def test_larger_offsets_sort_further_in_the_past(self):
        assert iso_seconds_ago(7200) < iso_seconds_ago(3600) < iso_seconds_ago(0)
