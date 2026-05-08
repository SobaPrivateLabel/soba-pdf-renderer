"""
Soba IQ Super: PDF report renderer (DocRaptor / Prince XML version).

Replaces the Playwright-based renderer. DocRaptor uses Prince XML on its
servers, which has full CSS Paged Media support (@page backgrounds, margin
boxes, page-break controls, etc), so the existing main.css renders properly
without compromise.

Usage:
    python3 render_pdf.py test_bundle.json
    python3 render_pdf.py test_bundle.json --out custom/path.pdf
    python3 render_pdf.py test_bundle.json --live   (uses live render, charges)

Defaults to test mode (free, watermarked). Pass --live to render an
unwatermarked production document (counts against your monthly quota).
"""

import argparse
import base64
import json
import sys
from datetime import datetime
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = SCRIPT_DIR / "templates"
ASSETS_DIR = SCRIPT_DIR / "assets"

DOCRAPTOR_URL = "https://docraptor.com/docs"

# Read the API key from environment if set, otherwise fall back to the
# hard-coded value below. For production you'll want to set this as an
# environment variable rather than commit it to the file.
import os
DOCRAPTOR_API_KEY = os.environ.get(
    "DOCRAPTOR_API_KEY",
    "9KpcwOR9KC1GZtqTgGec",  # your DocRaptor key, rotate after testing
)


# ---------------------------------------------------------------------------
# Asset embedding
# ---------------------------------------------------------------------------

# DocRaptor fetches resources via URL by default. Since our assets live on
# Storm's local disk (not a public URL), we embed them as base64 data URIs
# in the HTML before sending it to DocRaptor. This means the rendered HTML
# is fully self-contained.

def asset_data_uri(filename: str) -> str:
    """Read an asset file and return a base64 data URI."""
    path = ASSETS_DIR / filename
    if not path.exists():
        print(f"WARNING: Asset not found: {path}", file=sys.stderr)
        return ""

    suffix = path.suffix.lower().lstrip(".")
    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")

    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def inline_assets_in_html(html: str) -> str:
    """Replace ../assets/<filename> references with embedded data URIs."""
    import re
    pattern = re.compile(r"\.\./assets/([\w\-.]+)")

    def replace(match):
        filename = match.group(1)
        return asset_data_uri(filename)

    return pattern.sub(replace, html)


def inline_css_assets(css: str) -> str:
    """Replace ../assets/<filename> references inside the CSS with data URIs."""
    import re
    pattern = re.compile(r"url\(['\"]?\.\./assets/([\w\-.]+)['\"]?\)")

    def replace(match):
        filename = match.group(1)
        uri = asset_data_uri(filename)
        return f"url('{uri}')"

    return pattern.sub(replace, css)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def normalise_bundle(bundle, company_override=None):
    """Translate the orchestrator's bundle shape into what report.html expects."""
    if not bundle.get("report_date"):
        bundle["report_date"] = datetime.now().strftime("%d/%m/%Y")

    if company_override:
        bundle["company_name"] = company_override

    score_section = bundle.get("sections", {}).get("score") or {}
    presentation = score_section.get("presentation")
    if presentation and " (" in presentation:
        score_section["presentation"] = presentation.split(" (")[0]

    return bundle

def build_html(bundle: dict) -> str:
    """Render report.html with the bundle data, then embed assets as base64."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("report.html")

    # Read the CSS, inline its asset references, and embed it directly into
    # the HTML in a <style> block. This avoids DocRaptor having to fetch
    # main.css separately.
    css_path = TEMPLATES_DIR / "main.css"
    css_content = css_path.read_text(encoding="utf-8")
    css_content = inline_css_assets(css_content)

    html = template.render(**bundle)

    # Replace the <link rel="stylesheet"> with an inline <style> block
    inline_style = f"<style>{css_content}</style>"
    html = html.replace(
        '<link rel="stylesheet" href="main.css">',
        inline_style,
    )

    # Embed image references (e.g. ../assets/cat.png) as data URIs
    html = inline_assets_in_html(html)

    return html


def render_pdf(bundle_path: Path, out_path: Path, live: bool = False, company=None) -> None:
    """Render the bundle JSON to PDF via DocRaptor."""
    print(f"Reading bundle: {bundle_path}")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle = normalise_bundle(bundle, company_override=company)

    print("Building HTML with embedded assets...")
    html = build_html(bundle)

    # Optionally save the assembled HTML for debugging
    debug_html = SCRIPT_DIR / "output" / "_debug_last.html"
    debug_html.parent.mkdir(parents=True, exist_ok=True)
    debug_html.write_text(html, encoding="utf-8")
    print(f"Debug HTML saved: {debug_html}")

    mode = "LIVE (charged)" if live else "TEST (free, watermarked)"
    print(f"Calling DocRaptor in {mode} mode...")

    response = requests.post(
        DOCRAPTOR_URL,
        auth=(DOCRAPTOR_API_KEY, ""),
        json={
            "test": not live,
            "document_content": html,
            "type": "pdf",
            "name": out_path.stem,
            "prince_options": {
                "media": "print",
            },
        },
        timeout=120,
    )

    if response.status_code != 200:
        print(f"ERROR: DocRaptor returned {response.status_code}", file=sys.stderr)
        try:
            error_detail = response.json()
            print(json.dumps(error_detail, indent=2), file=sys.stderr)
        except Exception:
            print(response.text[:2000], file=sys.stderr)
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(response.content)
    size_kb = len(response.content) / 1024
    print(f"PDF written: {out_path} ({size_kb:.1f} KB)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "bundle",
        type=Path,
        help="Path to the JSON report bundle",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output PDF path. Defaults to ./output/<company>_<timestamp>.pdf",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Render in live mode (no watermark, charged against quota). "
             "Default is test mode (free, watermarked).",
    )
    parser.add_argument(
        "--company",
        type=str,
        default=None,
        help="Override the company name displayed on the cover.",
    )
    args = parser.parse_args()

    if not args.bundle.exists():
        print(f"ERROR: Bundle not found: {args.bundle}", file=sys.stderr)
        return 1

    if args.out is None:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        company = (
            bundle.get("company_name", "report")
            .replace(" ", "_")
            .replace(".", "_")
            .lower()
        )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.out = SCRIPT_DIR / "output" / f"{company}_{timestamp}.pdf"

    args.out.parent.mkdir(parents=True, exist_ok=True)

    try:
        render_pdf(args.bundle, args.out, live=args.live, company=args.company)
    except Exception as e:
        print(f"\nERROR: PDF render failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
