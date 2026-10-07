"""Background runner for Quarry Harvester (runs silently via pythonw with no console window)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_file = open(logs_dir / "harvester_20min.log", "a", encoding="utf-8")
    sys.stdout = log_file
    sys.stderr = log_file

    from run_harvester import main
    sys.argv = [
        "run_harvester.py",
        "--oneshot",
        "--interval", "1200",
        "--export-snapshot", "data/snapshot.json",
        "--auto-push",
        "--heartbeat"
    ]
    try:
        main()
    finally:
        log_file.flush()
        log_file.close()
