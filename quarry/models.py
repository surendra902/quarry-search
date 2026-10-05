from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


@dataclass
class ReferralRecord:
    referral_code: str
    url: str
    platform: str
    source_url: str
    author: Optional[str] = None
    published_at: Optional[str] = None
    discovered_at: Optional[str] = field(default_factory=utc_now)
    evidence_snippet: Optional[str] = None
    status: str = 'unknown'
    evidence_kind: str = 'legacy_unverified'
    source_updated_at: Optional[str] = None
    timestamp_basis: Optional[str] = None

    def to_dict(self):
        if not self.discovered_at:
            self.discovered_at = utc_now()
        return asdict(self)
