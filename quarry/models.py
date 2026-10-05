from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime

@dataclass
class ReferralRecord:
    referral_code: str
    url: str
    platform: str
    source_url: str
    author: Optional[str] = None
    published_at: Optional[str] = None
    discovered_at: Optional[str] = None
    evidence_snippet: Optional[str] = None
    status: str = "unknown"  # valid, redeemed, expired, invalid, unknown

    def to_dict(self):
        d = asdict(self)
        if not d.get("discovered_at"):
            d["discovered_at"] = datetime.utcnow().isoformat() + "Z"
        return d
