"""
Muse 2 per Bluetooth verbinden und LSL-Stream starten.
Dieses Script laufen lassen, dann app.py in einem zweiten Terminal starten.
"""

from muselsl import list_muses, stream

muses = list_muses()
if not muses:
    print("❌ Keine Muse gefunden — Bluetooth an?")
    raise SystemExit(1)

print(f"✅ Gefunden: {muses[0].get('name', 'Muse')}")
stream(muses[0]["address"])

