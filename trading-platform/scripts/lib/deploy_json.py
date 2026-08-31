#!/usr/bin/env python3
"""Shared JSON helpers for deploy preflight shell scripts."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def minutes_until_open(prep: dict[str, Any]) -> int | None:
  """Resolve CME minutes from prep-status (commodities or cme_reopen)."""
  comm = prep.get("commodities") or {}
  cme = (prep.get("next_session_events") or {}).get("cme_reopen") or {}
  for raw in (comm.get("minutes_until_open"), cme.get("minutes_until_open")):
    if raw is None:
      continue
    try:
      return int(raw)
    except (TypeError, ValueError):
      continue
  return None


def cme_prep_fields(prep: dict[str, Any]) -> dict[str, Any]:
  comm = prep.get("commodities") or {}
  cme = (prep.get("next_session_events") or {}).get("cme_reopen") or {}
  mins = minutes_until_open(prep)
  phase = comm.get("prep_phase") or cme.get("prep_phase")
  open_ready = comm.get("open_ready_symbols") or cme.get("open_ready_symbols") or []
  auto_entry = comm.get("auto_entry_queued")
  if auto_entry is not True:
    auto_entry = cme.get("auto_entry_queued")
  return {
    "minutes_until_open": mins,
    "prep_phase": phase,
    "open_ready_symbols": open_ready,
    "auto_entry_queued": auto_entry,
  }


def evaluate_cme_prep_preflight(prep: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
  fields = cme_prep_fields(prep)
  errors: list[str] = []
  if fields["minutes_until_open"] is None:
    errors.append("missing_minutes_until_open")
  if fields["auto_entry_queued"] is not True and fields["open_ready_symbols"]:
    errors.append("auto_entry_not_queued")
  return errors, fields


def intel_source_fields(sources_payload: Any) -> dict[str, Any]:
  sources = sources_payload.get("sources", sources_payload) if isinstance(sources_payload, dict) else sources_payload
  if not isinstance(sources, list):
    return {}
  by = {s.get("source"): s for s in sources if isinstance(s, dict)}
  x = by.get("x") or {}
  tv = by.get("tradingview") or {}
  political = by.get("political") or {}
  return {
    "x_collection_mode": x.get("collection_mode"),
    "tv_scoring_excludes_synthetic": tv.get("scoring_excludes_synthetic"),
    "tv_webhook_items_24h": tv.get("webhook_items_24h"),
    "tv_synthetic_items_24h": tv.get("synthetic_items_24h"),
    "political_status": political.get("status"),
  }


def evaluate_intel_readiness(
  sources_payload: Any,
  snapshot: dict[str, Any],
  *,
  prod_rev: str,
  code_rev: str,
) -> str:
  """Return ok | partial | missing for shell preflight messaging."""
  fields = intel_source_fields(sources_payload)
  sources_ok = bool(fields.get("x_collection_mode")) and fields.get("tv_scoring_excludes_synthetic") is True
  political_ok = fields.get("political_status") in ("active", "degraded")
  snapshot_ok = bool(snapshot.get("x_intel_collection_mode")) and bool(
    snapshot.get("tradingview_item_breakdown") or snapshot.get("tradingview_webhook_items_24h") is not None
  )
  if prod_rev == code_rev:
    if sources_ok and snapshot_ok and political_ok:
      return "ok"
    if sources_ok and political_ok:
      return "partial"
    return "partial" if sources_ok else "missing"
  if sources_ok and not snapshot_ok:
    return "partial"
  if sources_ok:
    return "partial"
  return "missing"


def evaluate_post_deploy(
  status: dict[str, Any],
  checklist: dict[str, Any],
  snapshot: dict[str, Any],
  *,
  expected: str,
) -> list[str]:
  errors: list[str] = []
  deploy = status.get("deploy") or {}
  if not deploy and snapshot:
    deploy = snapshot
  prod_rev = deploy.get("platform_revision") or snapshot.get("platform_revision") or "?"
  print(f"  platform_revision={prod_rev} expected={expected}")
  if prod_rev != expected:
    errors.append("revision_mismatch")

  summaries = status.get("session_open_checklists") or {}
  if not summaries.get("cme_reopen"):
    if status:
      errors.append("session_open_checklists_missing")
    else:
      print("  session_open_checklists=skipped (/api/status unavailable)")
  else:
    cme = summaries["cme_reopen"]
    print(
      f"  session_open_checklists.cme_reopen ready={cme.get('ready')} "
      f"phase={cme.get('phase')}"
    )
    print(
      f"    open_ready={cme.get('open_ready_symbols')} "
      f"near_floor={cme.get('near_floor_symbols')}"
    )
    gaps = cme.get("near_floor_gaps") or {}
    if gaps:
      print(f"    near_floor_gaps={gaps}")

  open_ready = checklist.get("open_ready") or {}
  if checklist and "sticky_symbols" not in open_ready:
    errors.append("sticky_symbols_field_missing")
  elif open_ready.get("sticky_symbols") is not None:
    sticky = open_ready.get("sticky_symbols") or []
    print(f"  checklist sticky_symbols={sticky} release_margin={open_ready.get('release_margin')}")

  near = checklist.get("near_floor") or {}
  for row in near.get("details") or []:
    sym = row.get("symbol")
    gap = row.get("gap_to_floor")
    comp = row.get("composite")
    if sym and gap is not None:
      print(f"    near_floor {sym}: composite={comp} gap_to_floor={gap}")

  deploy_info = status.get("deploy") or {}
  revision_current = deploy_info.get("platform_revision_current")
  if snapshot.get("platform_revision_current") is not None:
    revision_current = snapshot.get("platform_revision_current")
  deploy_window = deploy_info.get("cme_deploy_window") or snapshot.get("cme_deploy_window")
  if deploy_window:
    print(
      "  cme_deploy_window "
      f"in_window={deploy_window.get('in_window')} "
      f"opens={deploy_window.get('window_opens_at_utc')}"
    )
  elif revision_current is True or prod_rev == expected:
    print("  cme_deploy_window=none (revision current — expected outside deploy window)")
  else:
    errors.append("cme_deploy_window_missing")

  if deploy_info.get("vercel_bundle_behind_expected") is True:
    exp = deploy_info.get("expected_dashboard_bundle") or "?"
    act = deploy_info.get("vercel_bundle_revision") or "?"
    print(f"  note: dashboard bundle behind expected ({act} vs {exp}) — non-blocking")

  if prod_rev == expected:
    if snapshot.get("run_deploy_window_command"):
      print("  run_deploy_window_command=ok")
    else:
      print("  note: run_deploy_window_command missing on snapshot (pre-r366)")
    if snapshot.get("wait_for_deploy_command"):
      print("  wait_for_deploy_command=ok")
    for key in ("github_token_configured", "fomo_bearer_configured"):
      if key not in snapshot:
        errors.append(f"snapshot_missing_{key}")
    if "fomo_bearer_configured" in snapshot:
      print(
        f"  fomo_bearer configured={snapshot.get('fomo_bearer_configured')} "
        f"polling={snapshot.get('fomo_bearer_polling_active')} "
        f"mins={snapshot.get('fomo_bearer_minutes_remaining')} "
        f"nudge_tier={snapshot.get('fomo_bearer_nudge_tier')}"
      )
      if snapshot.get("fomo_bearer_configured") and snapshot.get("fomo_bearer_nudge_tier") is None:
        errors.append("snapshot_missing_fomo_bearer_nudge_tier")
    if snapshot.get("github_token_configured") is False:
      print("  note: GITHUB_TOKEN missing on Render — deploy staleness checks incomplete")
    x_mode = snapshot.get("x_intel_collection_mode")
    if x_mode:
      print(f"  x_intel_collection_mode={x_mode}")
    else:
      errors.append("snapshot_missing_x_intel_collection_mode")

  learning = status.get("learning") or snapshot.get("learning") or {}
  if learning:
    intel_count = learning.get("intel_pattern_count") or 0
    print(
      "  learning_loop "
      f"analyses={learning.get('trade_analyses')} "
      f"reviews={learning.get('daily_reviews')} "
      f"pending_insights={learning.get('insights_pending')} "
      f"insights_applied={learning.get('insights_applied')} "
      f"intel_pattern_alerts={intel_count}"
    )
    for alert in (learning.get("intel_pattern_alerts") or [])[:3]:
      print(f"    intel_alert={alert}")
  elif status:
    errors.append("learning_loop_missing")

  content = status.get("content_study") or snapshot.get("content_study") or {}
  recent = content.get("recent") or []
  if recent:
    print(
      f"  content_study applied={content.get('insights_applied') or 0} "
      f"recent={len(recent)}"
    )
    for row in recent[:3]:
      source_type = row.get("source_type")
      label = row.get("source_label")
      if source_type and not label:
        errors.append("content_study_missing_source_label")
      title = (row.get("title") or "")[:48]
      state = "applied" if row.get("applied") else "pending"
      print(f"    [{label or source_type or 'unknown'}] {title} ({state})")

  if snapshot.get("cme_deploy_window") or snapshot.get("platform_revision"):
    print(f"  deploy_snapshot=ok revision={snapshot.get('platform_revision')}")
  elif snapshot:
    errors.append("deploy_snapshot_missing_window")
  elif prod_rev == expected:
    print("  deploy_snapshot=skipped (pre-r358 backend)")

  return errors


def main() -> int:
  parser = argparse.ArgumentParser()
  sub = parser.add_subparsers(dest="cmd", required=True)

  mins_p = sub.add_parser("prep-mins")
  mins_p.add_argument("--file", default="-")

  preflight_p = sub.add_parser("cme-prep-preflight")
  preflight_p.add_argument("--file", default="-")

  intel_p = sub.add_parser("intel-readiness")
  intel_p.add_argument("--sources-file", default="-")
  intel_p.add_argument("--snapshot-file", default="-")
  intel_p.add_argument("--prod-rev", default="")
  intel_p.add_argument("--code-rev", default="")

  post_p = sub.add_parser("post-deploy-check")
  post_p.add_argument("--status-file", default="-")
  post_p.add_argument("--checklist-file", default="-")
  post_p.add_argument("--snapshot-file", default="-")
  post_p.add_argument("--expected", required=True)

  args = parser.parse_args()

  if args.cmd == "prep-mins":
    path = None if args.file == "-" else args.file
    with open(path, encoding="utf-8") if path else sys.stdin as fh:
      prep = json.load(fh)
    mins = minutes_until_open(prep)
    print(mins if mins is not None else "")
    return 0

  if args.cmd == "cme-prep-preflight":
    path = None if args.file == "-" else args.file
    with open(path, encoding="utf-8") if path else sys.stdin as fh:
      prep = json.load(fh)
    errors, fields = evaluate_cme_prep_preflight(prep)
    print(f"cme_phase={fields['prep_phase']} minutes_until_open={fields['minutes_until_open']}")
    print(f"auto_entry_queued={fields['auto_entry_queued']} open_ready={fields['open_ready_symbols']}")
    if errors:
      print("errors=" + ",".join(errors))
      return 1
    return 0

  if args.cmd == "intel-readiness":
    with open(args.sources_file, encoding="utf-8") if args.sources_file != "-" else sys.stdin as fh:
      sources = json.load(fh)
    with open(args.snapshot_file, encoding="utf-8") if args.snapshot_file != "-" else sys.stdin as fh:
      snapshot = json.load(fh)
    print(evaluate_intel_readiness(sources, snapshot, prod_rev=args.prod_rev, code_rev=args.code_rev))
    return 0

  if args.cmd == "post-deploy-check":
    with open(args.status_file, encoding="utf-8") if args.status_file != "-" else sys.stdin as fh:
      status = json.load(fh)
    with open(args.checklist_file, encoding="utf-8") if args.checklist_file != "-" else sys.stdin as fh:
      checklist = json.load(fh)
    with open(args.snapshot_file, encoding="utf-8") if args.snapshot_file != "-" else sys.stdin as fh:
      snapshot = json.load(fh)
    errors = evaluate_post_deploy(status, checklist, snapshot, expected=args.expected)
    if errors:
      print("  errors=" + ",".join(errors))
      return 1
    return 0

  return 2


if __name__ == "__main__":
  raise SystemExit(main())
