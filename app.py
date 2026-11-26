"""Desktop app launcher for the agent controller.

Run from the project root:   python app.py

Starts the existing local controller server on a free port and shows it
in a native window (pywebview) instead of the system browser.
"""

import json
import os
import re
import threading
import sys
import subprocess
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from openai import OpenAI

from agent_controller import openai_agent
from agent_controller.claude_agent import _MODEL_PATTERN
from agent_controller.config import OPENAI_API_KEY, OPENAI_MODEL as DEFAULT_OPENAI_MODEL
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
.bub,.bub *,.h b,#diff,#diff div,#files{-webkit-user-select:text!important;user-select:text!important;cursor:text}
.h{cursor:pointer!important}
.cp{float:right;height:22px;padding:0 8px;margin-left:8px;font-size:11px;background:var(--btn);color:var(--btn-t);border:0;cursor:pointer!important}
#cbtn{margin-left:auto;height:30px;padding:0 12px;background:var(--btn);color:var(--btn-t);border:1px solid transparent;font-size:12px}
#cbtn+#themebtn{margin-left:8px}
#mbtn{margin-left:auto;height:30px;padding:0 12px;background:var(--btn);color:var(--btn-t);border:1px solid transparent;font-size:12px}
#mbtn+#cbtn{margin-left:8px}
.mf{display:block;margin:6px 0;font-size:12px;color:var(--mute)}
.mf input{display:block;width:100%;box-sizing:border-box;margin-top:3px;padding:6px 8px;background:var(--bg);color:var(--text);border:1px solid var(--line);border-radius:6px;font:12.5px ui-monospace,Consolas,monospace}
.mbar{display:flex;gap:8px;align-items:center;margin:12px 0 6px;flex-wrap:wrap}
#ov{position:fixed;inset:0;background:rgba(0,0,0,.55);display:none;align-items:center;justify-content:center;z-index:9}
#ov.on{display:flex}
#ovb{width:min(760px,92vw);max-height:80vh;overflow:auto;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 20px;-webkit-user-select:text;user-select:text}
.nx{margin-top:10px;padding-top:8px;border-top:1px solid var(--line);white-space:normal}
.nx b{display:block;font-size:12px;margin-bottom:4px}
.nxr{margin:6px 0}
.nxr small{display:flex!important;align-items:center;justify-content:space-between;color:var(--mute);margin:0 0 3px}
.nxr pre{margin:0;padding:6px 8px;background:var(--bg);border:1px solid var(--line);border-radius:6px;font:12px/1.5 ui-monospace,Consolas,monospace;white-space:pre-wrap;word-break:break-all}
.nxc{height:20px;padding:0 8px;font-size:11px;background:var(--btn);color:var(--btn-t);border:0;cursor:pointer!important}
.ci{padding:6px 0;border-bottom:1px solid var(--line);font:12.5px/1.5 ui-monospace,Consolas,monospace;white-space:pre-wrap;word-break:break-word}
"""

THEME_JS = r"""
(function(){
  var root=document.documentElement,T="__TOKEN__";
  var b=document.createElement("button");b.id="themebtn";b.type="button";
  var MOON='<svg viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>',
      SUN='<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
      NEXT={dark:"light",light:"dark"};
  function apply(t){root.setAttribute("data-theme",t);b.innerHTML=t==="dark"?MOON:SUN;
    b.title="Switch to "+NEXT[t]+" mode";b.setAttribute("aria-label",b.title);}
  document.querySelector("section h2").append(b);
  b.onclick=function(){
    var t=NEXT[root.getAttribute("data-theme")]||"dark";root.classList.add("tx");apply(t);setTimeout(function(){root.classList.remove("tx")},500);
    fetch("/api/theme",{method:"POST",headers:{"X-Token":T,"Content-Type":"application/json"},
      body:JSON.stringify({theme:t})});
  };
  apply("__THEME__");
  var ov=document.createElement("div");ov.id="ov";
  var box=document.createElement("div");box.id="ovb";ov.append(box);document.body.append(ov);
  ov.onclick=function(e){if(e.target===ov)ov.classList.remove("on")};
  function show(title,lines){
    box.textContent="";var h=document.createElement("h3");h.textContent=title;box.append(h);
    lines.forEach(function(l){var d=document.createElement("div");d.className="ci";d.textContent=l;box.append(d)});
    ov.classList.add("on");
  }
  function get(p){return fetch(p,{headers:{"X-Token":T}}).then(function(r){return r.json()})}
  var cb=document.createElement("button");cb.id="cbtn";cb.type="button";cb.textContent="Commits";
  cb.onclick=function(){get("/api/commits").then(function(c){show("Recent commits",c.error?[c.error]:c)})};
  document.querySelector("section h2").insertBefore(cb,b);
  var mb=document.createElement("button");mb.id="mbtn";mb.type="button";mb.textContent="Models";
  var PRESETS={"Cloud (.env defaults)":{planner:{model:"",base_url:""},proposer:{model:"",base_url:""}},
    "Local Qwen (Ollama)":{planner:{model:"qwen3-coder",base_url:"http://localhost:11434/v1"},
      proposer:{model:"qwen3-coder",base_url:"http://localhost:11434"}}};
  mb.onclick=function(){get("/api/models").then(function(m){
    if(m.error){show("Models",[m.error]);return}
    show("Models",[]);var inputs={};
    function field(role,key,label,ph){
      var l=document.createElement("label");l.className="mf";l.textContent=label;
      var i=document.createElement("input");i.value=(m.settings[role]||{})[key]||"";i.placeholder=ph;
      l.append(i);box.append(l);inputs[role+"."+key]=i;
    }
    [["planner","Planner (GPT role, OpenAI-compatible API)"],["proposer","Proposer (Claude CLI, Anthropic-compatible API)"]].forEach(function(r){
      var h=document.createElement("b");h.textContent=r[1];box.append(h);
      field(r[0],"model","Model (empty = .env default)",m.defaults[r[0]]);
      field(r[0],"base_url","Base URL (empty = cloud)",r[0]==="planner"?"http://localhost:11434/v1":"http://localhost:11434");
    });
    var bar=document.createElement("div");bar.className="mbar";var st=document.createElement("small");
    Object.keys(PRESETS).forEach(function(n){
      var p=document.createElement("button");p.type="button";p.className="nxc";p.textContent=n;
      p.onclick=function(){Object.keys(inputs).forEach(function(k){var a=k.split(".");inputs[k].value=PRESETS[n][a[0]][a[1]]})};
      bar.append(p);
    });
    var sv=document.createElement("button");sv.type="button";sv.className="nxc";sv.textContent="Save";
    sv.onclick=function(){
      var body={planner:{},proposer:{}};
      Object.keys(inputs).forEach(function(k){var a=k.split(".");body[a[0]][a[1]]=inputs[k].value.trim()});
      fetch("/api/models",{method:"POST",headers:{"X-Token":T,"Content-Type":"application/json"},body:JSON.stringify(body)})
        .then(function(r){return r.json()}).then(function(r){st.textContent=r.error?"Error: "+r.error:"Saved - used from the next agent call."},
          function(){st.textContent="Error: request failed"});
    };
    bar.append(sv,st);box.append(bar);
  })};
  document.querySelector("section h2").insertBefore(mb,cb);
  var hl=document.getElementById("histlist");
  hl.addEventListener("click",function(e){
    var el=e.target.closest(".h");if(!el)return;
    var i=Array.prototype.indexOf.call(hl.children,el);
    get("/api/history").then(function(h){var r=h[i];if(!r)return;
      show("Previous chat - "+r.time,["Task: "+r.task,"Outcome: "+r.outcome,"Summary: "+(r.summary||"-"),"Files: "+((r.files||[]).join(", ")||"-"),"Undo: "+(r.undo||"-")]);});
  });
  function addCopy(bub){
    if(bub.querySelector(".cp"))return;
    var c=document.createElement("button");c.className="cp";c.type="button";c.textContent="Copy";
    c.onclick=function(){
      var k=bub.cloneNode(true);k.querySelectorAll(".cp,small,.nx").forEach(function(n){n.remove()});
      var t=k.textContent;
      (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).catch(function(){
        var a=document.createElement("textarea");a.value=t;document.body.append(a);a.select();document.execCommand("copy");a.remove()});
      c.textContent="Copied";setTimeout(function(){c.textContent="Copy"},1200);
    };
    bub.insertBefore(c,bub.firstChild);
  }
  // ---- "Next steps" block under GPT reviews -------------------------
  function bodyText(el){
    var k=el.cloneNode(true);k.querySelectorAll(".cp,small,.nx").forEach(function(n){n.remove()});
    return k.textContent.trim();
  }
  function q(v){return "'"+String(v).replace(/'/g,"''")+"'"}  // PowerShell-safe single quotes
  function slug(t){
    var s=t.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"").slice(0,40).replace(/-+$/,"");
    return s||"change";
  }
  // Collect data for ONE task: walk back from the review to that task's own
  // "You" message. Nothing from earlier tasks is used.
  function taskData(msg){
    var d={task:"",summary:"",files:[],applied:false},n=msg.previousElementSibling;
    while(n){
      var b=n.querySelector(".bub");
      if(n.classList.contains("user")){d.task=b?bodyText(b):"";break}
      if(b&&n.classList.contains("result")){
        var t=bodyText(b);
        if(/^Patch applied/.test(t)){d.applied=true;
          var sec=t.split("Files changed:")[1]||"";sec=sec.split("To undo:")[0];
          sec.split("\n").forEach(function(l){var m=l.match(/^\s*-\s+(.+?)\s*$/);if(m)d.files.push(m[1])});}
      }
      if(b&&n.classList.contains("agent")&&n.querySelector(".av.Claude")&&!d.summary)
        d.summary=bodyText(b).split("\n")[0].trim();
      n=n.previousElementSibling;
    }
    return d;
  }
  function row(title,lines){
    var r=document.createElement("div");r.className="nxr";
    var h=document.createElement("small");var l=document.createElement("span");l.textContent=title;h.append(l);
    var c=document.createElement("button");c.type="button";c.className="nxc";c.textContent="Copy";
    var cmd=lines.join("\n");
    c.onclick=function(){
      (navigator.clipboard?navigator.clipboard.writeText(cmd):Promise.reject()).catch(function(){
        var a=document.createElement("textarea");a.value=cmd;document.body.append(a);a.select();document.execCommand("copy");a.remove()});
      c.textContent="Copied";setTimeout(function(){c.textContent="Copy"},1200);
    };
    h.append(c);var p=document.createElement("pre");p.textContent=cmd;r.append(h,p);return r;
  }
  function addNext(msg){
    if(msg.dataset.nx)return;msg.dataset.nx="1";
    var bub=msg.querySelector(".bub");if(!bub||!/^VERDICT:/.test(bodyText(bub)))return;
    var d=taskData(msg);if(!d.applied||!d.files.length)return;
    var summary=(d.summary||d.task||"update").replace(/\s+/g," ").slice(0,72);
    var msgArg=q("Agent: "+summary),br="agent/"+slug(d.task||summary);
    get("/api/branch").then(function(r){return r.branch||""},function(){return ""}).then(function(cur){
      var box=document.createElement("div");box.className="nx";
      var h=document.createElement("b");h.textContent="Next steps"+(cur?" (on branch "+cur+")":"");box.append(h);
      var commit=row("Commit everything",["git add -A","git commit -m "+msgArg]);
      var branch=row("Commit to a new branch",["git switch -c "+br,"git add -A","git commit -m "+msgArg,"git push -u origin "+br]);
      var undo=row("Undo this change (only while uncommitted)",["git restore -- "+d.files.map(q).join(" ")]);
      if(cur==="main"||cur==="master")box.append(branch,commit);else box.append(commit,branch);
      box.append(undo);bub.append(box);
    });
  }
  var chat=document.getElementById("chat");
  function decorate(){chat.querySelectorAll(".bub").forEach(addCopy);chat.querySelectorAll(".m.agent").forEach(addNext)}
  new MutationObserver(decorate).observe(chat,{childList:true});
  decorate();
})();
"""


def load_theme():
    try:
        theme = THEME_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "dark"
    return theme if theme in ("dark", "light") else "dark"


MODELS_FILE = Path.home() / ".agent_controller" / "models.json"
MODELS_LOCK = threading.Lock()
ROLES = ("planner", "proposer")
# The planner talks to an HTTP API, so vendor-style names such as
# "Qwen/Qwen3-Coder-30B" are allowed. The proposer name goes to the Claude CLI
# and reuses claude_agent's stricter pattern.
_PLANNER_MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/\[\]-]{0,127}")
_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]{1,200}")
# Values from the environment/.env at startup; restored when a role goes back to cloud.
_ENV_AT_START = {
    key: os.environ.get(key)
    for key in ("CLAUDE_MODEL", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN")
}
current_models = {role: {"model": "", "base_url": ""} for role in ROLES}


def clean_models(data):
    """Validate {"planner": {model, base_url}, "proposer": {...}}; empty means the .env default."""
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    result = {}
    for role in ROLES:
        entry = data.get(role) or {}
        if not isinstance(entry, dict):
            raise ValueError(f"{role}: expected an object")
        model = str(entry.get("model") or "").strip()
        base_url = str(entry.get("base_url") or "").strip().rstrip("/")
        pattern = _PLANNER_MODEL_PATTERN if role == "planner" else _MODEL_PATTERN
        if model and not pattern.fullmatch(model):
            raise ValueError(f"{role}: invalid model name")
        if base_url and not _URL_PATTERN.fullmatch(base_url):
            raise ValueError(f"{role}: base URL must start with http:// or https://")
        result[role] = {"model": model, "base_url": base_url}
    return result


def load_models():
    """Saved model choice from ~/.agent_controller/models.json (outside the repo)."""
    try:
        return clean_models(json.loads(MODELS_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return clean_models({})


def _set_env(key, value):
    if value:
        os.environ[key] = value
    else:
        os.environ.pop(key, None)


def apply_models(settings):
    """Point both agents at the chosen models; takes effect on the next agent call.

    API keys stay in .env. A base URL switches a role to another server:
    the planner to any OpenAI-compatible API (Ollama, vLLM, LM Studio),
    the proposer to an Anthropic-compatible API (e.g. Ollama) used by the
    Claude CLI. LOCAL_LLM_API_KEY is optional; local servers ignore the key.
    """
    local_key = os.getenv("LOCAL_LLM_API_KEY") or "local"
    planner, proposer = settings["planner"], settings["proposer"]

    # ask_gpt() reads these module globals on every call.
    openai_agent.OPENAI_MODEL = planner["model"] or DEFAULT_OPENAI_MODEL
    if planner["base_url"]:
        openai_agent.client = OpenAI(api_key=local_key, base_url=planner["base_url"])
    else:
        openai_agent.client = OpenAI(api_key=OPENAI_API_KEY)

    # ask_claude() runs the CLI with this process's environment; load_dotenv()
    # in get_claude_model() never overrides a value that is already set.
    _set_env("CLAUDE_MODEL", proposer["model"] or _ENV_AT_START["CLAUDE_MODEL"])
    if proposer["base_url"]:
        _set_env("ANTHROPIC_BASE_URL", proposer["base_url"])
        _set_env("ANTHROPIC_AUTH_TOKEN", local_key)
    else:
        _set_env("ANTHROPIC_BASE_URL", _ENV_AT_START["ANTHROPIC_BASE_URL"])
        _set_env("ANTHROPIC_AUTH_TOKEN", _ENV_AT_START["ANTHROPIC_AUTH_TOKEN"])
    current_models.update(settings)


class ThemedHandler(Handler):
    """Same server as web_ui, plus a saved light/dark theme and modern styling."""

    def _send(self, code, body, ctype="application/json"):
        if ctype == "text/html":
            js = THEME_JS.replace("__TOKEN__", TOKEN).replace("__THEME__", load_theme())
            body = body.replace("</head>", f"<style>{THEME_CSS}</style></head>", 1)
            body = body.replace("</body>", f"<script>{js}</script></body>", 1)
        super()._send(code, body, ctype)

    def do_GET(self):
        if self.path.split("?")[0] == "/api/models":
            if not self._local_only() or not self._authorized():
                return self._json({"error": "unauthorized"}, 401)
            with MODELS_LOCK:
                settings = {role: dict(entry) for role, entry in current_models.items()}
            return self._json({"settings": settings, "defaults": {
                "planner": DEFAULT_OPENAI_MODEL,
                "proposer": _ENV_AT_START["CLAUDE_MODEL"] or "Claude CLI default",
            }})
        if self.path.split("?")[0] == "/api/branch":
            if not self._local_only() or not self._authorized():
                return self._json({"error": "unauthorized"}, 401)
            try:
                branch = subprocess.run(
                    ["git", "branch", "--show-current"], cwd=PROJECT_ROOT,
                    capture_output=True, text=True, encoding="utf-8", timeout=15,
                ).stdout.strip()
            except (OSError, subprocess.SubprocessError) as error:
                return self._json({"error": f"git failed: {error}"}, 500)
            return self._json({"branch": branch})
        if self.path.split("?")[0] != "/api/commits":
            return super().do_GET()
        if not self._local_only() or not self._authorized():
            return self._json({"error": "unauthorized"}, 401)
        try:
            out = subprocess.run(
                ["git", "log", "-50", "--date=short", "--pretty=format:%h  %ad  %an  %s"],
                cwd=PROJECT_ROOT, capture_output=True, text=True,
                encoding="utf-8", timeout=15, check=True,
            ).stdout
        except (OSError, subprocess.SubprocessError) as error:
            return self._json({"error": f"git log failed: {error}"}, 500)
        self._json(out.splitlines())

    def do_POST(self):
        if self.path == "/api/models":
            return self._post_models()
        if self.path != "/api/theme":
            return super().do_POST()
        if not self._local_only() or not self._authorized():
            return self._json({"error": "unauthorized"}, 401)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            theme = json.loads(self.rfile.read(length) or b"{}").get("theme")
        except (ValueError, AttributeError):
            return self._json({"error": "bad json"}, 400)
        if theme not in ("dark", "light"):
            return self._json({"error": "bad theme"}, 400)
        THEME_FILE.parent.mkdir(parents=True, exist_ok=True)
        THEME_FILE.write_text(theme, encoding="utf-8")
        self._json({"ok": True})

    def _post_models(self):
        if not self._local_only() or not self._authorized():
            return self._json({"error": "unauthorized"}, 401)
        length = int(self.headers.get("Content-Length") or 0)
        try:
            settings = clean_models(json.loads(self.rfile.read(length) or b"{}"))
        except ValueError as error:
            return self._json({"error": str(error)}, 400)
        with MODELS_LOCK:
            apply_models(settings)
            MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
            MODELS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        self._json({"ok": True, "settings": settings})


def main():
    try:
        import webview
    except ImportError:
        raise SystemExit("pywebview is missing. Run: pip install -r requirements.txt")

    apply_models(load_models())

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
        f"Agent World - {PROJECT_ROOT.name}", url, width=1280, height=820, text_select=True
    )
    try:
        webview.start()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
