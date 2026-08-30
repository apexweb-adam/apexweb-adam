"""Sanity checks for weekend ops shell script operator output."""

from pathlib import Path


def test_verify_weekend_ops_includes_gate_and_revision_hints():
  script = Path(__file__).resolve().parents[2] / "scripts" / "verify-weekend-ops.sh"
  text = script.read_text(encoding="utf-8")
  assert "Code target:" in text
  assert "/api/profitability" in text
  assert "Profitability gate:" in text
  assert "fomo bearer" in text
  assert "github_verified" in text
  assert "deploy will advance prod expected" in text
