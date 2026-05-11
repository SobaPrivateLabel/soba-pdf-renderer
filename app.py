import io
import os
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_file

from render_pdf import build_html

import requests

app = Flask(__name__)

DOCRAPTOR_URL = "https://docraptor.com/docs"
DOCRAPTOR_API_KEY = os.environ.get("DOCRAPTOR_API_KEY")
SHARED_SECRET = os.environ.get("RENDERER_SHARED_SECRET")


@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "soba-pdf-renderer"}), 200


@app.route("/render", methods=["POST"])
def render():
    auth_header = request.headers.get("Authorization", "")
    if not SHARED_SECRET or auth_header != f"Bearer {SHARED_SECRET}":
        return jsonify({"error": "unauthorized"}), 401

    bundle = request.get_json(silent=True)
    if not bundle:
        return jsonify({"error": "missing or invalid JSON body"}), 400

    live = request.args.get("live", "false").lower() == "true"

    try:
        html = build_html(bundle)
    except Exception as e:
        return jsonify({"error": f"html build failed: {type(e).__name__}: {e}"}), 500

    company = (
        bundle.get("company_name", "report")
        .replace(" ", "_")
        .replace(".", "_")
        .lower()
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{company}_{timestamp}.pdf"

    response = requests.post(
        DOCRAPTOR_URL,
        auth=(DOCRAPTOR_API_KEY, ""),
        json={
            "test": not live,
            "document_content": html,
            "type": "pdf",
            "name": Path(filename).stem,
            "prince_options": {"media": "print"},
        },
        timeout=120,
    )

    if response.status_code != 200:
        return jsonify({
            "error": "docraptor failed",
            "status": response.status_code,
            "detail": response.text[:500],
        }), 502

    return send_file(
        io.BytesIO(response.content),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
