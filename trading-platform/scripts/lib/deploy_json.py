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
  return {
    "x_collection_mode": x.get("collection_mode"),
    "tv_scoring_excludes_synthetic": tv.get("scoring_excludes_synthetic"),
    "tv_webhook_items_24h": tv.get("webhook_items_24h"),
    "tv_synthetic_items_24h": tv.get("synthetic_items_24h"),
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
  snapshot_ok = bool(snapshot.get("x_intel_collection_mode")) and bool(
    snapshot.get("tradingview_item_breakdown") or snapshot.get("tradingview_webhook_items_24h") is not None
  )
  if prod_rev == code_rev:
    return "ok" if sources_ok and snapshot_ok else ("partial" if sources_ok else "missing")
  if sources_ok and not snapshot_ok:
    return "partial"
  if sources_ok:
    return "partial"
  return "missing"


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

  return 2


if __name__ == "__main__":
  raise SystemExit(main())
