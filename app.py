"""Web UI for Harper agent."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    # Load .env from project root so it works no matter where the app is run from
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

from flask import Flask, jsonify, render_template_string, request

from harper_agent.main import run_agent_loop
from harper_agent.session_manager import create_session_id, get_session

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
      margin: 0;
      background: #F8EDE6;
      color: #2C2C2C;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    .header {
      flex-shrink: 0;
      padding: 1rem 1.25rem;
      background: #F8EDE6;
      border-bottom: 1px solid #e8d9cf;
    }
    h1 { font-size: 1.25rem; margin: 0 0 0.25rem 0; color: #EC7A72; }
    .sub { font-size: 0.85rem; color: #2C2C2C; margin: 0; opacity: 0.9; }
    .chat-wrap {
      flex: 1;
      overflow-y: auto;
      padding: 1rem 1.25rem;
      max-width: 720px;
      margin: 0 auto;
      width: 100%;
    }
    .chat { display: flex; flex-direction: column; gap: 0.75rem; }
    .msg { padding: 0.75rem 1rem; border-radius: 8px; max-width: 90%; }
    .msg.user { background: #fff; border: 1px solid #e8d9cf; margin-left: auto; margin-right: 0; color: #2C2C2C; }
    .msg.agent {
      background: #fff;
      border: 1px solid #e8d9cf;
      margin-left: 0;
      margin-right: auto;
      white-space: pre-wrap;
      color: #2C2C2C;
    }
    .msg.agent .narrative { margin-bottom: 0.5rem; }
    .msg.agent .msg-list { margin: 0.5rem 0; padding-left: 1.25rem; }
    .msg.agent .msg-list ol { margin: 0; padding-left: 1.25rem; }
    .msg.agent .msg-list ul { margin: 0; padding-left: 1.25rem; }
    .msg.agent .references {
      margin-top: 0.75rem;
      padding-top: 0.75rem;
      border-top: 1px solid #e8d9cf;
      font-size: 0.85rem;
      color: #2C2C2C;
      opacity: 0.85;
    }
    .msg.agent .references h4 { margin: 0 0 0.5rem 0; font-size: 0.8rem; color: #2D5E6C; font-weight: 600; }
    .msg.agent .references .ref-item { margin: 0.25rem 0; }
    .input-area {
      flex-shrink: 0;
      padding: 1rem 1.25rem;
      background: #F8EDE6;
      border-top: 1px solid #e8d9cf;
    }
    .input-inner { max-width: 720px; margin: 0 auto; display: flex; gap: 0.5rem; align-items: center; }
    input[type="text"] {
      flex: 1;
      padding: 0.65rem 0.85rem;
      border: 1px solid #e8d9cf;
      border-radius: 8px;
      background: #fff;
      color: #2C2C2C;
      font-size: 1rem;
    }
    input[type="text"]:focus { outline: none; border-color: #2D5E6C; }
    .send-btn {
      padding: 0.65rem 1rem;
      background: #EC7A72;
      color: #fff;
      border: none;
      border-radius: 8px;
      font-weight: 500;
      cursor: pointer;
    }
    .send-btn:hover { background: #e06a62; }
    .send-btn:disabled { opacity: 0.6; cursor: not-allowed; }
    .samples {
      max-width: 720px;
      margin: 0.25rem auto 0;
      padding: 0 1.25rem;
    }
    .samples p { font-size: 0.8rem; color: #2C2C2C; margin: 0 0 0.35rem 0; opacity: 0.9; }
    .samples button {
      background: transparent;
      border: 1px solid #2D5E6C;
      color: #2D5E6C;
      margin: 0.2rem 0.2rem 0 0;
      padding: 0.3rem 0.55rem;
      font-size: 0.8rem;
      border-radius: 6px;
    }
    .samples button:hover { border-color: #EC7A72; color: #EC7A72; background: rgba(236,122,114,0.1); }
    .error { color: #c62828; font-size: 0.9rem; }
  </style>
</head>
<body>
  <header class="header">
    <h1>Harper Agent</h1>
    <p class="sub">Ask about accounts, status, or contacts. Answers are grounded in your memory indices.</p>
  </header>

  <div class="chat-wrap">
    <div class="chat" id="chat"></div>
  </div>

  <div class="input-area">
    <form id="form" class="input-inner">
      <input type="text" id="input" placeholder="e.g. What is the status of Evergreen Public Services?" autocomplete="off" />
      <button type="submit" id="send" class="send-btn">Send</button>
    </form>
    <div class="samples">
    <p>Sample queries:</p>
    <button type="button" data-query="What is the status of Evergreen Public Services?">Evergreen status</button>
    <button type="button" data-query="Tell me about Harborline Hotel Group">Harborline Hotel</button>
    <button type="button" data-query="Accounts in Colorado">Accounts in CO</button>
    <button type="button" data-query="Who is the contact for Skyline Protective Services?">Skyline contact</button>
    </div>
  </div>

  <script>
    const chat = document.getElementById('chat');
    const form = document.getElementById('form');
    const input = document.getElementById('input');
    const send = document.getElementById('send');

    var renderedCount = 0;
    function renderTurns(turns) {
      var list = turns || [];
      for (var i = renderedCount; i < list.length; i++) {
        var t = list[i];
        addMsg(t.role, t.message || '', t.list_items || null, t.references || null, false);
      }
      renderedCount = list.length;
      if (list.length > 0) {
        var wrap = chat.closest('.chat-wrap');
        if (wrap) wrap.scrollTop = wrap.scrollHeight;
      }
    }
    function fetchHistory() {
      fetch('/api/history').then(function(r) { return r.json(); }).then(function(data) {
        var turns = data.turns || [];
        renderTurns(turns);
      }).catch(function() {});
    }
    document.addEventListener('DOMContentLoaded', function() {
      fetchHistory();
      if (document.location.search.indexOf('session_id=') >= 0) {
        var pollId = setInterval(function() {
          fetch('/api/history').then(function(r) { return r.json(); }).then(function(data) {
            var turns = data.turns || [];
            renderTurns(turns);
            if (turns.length >= 40) clearInterval(pollId);
          }).catch(function() {});
        }, 1500);
      }
    });

    function addMsg(role, text, listItems, references, doScroll) {
      if (doScroll === undefined) doScroll = true;
      const div = document.createElement('div');
      div.className = 'msg ' + role;
      if (role === 'user') {
        div.textContent = text;
      } else {
        div.innerHTML = '';
        if (text) {
          const p = document.createElement('div');
          p.className = 'narrative';
          p.textContent = text;
          div.appendChild(p);
        }
        if (listItems && listItems.length) {
          const listWrap = document.createElement('div');
          listWrap.className = 'msg-list';
          const isNumbered = listItems.some(function(item) { return /^\d+\.\s/.test(item); });
          const list = document.createElement(isNumbered ? 'ol' : 'ul');
          listItems.forEach(function(item) {
            const li = document.createElement('li');
            li.textContent = item;
            list.appendChild(li);
          });
          listWrap.appendChild(list);
          div.appendChild(listWrap);
        }
        if (references && references.length) {
          const refBlock = document.createElement('div');
          refBlock.className = 'references';
          refBlock.innerHTML = '<h4>References</h4>';
          references.forEach(function(r) {
            const refItem = document.createElement('div');
            refItem.className = 'ref-item';
            refItem.textContent = '[' + r.num + '] ' + (r.label || r.source_id || '');
            refBlock.appendChild(refItem);
          });
          div.appendChild(refBlock);
        }
      }
      chat.appendChild(div);
      if (doScroll) {
        var w = chat.closest('.chat-wrap');
        if (w) w.scrollTop = w.scrollHeight;
      }
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
        else addMsg('agent', data.reply, data.list_items || null, data.references || null);
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
    resp = render_template_string(HTML)
    session_id = request.args.get("session_id", "").strip()
    if session_id:
        from flask import make_response
        r = make_response(resp)
        r.set_cookie("harper_session", session_id, max_age=60 * 60 * 24)
        return r
    return resp


@app.route("/api/history", methods=["GET"])
def api_history():
    session_id = request.cookies.get("harper_session") or request.args.get("session_id", "").strip()
    if not session_id:
        return jsonify({"turns": []})
    state = get_session(session_id)
    turns = []
    for t in state.turn_history:
        turn = {"role": t.role, "message": t.message or ""}
        if getattr(t, "list_items", None):
            turn["list_items"] = t.list_items
        if getattr(t, "references", None):
            turn["references"] = t.references
        turns.append(turn)
    return jsonify({"turns": turns, "session_id": session_id})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    session_id = request.cookies.get("harper_session") or data.get("session_id") or create_session_id()
    if not message:
        return jsonify({"error": "Empty message", "reply": ""}), 400
    try:
        result = run_agent_loop(session_id, message)
        payload = {"reply": result["narrative"], "session_id": session_id}
        if result.get("list_items"):
            payload["list_items"] = result["list_items"]
        if result.get("references"):
            payload["references"] = result["references"]
        resp = jsonify(payload)
        resp.set_cookie("harper_session", session_id, max_age=60 * 60 * 24)
        return resp
    except Exception as e:
        return jsonify({"error": str(e), "reply": ""}), 500


if __name__ == "__main__":
    os.environ.setdefault("HARPER_MEMORY_ROOT", "memory")
    port = int(os.environ.get("PORT", 5050))
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print("Warning: GEMINI_API_KEY not set. Put it in .env in the project root and restart.")
    else:
        print("GEMINI_API_KEY loaded from .env")
    app.run(host="0.0.0.0", port=port, debug=True)
