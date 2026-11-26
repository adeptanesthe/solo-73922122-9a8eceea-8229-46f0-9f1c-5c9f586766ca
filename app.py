"""Flask web application for choosing a discriminating re-measurement gear."""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, render_template, request

from diagnostics import (
    NoSolutionError,
    ValidationError,
    analyze_case,
    supplement_observation,
)
from examples import EXAMPLE_CASE

app = Flask(__name__)
app.json.ensure_ascii = False
app.config["JSON_SORT_KEYS"] = False


@app.get("/")
def index() -> str:
    return render_template("index.html")


@app.get("/api/health")
def health() -> Any:
    return jsonify({"status": "ok"})


@app.get("/api/example")
def example() -> Any:
    """Return the built-in demo, including fill-in values for the supplement."""

    return jsonify(EXAMPLE_CASE)


@app.post("/api/analyze")
def api_analyze() -> Any:
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "请求体必须是 JSON 对象"}), 400

    try:
        return jsonify(analyze_case(payload))
    except ValidationError as exc:
        return jsonify({"error": exc.message, "issues": exc.issues}), 400


@app.post("/api/supplement")
def api_supplement() -> Any:
    """Validate a supplemental table and return updated or original diagnosis."""

    body = request.get_json(silent=True)
    if body is None:
        return jsonify({"error": "请求体必须是 JSON 对象"}), 400

    new_observation = body.get("new_observation")
    if new_observation is None:
        new_observation = body.get("observation")

    if not isinstance(new_observation, dict):
        return (
            jsonify(
                {
                    "error": (
                        "必须通过 new_observation 对象提供补录档位，例如 "
                        '{"new_observation": {"sample_rate": 11025, "peaks": [1625]}}'
                    )
                }
            ),
            400,
        )

    # Allow {"case": {...}, "new_observation": {...}} as well as flat payloads.
    case_payload = body.get("case", body)
    if not isinstance(case_payload, dict):
        return jsonify({"error": "case 必须是对象"}), 400

    try:
        result = supplement_observation(case_payload, new_observation)
        return jsonify(result)
    except NoSolutionError as exc:
        return (
            jsonify(
                {
                    "accepted": False,
                    "error": exc.message,
                    "original": exc.original_result,
                }
            ),
            409,
        )
    except ValidationError as exc:
        return jsonify({"accepted": False, "error": exc.message, "issues": exc.issues}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
