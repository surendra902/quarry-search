# Quarry Search — corrected demo audit

Baseline: `6e52e7ad99b93c8457bc175ebd614859528af627`.

The prior report's unsupported claims about private distribution, AutoModerator deletion, daily yields, exact delays, prices, and completeness are withdrawn. The current deliverable is the **free-source demo** documented in README.md, not a complete production harvesting system.

## Reproduced baseline findings

- All eight deployed records had `status=unknown` while the UI labelled them verified.
- `q=bad!` returned HTTP 500. A lookalike-host URL using `evilclaude.ai` returned cached success instead of being rejected.
- The original four tests passed without covering unsafe parsing, HTML injection, evidence mismatch, lost source occurrences or Vercel persistence.
- Lookup selected first search hits without sufficient exact evidence and falsely described them as original posts.
- Vercel `/tmp` SQLite did not provide shared durable persistence.
- No validator, Telegram notifier or continuous worker was present.

## Current verification

Regression tests cover parsing, exact source matching, storage, API behaviour and browser interactions. Run the documented commands to reproduce them. `.audit/` contains local baseline/live reports and is excluded from deployment. Test fixtures are not production seed data.

The requested token `PFQOnxQmRQ` remains unresolved unless live exact evidence establishes otherwise. No cause for its absence is asserted. Free sources can be blocked or rate limited, and all observed limitations are reported.

Cloud/paid deployment and continuous collection are intentionally outside the current demo scope. No paid service was provisioned.
