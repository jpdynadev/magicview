#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "kinnan_policy_parity_manifest_v2.json"


def validate(manifest: dict, *, component_only: bool) -> dict:
    caps = manifest.get("capabilities") or {}
    failures: list[str] = []
    checked: list[str] = []

    if component_only:
        for cid, meta in caps.items():
            if not meta.get("componentImplemented"):
                continue
            checked.append(cid)
            if not meta.get("positiveGoldens"):
                failures.append(f"{cid}: componentImplemented requires >=1 positive golden")
            if not meta.get("negativeGoldens"):
                failures.append(f"{cid}: componentImplemented requires >=1 negative golden")
    else:
        if not manifest.get("rankingReady"):
            failures.append("manifest rankingReady is false")
        for anchor_id, anchor in (manifest.get("anchors") or {}).items():
            deck_path = anchor.get("deckPath")
            if not deck_path or not (HERE.parent / deck_path).exists():
                failures.append(f"{anchor_id}: missing exact anchor deck registration {deck_path}")
            for cid in anchor.get("requiredCapabilities") or []:
                checked.append(cid)
                meta = caps.get(cid)
                if not meta:
                    failures.append(f"{anchor_id}: unknown required capability {cid}")
                    continue
                if not meta.get("componentImplemented"):
                    failures.append(f"{anchor_id}: {cid} component not implemented")
                if not meta.get("productionSupported"):
                    failures.append(f"{anchor_id}: {cid} not production-integrated")
                if not meta.get("positiveGoldens") or not meta.get("negativeGoldens"):
                    failures.append(f"{anchor_id}: {cid} lacks positive/negative goldens")

    return {
        "schemaVersion": manifest.get("schemaVersion"),
        "pilotVersion": manifest.get("pilotVersion"),
        "policyVersion": manifest.get("policyVersion"),
        "mode": "component" if component_only else "production",
        "checkedCapabilities": sorted(set(checked)),
        "failures": failures,
        "valid": not failures,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--component-only", action="store_true")
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    manifest = json.loads(args.manifest.read_text())
    report = validate(manifest, component_only=args.component_only)
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
