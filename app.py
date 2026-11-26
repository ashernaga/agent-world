"""Desktop app launcher for the agent controller.

Run:   python app.py [--project PATH] [--console] [--smoke]

Starts the existing local controller server on a free port and shows it
in a native window (pywebview) instead of the system browser. The window
runs in the background, so the terminal is free again right away.
--project points the agents at another Git repository (default: the
current folder), so the controller files never need to be copied there.
"""

import argparse
import json
import os
import re
import threading
import sys
import subprocess
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from openai import OpenAI

from agent_controller import claude_agent, openai_agent, patch_applier, proposal, web_ui
from agent_controller.claude_agent import _MODEL_PATTERN
from agent_controller.config import OPENAI_API_KEY, OPENAI_MODEL as DEFAULT_OPENAI_MODEL
from agent_controller.web_ui import HOST, TOKEN, Handler


THEME_FILE = Path.home() / ".agent_controller" / "theme.txt"
LOG_FILE = Path.home() / ".agent_controller" / "app.log"

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
#ubtn{margin-left:auto;height:30px;padding:0 12px;background:var(--btn);color:var(--btn-t);border:1px solid transparent;font-size:12px}
#ubtn+#mbtn{margin-left:8px}
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
.uh{display:block;margin:12px 0 4px;font-size:12.5px}
.ut{width:100%;margin-bottom:6px;border-collapse:collapse;font:12px/1.5 ui-monospace,Consolas,monospace}
.ut th,.ut td{padding:3px 6px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
.ut .n{text-align:right}
#fsbtn{margin-left:8px;width:34px;height:30px;padding:0;display:inline-flex;align-items:center;justify-content:center;background:var(--btn);color:var(--btn-t);border:1px solid transparent}
#fsbtn:hover{background:var(--btn-h)}
#fsbtn svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
#room{position:relative;flex:none;height:136px;overflow:hidden;border-bottom:1px solid var(--line);
  background:linear-gradient(to bottom,#151a26 0,#151a26 52%,transparent 52%),
  repeating-linear-gradient(90deg,#1c2232 0 16px,#20273a 16px 32px);transition:height .25s}
:root[data-theme=light] #room{background:linear-gradient(to bottom,#e8ecf6 0,#e8ecf6 52%,transparent 52%),
  repeating-linear-gradient(90deg,#d6dceb 0 16px,#dde2ef 16px 32px)}
#room.min{height:26px}
#room.min .npc,#room.min .prop{display:none}
#room .rt{position:absolute;left:12px;top:6px;font-size:11px;color:var(--mute);letter-spacing:.04em}
#room .rb{position:absolute;right:8px;top:4px;height:20px;padding:0 8px;font-size:11px;background:var(--btn);color:var(--btn-t);border:0}
#room .prop{position:absolute;bottom:30px;transform:translateX(-50%);image-rendering:pixelated}
.npc{position:absolute;bottom:22px;width:42px;height:45px;transform:translateX(-50%);will-change:left}
.npc svg{display:block;width:42px;height:45px;shape-rendering:crispEdges}
.npc .f2{display:none}.npc.step .f1{display:none}.npc.step .f2{display:block}
.npc .flip{transform:scaleX(-1)}
.npc .tag{position:absolute;left:50%;top:46px;transform:translateX(-50%);font-size:9.5px;color:var(--mute);white-space:nowrap}
.npc .say{position:absolute;left:50%;bottom:52px;transform:translateX(-50%);padding:3px 8px;border-radius:8px;
  background:var(--panel);border:1px solid var(--line);color:var(--text);font-size:11px;white-space:nowrap;display:none}
.npc .say::after{content:"";position:absolute;left:50%;bottom:-5px;margin-left:-4px;border:4px solid transparent;border-top-color:var(--line);border-bottom:0}
.npc.talk .say{display:block}
.npc.busy svg{animation:bob .6s ease-in-out infinite}
.npc.jump svg{animation:hop .45s ease-out 3}
.npc.sad svg{animation:shake .35s linear 2}
@keyframes bob{50%{transform:translateY(-2px)}}
@keyframes hop{40%{transform:translateY(-12px)}}
@keyframes shake{25%{transform:translateX(-2px)}75%{transform:translateX(2px)}}
@media (prefers-reduced-motion:reduce){.npc svg{animation:none!important}}
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
  // ---- Token usage per agent call, grouped by task --------------------
  function fmt(n){return n==null?"-":Number(n).toLocaleString("en-US")}
  var ub=document.createElement("button");ub.id="ubtn";ub.type="button";ub.textContent="Tokens";
  ub.title="Token usage per request";
  function usageLabel(u){if(u&&u.totals)ub.textContent="Tokens: "+fmt(u.totals.total)}
  function refreshUsage(){get("/api/usage").then(usageLabel,function(){})}
  ub.onclick=function(){get("/api/usage").then(function(u){
    if(u.error){show("Token usage",[u.error]);return}
    usageLabel(u);
    var t=u.totals,cost=t.cost?" | Claude CLI cost $"+t.cost.toFixed(4):"";
    show("Token usage",["Session total: input "+fmt(t.input)+" | output "+fmt(t.output)+" | total "+fmt(t.total)+cost,
      u.rows.length?"Counts are kept until the app is closed; '-' means the server did not report usage.":"No agent calls yet in this session."]
      .concat(u.dropped>0?["The list shows the last "+u.rows.length+" calls; the "+u.dropped+" older calls are still counted in the total."]:[]));
    var groups=[];
    u.rows.forEach(function(r){var g=groups[groups.length-1];
      if(!g||g.id!==r.task_id){g={id:r.task_id,task:r.task,rows:[],total:0};groups.push(g)}
      g.rows.push(r);g.total+=r.total||0;});
    groups.reverse().forEach(function(g){
      var h=document.createElement("b");h.className="uh";h.textContent=(g.task||"(no task)")+" - "+fmt(g.total)+" tokens";box.append(h);
      var tb=document.createElement("table");tb.className="ut";var hr=tb.insertRow();
      ["Time","Step","Agent","Model","Input","Output","Total"].forEach(function(c,i){
        var th=document.createElement("th");th.textContent=c;if(i>3)th.className="n";hr.append(th)});
      g.rows.forEach(function(r){var tr=tb.insertRow();
        [r.time,r.step,r.agent,r.model,fmt(r.input),fmt(r.output),fmt(r.total)].forEach(function(v,i){
          var td=tr.insertCell();td.textContent=v||"-";if(i>3)td.className="n"})});
      box.append(tb);
    });
  },function(){show("Token usage",["Error: request failed"])})};
  document.querySelector("section h2").insertBefore(ub,mb);
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
  function decorate(){chat.querySelectorAll(".bub").forEach(addCopy);chat.querySelectorAll(".m.agent").forEach(addNext);refreshUsage()}
  new MutationObserver(decorate).observe(chat,{childList:true});
  decorate();
  // ---- Agent room: small pixel NPCs that act out the workflow ------------
  (function(){
    var FS='<svg viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
        FSX='<svg viewBox="0 0 24 24"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/></svg>';
    var fb=document.createElement("button");fb.id="fsbtn";fb.type="button";fb.title="Full screen (F11)";fb.innerHTML=FS;
    document.querySelector("section h2").append(fb);
    var full=false;
    function toggleFull(){
      var api=window.pywebview&&window.pywebview.api;
      if(api&&api.toggle_fullscreen){api.toggle_fullscreen();full=!full}
      else if(document.fullscreenElement){document.exitFullscreen();full=false}
      else if(document.documentElement.requestFullscreen){document.documentElement.requestFullscreen();full=true}
      fb.innerHTML=full?FSX:FS;fb.title=full?"Exit full screen (F11)":"Full screen (F11)";
    }
    fb.onclick=toggleFull;
    document.addEventListener("keydown",function(e){
      if(e.key==="F11"){e.preventDefault();toggleFull()}
      else if(e.key==="Escape"&&full&&!document.getElementById("ov").classList.contains("on")){toggleFull()}
    });

    // Pixel sprites: o outline, b body, f face screen, e eyes, a antenna tip.
    var TOP=["......a.....","......o.....","..oooooooo..",".obbbbbbbbo.",".obffffffbo.",".obfeffefbo.",
             ".obffffffbo.",".obbbbbbbbo.","..oooooooo..","...obbbbo..."];
    var LEGS=[["..obbbbbbo..","...oo..oo...","..ooo..oo..."],["..obbbbbbo..","...oo..oo...","...oo..ooo.."]];
    function sprite(col,legs,cls){
      var pal={o:"#0b0d12",b:col,f:"#141925",e:"#9dffcf",a:col},rows=TOP.concat(legs),r="";
      rows.forEach(function(row,y){for(var x=0;x<row.length;x++){var c=pal[row[x]];
        if(c)r+='<rect x="'+x+'" y="'+y+'" width="1.02" height="1.02" fill="'+c+'"/>'}});
      return '<svg class="'+cls+'" viewBox="0 0 12 13">'+r+'</svg>';
    }
    var sec=document.querySelector("section"),room=document.createElement("div");room.id="room";
    var title=document.createElement("span");title.className="rt";title.textContent="AGENT ROOM";
    var rb=document.createElement("button");rb.className="rb";rb.type="button";
    room.append(title,rb);sec.insertBefore(room,document.getElementById("chat"));
    var desk=document.createElement("div");desk.className="prop";desk.style.left="calc(50% - 46px)";
    desk.innerHTML='<svg width="44" height="30" viewBox="0 0 22 15" shape-rendering="crispEdges">'+
      '<rect x="3" y="0" width="16" height="10" fill="#0b0d12"/><rect x="4" y="1" width="14" height="8" fill="#1e3a5f"/>'+
      '<rect x="5" y="2" width="6" height="1" fill="#7aa2ff"/><rect x="5" y="4" width="9" height="1" fill="#3ecf8e"/>'+
      '<rect x="5" y="6" width="5" height="1" fill="#ff6b6b"/><rect x="10" y="10" width="2" height="2" fill="#0b0d12"/>'+
      '<rect x="0" y="12" width="22" height="3" fill="#3a4254"/></svg>';
    room.append(desk);
    var minKey="agentRoomMin";
    function setMin(m){room.classList.toggle("min",m);rb.textContent=m?"Show":"Hide";try{localStorage.setItem(minKey,m?"1":"")}catch(e){}}
    var startMin=false;try{startMin=!!localStorage.getItem(minKey)}catch(e){}
    setMin(startMin);rb.onclick=function(){setMin(!room.classList.contains("min"))};

    var reduce=window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches;
    var cast=[["planner","Planner","#10a37f"],["proposer","Proposer","#d97757"],
              ["reviewer","Reviewer","#8b5cf6"],["controller","Controller","#6b7488"]];
    var npc={};
    cast.forEach(function(c,i){
      var el=document.createElement("div");el.className="npc";
      var wrap=document.createElement("div");
      wrap.innerHTML=sprite(c[2],LEGS[0],"f1")+sprite(c[2],LEGS[1],"f2");
      var tag=document.createElement("span");tag.className="tag";tag.textContent=c[1];
      var say=document.createElement("span");say.className="say";
      el.append(say,wrap,tag);room.append(el);
      npc[c[0]]={el:el,wrap:wrap,say:say,x:0.15+0.22*i,tx:0.15+0.22*i,wait:Math.random()*120,mode:"idle",tick:0};
    });
    function W(){return room.clientWidth||600}
    function speak(n,text){n.say.textContent=text||"";n.el.classList.toggle("talk",!!text)}
    function goTo(n,frac,text,busy){n.mode="task";n.tx=frac;speak(n,text);n.el.classList.toggle("busy",!!busy)}
    function relax(n){n.mode="idle";n.wait=40+Math.random()*120;speak(n,"");n.el.classList.remove("busy")}
    function flash(name,cls,text,ms){var n=npc[name];speak(n,text);n.el.classList.remove(cls);void n.el.offsetWidth;
      n.el.classList.add(cls);setTimeout(function(){n.el.classList.remove(cls);if(n.mode==="idle")speak(n,"")},ms||1800)}

    var ROLE={1:["planner","Planning..."],2:["proposer","Writing a diff..."],4:["controller","Applying patch..."],
              5:["controller","Running checks..."],6:["reviewer","Reviewing..."]};
    function stage(status,step){
      Object.keys(npc).forEach(function(k){relax(npc[k])});
      if(status==="awaiting_approval"){
        goTo(npc.controller,0.5,"Your call!",true);
        goTo(npc.planner,0.28,"");goTo(npc.proposer,0.36,"");goTo(npc.reviewer,0.64,"");
        return;
      }
      var r=ROLE[step];
      if(status!=="idle"&&r){goTo(npc[r[0]],0.5,r[1],true);
        if(step===2)goTo(npc.planner,0.3,"");
        if(step>=5)goTo(npc.proposer,0.3,"");}
    }
    function loop(){
      var w=W();
      Object.keys(npc).forEach(function(k){
        var n=npc[k];
        if(n.mode==="idle"&&!reduce){
          if(n.wait>0)n.wait--;
          else if(Math.abs(n.x-n.tx)<0.004){n.tx=0.06+Math.random()*0.88;n.wait=60+Math.random()*200;
            if(Math.random()<0.08)flash(k,"jump","",900);}
        }
        var dx=n.tx-n.x,step=(n.mode==="task"?2.2:0.9)/w;
        var moving=Math.abs(dx)>step;
        if(reduce){n.x=n.tx;moving=false}
        else if(moving){n.x+=dx>0?step:-step;n.wrap.className=dx<0?"flip":""}
        n.tick++;
        n.el.classList.toggle("step",moving&&Math.floor(n.tick/9)%2===0);
        n.el.style.left=(n.x*100)+"%";
      });
      requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);

    var cursor=null,last="";
    function watch(){
      get("/api/state?since="+(cursor===null?0:cursor)).then(function(s){
        var key=s.status+":"+s.step;
        if(key!==last){last=key;stage(s.status,s.step)}
        if(cursor!==null)s.events.forEach(function(e){
          if(e.kind==="error")flash("controller","sad","Uh oh!",2600);
          else if(e.kind==="user")flash("planner","jump","On it!",1500);
          else if(e.kind==="system"&&/^Done\./.test(e.text))
            ["planner","proposer","reviewer","controller"].forEach(function(k){flash(k,"jump","Done!",2200)});
          else if(e.kind==="system"&&/rejected/i.test(e.text))flash("proposer","sad","Okay...",2000);
        });
        cursor=s.next;
      },function(){}).then(function(){setTimeout(watch,1200)});
    }
    watch();
  })();
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
        client = OpenAI(api_key=local_key, base_url=planner["base_url"])
    else:
        client = OpenAI(api_key=OPENAI_API_KEY)
    openai_agent.client = UsageTrackingClient(client)

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


# Token usage of every agent call in this app session (kept in memory only).
USAGE = []
USAGE_LOCK = threading.Lock()
USAGE_LIMIT = 500  # rows kept for the per-call list; totals below count every call
SESSION_TOTALS = {"input": 0, "output": 0, "total": 0, "cost": 0.0, "calls": 0}


def _tokens(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _current_task():
    """(id, text, step name) of the task the page is running, read from web_ui's session."""
    session = web_ui.S
    with session.lock:
        step = session.step
        task_id, task = None, ""
        for event in reversed(session.events):
            if event["kind"] == "user":
                task_id, task = event["id"], event["text"][:120]
                break
    name = web_ui.STEPS[step - 1] if 1 <= step <= len(web_ui.STEPS) else ""
    return task_id, task, name


def record_usage(agent, model, input_tokens, output_tokens, cost=None):
    """Store one agent call. Never raises: usage tracking must not break a task."""
    try:
        task_id, task, step = _current_task()
        input_tokens, output_tokens = _tokens(input_tokens), _tokens(output_tokens)
        total = None
        if input_tokens is not None or output_tokens is not None:
            total = (input_tokens or 0) + (output_tokens or 0)
        row = {
            "time": time.strftime("%H:%M:%S"), "task_id": task_id, "task": task,
            "step": step, "agent": agent, "model": str(model or ""),
            "input": input_tokens, "output": output_tokens, "total": total,
            "cost": float(cost) if isinstance(cost, (int, float)) else None,
        }
        with USAGE_LOCK:
            for key in ("input", "output", "total", "cost"):
                SESSION_TOTALS[key] += row[key] or 0
            SESSION_TOTALS["calls"] += 1
            USAGE.append(row)
            del USAGE[:-USAGE_LIMIT]
    except Exception as error:
        print(f"Token usage not recorded: {error}")


def usage_totals(rows):
    totals = {"input": 0, "output": 0, "total": 0, "cost": 0.0}
    for row in rows:
        for key in totals:
            totals[key] += row[key] or 0
    return totals


class _UsageTrackingResponses:
    def __init__(self, responses):
        self._responses = responses

    def create(self, **kwargs):
        response = self._responses.create(**kwargs)
        usage = getattr(response, "usage", None)
        record_usage("GPT", kwargs.get("model"),
                     getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None))
        return response


class UsageTrackingClient:
    """Wraps the OpenAI client used by ask_gpt() and records each response's usage."""

    def __init__(self, client):
        self._client = client
        self.responses = _UsageTrackingResponses(client.responses)

    def __getattr__(self, name):
        return getattr(self._client, name)


class ClaudeUsageSubprocess:
    """Replaces the subprocess module inside claude_agent only.

    ask_claude() runs the Claude CLI with "--output-format text", which has no
    token counts. This asks for "json" instead, records the reported usage and
    hands the plain result text back, so ask_claude() keeps working unchanged.
    """

    def __getattr__(self, name):
        return getattr(subprocess, name)

    def run(self, command, **kwargs):
        command = list(command)
        for i in range(len(command) - 1):
            if command[i] == "--output-format" and command[i + 1] == "text":
                command[i + 1] = "json"
                break
        else:
            return subprocess.run(command, **kwargs)
        result = subprocess.run(command, **kwargs)
        try:
            data = json.loads(result.stdout or "")
        except ValueError:
            # Not JSON (older CLI, or it ignored the flag): the output is the
            # plain text answer, so pass it through untouched.
            return result
        if not isinstance(data, dict) or "result" not in data and "usage" not in data:
            # JSON, but not the CLI's result object: it may be the answer itself.
            return result
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        parts = [usage.get(key) for key in (
            "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")]
        parts = [p for p in parts if _tokens(p) is not None]
        models = data.get("modelUsage")
        model = ", ".join(models) if isinstance(models, dict) and models else (
            os.environ.get("CLAUDE_MODEL") or "Claude CLI default")
        record_usage("Claude", model, sum(parts) if parts else None,
                     usage.get("output_tokens"), data.get("total_cost_usd"))
        text = data.get("result")
        if isinstance(text, str) and not data.get("is_error"):
            result.stdout = text
            return result
        # No usable answer (for example max turns reached or an API error).
        # Make ask_claude() raise a clear error instead of passing a
        # placeholder on to proposal parsing.
        reason = data.get("subtype") or "unknown"
        detail = text if isinstance(text, str) else ""
        result.returncode = result.returncode or 1
        result.stderr = (result.stderr or "") + (
            f"Claude CLI returned no usable result ({reason}). {detail}".strip())
        result.stdout = ""
        return result


def set_project(path):
    """Point every controller module at the Git repository containing path.

    The modules read PROJECT_ROOT on every call, so the agents work in that
    repository while the controller and its .env (API keys) stay in this folder.
    """
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=str(path),
            capture_output=True, text=True, encoding="utf-8", timeout=15, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        raise SystemExit(f"Not a Git repository (or Git is missing): {path}  Use --project PATH.")
    root = Path(top).resolve()
    for module in (claude_agent, proposal, patch_applier, web_ui):
        module.PROJECT_ROOT = root
    # History stays per project, outside the repository.
    web_ui.HISTORY_FILE = Path.home() / ".agent_controller" / f"{root.name}.json"
    return root


def detach(root):
    """Restart the app without a console window, so the terminal is free again."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        flags = {"start_new_session": True}
    with open(LOG_FILE, "a", encoding="utf-8") as log:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--project", str(root)],
            env=dict(os.environ, AGENT_APP_DETACHED="1"),
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, **flags,
        )
    print(f"Agent World opened for {root}. The terminal is free; log: {LOG_FILE}")


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
        if self.path.split("?")[0] == "/api/usage":
            if not self._local_only() or not self._authorized():
                return self._json({"error": "unauthorized"}, 401)
            with USAGE_LOCK:
                rows = [dict(row) for row in USAGE]
                totals = dict(SESSION_TOTALS)
            # Totals cover the whole session; only the oldest rows are dropped
            # from the list once it passes USAGE_LIMIT.
            return self._json({"rows": rows, "totals": totals,
                               "shown_totals": usage_totals(rows),
                               "dropped": totals["calls"] - len(rows)})
        if self.path.split("?")[0] == "/api/branch":
            if not self._local_only() or not self._authorized():
                return self._json({"error": "unauthorized"}, 401)
            try:
                branch = subprocess.run(
                    ["git", "branch", "--show-current"], cwd=web_ui.PROJECT_ROOT,
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
                cwd=web_ui.PROJECT_ROOT, capture_output=True, text=True,
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


# The native window, kept outside WindowApi so pywebview does not try to
# expose the window object itself to the page.
_WINDOWS = []


class WindowApi:
    """Methods the page can call as window.pywebview.api.<name>()."""

    def toggle_fullscreen(self):
        if _WINDOWS:
            _WINDOWS[0].toggle_fullscreen()


def main():
    parser = argparse.ArgumentParser(description="Agent World desktop app")
    parser.add_argument("--project", default=".",
                        help="Git repository the agents work on (default: current folder)")
    parser.add_argument("--console", action="store_true",
                        help="stay in this terminal instead of running in the background")
    parser.add_argument("--smoke", action="store_true",
                        help="start the server, check that it responds, and exit")
    args = parser.parse_args()

    try:
        import webview
    except ImportError:
        raise SystemExit("pywebview is missing. Run: pip install -r requirements.txt")

    root = set_project(Path(args.project).expanduser())
    if not (args.smoke or args.console or os.environ.get("AGENT_APP_DETACHED")):
        return detach(root)

    apply_models(load_models())
    # Record the Claude CLI's token usage (see ClaudeUsageSubprocess).
    claude_agent.subprocess = ClaudeUsageSubprocess()

    # Port 0 = let the OS pick a free port, so the app never clashes with
    # a running web_ui instance.
    server = ThreadingHTTPServer((HOST, 0), ThemedHandler)
    url = f"http://{HOST}:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    if args.smoke:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                print(f"smoke test OK: {url} -> HTTP {resp.status}")
        finally:
            server.shutdown()
            server.server_close()
        return

    _WINDOWS.append(webview.create_window(
        f"Agent World - {root.name}", url, width=1280, height=820, text_select=True,
        js_api=WindowApi(),
    ))
    try:
        webview.start()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
