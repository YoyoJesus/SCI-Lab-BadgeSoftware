"""Second observer on a phone or another computer, served over the local network.

The PC timestamps every tap when it arrives, so both observers share the PC clock.
If the page loses focus or stops checking in, its labels become unknown.
"""
from datetime import datetime, timezone
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import socket
import threading
import time
from typing import Optional

from ground_truth import IntervalRecorder

CHECKPOINT_SECONDS = .2
HEARTBEAT_SECONDS = 3.0


def lan_address() -> str:
    """Best guess at this PC's address on the local network; no packets are sent."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(('10.255.255.255', 1))
        return probe.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        probe.close()


class RemoteObserver:
    def __init__(self, output: Path, recording_id: str, badges: list[str], host: str = '0.0.0.0',
                 port: int = 8765, heartbeat_seconds: float = HEARTBEAT_SECONDS) -> None:
        self.badges = list(badges)
        self.recorder = IntervalRecorder(output, recording_id, self.badges, datetime.now(timezone.utc))
        self.code = f'{secrets.randbelow(10 ** 6):06d}'
        self.recording_id = recording_id
        self.heartbeat_seconds = heartbeat_seconds
        self.lock = threading.Lock()
        self.paused = True
        self.labels = dict.fromkeys(self.badges, 'unknown')
        self.last_seen = time.monotonic()
        self.closed = False
        self.error: Optional[str] = None
        try:
            try:
                self.server = ThreadingHTTPServer((host, port), self.handler())
            except OSError:
                if port == 0:
                    raise
                self.server = ThreadingHTTPServer((host, 0), self.handler())
        except OSError:
            self.recorder.close(datetime.now(timezone.utc))
            raise
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.url = f'http://{lan_address() if host == "0.0.0.0" else host}:{self.port}/{self.code}'
        self.stop = threading.Event()
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self.checkpoint, daemon=True).start()

    def save(self) -> None:
        try:
            self.recorder.change(dict(self.labels), datetime.now(timezone.utc))
        except (ValueError, OSError) as error:
            self.error = str(error)
            self.closed = True

    def state(self) -> dict:
        return {'recording_id': self.recording_id, 'badges': self.badges, 'paused': self.paused,
                'labels': dict(self.labels), 'closed': self.closed}

    def act(self, action: str, badge: Optional[str] = None) -> dict:
        with self.lock:
            if self.closed:
                raise ValueError('Observer session has ended')
            self.last_seen = time.monotonic()
            if action in ['start', 'silence']:
                self.paused = False
                self.labels = dict.fromkeys(self.badges, 'not_active')
            elif action == 'pause':
                self.paused = True
                self.labels = dict.fromkeys(self.badges, 'unknown')
            elif action == 'toggle' and badge in self.labels and not self.paused:
                self.labels[badge] = 'not_active' if self.labels[badge] == 'active' else 'active'
            elif action == 'unknown' and badge in self.labels and not self.paused:
                self.labels[badge] = 'unknown'
            else:
                raise ValueError('Invalid action')
            self.save()
            return self.state()

    def heartbeat(self) -> dict:
        with self.lock:
            self.last_seen = time.monotonic()
            return self.state()

    def checkpoint(self) -> None:
        while not self.stop.wait(CHECKPOINT_SECONDS):
            with self.lock:
                if self.closed:
                    return
                if not self.paused and time.monotonic() - self.last_seen > self.heartbeat_seconds:
                    self.paused = True
                    self.labels = dict.fromkeys(self.badges, 'unknown')
                self.save()

    def close(self) -> None:
        self.stop.set()
        with self.lock:
            if not self.recorder.closed:
                self.closed = True
                try:
                    self.recorder.close(datetime.now(timezone.utc))
                except (ValueError, OSError) as error:
                    self.error = str(error)
        self.server.shutdown()
        self.server.server_close()

    def handler(self) -> type:
        observer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: object) -> None:
                pass

            def route(self) -> Optional[str]:
                parts = self.path.split('?')[0].strip('/').split('/')
                if not parts or not hmac.compare_digest(parts[0], observer.code):
                    self.send_error(404)
                    return None
                return '/'.join(parts[1:])

            def reply(self, status: int, body: bytes, kind: str) -> None:
                self.send_response(status)
                self.send_header('Content-Type', kind)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                route = self.route()
                if route == '':
                    self.reply(200, PAGE.encode('utf-8'), 'text/html; charset=utf-8')
                elif route == 'state':
                    self.reply(200, json.dumps(observer.heartbeat()).encode(), 'application/json')
                elif route is not None:
                    self.send_error(404)

            def do_POST(self) -> None:
                route = self.route()
                if route is None:
                    return None
                if route != 'action':
                    return self.send_error(404)
                length = int(self.headers.get('Content-Length') or 0)
                if not 0 < length <= 1024:
                    return self.send_error(400)
                try:
                    body = json.loads(self.rfile.read(length))
                    badge = body.get('badge')
                    state = observer.act(str(body.get('action')), str(badge) if badge is not None else None)
                except (ValueError, AttributeError):
                    return self.send_error(400)
                self.reply(200, json.dumps(state).encode(), 'application/json')

        return Handler


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Second observer</title>
<style>
:root { --bg:#f6f6f4; --fg:#1d1d1b; --muted:#66655f; --card:#fff; --line:#d9d8d2; --on:#1f6f43; --onfg:#fff; --warn:#8a5a00; }
@media (prefers-color-scheme: dark) { :root { --bg:#161615; --fg:#ecebe6; --muted:#a3a29b; --card:#22221f; --line:#3a3935; --on:#2f9b60; --onfg:#fff; --warn:#e0a640; } }
* { box-sizing:border-box; }
body { margin:0; padding:32px 16px; font:16px/1.4 system-ui, sans-serif; background:var(--bg); color:var(--fg); }
main { max-width:720px; margin:0 auto; }
h1 { font-size:20px; margin:0 0 4px; }
#status { color:var(--muted); margin:0 0 16px; min-height:2.8em; }
#status.warn { color:var(--warn); }
.badges { display:grid; gap:10px; margin-bottom:16px; }
button { font:inherit; border:1px solid var(--line); border-radius:10px; background:var(--card); color:var(--fg); padding:14px; }
button:disabled { opacity:.45; }
.badge { display:grid; grid-template-columns:2.2em 1fr auto; align-items:center; gap:12px; width:100%; min-height:56px; font-size:18px; text-align:left; }
.key { font:600 14px ui-monospace, monospace; border:1px solid currentColor; border-radius:6px; padding:2px 0; text-align:center; opacity:.7; }
kbd { font:600 13px ui-monospace, monospace; border:1px solid var(--line); border-radius:4px; padding:1px 5px; }
.badge.active { background:var(--on); color:var(--onfg); border-color:var(--on); }
.badge.unknown .state { font-style:italic; }
.row { display:flex; gap:10px; flex-wrap:wrap; }
.row button { flex:1 1 30%; }
p.help { color:var(--muted); font-size:14px; }
</style></head><body>
<main>
<h1>Who is speaking?</h1>
<p id="status">Connecting...</p>
<div class="badges" id="badges"></div>
<div class="row">
  <button id="start">Start (Enter)</button>
  <button id="pause">Pause (Space)</button>
  <button id="silence">Silence (0)</button>
</div>
<p class="help">Tap or click a badge, or press <kbd>1</kbd> to <kbd>9</kbd>, to switch it between speaking and quiet.
Several people can speak at once. Pause when you cannot judge everyone.
Switching windows, tabs, or apps pauses labeling, and so does losing contact with the recording PC for 3 s.</p>
</main>
<script>
const base = location.pathname.replace(/\\/$/, '');
const list = document.getElementById('badges'), status = document.getElementById('status');
let buttons = {}, failures = 0;
function render(s) {
  if (!Object.keys(buttons).length) {
    s.badges.forEach((badge, i) => {
      const b = document.createElement('button');
      b.className = 'badge';
      const key = document.createElement('span'); key.className = 'key'; key.textContent = i + 1;
      const name = document.createElement('span'); name.textContent = badge;
      const state = document.createElement('span'); state.className = 'state';
      b.append(key, name, state);
      b.onclick = () => send({action: 'toggle', badge});
      list.append(b); buttons[badge] = b;
    });
  }
  for (const [badge, label] of Object.entries(s.labels)) {
    const b = buttons[badge];
    b.classList.toggle('active', label === 'active');
    b.classList.toggle('unknown', label === 'unknown');
    b.lastChild.textContent = label === 'active' ? 'Speaking' : label === 'not_active' ? 'Quiet' : 'Unknown';
    b.disabled = s.paused || s.closed;
  }
  document.getElementById('start').disabled = !s.paused || s.closed;
  document.getElementById('pause').disabled = s.paused || s.closed;
  document.getElementById('silence').disabled = s.closed;
  status.classList.toggle('warn', s.paused || s.closed);
  status.textContent = s.closed ? 'This observer session has ended.' :
    s.paused ? 'Paused. Press Enter when you can see and hear every wearer.' :
    'Observing ' + s.recording_id + '. Mark each wearer as soon as they start or stop talking.';
}
async function call(path, body) {
  const r = await fetch(base + path, body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {cache: 'no-store'});
  if (!r.ok) throw new Error(r.status);
  failures = 0; current = await r.json(); render(current);
}
function send(body) { call('/action', body).catch(lost); }
function lost() { if (++failures > 1) { status.classList.add('warn'); status.textContent = 'Lost contact with the PC. Your labels are unknown until it reconnects.'; } }
document.getElementById('start').onclick = () => send({action: 'start'});
document.getElementById('pause').onclick = () => send({action: 'pause'});
document.getElementById('silence').onclick = () => send({action: 'silence'});
let current = null;
const held = new Set();
document.addEventListener('keydown', e => {
  if (!current || held.has(e.key)) return;
  const index = Number(e.key) - 1;
  if (e.key === 'Enter' && current.paused) send({action: 'start'});
  else if (e.key === ' ') send({action: 'pause'});
  else if (e.key === '0') send({action: 'silence'});
  else if (index >= 0 && index < current.badges.length) send({action: 'toggle', badge: current.badges[index]});
  else return;
  held.add(e.key); e.preventDefault();
});
document.addEventListener('keyup', e => held.delete(e.key));
function away() { held.clear(); if (current && !current.paused) send({action: 'pause'}); }
window.addEventListener('blur', away);
document.addEventListener('visibilitychange', () => { if (document.hidden) away(); });
setInterval(() => call('/state').catch(lost), 1000);
call('/state').catch(lost);
</script></body></html>
"""
