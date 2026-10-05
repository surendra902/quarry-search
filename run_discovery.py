import sys
import os
import json

# Ensure search_task directory is in pythonpath
sys.path.insert(0, os.path.dirname(__file__))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from quarry.engine import QuarryEngine

def main():
    print("=" * 70)
    print(" QUARRY SEARCH — LIVE CLAUDE REFERRAL DISCOVERY ENGINE")
    print("=" * 70)
    
    engine = QuarryEngine()
    print("[+] Initializing multi-source discovery sweep...")
    summary = engine.discover(limit_per_source=30)
    
    print("\n" + "=" * 70)
    print(" DISCOVERY RESULTS SUMMARY")
    print("=" * 70)
    print(f"Timestamp:                 {summary['timestamp']}")
    print(f"Total Candidates Found:    {summary['total_candidates_found']}")
    print(f"New Unique Links Saved:    {summary['new_unique_links_saved']}")
    print(f"Total Links Stored in DB:  {summary['total_links_in_db']}")
    print("\nPer-Source Breakdown:")
    for source, count in summary["source_breakdown"].items():
        print(f"  - {source:15}: {count} candidates")

    if summary["new_records"]:
        print("\n" + "=" * 70)
        print(" NEWLY DISCOVERED REFERRAL LINKS & ORIGINAL SOURCES")
        print("=" * 70)
        for i, r in enumerate(summary["new_records"], 1):
            print(f"\n[{i}] Code: {r['referral_code']}")
            print(f"    Referral URL:     {r['url']}")
            print(f"    Platform:         {r['platform']}")
            print(f"    Source Post URL:  {r['source_url']}")
            print(f"    Author:           {r.get('author') or 'Unknown'}")
            print(f"    Publication Time: {r.get('published_at') or 'Unknown'}")
            print(f"    Evidence Snippet: {r.get('evidence_snippet') or 'None'}")
    else:
        print("\nNo brand-new unique links discovered in this specific sweep (links already in database).")

if __name__ == "__main__":
    main()
