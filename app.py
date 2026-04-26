"""Muse LSL → bandpower → WebSocket → Browser (single file).

This is the "web" student repo.
"""

import asyncio
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import websockets
from muselsl import list_muses, stream
from pylsl import StreamInlet, resolve_byprop


HTTP_HOST = "127.0.0.1"
HTTP_PORT = 3000
WS_HOST = "127.0.0.1"
WS_PORT = 8765

FS = 256
WINDOW_SECONDS = 1.0
WINDOW_SAMPLES = int(FS * WINDOW_SECONDS)
HOP_SAMPLES = max(1, FS // 4)  # ~4 updates/second


INDEX_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <meta http-equiv="Cache-Control" content="no-store" />
    <meta http-equiv="Pragma" content="no-cache" />
    <meta http-equiv="Expires" content="0" />
    <title>Neurointerfaces Web</title>
    <style>
      html, body { height: 100%; margin: 0; background: #000; overflow: hidden; }
      canvas { display: block; }
    </style>
  </head>
  <body>
    <canvas id="c"></canvas>
    <script>
      const WS_URL = `ws://${location.hostname}:__WS_PORT__`;
      const state = { alpha: 0.5, beta: 0.5, theta: 0.5, delta: 0.5, connected: false };
      const MAX_POINTS = 360; // ~90s at 4Hz
      const series = {
        alpha: Array(MAX_POINTS).fill(0.5),
        beta:  Array(MAX_POINTS).fill(0.5),
        theta: Array(MAX_POINTS).fill(0.5),
        delta: Array(MAX_POINTS).fill(0.5),
      };

      function pushPoint() {
        for (const k of ["alpha","beta","theta","delta"]) {
          series[k].push(state[k]);
          if (series[k].length > MAX_POINTS) series[k].shift();
        }
      }

      function connect() {
        const ws = new WebSocket(WS_URL);
        ws.onopen = () => { state.connected = true; };
        ws.onclose = () => { state.connected = false; setTimeout(connect, 1000); };
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data);
            const v = Array.isArray(msg.value) ? (msg.value[0] ?? 0) : msg.value;
            if (msg.address.includes("alpha")) state.alpha = v;
            else if (msg.address.includes("beta")) state.beta = v;
            else if (msg.address.includes("theta")) state.theta = v;
            else if (msg.address.includes("delta")) state.delta = v;
            pushPoint();
          } catch {}
        };
      }
      connect();

      const canvas = document.getElementById("c");
      const ctx = canvas.getContext("2d");
      function resize() { canvas.width = innerWidth; canvas.height = innerHeight; }
      addEventListener("resize", resize); resize();

      function drawGrid(x, y, w, h) {
        ctx.strokeStyle = "rgba(255,255,255,0.08)";
        ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) {
          const yy = y + (h * i / 4);
          ctx.beginPath();
          ctx.moveTo(x, yy);
          ctx.lineTo(x + w, yy);
          ctx.stroke();
        }
      }

      function drawLine(values, x, y, w, h, color) {
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (let i = 0; i < values.length; i++) {
          const t = i / (values.length - 1);
          const xx = x + t * w;
          const v = Math.max(0, Math.min(1, values[i]));
          const yy = y + (1 - v) * h;
          if (i === 0) ctx.moveTo(xx, yy);
          else ctx.lineTo(xx, yy);
        }
        ctx.stroke();
      }

      function draw() {
        requestAnimationFrame(draw);
        const W = canvas.width, H = canvas.height;
        ctx.fillStyle = "rgba(8,8,10,1)";
        ctx.fillRect(0,0,W,H);

        const pad = 18;
        const top = 64;
        const x = pad;
        const y = top;
        const w = W - pad * 2;
        const h = H - top - pad;
        drawGrid(x, y, w, h);

        drawLine(series.delta, x, y, w, h, "rgba(168, 85, 247, 0.95)");
        drawLine(series.theta, x, y, w, h, "rgba(56, 189, 248, 0.95)");
        drawLine(series.alpha, x, y, w, h, "rgba(34, 197, 94, 0.95)");
        drawLine(series.beta,  x, y, w, h, "rgba(251, 146, 60, 0.95)");

        ctx.font = "13px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";
        ctx.fillStyle = state.connected ? "rgba(255,255,255,0.75)" : "rgba(255,255,255,0.35)";
        ctx.fillText(state.connected ? "● CONNECTED" : "○ DISCONNECTED", 16, 28);

        let lx = 16;
        const ly = 48;
        function label(text, value, color) {
          ctx.fillStyle = color;
          const s = `${text} ${value.toFixed(2)}`;
          ctx.fillText(s, lx, ly);
          lx += ctx.measureText(s).width + 16;
        }
        label("δ delta", state.delta, "rgba(168, 85, 247, 0.95)");
        label("θ theta", state.theta, "rgba(56, 189, 248, 0.95)");
        label("α alpha", state.alpha, "rgba(34, 197, 94, 0.95)");
        label("β beta",  state.beta,  "rgba(251, 146, 60, 0.95)");
      }
      draw();
    </script>
  </body>
