from app.fomo_userscript import axiom_userscript_available, load_axiom_userscript_bytes


def test_axiom_userscript_loader():
  assert axiom_userscript_available()
  body = load_axiom_userscript_bytes()
  assert b"axiom.trade" in body
  assert b"webhooks/axiom" in body
