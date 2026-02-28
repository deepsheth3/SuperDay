"""Web UI for Harper agent."""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import Flask, jsonify, render_template_string, request

from harper_agent.main import run_agent_loop
from harper_agent.session_manager import create_session_id

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Harper Agent</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', system-ui, sans-serif;
      max-width: 640px;
      margin: 0 auto;
      padding: 1rem;
      background: #0f1419;
      color: #e6edf3;
      min-height: 100vh;
    }
    h1 { font-size: 1.25rem; margin-bottom: 0.5rem; color: #58a6ff; }
    .sub { font-size: 0.85rem; color: #8b949e; margin-bottom: 1rem; }
    .chat { display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1rem; }
    .msg { padding: 0.75rem 1rem; border-radius: 8px; max-width: 90%; }
    .msg.user { background: #21262d; margin-left: 0; margin-right: auto; }
    .msg.agent { background: #161b22; border: 1px solid #30363d; margin-left: auto; margin-right: 0; white-space: pre-wrap; }
    .msg.agent cite { color: #8b949e; font-size: 0.85em; }
    form { display: flex; gap: 0.5rem; }
    input[type="text"] {
      flex: 1;
      padding: 0.6rem 0.75rem;
      border: 1px solid #30363d;
      border-radius: 6px;
      background: #0d1117;
      color: #e6edf3;
      font-size: 1rem;
    }
    input[type="text"]:focus { outline: none; border-color: #58a6ff; }
    button {
      padding: 0.6rem 1rem;
      background: #238636;
      color: #fff;
      border: none;
      border-radius: 6px;
      font-weight: 500;
      cursor: pointer;
    }
    button:hover { background: #2ea043; }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    .samples { margin-top: 1rem; }
    .samples p { font-size: 0.85rem; color: #8b949e; margin-bottom: 0.5rem; }
    .samples button {
      background: transparent;
      border: 1px solid #30363d;
      color: #8b949e;
      margin: 0.25rem 0.25rem 0 0;
      padding: 0.35rem 0.6rem;
      font-size: 0.85rem;
    }
    .samples button:hover { border-color: #58a6ff; color: #58a6ff; }
    .error { color: #f85149; font-size: 0.9rem; }
  </style>
</head>
<body>
  <h1>Harper Agent</h1>
  <p class="sub">Ask about accounts, status, or contacts. Answers are grounded in your memory indices.</p>

  <div class="chat" id="chat"></div>

  <form id="form">
    <input type="text" id="input" placeholder="e.g. What is the status of Evergreen Public Services?" autocomplete="off" />
    <button type="submit" id="send">Send</button>
  </form>

  <div class="samples">
    <p>Sample queries:</p>
    <button type="button" data-query="What is the status of Evergreen Public Services?">Evergreen status</button>
    <button type="button" data-query="Tell me about Harborline Hotel Group">Harborline Hotel</button>
    <button type="button" data-query="Accounts in Colorado">Accounts in CO</button>
    <button type="button" data-query="Who is the contact for Skyline Protective Services?">Skyline contact</button>
  </div>

  <script>
    const chat = document.getElementById('chat');
    const form = document.getElementById('form');
    const input = document.getElementById('input');
    const send = document.getElementById('send');

    function addMsg(role, text) {
      const div = document.createElement('div');
      div.className = 'msg ' + role;
      div.textContent = text;
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      addMsg('user', text);
      input.value = '';
      send.disabled = true;
      try {
        const r = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text })
        });
        const data = await r.json();
        if (data.error) addMsg('agent', 'Error: ' + data.error);
        else addMsg('agent', data.reply);
      } catch (err) {
        addMsg('agent', 'Error: ' + err.message);
      }
      send.disabled = false;
    });

    document.querySelectorAll('.samples button[data-query]').forEach(btn => {
      btn.addEventListener('click', () => {
        input.value = btn.getAttribute('data-query');
        input.focus();
      });
    });
  </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    session_id = request.cookies.get("harper_session") or data.get("session_id") or create_session_id()
    if not message:
        return jsonify({"error": "Empty message", "reply": ""}), 400
    try:
        reply = run_agent_loop(session_id, message)
        resp = jsonify({"reply": reply, "session_id": session_id})
        resp.set_cookie("harper_session", session_id, max_age=60 * 60 * 24)
        return resp
    except Exception as e:
        return jsonify({"error": str(e), "reply": ""}), 500


if __name__ == "__main__":
    os.environ.setdefault("HARPER_MEMORY_ROOT", "memory")
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)
