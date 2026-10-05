from abc import ABC, abstractmethod
from typing import List, Optional
from quarry.models import ReferralRecord

class BaseSource(ABC):
    name: str = "base"

    @abstractmethod
    def discover_new(self, limit: int = 50) -> List[ReferralRecord]:
        """Discovers newly published referral links across this source."""
        pass

    @abstractmethod
    def find_original_source(self, referral_code: str) -> Optional[ReferralRecord]:
        """Searches specifically for the original post of a given referral code."""
        pass
