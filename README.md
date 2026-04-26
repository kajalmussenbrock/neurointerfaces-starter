# neurointerfaces-web

Single-file web visualization for Muse EEG bandpower.

Pipeline:

**Muse 2 (Bluetooth) → LSL (muselsl) → bandpower (numpy) → WebSocket → Browser Canvas**

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run (recommended: two terminals)

### Terminal A: start Muse → LSL

```bash
python stream.py
```

### Terminal B: start Web UI + WebSocket + analysis

```bash
python app.py
```

Open the printed `🌐 UI: http://127.0.0.1:30xx` URL.

## One-command mode

```bash
python app.py --start-muse
```

