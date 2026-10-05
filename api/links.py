import sys
import os
import json
from http.server import BaseHTTPRequestHandler

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from quarry.storage import QuarryStorage

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        storage = QuarryStorage()
        links = storage.list_links(limit=100)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(links).encode("utf-8"))

    def log_message(self, format, *args):
        pass
