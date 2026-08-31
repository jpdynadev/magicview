#!/usr/bin/env python3
"""Fail closed when a deck-ranking anchor lacks declared pilot capabilities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_dck(path: Path) -> tuple[list[str], list[str]]:
    section = None
    commander: list[str] = []
    main: list[str] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line.lower()
            continue
        count_text, name = line.split(" ", 1)
        cards = [name.strip()] * int(count_text)
        if section == "[commander]":
            commander.extend(cards)
        elif section == "[main]":
            main.extend(cards)
    return commander, main


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--root", default=".")
    parser.add_argument("--output")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest = json.loads(Path(args.manifest).read_text())
    supported = set(manifest.get("currentPilotCapabilities", []))
    reports = []
    all_valid = True

    for anchor in manifest.get("anchors", []):
        deck_path = root / anchor["deckPath"]
        commander, main = parse_dck(deck_path)
        required = set(anchor.get("requiredCapabilities", []))
        missing = sorted(required - supported)
        exact_99 = len(main) == 99 and len(set(main)) == 99
        commander_valid = commander == ["Kinnan, Bonder Prodigy"]
        comparable = exact_99 and commander_valid and not missing
        all_valid &= comparable
        reports.append(
            {
                "id": anchor["id"],
                "deckPath": anchor["deckPath"],
                "mainCount": len(main),
                "distinctMainCards": len(set(main)),
                "exact99": exact_99,
                "commanderValid": commander_valid,
                "requiredCapabilities": sorted(required),
                "missingCapabilities": missing,
                "policyComparable": comparable,
            }
        )

    result = {
        "schemaVersion": manifest.get("schemaVersion"),
        "pilotVersion": manifest.get("pilotVersion"),
        "policyParityValid": all_valid,
        "supportedCapabilities": sorted(supported),
        "anchors": reports,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered)
    print(rendered, end="")
    return 0 if all_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
