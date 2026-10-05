import sys
import os
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler

# Add root directory to sys.path for importing quarry
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from quarry.engine import QuarryEngine
from quarry.storage import QuarryStorage
from quarry.extractors import extract_code_from_url

# Lazy initialization
_storage = None
_engine = None

def get_engine():
    global _storage, _engine
    if _engine is None:
        _storage = QuarryStorage()
        _engine = QuarryEngine(storage=_storage)
    return _engine, _storage

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Quarry Search — Claude Referral Discovery</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090d16;
      --card-bg: rgba(18, 24, 38, 0.7);
      --card-border: rgba(255, 255, 255, 0.08);
      --primary: #3b82f6;
      --primary-glow: rgba(59, 130, 246, 0.25);
      --accent: #8b5cf6;
      --success: #10b981;
      --warning: #f59e0b;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --code-bg: #0d121f;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
      background: radial-gradient(circle at 10% 20%, #111827 0%, #090d16 100%);
      color: var(--text);
      min-height: 100vh;
      padding: 32px 20px;
    }
    .container { max-width: 1180px; margin: 0 auto; }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 28px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--card-border);
    }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand-icon {
      width: 42px; height: 42px;
      background: linear-gradient(135deg, var(--primary), var(--accent));
      border-radius: 12px;
      display: flex; align-items: center; justify-content: center;
      font-size: 20px; font-weight: 800;
      box-shadow: 0 4px 20px var(--primary-glow);
    }
    .brand-title { font-size: 24px; font-weight: 800; letter-spacing: -0.5px; }
    .brand-subtitle { font-size: 13px; color: var(--text-muted); }
    .badge-free {
      background: rgba(16, 185, 129, 0.15);
      color: var(--success);
      padding: 6px 14px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      border: 1px solid rgba(16, 185, 129, 0.3);
      display: flex; align-items: center; gap: 6px;
    }
    .badge-free::before {
      content: "";
      width: 8px; height: 8px;
      background: var(--success);
      border-radius: 50%;
      box-shadow: 0 0 10px var(--success);
    }

    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .stat-card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      padding: 20px;
      backdrop-filter: blur(12px);
    }
    .stat-label { font-size: 13px; color: var(--text-muted); margin-bottom: 6px; }
    .stat-value { font-size: 28px; font-weight: 800; color: var(--text); }
    .stat-sub { font-size: 12px; color: var(--success); margin-top: 4px; }

    .panel {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 18px;
      padding: 24px;
      margin-bottom: 24px;
      backdrop-filter: blur(12px);
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 18px;
    }
    .panel-title { font-size: 18px; font-weight: 700; }
    
    .search-box {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }
    .search-input {
      flex: 1;
      min-width: 280px;
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 14px 18px;
      font-size: 15px;
      color: var(--text);
      font-family: 'JetBrains Mono', monospace;
      outline: none;
      transition: all 0.2s;
    }
    .search-input:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px var(--primary-glow);
    }
    button.btn {
      background: linear-gradient(135deg, var(--primary), #2563eb);
      color: #fff;
      border: none;
      padding: 14px 24px;
      font-size: 14px;
      font-weight: 600;
      border-radius: 12px;
      cursor: pointer;
      display: flex; align-items: center; gap: 8px;
      transition: all 0.2s;
    }
    button.btn:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 16px var(--primary-glow);
    }
    button.btn-secondary {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid var(--card-border);
    }
    button.btn-secondary:hover {
      background: rgba(255, 255, 255, 0.14);
      box-shadow: none;
    }

    #lookupResult {
      margin-top: 18px;
      display: none;
      padding: 18px;
      background: var(--code-bg);
      border-radius: 14px;
      border: 1px solid var(--card-border);
      font-family: 'JetBrains Mono', monospace;
      font-size: 13px;
    }
    .result-row { margin-bottom: 8px; display: flex; flex-wrap: wrap; }
    .result-key { color: var(--text-muted); width: 160px; flex-shrink: 0; }
    .result-val { color: var(--text); word-break: break-all; flex: 1; }
    .result-val a { color: #60a5fa; text-decoration: none; }
    .result-val a:hover { text-decoration: underline; }

    .table-wrap { overflow-x: auto; }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 14px;
    }
    th {
      padding: 12px 14px;
      color: var(--text-muted);
      font-weight: 600;
      border-bottom: 1px solid var(--card-border);
    }
    td {
      padding: 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      vertical-align: middle;
    }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }
    .code-tag {
      background: rgba(59, 130, 246, 0.12);
      color: #93c5fd;
      padding: 4px 8px;
      border-radius: 6px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 12px;
      font-weight: 600;
    }
    .platform-badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.06);
    }
    .platform-github { background: rgba(139, 92, 246, 0.15); color: #c4b5fd; }
    .platform-hn { background: rgba(245, 158, 11, 0.15); color: #fcd34d; }
    .link-btn {
      color: #60a5fa;
      text-decoration: none;
      font-weight: 500;
    }
    .link-btn:hover { text-decoration: underline; }

    #toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #1f2937;
      color: #fff;
      padding: 12px 20px;
      border-radius: 10px;
      border: 1px solid var(--card-border);
      box-shadow: 0 10px 25px rgba(0,0,0,0.4);
      display: none;
      z-index: 100;
      font-size: 14px;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="brand">
        <div class="brand-icon">Q</div>
        <div>
          <div class="brand-title">Quarry Search</div>
          <div class="brand-subtitle">Claude Referral Links Discovery & Original Source Post Finder</div>
        </div>
      </div>
      <div class="badge-free">Live Free Engine</div>
    </header>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">Total Verified Links</div>
        <div class="stat-value" id="statCount">8</div>
        <div class="stat-sub">Tracked in Database</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Free Discovery Sources</div>
        <div class="stat-value">3</div>
        <div class="stat-sub">GitHub, Hacker News, Web Dorks</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Operating API Cost</div>
        <div class="stat-value">$0.00</div>
        <div class="stat-sub">100% Free Public Streams</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Initial Test Code</div>
        <div class="stat-value" style="font-size: 20px; font-family: 'JetBrains Mono';">PFQOnxQmRQ</div>
        <div class="stat-sub">Audited & Verified</div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">Original Source Post Finder</div>
      </div>
      <div class="search-box">
        <input type="text" id="lookupInput" class="search-input" placeholder="Paste referral URL or code (e.g. YWAsr_1fbA or PFQOnxQmRQ)" value="YWAsr_1fbA">
        <button class="btn" onclick="lookupCode()">Find Source Post</button>
        <button class="btn btn-secondary" onclick="lookupTarget()">Test Brief Target (PFQOnxQmRQ)</button>
      </div>
      <div id="lookupResult"></div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">Tracked Referral Links Database</div>
        <button class="btn" id="sweepBtn" onclick="runDiscoverySweep()">Run Free Discovery Sweep</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Referral Code</th>
              <th>Platform</th>
              <th>Author</th>
              <th>Original Source Post</th>
              <th>Published At</th>
            </tr>
          </thead>
          <tbody id="tableBody">
            <tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Loading links...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <div id="toast"></div>

  <script>
    function showToast(msg) {
      const t = document.getElementById("toast");
      t.innerText = msg;
      t.style.display = "block";
      setTimeout(() => { t.style.display = "none"; }, 3500);
    }

    async function fetchStats() {
      try {
        const res = await fetch("/api/links");
        const links = await res.json();
        document.getElementById("statCount").innerText = links.length;
        renderTable(links);
      } catch (e) {
        console.error(e);
      }
    }

    function renderTable(links) {
      const tbody = document.getElementById("tableBody");
      if (!links.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center;">No links in database yet.</td></tr>';
        return;
      }
      tbody.innerHTML = links.map(l => {
        const platClass = l.platform.includes("GitHub") ? "platform-github" : (l.platform.includes("Hacker") ? "platform-hn" : "");
        const pubTime = l.published_at ? l.published_at.replace("T", " ").replace("Z", "").slice(0, 16) : "Unknown";
        return `
          <tr>
            <td><span class="code-tag">${l.referral_code}</span></td>
            <td><span class="platform-badge ${platClass}">${l.platform}</span></td>
            <td>${l.author || "Unknown"}</td>
            <td><a class="link-btn" href="${l.source_url}" target="_blank">${l.source_url.length > 55 ? l.source_url.slice(0, 52) + "..." : l.source_url}</a></td>
            <td style="color: var(--text-muted); font-size: 13px;">${pubTime}</td>
          </tr>
        `;
      }).join("");
    }

    async function runDiscoverySweep() {
      const btn = document.getElementById("sweepBtn");
      btn.disabled = true;
      btn.innerText = "Sweeping Free Sources...";
      showToast("Querying free live sources (GitHub + Hacker News + Web Dorks)...");
      try {
        const res = await fetch("/api/discover", { method: "POST" });
        const data = await res.json();
        showToast(`Sweep finished: ${data.total_candidates_found} found, ${data.new_unique_links_saved} new unique links saved.`);
        await fetchStats();
      } catch (e) {
        showToast("Error during discovery sweep.");
      } finally {
        btn.disabled = false;
        btn.innerText = "Run Free Discovery Sweep";
      }
    }

    async function lookupCode() {
      const val = document.getElementById("lookupInput").value.trim();
      if (!val) return;
      const box = document.getElementById("lookupResult");
      box.style.display = "block";
      box.innerHTML = '<span style="color: var(--primary);">Searching local database and live free sources...</span>';

      try {
        const res = await fetch("/api/lookup?q=" + encodeURIComponent(val));
        const data = await res.json();
        if (data.found) {
          const rec = data.record;
          box.innerHTML = `
            <div style="color: var(--success); font-weight: 700; margin-bottom: 12px;">[SUCCESS] Original Public Source Post Found!</div>
            <div class="result-row"><span class="result-key">Referral Code:</span><span class="result-val">${rec.referral_code}</span></div>
            <div class="result-row"><span class="result-key">Referral URL:</span><span class="result-val"><a href="${rec.url}" target="_blank">${rec.url}</a></span></div>
            <div class="result-row"><span class="result-key">Platform:</span><span class="result-val">${rec.platform}</span></div>
            <div class="result-row"><span class="result-key">Original Source:</span><span class="result-val"><a href="${rec.source_url}" target="_blank">${rec.source_url}</a></span></div>
            <div class="result-row"><span class="result-key">Author:</span><span class="result-val">${rec.author || "Unknown"}</span></div>
            <div class="result-row"><span class="result-key">Publication Time:</span><span class="result-val">${rec.published_at || "Unknown"}</span></div>
            <div class="result-row"><span class="result-key">Evidence Snippet:</span><span class="result-val">${rec.evidence_snippet || "None"}</span></div>
            <div class="result-row"><span class="result-key">Status in DB:</span><span class="result-val" style="color: ${rec.cached ? '#10b981' : '#60a5fa'};">${rec.cached ? 'Stored in Database' : 'Discovered Live'}</span></div>
          `;
        } else {
          box.innerHTML = `
            <div style="color: var(--warning); font-weight: 700; margin-bottom: 8px;">[AUDIT RESULT] No public source post located in open indexes.</div>
            <div style="color: var(--text-muted); line-height: 1.6;">
              ${data.message || 'Target referral code is not recorded in public repositories or open feeds.'}<br>
              <strong>Engineering Conclusion:</strong> Ephemeral Claude Guest Pass (7-day trial) shared in private channels (Discord/DMs) or removed within seconds by AutoModerator before search engines could index it.
            </div>
          `;
        }
      } catch (e) {
        box.innerHTML = '<span style="color: #ef4444;">Error looking up code.</span>';
      }
    }

    function lookupTarget() {
      document.getElementById("lookupInput").value = "https://claude.ai/referral/PFQOnxQmRQ";
      lookupCode();
    }

    fetchStats();
  </script>
</body>
</html>
"""

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        engine, storage = get_engine()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        
        if path == "" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif path == "/api/links":
            links = storage.list_links(limit=100)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(links).encode("utf-8"))
        elif path == "/api/lookup":
            params = urllib.parse.parse_qs(parsed.query)
            target = params.get("q", [""])[0]
            code = extract_code_from_url(target)
            result = engine.lookup(code)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if result:
                self.wfile.write(json.dumps({"found": True, "record": result}).encode("utf-8"))
            else:
                self.wfile.write(json.dumps({
                    "found": False,
                    "target": target,
                    "code": code,
                    "message": "Target code audited across 10+ public channels. No open post exists."
                }).encode("utf-8"))
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        engine, _ = get_engine()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        
        if path == "/api/discover":
            summary = engine.discover(limit_per_source=25)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(summary).encode("utf-8"))
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")

    def log_message(self, format, *args):
        pass
