from pathlib import Path
import sys
root = str(Path(__file__).resolve().parent.parent)
if root not in sys.path:
    sys.path.insert(0, root)
from quarry.web import QuarryHandler

class handler(QuarryHandler):
    pass
