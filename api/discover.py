import sys
import os
import json
from http.server import BaseHTTPRequestHandler

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from quarry.engine import QuarryEngine
from quarry.storage import QuarryStorage

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        storage = QuarryStorage()
        engine = QuarryEngine(storage=storage)
        summary = engine.discover(limit_per_source=20)
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(summary).encode("utf-8"))

    def do_GET(self):
        # Allow GET trigger as well
        self.do_POST()

    def log_message(self, format, *args):
        pass
