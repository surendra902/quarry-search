import sys
import os
import json

# Ensure search_task directory is in pythonpath
sys.path.insert(0, os.path.dirname(__file__))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from quarry.engine import QuarryEngine
from quarry.extractors import extract_code_from_url

def main():
    if len(sys.argv) < 2:
        print("Usage: python lookup_source.py <referral_link_or_code>")
        print("Example: python lookup_source.py https://claude.ai/referral/YWAsr_1fbA")
        print("Example: python lookup_source.py PFQOnxQmRQ")
        sys.exit(1)

    target = sys.argv[1].strip()
    code = extract_code_from_url(target)
    
    print("=" * 70)
    print(" QUARRY SEARCH — ORIGINAL SOURCE POST FINDER")
    print("=" * 70)
    print(f"Target Input: {target}")
    print(f"Extracted Code: {code}")
    print("-" * 70)

    engine = QuarryEngine()
    result = engine.lookup(code)

    if result:
        print("\n[SUCCESS] Original Public Source Post Found!")
        print(f"  Referral Code:    {result['referral_code']}")
        print(f"  Referral URL:     {result['url']}")
        print(f"  Platform:         {result['platform']}")
        print(f"  Source Post URL:  {result['source_url']}")
        print(f"  Author:           {result.get('author') or 'Unknown'}")
        print(f"  Publication Time: {result.get('published_at') or 'Unknown'}")
        print(f"  Evidence Snippet: {result.get('evidence_snippet') or 'None'}")
        print(f"  Cached in DB:     {result.get('cached', False)}")
        print(f"  Discovered At:    {result.get('discovered_at')}")
    else:
        print("\n[NOT FOUND] No public source post located in indexed channels or database.")
        print("Investigation Audit:")
        print("  - Target referral code is not recorded in local Quarry database.")
        print("  - Live multi-platform search (GitHub, HackerNews, Reddit, Web Dorks) yielded 0 public matches.")
        print("  - Cause: Link may be ephemeral (Claude Guest Pass), shared in private channels (DMs/Discord),")
        print("    or auto-moderated/deleted before search engine crawlers could index it.")

if __name__ == "__main__":
    main()
