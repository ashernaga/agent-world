"""Desktop app launcher for the agent controller.

Run from the project root:   python app.py

Starts the existing local controller server on a free port and shows it
in a native window (pywebview) instead of the system browser.
"""

import json
import threading
import sys
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from agent_controller.web_ui import HOST, PROJECT_ROOT, TOKEN, Handler


THEME_FILE = Path.home() / ".agent_controller" / "theme.txt"

# Look & feel injected into the existing page (the page itself is untouched).
# Dark is the default; the light palette overrides the same CSS variables.
THEME_CSS = """
:root{--accent:#4f7cff;--accent-h:#6b92ff;--r:8px;--btn:#3a4254;--btn-h:#465068;--btn-t:#e6e8ee}
:root[data-theme=light]{--bg:#f4f5f8;--panel:#fff;--line:#e2e5ec;--text:#1b1f29;
  --mute:#667085;--add:#dcf5e5;--del:#fde3e3;--ok:#16a068;--bad:#d64545;--ctl:#7b8498;--btn:#6b7488;--btn-h:#5a6377;--btn-t:#fff}
:root[data-theme=light] .h{background:#f1f3f7}
:root[data-theme=light] .tag,:root[data-theme=light] .dot{background:#e3e6ee}
:root[data-theme=light] .tag.applied{background:#dcf5e5}
:root[data-theme=light] .tag.rejected{background:#fdeccf;color:#a76100}
:root[data-theme=light] .hh{color:#2b5be0}
body{font-size:13.5px}
h2{display:flex;align-items:center;gap:8px;height:52px;padding:0 18px;font-size:13px;
  font-weight:600;letter-spacing:0;text-transform:none;color:var(--text);background:var(--panel)}
h2::before{content:"";width:3px;height:16px;border-radius:2px;background:var(--accent)}
#diffwrap h2{border-top:1px solid var(--line)}
button{border-radius:var(--r);font-weight:500;transition:background .15s,border-color .15s,opacity .15s}
#send,#ok,#no,#themebtn{background:var(--btn);color:var(--btn-t);border:1px solid transparent}
#send:hover:not(:disabled),#ok:hover,#no:hover,#themebtn:hover{background:var(--btn-h)}
#send{padding:0 22px}
#act button{height:38px}
textarea{border-radius:var(--r)}textarea:focus{outline:2px solid var(--accent);outline-offset:-1px}
.bub{border-radius:10px}
#themebtn{margin-left:auto;width:34px;height:30px;padding:0;display:inline-flex;align-items:center;justify-content:center}
#themebtn svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
:root.tx,:root.tx *{transition:background-color .45s ease,color .45s ease,border-color .45s ease}
"""

THEME_JS = """
(function(){
  var root=document.documentElement,T="__TOKEN__";
  var b=document.createElement("button");b.id="themebtn";b.type="button";
  var MOON='<svg viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>',
      SUN='<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  function apply(t){root.setAttribute("data-theme",t);b.innerHTML=t==="dark"?MOON:SUN;
    b.title="Switch to "+(t==="dark"?"light":"dark")+" mode";b.setAttribute("aria-label",b.title);}
  document.querySelector("section h2").append(b);
  b.onclick=function(){
    var t=root.getAttribute("data-theme")==="dark"?"light":"dark";root.classList.add("tx");apply(t);setTimeout(function(){root.classList.remove("tx")},500);
    fetch("/api/theme",{method:"POST",headers:{"X-Token":T,"Content-Type":"application/json"},
      body:JSON.stringify({theme:t})});
  };
  apply("__THEME__");
})();
"""


def load_theme():
    try:
        theme = THEME_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "dark"
    return theme if theme in ("dark", "light") else "dark"


class ThemedHandler(Handler):
    """Same server as web_ui, plus a saved light/dark theme and modern styling."""

    def _send(self, code, body, ctype="application/json"):
        if ctype == "text/html":
            js = THEME_JS.replace("__TOKEN__", TOKEN).replace("__THEME__", load_theme())
            body = body.replace("</head>", f"<style>{THEME_CSS}</style></head>", 1)
            body = body.replace("</body>", f"<script>{js}</script></body>", 1)
        super()._send(code, body, ctype)

    def do_POST(self):
        if self.path != "/api/theme":
            return super().do_POST()
        if not self._local_only() or not self._authorized():
            return self._json({"error": "unauthorized"}, 401)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            theme = json.loads(self.rfile.read(length) or b"{}").get("theme")
        except ValueError:
            return self._json({"error": "bad json"}, 400)
        if theme not in ("dark", "light"):
            return self._json({"error": "bad theme"}, 400)
        THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
        THEME_FILE.write_text(theme, encoding="utf-8")
        self._json({"ok": True})


def main():
    try:
        import webview
    except ImportError:
        raise SystemExit("pywebview is missing. Run: pip install -r requirements.txt")

    # Port 0 = let the OS pick a free port, so the app never clashes with
    # a running web_ui instance.
    server = ThreadingHTTPServer((HOST, 0), ThemedHandler)
    url = f"http://{HOST}:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    if "--smoke" in sys.argv:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                print(f"smoke test OK: {url} -> HTTP {resp.status}")
        finally:
            server.shutdown()
            server.server_close()
        return

    webview.create_window(
        f"Agent World - {PROJECT_ROOT.name}", url, width=1280, height=820
    )
    try:
        webview.start()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
