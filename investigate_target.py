import os
import json
import time
import urllib.parse
import requests

TARGET_CODE = "PFQOnxQmRQ"
TARGET_URL = f"https://claude.ai/referral/{TARGET_CODE}"
EVIDENCE_DIR = os.path.join(os.path.dirname(__file__), "evidence")
os.makedirs(EVIDENCE_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

audit_log = []

def log_event(source, query, status, count, details, raw_data=None, filename=None):
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": source,
        "query": query,
        "status": status,
        "matches_found": count,
        "details": details,
    }
    audit_log.append(entry)
    print(f"[{source}] Query: '{query}' -> Status: {status} | Matches: {count} | {details}")
    if filename and raw_data is not None:
        file_path = os.path.join(EVIDENCE_DIR, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            if isinstance(raw_data, (dict, list)):
                json.dump(raw_data, f, indent=2)
            else:
                f.write(str(raw_data))

# 1. Direct Target Probe
def check_direct_url():
    print("\n--- 1. Probing Target Referral URL Directly ---")
    try:
        session = requests.Session()
        resp = session.get(TARGET_URL, headers=HEADERS, timeout=15, allow_redirects=True)
        redirect_chain = [r.url for r in resp.history] + [resp.url]
        content_preview = resp.text[:1000]
        
        info = {
            "status_code": resp.status_code,
            "final_url": resp.url,
            "redirect_history": redirect_chain,
            "headers": dict(resp.headers),
            "cookies": resp.cookies.get_dict(),
            "content_length": len(resp.text),
            "contains_target_code": TARGET_CODE in resp.text,
        }
        log_event(
            "Direct HTTP Probe",
            TARGET_URL,
            "OK",
            1 if resp.status_code == 200 else 0,
            f"HTTP {resp.status_code}, Final URL: {resp.url}, Redirects: {len(resp.history)}",
            info,
            "direct_probe.json"
        )
    except Exception as e:
        log_event("Direct HTTP Probe", TARGET_URL, "ERROR", 0, str(e))

# 2. Reddit Search API
def check_reddit():
    print("\n--- 2. Checking Reddit Public API ---")
    reddit_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    }
    queries = [
        ("Reddit Search (Code)", f"https://www.reddit.com/search.json?q={TARGET_CODE}&sort=new&limit=25"),
        ("Reddit Search (URL)", f"https://www.reddit.com/search.json?q=\"{urllib.parse.quote(TARGET_URL)}\"&sort=new&limit=25"),
        ("Reddit Comments (Code)", f"https://www.reddit.com/search.json?q={TARGET_CODE}&type=comment&sort=new&limit=25"),
    ]
    for label, url in queries:
        try:
            resp = requests.get(url, headers=reddit_headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                children = data.get("data", {}).get("children", [])
                log_event("Reddit API", label, "200 OK", len(children), f"Found {len(children)} posts", data, f"reddit_{label.replace(' ', '_').lower()}.json")
            else:
                log_event("Reddit API", label, f"HTTP {resp.status_code}", 0, f"Returned status {resp.status_code}")
        except Exception as e:
            log_event("Reddit API", label, "ERROR", 0, str(e))
        time.sleep(1)

# 3. PullPush / Pushshift (Reddit Archive)
def check_pullpush():
    print("\n--- 3. Checking PullPush (Reddit Historic Archive API) ---")
    endpoints = [
        ("PullPush Submission", f"https://api.pullpush.io/reddit/search/submission/?q={TARGET_CODE}"),
        ("PullPush Comment", f"https://api.pullpush.io/reddit/search/comment/?q={TARGET_CODE}"),
    ]
    for label, url in endpoints:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", [])
                log_event("PullPush API", label, "200 OK", len(items), f"Returned {len(items)} items", data, f"pullpush_{label.replace(' ', '_').lower()}.json")
            else:
                log_event("PullPush API", label, f"HTTP {resp.status_code}", 0, f"Returned status {resp.status_code}")
        except Exception as e:
            log_event("PullPush API", label, "ERROR", 0, str(e))

# 4. HackerNews Algolia Search API
def check_hackernews():
    print("\n--- 4. Checking Hacker News Algolia Search API ---")
    queries = [
        ("HN Search Code", f"https://hn.algolia.com/api/v1/search?query={TARGET_CODE}&tags=(story,comment)"),
        ("HN Search URL", f"https://hn.algolia.com/api/v1/search?query=\"{urllib.parse.quote(TARGET_URL)}\"&tags=(story,comment)"),
    ]
    for label, url in queries:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("hits", [])
                log_event("HackerNews Algolia", label, "200 OK", len(hits), f"Returned {len(hits)} hits", data, f"hn_{label.replace(' ', '_').lower()}.json")
            else:
                log_event("HackerNews Algolia", label, f"HTTP {resp.status_code}", 0, f"Returned status {resp.status_code}")
        except Exception as e:
            log_event("HackerNews Algolia", label, "ERROR", 0, str(e))

# 5. GitHub Public API
def check_github():
    print("\n--- 5. Checking GitHub Public Search API ---")
    gh_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/vnd.github.v3+json"
    }
    endpoints = [
        ("GitHub Issues", f"https://api.github.com/search/issues?q={TARGET_CODE}"),
        ("GitHub Code", f"https://api.github.com/search/code?q={TARGET_CODE}"),
        ("GitHub Commits", f"https://api.github.com/search/commits?q={TARGET_CODE}"),
        ("GitHub Repos", f"https://api.github.com/search/repositories?q={TARGET_CODE}"),
    ]
    for label, url in endpoints:
        try:
            resp = requests.get(url, headers=gh_headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                count = data.get("total_count", 0)
                items = data.get("items", [])
                log_event("GitHub API", label, "200 OK", count, f"Total count: {count}", data, f"github_{label.replace(' ', '_').lower()}.json")
            elif resp.status_code == 403:
                log_event("GitHub API", label, "403 Rate Limited", 0, "Rate limit reached for unauthenticated search")
            else:
                log_event("GitHub API", label, f"HTTP {resp.status_code}", 0, f"Returned status {resp.status_code}")
        except Exception as e:
            log_event("GitHub API", label, "ERROR", 0, str(e))
        time.sleep(1)

# 6. Wayback Machine CDX API
def check_wayback():
    print("\n--- 6. Checking Wayback Machine CDX API ---")
    endpoints = [
        ("Wayback CDX Exact", f"https://web.archive.org/cdx/search/cdx?url=claude.ai/referral/{TARGET_CODE}&output=json"),
        ("Wayback CDX Wildcard", f"https://web.archive.org/cdx/search/cdx?url=*claude.ai/referral/{TARGET_CODE}*&output=json"),
        ("Wayback Availability", f"https://archive.org/wayback/available?url=https://claude.ai/referral/{TARGET_CODE}"),
    ]
    for label, url in endpoints:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    count = max(0, len(data) - 1) if isinstance(data, list) else (1 if data.get("archived_snapshots") else 0)
                    log_event("Wayback Machine", label, "200 OK", count, f"Returned {count} snapshots", data, f"wayback_{label.replace(' ', '_').lower()}.json")
                except:
                    log_event("Wayback Machine", label, "200 OK", 0, "No JSON parsed", resp.text)
            else:
                log_event("Wayback Machine", label, f"HTTP {resp.status_code}", 0, f"Returned status {resp.status_code}")
        except Exception as e:
            log_event("Wayback Machine", label, "ERROR", 0, str(e))

# 7. DuckDuckGo Search Probing
def check_duckduckgo():
    print("\n--- 7. Checking DuckDuckGo HTML & Instant Answer ---")
    dorks = [
        f'"{TARGET_CODE}"',
        f'"claude.ai/referral/{TARGET_CODE}"',
        f'site:twitter.com "{TARGET_CODE}"',
        f'site:x.com "{TARGET_CODE}"',
        f'site:reddit.com "{TARGET_CODE}"',
        f'site:t.me "{TARGET_CODE}"',
        f'site:youtube.com "{TARGET_CODE}"',
        f'site:linkedin.com "{TARGET_CODE}"',
        f'site:facebook.com "{TARGET_CODE}"',
        f'site:threads.net "{TARGET_CODE}"',
    ]
    for dork in dorks:
        try:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(dork)}"
            resp = requests.post("https://html.duckduckgo.com/html/", data={"q": dork}, headers=HEADERS, timeout=12)
            if resp.status_code == 200:
                has_no_results = "No results." in resp.text or "not found" in resp.text.lower()
                # Check for link occurrences in response
                matches = resp.text.count(TARGET_CODE)
                log_event(
                    "DuckDuckGo Query",
                    dork,
                    "200 OK",
                    matches if not has_no_results else 0,
                    f"Result page received. Matches: {matches}. 'No results': {has_no_results}",
                    resp.text if matches > 0 else None,
                    f"ddg_{abs(hash(dork))}.html" if matches > 0 else None
                )
            else:
                log_event("DuckDuckGo Query", dork, f"HTTP {resp.status_code}", 0, f"Status {resp.status_code}")
        except Exception as e:
            log_event("DuckDuckGo Query", dork, "ERROR", 0, str(e))
        time.sleep(1.5)

if __name__ == "__main__":
    check_direct_url()
    check_reddit()
    check_pullpush()
    check_hackernews()
    check_github()
    check_wayback()
    check_duckduckgo()

    with open(os.path.join(EVIDENCE_DIR, "investigation_summary.json"), "w", encoding="utf-8") as f:
        json.dump(audit_log, f, indent=2)
    print("\n--- Investigation Complete. Summary saved to evidence/investigation_summary.json ---")
