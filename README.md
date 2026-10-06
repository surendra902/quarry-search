# Quarry Search — bounded free-web collector

Collects public Claude-referral evidence and preserves exact codes, source URLs and timestamps. It does **not** crawl the entire internet or validate redemption. **30–50 new codes/day is a target, not an established result.**

## Coverage

- GitHub public issues/PR bodies and commit messages; Hacker News.
- DEV.to article discovery followed by native article bodies; Qiita native search.
- Public RSS/Atom feeds and relevant article/topic follow-up on V2EX, PyTorchKR, zhaoJian and Dev Problems. Known discussion pages are also revisited.
- Public web directories. Active entries and archived stock are distinguished.
- URLScan observations are candidates only, not proof of a source post or publication time.

`data/web_sources.json` holds public entrypoints. The crawler rotates four seeds per run, follows at most three relevant children per feed/sitemap and reports unscanned entries. It checks robots, public IPs and same-host redirects; it stops on denial/challenges. Request/time limits mean coverage is deliberately partial. RSS discovery and sitemap parsing do not imply exhaustive website coverage.

**X/Twitter is excluded.** Reddit remains disabled unless explicitly configured. No private groups, login bypass, CAPTCHA bypass, or paid provider is enabled by default. Optional Exa/Tavily integrations and the unimplemented Apify placeholder require `QUARRY_ENABLE_PAID_SOURCES=1` as well as credentials.

## Run safely

```bash
python -m pip install -r requirements-scraping.txt
python -m unittest discover -s tests -p "test_*.py" -v
python test_suite.py
python run_harvester.py --dry-run
```

`--dry-run` uses `.audit/dry-run.db`, exports `.audit/dry-run-snapshot.json`, does not load `.env`, disables paid providers, sends no Telegram/Discord messages and does not poll the Telegram bot. It performs real public reads. Reuse the database for cross-run deduplication. Override paths with `--db` and `--export-snapshot` if needed.

For the existing operator-configured alerts and periodic local collector:

```bash
python run_harvester.py --oneshot --interval 1200
python run_harvester.py --interval 1200
```

Normal runs may send alerts using configured credentials. Alerts mean a link was newly observed in this database, not that it was issued today or remains redeemable. Archived directory entries and scan-only candidates are not broadcast.

## Scheduled collection

`.github/workflows/harvester.yml` requests a GitHub Actions run every 20 minutes. Runs are serialized and persist `data/snapshot.json`, the seed cursor and measurement start time. GitHub scheduling is best-effort, not 24/7 uptime. Manual workflow dispatch runs without notifications or paid providers, but still commits and pushes its updated snapshot. It is not a read-only operation. Scheduled runs retain the existing Telegram configuration.

The Vercel dashboard reads a **deployment snapshot**. Browser-triggered sweeps return live results but do not save them. An updated GitHub snapshot is visible on Vercel only after a deployment containing it; a workflow success alone does not prove that deployment happened.

## Daily accounting

`GET /api/status` includes `daily_yield` with UTC-day counts:

- First observed in stored history, deduplicated by exact code.
- Same-day source-dated candidates, separately from historical or unknown dates and unverified candidates.
- Measurement start time and complete days available.

Old reposts, scan times, directory stock and unknown dates cannot establish the daily target. Bootstrap inventory is not a measured daily rate. The target indicator requires seven complete measured days with at least 30 same-day candidates each. Even that is an observed sample, not a future-volume or redemption guarantee.

## Dashboard and API

```bash
python demo_server.py 8080
```

- `GET /api/links?limit=100&offset=0` — stored observations, limit 1–500.
- `GET /api/status` and `/api/health` — totals, source configuration and collector heartbeat.
- `GET /api/lookup?q=<code-or-url>` — exact evidence; `refresh=1` rechecks sources.
- `POST /api/discover` — bounded discovery, with per-source errors and limits.

Inputs are validated without changing identifiers. A match is the earliest evidenced occurrence among checked sources, not proof of the original publisher. HTTP 400 means bad input; blocked or failed source checks remain explicitly unresolved. The demo has per-instance concurrency/cooldown controls, not a global abuse-control guarantee.