</html>
"""


def _index_html() -> str:
    return INDEX_HTML_TEMPLATE.replace("__WS_PORT__", str(WS_PORT))


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path not in ("/", "/index.html"):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"not found")
            return
        body = _index_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


def _start_http() -> None:
    global HTTP_PORT
    last_err: Exception | None = None
    for port in range(HTTP_PORT, HTTP_PORT + 20):
        try:
            httpd = HTTPServer((HTTP_HOST, port), _Handler)
            HTTP_PORT = port
            print(f"🌐 UI: http://{HTTP_HOST}:{HTTP_PORT}")
            httpd.serve_forever()
            return
        except OSError as e:
            last_err = e
            continue
    raise RuntimeError(f"Kein freier HTTP-Port gefunden (ab {HTTP_PORT}). Letzter Fehler: {last_err}")


def _band_power(freqs: np.ndarray, power: np.ndarray, low: float, high: float) -> float:
    idx = (freqs >= low) & (freqs <= high)
    if not np.any(idx):
        return 0.0
    return float(np.mean(power[idx]))


def _relative_bandpowers(x: np.ndarray, fs: int) -> dict[str, float]:
    x = x.astype(np.float64) - float(np.mean(x))
    fft_vals = np.fft.rfft(x)
    fft_freq = np.fft.rfftfreq(len(x), d=1.0 / fs)
    power = (np.abs(fft_vals) ** 2).astype(np.float64)

    delta = _band_power(fft_freq, power, 1, 4)
    theta = _band_power(fft_freq, power, 4, 8)
    alpha = _band_power(fft_freq, power, 8, 12)
    beta = _band_power(fft_freq, power, 12, 30)
    total = delta + theta + alpha + beta
    if total <= 0:
        return {"delta": 0.0, "theta": 0.0, "alpha": 0.0, "beta": 0.0}
    return {"delta": delta / total, "theta": theta / total, "alpha": alpha / total, "beta": beta / total}


def _start_muse_lsl_stream() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    muses = list_muses()
    if not muses:
        raise RuntimeError("Keine Muse gefunden — Bluetooth an?")
    muse = muses[0]
    print(f"✅ Muse gefunden: {muse.get('name', 'Muse')} ({muse.get('address')})")
    stream(muse["address"])


async def _publish_from_lsl(clients: set[websockets.ServerConnection]) -> None:
    buffer: list[float] = []
    inlet: StreamInlet | None = None

    while True:
        if inlet is None:
            print("🔍 Warte auf LSL EEG-Stream (type=EEG)...")
            streams = await asyncio.to_thread(resolve_byprop, "type", "EEG")
            if not streams:
                await asyncio.sleep(0.5)
                continue
            inlet = StreamInlet(streams[0])
            print("✅ LSL verbunden.")

        try:
            for _ in range(32):
                sample, _ = inlet.pull_sample(timeout=0.0)
                if sample:
                    buffer.append(float(np.mean(sample)))

            if len(buffer) >= WINDOW_SAMPLES:
                x = np.array(buffer[:WINDOW_SAMPLES], dtype=np.float64)
                buffer = buffer[HOP_SAMPLES:]
                rel = _relative_bandpowers(x, FS)
                now = int(time.time() * 1000)

                msgs = [
                    {"address": "/muse/elements/alpha_relative", "value": [rel["alpha"]], "timestamp": now},
                    {"address": "/muse/elements/beta_relative", "value": [rel["beta"]], "timestamp": now},
                    {"address": "/muse/elements/theta_relative", "value": [rel["theta"]], "timestamp": now},
                    {"address": "/muse/elements/delta_relative", "value": [rel["delta"]], "timestamp": now},
                ]

                if clients:
                    payloads = [json.dumps(m) for m in msgs]
                    await asyncio.gather(
                        *[c.send(p) for c in clients for p in payloads],
                        return_exceptions=True,
                    )

            await asyncio.sleep(0.02)
        except Exception:
            inlet = None
            buffer = []
            await asyncio.sleep(0.5)


async def run_app(ws_port_start: int) -> None:
    global WS_PORT
    clients: set[websockets.ServerConnection] = set()

    async def handler(ws: websockets.ServerConnection):
        clients.add(ws)
        try:
            await ws.wait_closed()
        finally:
            clients.discard(ws)

    server = None
    last_err: Exception | None = None
    for port in range(ws_port_start, ws_port_start + 50):
        try:
            server = await websockets.serve(handler, WS_HOST, port)
            WS_PORT = port
            break
        except OSError as e:
            last_err = e
            continue

    if server is None:
        raise RuntimeError(f"Kein freier WebSocket-Port gefunden (ab {ws_port_start}). Letzter Fehler: {last_err}")

    print(f"🔌 WebSocket: ws://{WS_HOST}:{WS_PORT}")
    try:
        await _publish_from_lsl(clients)
    finally:
        server.close()
        await server.wait_closed()


def main() -> None:
    global HTTP_PORT, WS_PORT
    parser = argparse.ArgumentParser(description="Neurointerfaces Web: LSL → WebSocket → Canvas UI (single-file).")
    parser.add_argument("--http-port", type=int, default=3000)
    parser.add_argument("--ws-port", type=int, default=8765)
    parser.add_argument("--start-muse", action="store_true")
    args = parser.parse_args()

    HTTP_PORT = args.http_port
    WS_PORT = args.ws_port

    threading.Thread(target=_start_http, daemon=True).start()
    if args.start_muse:
        threading.Thread(target=_start_muse_lsl_stream, daemon=True).start()
    else:
        print("ℹ️ Muse-Streaming aus. Starte den LSL-Stream separat (z.B. `python stream.py`) oder nutze `--start-muse`.")

    asyncio.run(run_app(args.ws_port))


if __name__ == "__main__":
    main()

