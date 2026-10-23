import os
import pathlib
import sqlite3
import sys

# Ensure stdout handles non-ascii safely
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

db_path = pathlib.Path(os.environ["LOCALAPPDATA"]) / "SteadyDev" / "steadydev.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

snap = conn.execute("SELECT * FROM snapshots WHERE snapshot_id = 'snap-f1b8fc321dbf'").fetchone()
if snap:
    print("Snapshot found:")
    for k in snap.keys():
        print(f"  {k}: {snap[k]}")
    sess = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (snap["session_id"],)).fetchone()
    if sess:
        print("Session found:")
        for k in sess.keys():
            print(f"  {k}: {sess[k]}")
    findings = conn.execute("SELECT * FROM findings WHERE snapshot_id = 'snap-f1b8fc321dbf'").fetchall()
    print(f"Findings count: {len(findings)}")
    for f in findings:
        engine_val = f['engine'] if 'engine' in f.keys() else 'N/A'
        print(f"  [{f['category']}] {f['file_path']}: {f['title']} (engine: {engine_val})")
else:
    print("Snapshot snap-f1b8fc321dbf not found in DB.")
