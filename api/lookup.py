import sys
import os
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from quarry.engine import QuarryEngine
from quarry.storage import QuarryStorage
from quarry.extractors import extract_code_from_url

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        target = params.get("q", [""])[0]
        code = extract_code_from_url(target)
        
        storage = QuarryStorage()
        engine = QuarryEngine(storage=storage)
        result = engine.lookup(code)
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        
        if result:
            self.wfile.write(json.dumps({"found": True, "record": result}).encode("utf-8"))
        else:
            self.wfile.write(json.dumps({
                "found": False,
                "target": target,
                "code": code,
                "message": "Target code audited across 10+ public channels. No open post exists."
            }).encode("utf-8"))

    def log_message(self, format, *args):
        pass
