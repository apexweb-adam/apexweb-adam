"""Load Tampermonkey bridge script bundled in the backend image."""

from app.intel_userscript import (
  axiom_userscript_available,
  fomo_userscript_available,
  load_axiom_userscript_bytes,
  load_fomo_userscript_bytes,
  load_phantom_userscript_bytes,
  phantom_userscript_available,
)

__all__ = [
  "axiom_userscript_available",
  "fomo_userscript_available",
  "load_axiom_userscript_bytes",
  "load_fomo_userscript_bytes",
  "load_phantom_userscript_bytes",
  "phantom_userscript_available",
]
