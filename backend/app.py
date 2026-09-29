"""Local Flask demonstration with real Hindsight operations and human verification."""
from datetime import datetime, timezone
import os
from pathlib import Path
import secrets
import time
from uuid import uuid4

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

from . import hindsight_service
from .incident_service import (build_recall_query, build_verified_memory, classify_incident,
                               generate_recommendation, load_sample_incidents,
                               normalize_memories, summarize_memory_evidence)
from .store import IncidentStore

ROOT = Path(__file__).resolve().parents[1]
INCIDENT_FIELDS = ("machine", "product", "batch", "quality_defect", "machine_condition",
                   "recent_change", "previous_action", "previous_result", "before_metric")
RESOLUTION_FIELDS = ("confirmed_root_cause", "action_taken", "action_result", "before_metric",
                     "after_metric", "verification_status")


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=secrets.token_hex(32), MAX_CONTENT_LENGTH=32 * 1024,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      DATABASE=ROOT / "data/local.sqlite3", AUTO_CHECK=True)
    if test_config:
        app.config.update(test_config)
    store = IncidentStore(app.config["DATABASE"])
    app.extensions["incident_store"] = store
    connection = {"state": "NOT CHECKED", "at": 0, "message": "No cloud operation checked yet."}
    samples = load_sample_incidents()
    demos = {s["incident_id"]: {k: s.get(k, "") for k in INCIDENT_FIELDS} for s in samples if s["incident_id"] != "INC-001"}
    for sample in samples:
        if sample["incident_id"] in demos and sample.get("defect_rate_before_percent") is not None:
            demos[sample["incident_id"]]["before_metric"] = f"{sample['defect_rate_before_percent']}%"

    def update_connection(success):
        connection.update(state="CONNECTED" if success else "OFFLINE / ERROR", at=time.time(),
                          message="Last cloud operation succeeded." if success else "Last cloud operation failed.")

    def check_connection():
        try:
            normalize_memories(hindsight_service.recall_incidents("Capping Machine C-07 previous incident evidence"))
            update_connection(True)
        except Exception:
            update_connection(False)

    @app.before_request
    def protect_forms():
        session.setdefault("owner", uuid4().hex)
        session.setdefault("csrf", secrets.token_urlsafe(32))
        if request.method == "POST" and not secrets.compare_digest(request.form.get("csrf_token", ""), session["csrf"]):
            abort(400, description="This form expired. Reload the page and try again.")

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.context_processor
    def common():
        status = dict(connection)
        if status["state"] == "CONNECTED" and time.time() - status["at"] > 300:
            status["state"] = "CHECK AGAIN"
            status["message"] = "Last success is more than five minutes old."
        return {"connection": status, "bank": os.getenv("HINDSIGHT_BANK_ID", "rootcause-twin"), "csrf": session.get("csrf")}

    def get_incident(incident_id):
        incident = store.get(incident_id, session["owner"])
        if not incident:
            abort(404, description="Incident not found in this browser session. Start a new investigation.")
        return incident

    def read_fields(fields, required):
        values = {key: request.form.get(key, "").strip() for key in fields}
        errors = [f"{key.replace('_', ' ').capitalize()} is required." for key in required if not values[key]]
        errors += [f"{key.replace('_', ' ').capitalize()} must be 1,000 characters or fewer." for key, value in values.items() if len(value) > 1000]
        errors += ["Use single-line text for incident and resolution fields." for value in values.values() if any(ord(c) < 32 for c in value)]
        return values, errors

    @app.get("/")
    def dashboard():
        if not connection["at"] and app.config["AUTO_CHECK"]:
            check_connection()
        current = store.list_for(session["owner"])
        counts = {"total": len(samples) + len(current),
                  "verified": sum(s["verification_status"] == "VERIFIED" for s in samples) + sum(i["state"] == "RETAINED" for i in current),
                  "known": sum(i.get("analysis", {}).get("classification") == "KNOWN" for i in current),
                  "novel": sum(i.get("analysis", {}).get("classification") == "NOVEL" for i in current)}
        return render_template("dashboard.html", samples=samples, incidents=current, counts=counts)

    @app.post("/connection/check")
    def connection_check():
        check_connection()
        flash(connection["message"], "info")
        return redirect(url_for("dashboard"))

    @app.get("/incident/new")
    def new_incident():
        return render_template("new.html", values={}, errors=[], demos=demos)

    @app.post("/incident/analyze")
    def analyze():
        values, errors = read_fields(INCIDENT_FIELDS, ("machine", "product", "batch", "quality_defect", "machine_condition"))
        if values["previous_result"] not in ("", "SUCCESS", "FAILED", "PARTIAL"):
            errors.append("Select a valid previous action result.")
        if errors:
            return render_template("new.html", values=values, errors=errors, demos=demos), 400
        demo = request.form.get("demo", "")
        incident = {**values, "incident_id": "INC-" + uuid4().hex[:8].upper(),
                    "demo": demo if demo in demos else "", "created_at": datetime.now(timezone.utc).isoformat()}
        try:
            memories = normalize_memories(hindsight_service.recall_incidents(build_recall_query(incident)))
            update_connection(True)
        except Exception:
            update_connection(False)
            errors = ["Hindsight could not be reached or returned unreadable evidence. The incident was not analyzed with persistent memory. Verify the connection and try again."]
            return render_template("new.html", values=values, errors=errors, demos=demos), 503
        analysis = classify_incident(incident, memories)
        incident.update(analysis=analysis, memories=memories,
                        summary=summarize_memory_evidence(memories),
                        guidance=generate_recommendation(incident, memories, analysis))
        store.save(incident, session["owner"])
        return redirect(url_for("investigation", incident_id=incident["incident_id"]))

    @app.get("/incident/<incident_id>")
    def investigation(incident_id):
        return render_template("analysis.html", incident=get_incident(incident_id))

    @app.route("/incident/<incident_id>/resolve", methods=["GET", "POST"])
    def resolve(incident_id):
        incident = get_incident(incident_id)
        if incident["state"] == "RETAINED":
            return render_template("success.html", incident=incident)
        errors, values = [], {"before_metric": incident.get("before_metric", "")}
        if request.method == "POST":
            values, errors = read_fields(RESOLUTION_FIELDS, RESOLUTION_FIELDS)
            if values["verification_status"] not in ("VERIFIED", "UNVERIFIED"):
                errors.append("Select a valid verification status.")
            if values["action_result"] not in ("SUCCESS", "FAILED", "PARTIAL"):
                errors.append("Select a valid action result.")
            if values["verification_status"] == "UNVERIFIED":
                errors.append("Unverified resolution was not retained. Complete human verification before adding trusted memory.")
            if not errors and not store.claim(incident_id, session["owner"]):
                errors.append("Retention is already in progress or its outcome is uncertain. Check Hindsight before attempting another submission.")
            if not errors:
                incident["resolution"] = values
                try:
                    result = hindsight_service.retain_incident(build_verified_memory(incident, values))
                    if not result.success:
                        raise ValueError("Retention not confirmed")
                except Exception:
                    update_connection(False)
                    store.update(incident, session["owner"], "UNCERTAIN")
                    errors.append("Hindsight did not confirm retention. It may have stored the record before the connection failed. Check the bank before retrying; automatic retries are disabled.")
                else:
                    update_connection(True)
                    store.update(incident, session["owner"], "RETAINED")
                    return redirect(url_for("resolve", incident_id=incident_id))
        return render_template("resolve.html", incident=incident, values=values, errors=errors), (400 if errors else 200)

    @app.get("/about")
    def about():
        return render_template("about.html")

    @app.get("/health")
    def health():
        # Configuration is distinct from an actual connection success.
        from dotenv import dotenv_values
        key = os.getenv("HINDSIGHT_API_KEY") or dotenv_values(ROOT / ".env").get("HINDSIGHT_API_KEY")
        return {"status": "ok", "service": "RootCause Twin AI", "hindsight_configured": bool(key and key != "your_hindsight_api_key_here")}

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def friendly_error(error):
        return render_template("error.html", message=error.description), error.code

    @app.errorhandler(500)
    def server_error(error):
        return render_template("error.html", message="The request could not be completed. Return to the dashboard and try again."), 500

    return app
