from app.fomo_userscript import load_phantom_userscript_bytes, phantom_userscript_available


def test_phantom_userscript_loader():
  assert phantom_userscript_available()
  body = load_phantom_userscript_bytes()
  assert b"phantom" in body.lower()
  assert b"webhooks/phantom" in body
