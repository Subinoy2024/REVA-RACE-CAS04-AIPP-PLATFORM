"""Iteration-26.5 · Site visit counter API — unit test."""

from __future__ import annotations

import pytest

pytest.importorskip("httpx")


def test_site_router_registered_in_server():
    """`/api/site/visit` and `/api/site/visits` routes are exposed."""
    from backend.server import app
    routes = {getattr(r, "path", None) for r in app.routes}
    assert "/api/site/visit" in routes
    assert "/api/site/visits" in routes


def test_visit_response_shape_matches_schema():
    """Pydantic model returned by the visit endpoint."""
    from backend.api.site import VisitCount
    obj = VisitCount(count=42)
    assert obj.count == 42
    dumped = obj.model_dump()
    assert dumped == {"count": 42}


def test_site_visit_orm_model_has_expected_columns():
    from backend.database.models import SiteVisit
    cols = {c.name for c in SiteVisit.__table__.columns}
    assert {"id", "visited_at", "surface"}.issubset(cols)
