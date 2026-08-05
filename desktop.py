"""
desktop.py - Froth as a standalone desktop window (Spotify-style).

Industry secret: Spotify and WhatsApp Desktop ARE browsers in disguise (Chromium windows
without the address bar). This does the same: it boots the local Streamlit server in the
background and shows it inside a native window (pywebview -> Edge WebView2 on Windows).
Same app, no browser chrome.

Run it with:  Froth App.bat   (double-click)
Closing the window shuts the server down too.
"""
import atexit
import ctypes
import json
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import webview

ROOT = Path(__file__).resolve().parent
PORT = 8501
ICON = ROOT / "assets" / "froth.ico"

# Splash while the engine warms up (~40s first run): rising flotation bubbles that
# collide and burst into particles - the brand, animated, so nobody stares at a blank
# window (Batman's spec). Self-contained: no network needed.
SPLASH = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html,body { margin:0; height:100%; background:#18181b; overflow:hidden;
  font-family:'Segoe UI',sans-serif; }
.wordmark { position:absolute; top:36%; width:100%; text-align:center;
  color:#fafafa; font-size:44px; font-weight:600; letter-spacing:-0.5px; }
.sub { position:absolute; top:48%; width:100%; text-align:center;
  color:#a1a1aa; font-size:14px; }
.rail { position:absolute; top:54%; left:50%; transform:translateX(-50%);
  width:280px; height:4px; background:#27272a; border-radius:2px; overflow:hidden; }
.rail > div { width:4%; height:100%; background:#6366f1; border-radius:2px;
  transition:width .5s; }
canvas { position:absolute; inset:0; }
</style></head><body>
<canvas id="c"></canvas>
<div class="wordmark">Froth</div>
<div class="sub" id="stage">warming up the flotation cell&hellip;</div>
<div class="rail"><div id="bar"></div></div>
<script>
// Python drives the stage text; the bar creeps on typical warm-up time (~40s)
// and never claims 100% until the app is truly ready (honest progress).
function setStage(m) { document.getElementById('stage').textContent = m; }
const t0 = Date.now();
setInterval(() => {
  const el = (Date.now() - t0) / 1000;
  document.getElementById('bar').style.width = Math.min(60, 4 + el/40*56) + '%';
}, 500);
const cv = document.getElementById('c'), ctx = cv.getContext('2d');
const COLORS = ['#6366f1', '#8b5cf6', '#14b8a6', '#378ADD'];
let W, H; const fit = () => { W = cv.width = innerWidth; H = cv.height = innerHeight; };
fit(); onresize = fit;
const bubbles = [], parts = [];
// Rise speed follows SIZE, the way it does in a real flotation cell: big bubbles climb
// faster, overtake the small ones and coalesce. With an independent random speed
// everything drifted up in parallel and collisions were pure luck. Each bubble also gets
// its OWN wobble frequency - with one shared period neighbours swayed in step and almost
// never crossed, and varying it multiplies collisions more than raising the count does
// (measured on v1 with a fake clock: 40 -> 257 bursts per 15s).
const spawn = () => { const r = 4+Math.random()*18;
  bubbles.push({ x: Math.random()*W, y: H+20, r: r,
    v: 0.5 + r*0.075 + Math.random()*0.25,
    c: COLORS[Math.floor(Math.random()*COLORS.length)],
    wob: Math.random()*6.28, fr: 700 + Math.random()*500 }); };
for (let i = 0; i < 70; i++) spawn();
// Spawn rate, not the cap, sets how many are on screen: they leave through the top in
// ~8s and every collision eats one, so at 450ms the population sat far below the cap.
// 55ms holds ~81 (measured). The cap still matters for a different reason: spawning is a
// timer but movement runs on requestAnimationFrame, which browsers PAUSE when the window
// has no focus, so a backgrounded splash would come back to a wall of bubbles.
setInterval(() => { if (bubbles.length < 140) spawn(); }, 55);
function burst(x, y, col) { if (parts.length > 260) return;   // keep the boot CPU free
  for (let i = 0; i < 12; i++)
  parts.push({ x, y, vx: (Math.random()-0.5)*3, vy: (Math.random()-0.5)*3,
               life: 1, c: col }); }
(function loop(t) {
  ctx.clearRect(0, 0, W, H);
  for (let i = bubbles.length-1; i >= 0; i--) {
    const b = bubbles[i];
    b.y -= b.v; b.x += Math.sin(t/b.fr + b.wob)*1.6;  // own period + wider = crossings
    for (let j = i-1; j >= 0; j--) {           // collisions -> particle bursts
      const o = bubbles[j], dx = b.x-o.x, dy = b.y-o.y;
      // 0.95: they burst when they actually TOUCH. At 0.55 they had to overlap by a
      // quarter first, which is why bursts were rare.
      if (dx*dx + dy*dy < (b.r+o.r)*(b.r+o.r)*0.95) {
        burst((b.x+o.x)/2, (b.y+o.y)/2, b.c);
        b.r = Math.min(b.r*1.08, 32);           // survivor grows, like real froth
        bubbles.splice(j, 1); i--;
      }
    }
    if (b.y < -30) { bubbles.splice(i, 1); continue; }
    ctx.globalAlpha = 0.75; ctx.fillStyle = b.c;
    ctx.beginPath(); ctx.arc(b.x, b.y, b.r, 0, 6.29); ctx.fill();
    ctx.globalAlpha = 0.35; ctx.fillStyle = '#fff';
    ctx.beginPath(); ctx.arc(b.x-b.r*0.3, b.y-b.r*0.3, b.r*0.25, 0, 6.29); ctx.fill();
  }
  for (let i = parts.length-1; i >= 0; i--) {
    const p = parts[i]; p.x += p.vx; p.y += p.vy; p.life -= 0.03;
    if (p.life <= 0) { parts.splice(i, 1); continue; }
    ctx.globalAlpha = p.life; ctx.fillStyle = p.c;
    ctx.fillRect(p.x, p.y, 2.5, 2.5);
  }
  ctx.globalAlpha = 1;
  requestAnimationFrame(loop);
})(0);
</script></body></html>"""


# Injected into the Streamlit page right after navigation: the port answers ~2s in,
# but the interface takes 20-60s more to actually render (model + data load). This
# overlay keeps the branded loading screen up and removes itself only when real app
# widgets exist in the DOM (tabs/buttons) - no more staring at a blank page.
_BOOT_OVERLAY_JS = """
(function () {
  if (document.getElementById('froth-boot')) return;
  const d = document.createElement('div');
  d.id = 'froth-boot';
  d.style.cssText = 'position:fixed;inset:0;z-index:2147483647;background:#18181b;' +
    'display:flex;flex-direction:column;align-items:center;justify-content:center;' +
    "font-family:'Segoe UI',sans-serif;transition:opacity .7s";
  d.innerHTML =
    '<canvas id="froth-boot-cv" style="position:absolute;inset:0"></canvas>' +
    '<div style="color:#fafafa;font-size:38px;font-weight:600;z-index:1;' +
    'letter-spacing:-0.5px">Froth</div>' +
    '<div id="froth-boot-msg" style="color:#a1a1aa;font-size:14px;margin-top:10px;' +
    'z-index:1">engine is up, assembling your map&hellip;</div>' +
    '<div style="width:280px;height:4px;background:#27272a;border-radius:2px;' +
    'margin-top:18px;overflow:hidden;z-index:1"><div id="froth-boot-bar" style="width:60%;' +
    'height:100%;background:#6366f1;border-radius:2px;transition:width .5s"></div></div>';
  document.body.appendChild(d);
  // Same show as the splash (Batman's spec): bubbles rising and COLLIDING into
  // particle bursts - bigger and bolder here, because this is the long phase
  // the user actually stares at.
  const cv = document.getElementById('froth-boot-cv'), cx = cv.getContext('2d');
  const COLS = ['#6366f1', '#8b5cf6', '#14b8a6', '#378ADD'];
  let W, H; const fit = () => { W = cv.width = innerWidth; H = cv.height = innerHeight; };
  fit(); addEventListener('resize', fit);
  const bubbles = [], parts = [];
  // Speed follows size (flotation physics): the big ones catch the small ones, so
  // coalescence happens by construction instead of by coincidence. Own drift period per
  // bubble, as in the splash - shared periods made neighbours sway in step and never meet.
  const spawn = () => { const r = 8 + Math.random() * 22;
    bubbles.push({ x: Math.random() * W, y: H + 24, r: r,
      v: 0.55 + r * 0.055 + Math.random() * 0.25,
      c: COLS[Math.floor(Math.random() * COLS.length)], ph: Math.random() * 6.28,
      fr: 700 + Math.random() * 500 }); };
  for (let i = 0; i < 60; i++) spawn();
  // 55ms because the population is set by the spawn rate, not the cap: bubbles leave
  // through the top and every collision eats one. The cap guards the unfocused-window
  // case described in the splash - rAF freezes while this timer keeps running.
  setInterval(() => {
    if (document.getElementById('froth-boot') && bubbles.length < 110) spawn();
  }, 55);
  function burst(x, y, col) { if (parts.length > 320) return;   // the engine needs the CPU
    for (let i = 0; i < 16; i++)
    parts.push({ x, y, vx: (Math.random() - 0.5) * 4, vy: (Math.random() - 0.5) * 4,
                 life: 1, c: col }); }
  (function loop(t) {
    if (!document.getElementById('froth-boot')) return;
    cx.clearRect(0, 0, W, H);
    for (let i = bubbles.length - 1; i >= 0; i--) {
      const b = bubbles[i];
      b.y -= b.v; b.x += Math.sin(t / b.fr + b.ph) * 1.8;
      for (let j = i - 1; j >= 0; j--) {
        const o = bubbles[j], dx = b.x - o.x, dy = b.y - o.y;
        // 0.95 = burst on contact (0.55 demanded a quarter of overlap first)
        if (dx * dx + dy * dy < (b.r + o.r) * (b.r + o.r) * 0.95) {
          burst((b.x + o.x) / 2, (b.y + o.y) / 2, b.c);
          b.r = Math.min(b.r * 1.10, 40);          // coalescence: survivor grows
          bubbles.splice(j, 1); i--;
        }
      }
      if (b.y < -40) { bubbles.splice(i, 1); continue; }
      cx.globalAlpha = 0.55; cx.fillStyle = b.c;
      cx.beginPath(); cx.arc(b.x, b.y, b.r, 0, 6.29); cx.fill();
      cx.globalAlpha = 0.3; cx.fillStyle = '#fff';
      cx.beginPath(); cx.arc(b.x - b.r * 0.3, b.y - b.r * 0.3, b.r * 0.28, 0, 6.29);
      cx.fill();
    }
    for (let i = parts.length - 1; i >= 0; i--) {
      const p = parts[i]; p.x += p.vx; p.y += p.vy; p.life -= 0.025;
      if (p.life <= 0) { parts.splice(i, 1); continue; }
      cx.globalAlpha = p.life; cx.fillStyle = p.c;
      cx.fillRect(p.x, p.y, 3, 3);
    }
    cx.globalAlpha = 1;
    requestAnimationFrame(loop);
  })(0);
  const t0 = Date.now();
  let sawRunning = false;
  const iv = setInterval(() => {
    const el = (Date.now() - t0) / 1000;
    const bar = document.getElementById('froth-boot-bar');
    if (bar) bar.style.width = Math.min(95, 60 + el / 45 * 35) + '%';
    // The sidebar paints a button BEFORE the app runs SPECTER for the cluster
    // subtitles, so a generic button check faded the overlay while the MAIN
    // area was still blank (the black screen). Wait for real MAIN content AND
    // for Streamlit to be idle (its "Running" status widget gone) - that only
    // happens after the heavy work finishes.
    const running = document.querySelector('[data-testid="stStatusWidget"]');
    if (running) sawRunning = true;
    const mainContent = document.querySelector(
      '[data-testid="stMain"] [data-testid="stTabs"], ' +
      '[data-testid="stMain"] .stTabs, ' +
      '[data-testid="stMain"] [data-testid="stButton"]');
    // ready = main content is painted AND Streamlit is no longer running
    // (or, if the status widget was never seen, a small time floor as fallback)
    const ready = mainContent && !running && (sawRunning || el > 6);
    if (ready || el > 240) {
      clearInterval(iv);
      if (bar) bar.style.width = '100%';
      setTimeout(() => { d.style.opacity = '0';
                         setTimeout(() => d.remove(), 800); }, 400);
    }
  }, 250);
})();
"""


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _http_ready(port: int) -> bool:
    """The port opens before Streamlit can serve pages; wait for a real HTTP 200."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _set_windows_icon() -> None:
    """Give the window and taskbar the Froth icon (pywebview has no icon arg on
    Windows: the icon comes from the .exe, i.e. pythonw's - so we set it by hand
    with the Win32 API once the window exists)."""
    if sys.platform != "win32" or not ICON.exists():
        return
    try:
        user32 = ctypes.windll.user32
        # The window is created on the GUI thread AFTER this thread starts:
        # retry until it exists (the first version looked once, found nothing,
        # and the icon silently never appeared).
        hwnd = 0
        for _ in range(40):                           # up to ~10 s
            hwnd = user32.FindWindowW(None, "Froth")
            if hwnd:
                break
            time.sleep(0.25)
        if not hwnd:
            return
        LR_LOADFROMFILE, IMAGE_ICON, WM_SETICON = 0x10, 1, 0x0080
        for size, which in ((16, 0), (32, 1)):        # ICON_SMALL, ICON_BIG
            hicon = user32.LoadImageW(None, str(ICON), IMAGE_ICON,
                                      size, size, LR_LOADFROMFILE)
            if hicon:
                user32.SendMessageW(hwnd, WM_SETICON, which, hicon)
    except Exception:
        pass                                          # cosmetic: never block startup


def _launch_ollama() -> None:
    """Zero-friction LLM polish (Batman: 'ollama launch'): if Ollama is installed
    but its server is not up, start it hidden so the Review tab's polish panel
    just works. Best-effort - Froth never depends on it."""
    if _port_open(11434):
        return                                        # already serving
    exe = Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"
    if not exe.exists():
        return                                        # not installed: nothing to do
    try:
        subprocess.Popen(
            [str(exe), "serve"],
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except Exception:
        pass                                          # polish panel will say so


def main() -> None:
    if sys.platform == "win32":
        try:  # own taskbar identity (otherwise Windows groups us under "Python")
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Froth.Desktop")
        except Exception:
            pass
    _launch_ollama()

    server = None
    if not _port_open(PORT):                      # reuse an already-running app if any
        # sys.executable = whichever Python launched us (the .venv OR the portable
        # runtime): the same file works in both worlds without hardcoded paths.
        server = subprocess.Popen(
            [sys.executable, "-m", "streamlit",
             "run", str(ROOT / "app.py"),
             "--server.headless", "true", "--server.port", str(PORT)],
            cwd=str(ROOT),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        atexit.register(server.terminate)         # window closes -> engine stops

    # Show the animated splash IMMEDIATELY (dark background_color kills the white
    # flash between pages); a background thread swaps in the app when it is ready.
    window = webview.create_window("Froth", html=SPLASH, width=1360, height=900,
                                   min_size=(900, 600), background_color="#18181b")
    swapping = {"to_app": False}

    def _stage(msg: str) -> None:
        try:
            window.evaluate_js(f"setStage({json.dumps(msg)})")
        except Exception:
            pass                                  # splash not painted yet: harmless

    def _on_loaded():
        # Fires for every navigation (splash included) - only dress the app page.
        if swapping["to_app"]:
            try:
                window.evaluate_js(_BOOT_OVERLAY_JS)
            except Exception:
                pass

    def _swap_when_ready():
        _set_windows_icon()
        deadline = time.time() + 240              # first run loads the model: be patient
        _stage("starting the local engine…")
        while time.time() < deadline and not _port_open(PORT):
            time.sleep(0.5)
        _stage("engine is up - loading the interface…")
        while time.time() < deadline and not _http_ready(PORT):
            time.sleep(0.5)
        if time.time() >= deadline:
            window.load_html("<h2 style='color:#fafafa;background:#18181b;height:100%;"
                             "display:flex;align-items:center;justify-content:center'>"
                             "Froth engine did not start - check the installation.</h2>")
            return
        swapping["to_app"] = True                 # the loaded handler takes it from here
        window.load_url(f"http://127.0.0.1:{PORT}")

    window.events.loaded += _on_loaded
    threading.Thread(target=_swap_when_ready, daemon=True).start()
    webview.start()


if __name__ == "__main__":
    main()
