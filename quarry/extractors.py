import re
import html
import urllib.parse
from typing import Set, Tuple, List

# Pattern matching claude referral URLs across raw text, markdown, HTML, and encoded entities
CLAUDE_REFERRAL_REGEX = re.compile(
    r'(?:https?://)?(?:www\.)?claude\.ai(?:&#x2F;|/|%2F)referral(?:&#x2F;|/|%2F)([a-zA-Z0-9_\-]{6,25})',
    re.IGNORECASE
)

def extract_referral_codes(text: str) -> List[Tuple[str, str]]:
    """
    Extracts all unique Claude referral links and codes from text.
    Returns list of tuples: (clean_canonical_url, referral_code)
    """
    if not text:
        return []
    
    # Pre-clean html entities and percent encodings
    decoded_text = html.unescape(text)
    decoded_text = urllib.parse.unquote(decoded_text)
    
    found: Set[str] = set()
    results = []
    
    for match in CLAUDE_REFERRAL_REGEX.finditer(decoded_text):
        code = match.group(1).strip()
        # Discard false positives or placeholder templates like 'XXXXXX', 'YOUR_CODE'
        if code.lower() in ("your_code", "xxxxxx", "placeholder", "referral_code", "xxxxxxxx"):
            continue
        if code not in found:
            found.add(code)
            canonical_url = f"https://claude.ai/referral/{code}"
            results.append((canonical_url, code))
            
    return results

def is_valid_referral_format(code_or_url: str) -> bool:
    """Checks if a code or URL matches the valid Claude referral pattern."""
    if "claude.ai/referral/" in code_or_url:
        match = CLAUDE_REFERRAL_REGEX.search(code_or_url)
        return bool(match)
    return bool(re.fullmatch(r'[a-zA-Z0-9_\-]{6,25}', code_or_url))

def extract_code_from_url(url_or_code: str) -> str:
    """Extracts just the referral code from either full URL or raw code."""
    url_or_code = url_or_code.strip()
    match = CLAUDE_REFERRAL_REGEX.search(url_or_code)
    if match:
        return match.group(1)
    if is_valid_referral_format(url_or_code):
        return url_or_code
    return url_or_code
