"""Syntactic referral parsing only. It never verifies redemption eligibility."""
import html
import re
from urllib.parse import unquote, urlsplit

# This is an input resource bound, not a claim about Anthropic's code length.
MAX_CODE_LENGTH = 128
_CODE = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')
_CANDIDATE = re.compile(r'''(?<![\w@./:-])(?:https?://|(?=claude\.ai/))[^\s<>"'`]+''', re.IGNORECASE)
_FULL_CANDIDATE = re.compile(r'''(?<![\w@./:-])https?://[^\s<>"'`]+''', re.IGNORECASE)
_PLACEHOLDERS = {'your_code', 'xxxxxx', 'placeholder', 'referral_code', 'xxxxxxxx', 'yyyy-mm-dd', 'example', 'sample', 'test'}
_DATE_PATTERN = re.compile(r'^(?:\d{4}[-_]\d{2}(?:[-_]\d{2})?|\d{2}[-_]\d{2})\Z')


def is_excluded_source(url):
    try:
        host = (urlsplit(url).hostname or '').lower().rstrip('.')
        return host in ('x.com', 'twitter.com') or host.endswith(('.x.com', '.twitter.com'))
    except (TypeError, ValueError):
        return False


def extract_code_from_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError('Enter a Claude referral URL or an unmodified referral code.')
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('Control characters are not allowed in referral input.')
    value = html.unescape(value.strip())
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('Encoded control characters are not allowed.')
    if _CODE.fullmatch(value):
        code = value
    else:
        if value.lower().startswith('claude.ai/'):
            value = 'https://' + value
        parts = urlsplit(value)
        if (parts.scheme not in ('http', 'https') or parts.hostname != 'claude.ai'
                or parts.username is not None or parts.password is not None
                or parts.port is not None or '\\' in value):
            raise ValueError('Referral URLs must use the exact claude.ai hostname.')
        path = unquote(parts.path)
        prefix = '/referral/'
        if not path.startswith(prefix):
            raise ValueError('Expected a /referral/ URL.')
        code = path[len(prefix):]
    if not _CODE.fullmatch(code) or code.lower() in _PLACEHOLDERS or _DATE_PATTERN.fullmatch(code):
        raise ValueError('Malformed, placeholder, or date pattern referral identifier.')
    return code


def is_valid_referral_format(value: str) -> bool:
    try:
        extract_code_from_url(value)
        return True
    except (ValueError, TypeError):
        return False


def extract_referral_codes(text: str):
    if not isinstance(text, str):
        return []
    decoded = html.unescape(text)
    # Parse URL boundaries before percent-decoding its path. Decoding the whole
    # text would turn encoded path characters into query/fragment delimiters.
    found = {}
    # A bare-URL Markdown label can otherwise greedily swallow its destination.
    matches = sorted([*_CANDIDATE.finditer(decoded), *_FULL_CANDIDATE.finditer(decoded)], key=lambda m: m.start())
    for match in matches:
        candidate = match.group().rstrip('.,;:!?)]}')
        try:
            code = extract_code_from_url(candidate)
        except (ValueError, TypeError):
            continue
        found.setdefault(code, ('https://claude.ai/referral/' + code, code))
    return list(found.values())
