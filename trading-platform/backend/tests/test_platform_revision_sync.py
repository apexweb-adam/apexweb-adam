"""PLATFORM_REVISION in Render blueprints must match code expectation."""

import re
from pathlib import Path

from app.engines.deploy_status import EXPECTED_PLATFORM_REVISION

REPO_ROOT = Path(__file__).resolve().parents[3]
RENDER_YAMLS = (
  REPO_ROOT / "render.yaml",
  REPO_ROOT / "trading-platform" / "render.yaml",
)


def _read_platform_revision(path: Path) -> str:
  text = path.read_text(encoding="utf-8")
  match = re.search(
    r"- key: PLATFORM_REVISION\s+value:\s*\"([^\"]+)\"",
    text,
  )
  assert match, f"PLATFORM_REVISION not found in {path}"
  return match.group(1)


def test_render_yaml_platform_revision_matches_expected():
  for path in RENDER_YAMLS:
    assert path.is_file(), f"missing {path}"
    assert _read_platform_revision(path) == EXPECTED_PLATFORM_REVISION
