# Quarry Search — free-source demo

A working demonstration of public Claude-referral discovery and evidence lookup. No paid API or hosting service is required or enabled for this demo.

## What the demo does

- Queries GitHub issues/PR bodies and commit messages, and Hacker News, through free public endpoints.
- Requires exact referral matches, preserves identifier case, and reports source evidence and available timestamps.
- Distinguishes verified source occurrences, search candidates and old unverified records. This does **not** establish pass validity or the original publisher.
- Reports blocked/rate-limited sources rather than treating errors as successful empty searches.
- Offers live lookup/sweep results alongside an explicitly labelled historical snapshot on Vercel.

## Run and verify locally

Use a project virtual environment, then:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py" -v
python test_suite.py
python run_discovery.py
python lookup_source.py YWAsr_1fbA
python lookup_source.py PFQOnxQmRQ
python demo_server.py 8080
```

Open http://127.0.0.1:8080. `demo.py` also launches the dashboard; `demo.py --auto` prints the real stored observations without canned source conclusions.

## Vercel behaviour

Vercel reads `data/snapshot.json` as a **read-only historical snapshot**. Live queries return results but do not pretend to save them into a shared `/tmp` database. The local CLI uses persistent SQLite and preserves multiple source occurrences per referral code.

Refresh the deployment snapshot explicitly from an actual source sweep:

```bash
python run_discovery.py --export-snapshot data/snapshot.json
```

The snapshot can contain old observations; it is not a list of newly published or currently redeemable links. Existing local data was preserved, with a pre-fix backup at `.audit/original-quarry.db`.

### API

- `GET /api/links?limit=100&offset=0` — stored snapshot/local observations; limit 1–500.
- `GET /api/status` — real totals, storage mode and configuration.
- `GET /api/lookup?q=<code-or-url>` — exact evidence lookup. Add `refresh=1` to recheck cached evidence.
- `POST /api/discover` — bounded free-source sweep. GET is not a write trigger.
- `GET /api/health` — service status.

Invalid inputs return JSON HTTP 400. A bounded per-instance concurrency limit and discovery cooldown protect the demo from accidental repeated clicks, but are not a global abuse-control guarantee.

## Optional scraping

The default deployed demo does not depend on browser scraping. To try the optional Scrapling web-search adapter locally:

```bash
python -m pip install -r requirements-scraping.txt
```

Then set `QUARRY_WEB_SEARCH=1` in the process environment. Search snippets are **candidates only**. Scrapling does not guarantee access through anti-bot blocks. Reddit is disabled by default and requires separate permission/access configuration. No paid source is automatically enabled.

## Deliberate demo limits

- No continuous collector, paid deployment, background Windows startup task, or cloud database is provisioned.
- The validator and Telegram notifier described in the original brief were not supplied in this repository; they are not configured. Source evidence is not referral eligibility.
- `PFQOnxQmRQ` is unresolved unless an exact verified occurrence is actually returned. A failed search cannot tell us that it was private or deleted.
- No promise of 50–100 links/day, internet-wide coverage, guaranteed original-source recovery or 24/7 uptime.
- One shared HTTP implementation and one dashboard template are used locally and on Vercel; there are no parallel copies of UI/business logic to drift apart.

Paid sources and production automation are deferred until the demo is accepted.
