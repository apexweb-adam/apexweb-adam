"""Verification history REST endpoint."""

import importlib


def test_routes_imports_verification_serializer():
  routes = importlib.import_module("app.api.routes")
  assert hasattr(routes, "serialize_verification_snapshot")
