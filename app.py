"""Harper agent API. UI is served by the Next.js frontend (see frontend/)."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from flask import Flask, Response, redirect, request, jsonify

from harper_agent.main import run_agent_loop
from harper_agent.session_manager import create_session_id, get_session
from harper_agent.transcript_service import get_transcript

app = Flask(__name__)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")


@app.after_request
def add_cors(response):
    origin = request.environ.get("HTTP_ORIGIN")
    if origin and (origin == FRONTEND_URL or origin.startswith("http://localhost:") or origin.startswith("https://")):
        response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Tenant-ID, X-Trace-ID, X-Request-ID"
    return response


@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        from flask import make_response
        r = make_response("", 204)
        return r


@app.route("/", methods=["GET"])
def index():
    session_id = request.args.get("session_id", "").strip()
    if session_id:
        r = redirect(FRONTEND_URL + "/?session_id=" + session_id, code=302)
        r.set_cookie("harper_session", session_id, max_age=60 * 60 * 24)
        return r
    return redirect(FRONTEND_URL, code=302)


@app.route("/api/history", methods=["GET"])
def api_history():
    session_id = request.cookies.get("harper_session") or request.args.get("session_id", "").strip()
    tenant_id = (request.args.get("tenant_id") or request.headers.get("X-Tenant-ID") or "").strip() or None
    if not session_id:
        return jsonify({"turns": []})
    state = get_session(session_id, tenant_id=tenant_id)
    turns = []
    for t in state.turn_history:
        msg = t.message or ""
        # Don't send raw tool output (e.g. evidence dumps) to the UI; show a short placeholder
        if t.role == "assistant" and msg.startswith("[Tool ") and len(msg) > 280:
            msg = msg.split("\n", 1)[0] + " — [details used to form the answer below]"
        turn = {"role": t.role, "message": msg}
        if getattr(t, "list_items", None):
            turn["list_items"] = t.list_items
        if getattr(t, "references", None):
            turn["references"] = t.references
        turns.append(turn)
    return jsonify({"turns": turns, "session_id": session_id})


@app.route("/api/transcript", methods=["GET"])
def api_transcript():
    """Return durable transcript for a session (replay, resume past conversation)."""
    session_id = request.args.get("session_id", "").strip() or request.cookies.get("harper_session", "")
    tenant_id = (request.args.get("tenant_id") or request.headers.get("X-Tenant-ID") or "").strip() or None
    if not session_id:
        return jsonify({"turns": [], "session_id": ""})
    turns = get_transcript(session_id, tenant_id=tenant_id)
    return jsonify({"turns": turns, "session_id": session_id})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    session_id = request.cookies.get("harper_session") or data.get("session_id") or create_session_id()
    goal = (data.get("goal") or "").strip() or None  # optional: reviewing_one_account | triaging_pipeline | checking_follow_ups | preparing_outreach
    tenant_id = (data.get("tenant_id") or request.headers.get("X-Tenant-ID") or "").strip() or None
    trace_id = (request.headers.get("X-Trace-ID") or request.headers.get("X-Request-ID") or str(uuid.uuid4())).strip()
    if not message:
        return jsonify({"error": "Empty message", "reply": ""}), 400
    try:
        result = run_agent_loop(session_id, message, goal=goal, tenant_id=tenant_id, trace_id=trace_id)
        payload = {"reply": result["narrative"], "session_id": session_id}
        if result.get("list_items"):
            payload["list_items"] = result["list_items"]
        if result.get("references"):
            payload["references"] = result["references"]
        if result.get("suggested_follow_ups"):
            payload["suggested_follow_ups"] = result["suggested_follow_ups"]
        resp = jsonify(payload)
        resp.set_cookie("harper_session", session_id, max_age=60 * 60 * 24)
        return resp
    except Exception as e:
        return jsonify({"error": str(e), "reply": ""}), 500


@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    """Stream response as Server-Sent Events (design §11.1 Step 8). Use stream=1 or Accept: text/event-stream on POST /api/chat for same."""
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    session_id = request.cookies.get("harper_session") or data.get("session_id") or create_session_id()
    goal = (data.get("goal") or "").strip() or None
    tenant_id = (data.get("tenant_id") or request.headers.get("X-Tenant-ID") or "").strip() or None
    trace_id = (request.headers.get("X-Trace-ID") or request.headers.get("X-Request-ID") or str(uuid.uuid4())).strip()
    if not message:
        return jsonify({"error": "Empty message", "reply": ""}), 400

    queue: Queue = Queue()

    def stream_callback(event: str, payload: str | dict) -> None:
        queue.put((event, payload))

    def run() -> None:
        try:
            run_agent_loop(
                session_id,
                message,
                goal=goal,
                tenant_id=tenant_id,
                trace_id=trace_id,
                stream_callback=stream_callback,
            )
        except Exception as e:
            queue.put(("error", str(e)))

    thread = Thread(target=run)
    thread.start()

    def generate() -> str:
        while True:
            try:
                event, payload = queue.get(timeout=60)
            except Empty:
                break
            if event == "chunk":
                yield f"data: {json.dumps({'chunk': payload})}\n\n"
            elif event == "result":
                yield f"data: {json.dumps(payload)}\n\n"
                break
            elif event == "error":
                yield f"data: {json.dumps({'error': payload})}\n\n"
                break

    resp = Response(generate(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    resp.set_cookie("harper_session", session_id, max_age=60 * 60 * 24)
    return resp


if __name__ == "__main__":
    os.environ.setdefault("HARPER_MEMORY_ROOT", "memory")
    port = int(os.environ.get("PORT", 5050))
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("Warning: GEMINI_API_KEY not set. Put it in .env in the project root and restart.")
    else:
        print("GEMINI_API_KEY loaded from .env")
    app.run(host="0.0.0.0", port=port, debug=True)
