#!/usr/bin/env python3
"""Fixture checks for the donation pin guard. Works in a temp dir."""
from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_donate  # noqa: E402

SOURCE = "https://example.gov.np/official.pdf"
QR_BYTES = b"\x89PNG official qr"
FIXTURE_HTML = f"""<!DOCTYPE html><html><body>
<p>Official page: <a href="{SOURCE}">PDF</a></p>
<button class="acct" data-acct="1130100003762001">1130100003762001</button>
<button class="acct" data-acct="RBBANPKA">RBBANPKA</button>
<a href="img/qr-rbb-disaster.png"><img src="img/qr-rbb-disaster.png"></a>
<p>tweet 2092849615360114978 · phone 9779851096547 · rain 0.02012472627688</p>
</body></html>
"""


def build(root: Path, html: str = FIXTURE_HTML, js: str = "", qr: bytes = QR_BYTES) -> None:
    (root / "img").mkdir(parents=True, exist_ok=True)
    (root / "img" / "qr-rbb-disaster.png").write_bytes(qr)
    (root / "donate.html").write_text(html, encoding="utf-8")
    (root / "i18n.js").write_text(js, encoding="utf-8")


PINS = {
    "official_source": SOURCE,
    "qr": {"img/qr-rbb-disaster.png": hashlib.sha256(QR_BYTES).hexdigest()},
    "data_acct": ["1130100003762001", "RBBANPKA"],
}


def errors_for(**kw) -> list[str]:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        build(root, **kw)
        return check_donate.check(root, PINS)


def expect(name: str, errors: list[str], needle: str) -> None:
    if not any(needle in e for e in errors):
        raise SystemExit(f"{name}: expected an error containing {needle!r}, got {errors}")


def main() -> int:
    clean = errors_for()
    if clean:
        raise SystemExit(f"clean fixture should pass, got {clean}")

    expect("swapped QR", errors_for(qr=b"\x89PNG attacker qr"), "QR image changed")
    expect("swapped account",
           errors_for(html=FIXTURE_HTML.replace("1130100003762001", "1130100009999001")),
           "is not pinned")
    expect("account removed",
           errors_for(html=FIXTURE_HTML.replace('data-acct="RBBANPKA"', "")),
           "is gone from the page")
    expect("new QR link",
           errors_for(html=FIXTURE_HTML + '<img src="img/qr-new-fund.png">'),
           "img/qr-new-fund.png")
    expect("source removed",
           errors_for(html=FIXTURE_HTML.replace(SOURCE, "https://elsewhere.example/")),
           "official source link")
    expect("account in a translation",
           errors_for(js='"dd_ccy": "Send to 01905631219999"'),
           "account-like number 01905631219999")
    expect("account in Devanagari digits",
           errors_for(js='"x": "खाता ११३०१००००९९९९००१"'),
           "account-like number 1130100009999001")

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        build(root)
        (root / "img" / "qr-extra.png").write_bytes(b"unpinned")
        expect("unpinned QR file", check_donate.check(root, PINS), "img/qr-extra.png: QR image is not pinned")

    print("check_donate fixtures ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
