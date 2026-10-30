#!/usr/bin/env python3
"""Fail when a donation QR image or bank account number drifts from its pin.

A swapped QR or a changed account number sends donors' money somewhere else,
and nothing on the page would show it. scripts/donate_pins.json records what
the Prime Minister's Office published. Any change has to edit that file too,
and .github/CODEOWNERS makes that edit need an owner's review.

  python scripts/check_donate.py            # check, exit 1 on any drift
  python scripts/check_donate.py --print    # print current values for a pin update

Update the pins only after matching the new QR / account against the official
PDF named in donate_pins.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINS = ROOT / "scripts" / "donate_pins.json"
DONATE = "donate.html"

# Images whose file name says QR. A new one must be pinned before it ships.
QR_NAME_RE = re.compile(r"(^|[-_/])qr([-_.]|$)", re.I)
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
QR_REF_RE = re.compile(r"""(?:src|href)\s*=\s*["']([^"'?#]*qr[^"'?#]*\.(?:png|jpe?g|webp|gif|svg))""", re.I)
DATA_ACCT_RE = re.compile(r'data-acct="([^"]*)"')
# Every PMDRF account starts with 0 or 1. Tweet ids start with 2 and Nepali
# phones with 9, so this stays quiet on the rest of the site. A '.' before
# the run means a decimal fraction, not an account.
ACCOUNT_LIKE_RE = re.compile(r"(?<![0-9A-Za-z_.])[01][0-9]{10,19}(?![0-9])")
DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
SKIP_DIRS = {".git", "_site", "vendor", "data", "node_modules", "tests"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def qr_images(root: Path) -> list[str]:
    out = []
    for p in (root / "img").rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXT and QR_NAME_RE.search(p.name):
            out.append(p.relative_to(root).as_posix())
    return sorted(out)


def page_files(root: Path) -> list[Path]:
    out = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in {".html", ".js"}:
            continue
        rel = p.relative_to(root)
        if rel.parts[0] in SKIP_DIRS:
            continue
        out.append(p)
    return sorted(out)


def current(root: Path) -> dict:
    html = (root / DONATE).read_text(encoding="utf-8")
    return {
        "qr": {rel: sha256(root / rel) for rel in qr_images(root)},
        "data_acct": sorted(set(DATA_ACCT_RE.findall(html))),
    }


def check(root: Path, pins: dict) -> list[str]:
    errors: list[str] = []
    pinned_qr: dict = pins["qr"]
    pinned_acct = set(pins["data_acct"])
    accounts = {a for a in pinned_acct if a.isdigit()}

    for rel in qr_images(root):
        if rel not in pinned_qr:
            errors.append(f"{rel}: QR image is not pinned")
        elif sha256(root / rel) != pinned_qr[rel]:
            errors.append(f"{rel}: QR image changed (sha256 differs from pin)")
    for rel in pinned_qr:
        if not (root / rel).is_file():
            errors.append(f"{rel}: pinned QR image is missing")

    html = (root / DONATE).read_text(encoding="utf-8")
    for ref in sorted(set(QR_REF_RE.findall(html))):
        if ref.lstrip("./") not in pinned_qr:
            errors.append(f"{DONATE}: links QR {ref!r}, which is not pinned")

    found = set(DATA_ACCT_RE.findall(html))
    for a in sorted(found - pinned_acct):
        errors.append(f"{DONATE}: data-acct {a!r} is not pinned")
    for a in sorted(pinned_acct - found):
        errors.append(f"{DONATE}: pinned data-acct {a!r} is gone from the page")

    source = pins.get("official_source", "")
    if source and source not in html:
        errors.append(f"{DONATE}: official source link {source} was removed")

    for path in page_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore").translate(DEVANAGARI_DIGITS)
        for run in sorted(set(ACCOUNT_LIKE_RE.findall(text))):
            if run not in accounts:
                rel = path.relative_to(root).as_posix()
                errors.append(f"{rel}: account-like number {run} is not a pinned account")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--pins", type=Path, default=PINS)
    ap.add_argument("--print", action="store_true", help="print current values instead of checking")
    args = ap.parse_args(argv)

    if args.print:
        print(json.dumps(current(args.root), indent=2, ensure_ascii=False))
        return 0
    pins = json.loads(args.pins.read_text(encoding="utf-8"))
    errors = check(args.root, pins)
    if errors:
        print("Donation details differ from scripts/donate_pins.json:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        print("Match the change against the official PDF, then update the pins in a reviewed PR.", file=sys.stderr)
        return 1
    print(f"donation pins ok: {len(pins['qr'])} QR images, {len(pins['data_acct'])} account/SWIFT values")
    return 0


if __name__ == "__main__":
    sys.exit(main())
