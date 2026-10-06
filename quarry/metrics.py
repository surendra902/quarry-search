"""Observed daily yield, separated from inventory and uncertain publication dates."""
from datetime import datetime, timedelta, timezone


def _time(value):
    try:
        date = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return date.astimezone(timezone.utc) if date.tzinfo else None
    except (TypeError, ValueError):
        return None


def publication_time(row):
    basis = (row.get('timestamp_basis') or '').lower()
    # These dates describe scans, indexes, git metadata, profiles or retired stock,
    # not the publication time of a new source post containing the referral.
    if not basis or any(word in basis for word in ('scan', 'commit', 'indexed', 'footer', 'retired', 'archived', 'directory')):
        return None
    return _time(row.get('published_at'))


def yield_summary(records, now=None, started_at=None, days=7):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Yield reporting requires an explicit timezone.')
    now = now.astimezone(timezone.utc)
    days = max(1, min(30, days))
    grouped = {}
    for row in records:
        grouped.setdefault(row['referral_code'], []).append(row)
    output = []
    for offset in range(days):
        day = (now - timedelta(days=offset)).date()
        counts = {'date': day.isoformat(), 'first_observed_unique': 0, 'recent_dated_candidates': 0,
                  'historical_dated': 0, 'unknown_publication': 0, 'unverified_candidates': 0}
        for rows in grouped.values():
            seen = [t for r in rows if (t := _time(r.get('discovered_at'))) is not None and t <= now]
            if not seen or min(seen).date() != day:
                continue
            counts['first_observed_unique'] += 1
            verified = [r for r in rows if r.get('evidence_kind') == 'direct_match']
            if not verified:
                counts['unverified_candidates'] += 1
                continue
            dates = [t for r in verified if (t := publication_time(r)) is not None and t <= now]
            # Inventory/scan dates cannot prove fresh publication, but a prior
            # dated observation still disproves a same-day 'new' repost.
            prior_inventory = any(
                any(word in (r.get('timestamp_basis') or '').lower() for word in ('archived', 'retired', 'directory', 'scan'))
                and (t := _time(r.get('published_at') or r.get('source_updated_at'))) is not None
                and t.date() < day
                for r in rows)
            if prior_inventory:
                counts['historical_dated'] += 1
            elif not dates:
                counts['unknown_publication'] += 1
            elif min(dates).date() == day:
                counts['recent_dated_candidates'] += 1
            else:
                counts['historical_dated'] += 1
        output.append(counts)
    start = _time(started_at)
    complete = [day for day in output if day['date'] < now.date().isoformat() and start and day['date'] > start.date().isoformat()]
    return {'timezone': 'UTC', 'as_of': now.isoformat().replace('+00:00', 'Z'), 'today': output[0],
            'days': output, 'target_daily_min': 30, 'target_daily_goal': 50,
            'measurement_started_at': started_at, 'complete_days_available': len(complete),
            'target_verified': len(complete) >= 7 and all(d['recent_dated_candidates'] >= 30 for d in complete[:7]),
            'definition': 'New to this stored history, with a source-reported publication date on the same UTC day. Old reposts, scans, directory stock and unknown dates do not establish fresh daily yield. This is not a future-volume or redemption guarantee.'}
