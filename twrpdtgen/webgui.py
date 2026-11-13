# SPDX-License-Identifier: Apache-2.0
"""Private, mobile-friendly localhost GUI for twrpdtgen-NEXT.

Works in a normal Android browser with Python running in Termux, as well
as Windows/Linux. The server binds loopback only, never exposes a network
service, and does not upload firmware to an external provider.
"""
from __future__ import annotations

from argparse import ArgumentParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock, Thread
from urllib.parse import parse_qs, urlsplit
import json
import os
import secrets
import shutil
import subprocess
import sys
import webbrowser
import zipfile

from twrpdtgen import __version__
from twrpdtgen.gui import parse_job, run_job
from twrpdtgen.option_sync import interface_schema


MAX_UPLOAD = 32 * 1024 ** 3
MAX_JSON = 64 * 1024

_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>twrpdtgen NEXT</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#e5ebf2;background:#111820}
*{box-sizing:border-box}
body{margin:0;background:#111820;min-height:100vh}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;max-width:920px;margin:auto;padding:16px 14px 12px;border-bottom:1px solid #34404d}
h1{font-size:21px;line-height:1.25;margin:0;font-weight:600}
small,.muted,.note{color:#b1becb}
main{max-width:920px;margin:auto;padding:14px 14px 36px}
.grid,.twocol{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.card{background:#1b2530;border:1px solid #334454;border-radius:7px;padding:15px;margin-bottom:12px}
.card h2{font-size:15px;margin:0 0 10px;font-weight:600}
label{display:block;font-size:13px;font-weight:500;margin:9px 0 5px}
input,select,button{font:inherit}
input[type=text],select{background:#101923;color:#eef4fb;border:1px solid #536476;border-radius:5px;padding:9px;width:100%;min-width:0}
input[type=file]{display:block;width:100%;background:#101923;padding:10px;border:1px solid #536476;border-radius:5px;font-size:13px}
input:focus-visible,select:focus-visible,button:focus-visible{outline:2px solid #8ab9ff;outline-offset:2px}
button{border:1px solid #596a7c;border-radius:5px;background:#304356;color:#f0f5fa;padding:8px 12px;cursor:pointer}
button.primary{background:#3c70ae;border-color:#477dbb;color:#fff;font-weight:600}
button:disabled{opacity:.5;cursor:not-allowed}
.check{display:flex;align-items:center;gap:9px;font-weight:400}
.check input{height:16px;width:16px}
.tools{position:relative}
#toolsPane{display:none;position:absolute;right:0;top:40px;min-width:190px;background:#25313e;border:1px solid #526475;border-radius:5px;padding:4px;z-index:3}
#toolsPane button{width:100%;text-align:left;background:none;border:0}
#toolsPane button:hover{background:#3e5062}
.actions{display:flex;flex-wrap:wrap;align-items:center;gap:9px}
#progress{height:5px;background:#283949;overflow:hidden;display:none;margin:10px 0}
#bar{width:34%;height:100%;background:#7ba9dc;animation:moving 1.2s ease-in-out infinite alternate}
@keyframes moving{from{transform:translateX(-80%)}to{transform:translateX(290%)}}
#log{background:#0d141c;border:1px solid #35495a;border-radius:5px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 ui-monospace,monospace;padding:10px;height:145px;margin-top:10px}
#status{color:#c4d2e0;font-size:13px}
#download{display:none;text-decoration:none;background:#315c51;border-radius:5px;color:white;padding:9px 12px}
#advanced{display:none}
.note{font-size:12px;line-height:1.45}
@media(max-width:680px){.grid,.twocol{grid-template-columns:1fr}header{padding:13px 12px}main{padding:12px}.card{padding:12px}#log{height:190px}}
</style></head><body>
<header><div><h1>twrpdtgen NEXT</h1>
<small>Device tree generator · __VERSION__</small></div>
<div class="tools"><button id="toolsButton" aria-haspopup="true" aria-expanded="false">⋮ Tools</button>
<div id="toolsPane"><button id="copyLogs">Copy logs</button><button id="toggleAdvanced">Advanced settings</button>
<button id="checkGitMenu">Check Git updates</button><button id="applyGitMenu">Update from Git…</button>
<button id="about">About & safety</button></div></div></header>
<main>
<div class="grid">
<section class="card"><h2>Source</h2>
<label for="sourceFile">Choose an image, ZIP, or TAR (phone file picker)</label>
<input type="file" id="sourceFile">
<label for="source">Or use an existing local file/folder path</label>
<input type="text" id="source" placeholder="~/storage/downloads/boot.img">
<p class="note">Files are processed locally (127.0.0.1).</p>
</section>
<section class="card"><h2>Output</h2>
<label for="output">Output folder on this device</label>
<input type="text" id="output" value="~/TWRP-Trees">
<label for="archive">ZIP filename (optional)</label>
<input type="text" id="archive" placeholder="Default: unique twrp-device-tree.zip">
<p class="note">A ZIP will be available for download in the browser when generation finishes.</p>
</section>
</div>
<section class="card"><h2>Additional images</h2>
<div class="grid">
<div><label for="bootFile">boot.img</label><input id="bootFile" type="file">
<label for="boot_image">Or enter local path</label><input id="boot_image" type="text"></div>
<div><label for="vendorFile">vendor_boot.img</label><input id="vendorFile" type="file">
<label for="vendor_boot">Or enter local path</label><input id="vendor_boot" type="text"></div>
<div><label for="initFile">init_boot.img</label><input id="initFile" type="file">
<label for="init_boot">Or enter local path</label><input id="init_boot" type="text"></div>
</div>
<p class="note">Matching images are auto-detected. init_boot is not proof of the recovery flash target.</p>
</section>
<section class="card"><h2>Options</h2>
<div class="grid">
<div><label for="skeleton">TWRP profile</label><select id="skeleton"><option>auto</option><option>omni</option><option>twrp-12.1</option><option>twrp-14.1</option></select></div>
<div><label for="recovery_layout">Recovery source</label><select id="recovery_layout"><option>auto</option><option>dedicated</option><option>boot</option><option>vendor_boot</option><option>init_boot</option></select></div>
<div><label for="recovery_root_mode">Ramdisk overlay</label><select id="recovery_root_mode"><option>auto</option><option>minimal</option><option>full</option></select></div>
<div><label for="recovery_fragment">Vendor recovery fragment (if verified)</label><input id="recovery_fragment" type="text" placeholder="Name or index"></div>
</div>
<div id="advanced">
<h2 style="margin-top:18px">Verified partition sizes</h2>
<div class="twocol">
<div><label for="boot_size">Boot</label><input id="boot_size" type="text" placeholder="e.g. 64MiB"></div>
<div><label for="recovery_size">Recovery</label><input id="recovery_size" type="text"></div>
<div><label for="super_size">Super</label><input id="super_size" type="text"></div>
<div><label for="dynamic_group_size">Dynamic group</label><input id="dynamic_group_size" type="text"></div>
</div>
<p class="note">Unknown sizes may be left blank; image lengths are not used as partition capacities.</p>
<h2 style="margin-top:18px">Other options</h2>
<div id="cliSyncedOptions" class="grid" aria-live="polite"></div>
</div>
<label class="check"><input type="checkbox" id="include_stock_root"> Include full stock ramdisk in downloaded ZIP</label>
<label class="check"><input type="checkbox" id="overwrite"> Replace an existing tree (asks for confirmation)</label>
</section>
<section class="card"><h2>Run</h2>
<div class="actions">
<button class="primary" id="generate">Generate tree + ZIP</button>
<button id="extract">Extract components only</button>
<a id="download" href="#">Download ZIP</a>
</div>
<div id="progress"><div id="bar"></div></div>
<p id="status" role="status">Ready to process an image.</p>
<pre id="log" aria-label="Job log">No job running.</pre>
<p class="note">Generated trees have not been boot-tested. Review generation-report.json and verify hardware details before flashing.</p>
</section>
<section class="card"><h2>Updates</h2>
<div class="actions"><button id="gitCheck">Check for updates</button>
<button id="gitApply" disabled>Update from Git…</button></div>
<p id="gitResult" class="note" role="status">Not checked. Use Check for updates to see if a clean fast-forward is available. The update action stays disabled otherwise.</p>
</section>
</main>
<script>
"use strict";
const csrf=__TOKEN__;
const el=id=>document.getElementById(id);
const fields=["source","output","archive","boot_image","vendor_boot","init_boot","skeleton","recovery_layout","recovery_root_mode","recovery_fragment","boot_size","recovery_size","super_size","dynamic_group_size"];
let polling=null,active=false,gitBusy=false,gitStatus=null;
let syncedExtras=[];
async function loadSharedOptions(){
 const response=await fetch("/api/options",{cache:"no-store"});
 if(!response.ok)throw new Error("Could not retrieve generator settings");
 const schema=await response.json();
 for(const [name,spec] of Object.entries(schema.choices||{})){
  const select=el(name);
  if(!select)throw new Error("Missing generator setting: "+name);
  const previous=select.value;
  select.replaceChildren();
  for(const choice of spec.choices){
   const option=document.createElement("option");
   option.value=choice;option.textContent=choice;
   select.append(option);
  }
  select.value=spec.choices.includes(previous)?previous:spec.default;
 }
 const target=el("cliSyncedOptions");
 target.replaceChildren();
 syncedExtras=schema.extras||[];
 for(const opt of syncedExtras){
  const holder=document.createElement("div");
  const label=document.createElement("label");
  label.htmlFor="cli_"+opt.name;
  label.textContent=opt.flag+" — "+opt.label;
  holder.append(label);
  let control;
  if(opt.kind==="boolean"){
   control=document.createElement("input");
   control.type="checkbox";
   control.checked=Boolean(opt.default);
  }else if(opt.kind==="choice"){
   control=document.createElement("select");
   for(const value of opt.choices){
    const item=document.createElement("option");
    item.value=value;item.textContent=value;control.append(item);
   }
   control.value=opt.default;
  }else{
   control=document.createElement("input");
   control.type="text";
   control.value=opt.default||"";
  }
  control.id="cli_"+opt.name;
  holder.append(control);
  target.append(holder);
 }
}
const optionsReady=loadSharedOptions();
function tools(open){el("toolsPane").style.display=open?"block":"none";el("toolsButton").setAttribute("aria-expanded",String(open))}
el("toolsButton").onclick=()=>tools(el("toolsPane").style.display!=="block");
el("toggleAdvanced").onclick=()=>{let a=el("advanced");a.style.display=a.style.display==="block"?"none":"block";tools(false)};
el("copyLogs").onclick=async()=>{await navigator.clipboard.writeText(el("log").textContent);tools(false)};
el("about").onclick=()=>{tools(false);alert("twrpdtgen-NEXT is an offline recovery source-tree generator. Generated trees and inferred partition sizes are not proof of flash safety.")};
function status(s){el("status").textContent=s}
function working(on){
 active=on;
 el("generate").disabled=on;
 el("extract").disabled=on;
 el("gitCheck").disabled=on||gitBusy;
 const canApply=!on&&!gitBusy&&Boolean(gitStatus?.can_apply);
 el("gitApply").disabled=!canApply;
 el("applyGitMenu").disabled=!canApply;
 el("progress").style.display=on?"block":"none";
}
working(false);
async function upload(input,name){
const file=el(input).files[0];if(!file)return null;
status("Uploading "+file.name+" to the local generator...");
return await new Promise((resolve,reject)=>{
 const xhr=new XMLHttpRequest();
 xhr.open("PUT","/api/upload?name="+encodeURIComponent(file.name));
 xhr.setRequestHeader("X-CSRF-Token",csrf);
 xhr.upload.onprogress=e=>{if(e.lengthComputable)status("Uploading "+file.name+" ("+Math.round(100*e.loaded/e.total)+"%)")};
 xhr.onload=()=>{try{const payload=JSON.parse(xhr.responseText);
   if(xhr.status>=200&&xhr.status<300)resolve(payload.path);
   else reject(new Error(payload.error||"Upload failed"));
 }catch(e){reject(e)}};
 xhr.onerror=()=>reject(new Error("Local upload failed"));
 xhr.send(file);
});
}
async function send(path,data){
const res=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":csrf},body:JSON.stringify(data)});
const value=await res.json();if(!res.ok)throw new Error(value.error||"Request rejected");
return value;
}
async function poll(){
try{
const res=await fetch("/api/status",{cache:"no-store"});
const data=await res.json();
status(data.message||data.status);
el("log").textContent=(data.logs||[]).join("\n");
el("log").scrollTop=el("log").scrollHeight;
if(data.status==="running"){working(true);return}
if(data.status==="done"){working(false);const a=el("download");if(data.download){
 a.href=data.download;a.style.display="inline-block";a.textContent="Download ZIP"
 }else a.style.display="none";stopPoll();return}
if(data.status==="error"){working(false);stopPoll()}
}catch(e){status("Cannot reach localhost generator: "+e.message);working(false);stopPoll()}
}
function stopPoll(){if(polling){clearInterval(polling);polling=null}}
async function start(mode){
if(active)return;
if(el("overwrite").checked && !confirm("Replace the existing generated device tree if it exists?"))return;
working(true);el("download").style.display="none";
try{
 await optionsReady;
 const data=Object.fromEntries(fields.map(name=>[name,el(name).value]));
 data.cli_options=Object.fromEntries(syncedExtras.map(
   spec=>[spec.name,spec.kind==="boolean"
     ?el("cli_"+spec.name).checked
     :el("cli_"+spec.name).value]));
 data.mode=mode;
 data.overwrite=el("overwrite").checked;
 data.include_stock_root=el("include_stock_root").checked;
 for(const [input,name] of [["sourceFile","source"],["bootFile","boot_image"],["vendorFile","vendor_boot"],["initFile","init_boot"]]){
    const path=await upload(input,name);
    if(path)data[name]=path;
 }
 await send("/api/start",data);
 status("Processing stock images locally...");
 if(!polling)polling=setInterval(poll,850);
 await poll();
}catch(e){status("Error: "+e.message);working(false);stopPoll()}
}
async function gitAction(kind){
 if(active||gitBusy)return;
 if(kind==="apply" && !gitStatus?.can_apply){
  el("gitResult").textContent=gitStatus?.explanation||
    "Check for updates before applying. No checkout was performed.";
  working(active);
  return;
 }
 if(kind==="apply"&&!confirm(
  "Fast-forward this clean Git checkout to "+gitStatus.latest.slice(0,12)+
  "? Local edits, untracked files and diverged commits are never overwritten."))return;
 if(kind==="check")gitStatus=null;
 gitBusy=true;
 working(active);
 el("gitResult").textContent=kind==="check"
  ?"Checking configured upstream for changes…"
  :"Applying verified fast-forward…";
 try{
  const result=await send("/api/git/"+kind,kind==="apply"?{confirmed:true}:{});
  gitStatus=result;
  if(kind==="apply"){
   el("gitResult").textContent="Updated to "+result.current.slice(0,12)+
     ". Restart this tool to load new code.";
  }else{
   el("gitResult").textContent=result.explanation+
     "  ·  "+result.branch+" → "+result.upstream+
     "  ·  "+result.behind+" behind / "+result.ahead+" ahead";
  }
 }catch(error){
  gitStatus=null;
  el("gitResult").textContent="Git updater: "+error.message+
    " Recheck the repository state before trying again.";
 }finally{
  gitBusy=false;
  working(active);
 }
}
el("gitCheck").onclick=()=>gitAction("check");
el("gitApply").onclick=()=>gitAction("apply");
el("checkGitMenu").onclick=()=>{tools(false);gitAction("check")};
el("applyGitMenu").onclick=()=>{tools(false);gitAction("apply")};
el("generate").onclick=()=>start("tree");
el("extract").onclick=()=>start("extract");
</script></body></html>"""


class WebState:
    def __init__(self):
        self.temp = TemporaryDirectory(prefix="twrpdtgen-web-")
        self.workspace = Path(self.temp.name)
        self.token = secrets.token_urlsafe(32)
        self.lock = RLock()
        self.status = "idle"
        self.message = "Ready"
        self.logs = []
        self.download = None
        self.thread = None
        self.updating = False

    def append(self, value):
        with self.lock:
            self.logs.append(str(value))
            self.logs = self.logs[-500:]
            self.message = str(value)

    def snapshot(self):
        with self.lock:
            return dict(status=self.status, message=self.message,
                        logs=list(self.logs),
                        download=("/api/download?key=" + self.token)
                        if self.download is not None else None)

    def start(self, job):
        with self.lock:
            if self.status == "running" or self.updating:
                raise RuntimeError("Another generation or Git update is running")
            self.status = "running"
            self.message = "Preparing source images"
            self.logs = []
            self.download = None

        def work():
            try:
                result = run_job(job, report=self.append)
                download = result.archive
                if result.extracted is not None:
                    # Extraction-only mode also supports downloading results
                    # through the phone browser without manual file copying.
                    download = self.workspace / "extracted-images.zip"
                    with zipfile.ZipFile(
                            download, "w", compression=zipfile.ZIP_DEFLATED,
                            allowZip64=True) as output:
                        for entry in sorted(result.extracted.rglob("*")):
                            if entry.is_file() and not entry.is_symlink():
                                output.write(
                                    entry,
                                    (Path("extracted-images") /
                                     entry.relative_to(result.extracted)).as_posix())
                with self.lock:
                    self.download = download
                    self.status = "done"
                    self.message = "Completed: candidate files created"
            except Exception as exc:
                with self.lock:
                    self.status = "error"
                    self.message = "{}: {}".format(type(exc).__name__, exc)
                    self.logs.append("ERROR: " + self.message)

        self.thread = Thread(target=work, daemon=True)
        self.thread.start()


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class WebHandler(BaseHTTPRequestHandler):
    server_version = "twrpdtgen-NEXT"

    def _host_ok(self):
        host = self.headers.get("Host", "")
        return host in (
            "127.0.0.1:{}".format(self.server.server_port),
            "localhost:{}".format(self.server.server_port),
        )

    def _headers(self, status, content_type, length):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'unsafe-inline'; "
                         "style-src 'unsafe-inline'; base-uri 'none'; "
                         "frame-ancestors 'none'")
        self.end_headers()

    def _json(self, status, obj):
        raw = json.dumps(obj, ensure_ascii=True).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(raw))
        self.wfile.write(raw)

    def _read_json(self):
        raw = self.headers.get("Content-Length")
        if not raw or not raw.isdigit():
            raise ValueError("Missing request length")
        length = int(raw)
        if length < 2 or length > MAX_JSON:
            raise ValueError("Request is too large")
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Request must be an object")
        return data

    def _check(self, changing=False):
        if not self._host_ok():
            self._json(403, {"error": "Localhost requests only"})
            return False
        if changing and not secrets.compare_digest(
                self.headers.get("X-CSRF-Token", ""), self.server.state.token):
            self._json(403, {"error": "Missing or invalid session token"})
            return False
        return True

    def do_GET(self):
        if not self._check():
            return
        parsed = urlsplit(self.path)
        if parsed.path == "/":
            html = (_PAGE.replace("__VERSION__", __version__)
                    .replace("__TOKEN__", json.dumps(self.server.state.token)))
            raw = html.encode("utf-8")
            self._headers(200, "text/html; charset=utf-8", len(raw))
            self.wfile.write(raw)
        elif parsed.path == "/api/status":
            self._json(200, self.server.state.snapshot())
        elif parsed.path == "/api/options":
            self._json(200, interface_schema())
        elif parsed.path == "/api/download":
            args = parse_qs(parsed.query)
            key = args.get("key", [""])[0]
            state = self.server.state
            if not secrets.compare_digest(key, state.token):
                self._json(403, {"error": "Invalid download key"})
                return
            with state.lock:
                path = state.download
            if path is None or not path.is_file():
                self._json(404, {"error": "No completed output ZIP"})
                return
            length = path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition",
                             "attachment; filename=\"twrpdtgen-NEXT-output.zip\"")
            self.send_header("Content-Length", str(length))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with path.open("rb") as stream:
                shutil.copyfileobj(stream, self.wfile, length=1024 * 1024)
        else:
            self._json(404, {"error": "Unknown endpoint"})

    def do_PUT(self):
        if not self._check(changing=True):
            return
        parsed = urlsplit(self.path)
        if parsed.path != "/api/upload":
            self._json(404, {"error": "Unknown endpoint"})
            return
        args = parse_qs(parsed.query)
        name = args.get("name", [""])[0].strip()
        if (not name or len(name) > 150
                or name in (".", "..")
                or "/" in name or "\\" in name or ":" in name):
            self._json(400, {"error": "Invalid image filename"})
            return
        allowed = (".img", ".img.lz4", ".zip", ".tar",
                   ".tar.md5", ".tgz", ".tar.gz", ".tar.xz", ".tar.bz2")
        if not name.lower().endswith(allowed):
            self._json(400, {"error": "Unsupported firmware file type"})
            return
        raw = self.headers.get("Content-Length", "")
        if not raw.isdigit() or not 0 < int(raw) <= MAX_UPLOAD:
            self._json(413, {"error": "Invalid upload size or above 32 GiB"})
            return
        folder = self.server.state.workspace / secrets.token_hex(10)
        folder.mkdir()
        path = folder / name
        remain = int(raw)
        try:
            with path.open("xb") as file:
                while remain:
                    chunk = self.rfile.read(min(remain, 1024 * 1024))
                    if not chunk:
                        raise ConnectionError("Upload was interrupted")
                    file.write(chunk)
                    remain -= len(chunk)
            self._json(200, {"path": str(path)})
        except (ConnectionError, OSError):
            path.unlink(missing_ok=True)
            try:
                self._json(400, {"error": "Upload interrupted or disk full"})
            except OSError:
                pass

    def do_POST(self):
        if not self._check(changing=True):
            return
        endpoint = urlsplit(self.path).path
        if endpoint in ("/api/git/check", "/api/git/apply"):
            state = self.server.state
            try:
                values = self._read_json()
                if endpoint.endswith("/apply") and values.get("confirmed") is not True:
                    raise ValueError("Git update requires explicit confirmation")
                with state.lock:
                    if state.updating or state.status == "running":
                        raise RuntimeError("Cannot update Git while generation or another update is running")
                    state.updating = True
                try:
                    from twrpdtgen.git_updater import check_updates, apply_update
                    result = (apply_update(confirmed=True)
                              if endpoint.endswith("/apply")
                              else check_updates())
                finally:
                    with state.lock:
                        state.updating = False
            except RuntimeError as exc:
                self._json(409, {"error": str(exc)})
                return
            except (ValueError, FileNotFoundError, TypeError,
                    json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, result.to_dict())
            return
        if endpoint != "/api/start":
            self._json(404, {"error": "Unknown endpoint"})
            return
        try:
            values = self._read_json()
            job = parse_job(values)
            self.server.state.start(job)
        except RuntimeError as exc:
            self._json(409, {"error": str(exc)})
            return
        except (ValueError, FileNotFoundError, TypeError,
                json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
            return
        self._json(202, {"status": "running"})

    def log_message(self, fmt, *args):
        # No firmware paths or query tokens are written to terminal access logs.
        return


def main(argv=None):
    parser = ArgumentParser(
        prog="twrpdtgen-web",
        description="Local-only mobile/browser GUI for twrpdtgen-NEXT")
    parser.add_argument("--port", type=int, default=8765,
                        help="localhost port (default 8765; 0 chooses any free port)")
    parser.add_argument("--no-browser", action="store_true",
                        help="do not open a browser automatically")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("port must be 0..65535")
    state = WebState()
    server = LocalServer(("127.0.0.1", args.port), WebHandler)
    server.state = state
    address = "http://127.0.0.1:{}/".format(server.server_port)
    print("twrpdtgen-NEXT {} local GUI: {}".format(__version__, address))
    print("Firmware stays on your device. Press Ctrl+C to stop the web GUI.")
    if not args.no_browser:
        try:
            if shutil.which("termux-open-url"):
                subprocess.Popen(["termux-open-url", address])
            else:
                webbrowser.open(address)
        except OSError:
            print("Open this address manually: " + address)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        print("\nStopping localhost GUI...")
    finally:
        server.server_close()
        if state.thread is not None and state.thread.is_alive():
            print("WARNING: Job was interrupted; unfinished output may remain.")
        state.temp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
