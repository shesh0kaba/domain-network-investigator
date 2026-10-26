"""Compare literal name snapshots within one profile; never execute source JavaScript.

python dictionary_diff.py current.json --previous oldest.json latest.json --out delta.json
Each snapshot needs profile_id, snapshot_id, entries:[{name,...}], and summary.
Previous snapshots must be supplied in chronological order (oldest first).
"""
import argparse
import json
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit


def key(name):
    # Preserve meaningful accents and punctuation. Aliases require separate evidence.
    return ' '.join(unicodedata.normalize('NFKC', name).casefold().split())


def names(snapshot):
    result = {}
    for entry in snapshot['entries']:
        name = entry['name']
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Every entry must have a nonempty literal name')
        result.setdefault(key(name), []).append(entry)
    return result


def compare(current, previous, registration_date_proxy=False):
    profile = current.get('profile_id')
    if not profile or any(p.get('profile_id') != profile for p in previous):
        raise ValueError('Snapshots must have the same explicit profile_id')
    ids = [p['snapshot_id'] for p in previous] + [current['snapshot_id']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate snapshot_id')
    curr = names(current)
    past = [names(p) for p in previous]
    last = past[-1] if past else {}
    ever = set().union(*(set(p) for p in past)) if past else set()
    summary = current['summary']
    same_bytes = bool(previous) and bool(summary.get('sha256')) and summary.get('sha256') == previous[-1]['summary'].get('sha256')
    if same_bytes and set(curr) != set(last):
        raise ValueError('Identical source bytes have different extracted names; reconcile parser/context before comparison')
    def rows(keys, new=False):
        out = []
        for k in sorted(keys):
            entries = curr.get(k, last.get(k))
            row = {'name': entries[0]['name'], 'entries': entries,
                   'source_url': summary.get('source_url'),
                   'observed_at': summary.get('retrieved_at')}
            if new and registration_date_proxy:
                row['name_created_at_proxy'] = summary.get('registration_utc')
                row['proxy_source_domain'] = urlsplit(summary.get('source_url', '')).hostname
                row['proxy_basis'] = 'registration of the domain hosting this newly observed dictionary entry'
                row['proxy_is_historical_creation_proof'] = False
            out.append(row)
        return out
    added = set(curr) - set(last)
    return {
        'profile_id': profile, 'snapshot_id': current['snapshot_id'],
        'is_first_baseline': not previous,
        'previous_snapshot_ids': ids[:-1],
        'source_url': summary.get('source_url'),
        'source_sha256': summary.get('sha256'),
        'same_source_bytes_as_previous': same_bytes,
        'registration_date_proxy_requested': registration_date_proxy,
        'counts': {'current_unique_normalized': len(curr), 'previous_unique_normalized': len(last),
                   'added_since_previous': len(added), 'new_to_profile_dictionary_history': len(set(curr)-ever),
                   'removed_since_previous': len(set(last)-set(curr)), 'reappeared': len(added & ever)},
        'added_since_previous': rows(added),
        'new_to_profile_dictionary_history': rows(set(curr)-ever, new=bool(previous)),
        'reappeared': rows(added & ever),
        'removed_since_previous': [{'name': last[k][0]['name'], 'previous_entries': last[k]} for k in sorted(set(last)-set(curr))],
        'normalization': 'NFKC + casefold + collapsed whitespace; accents/punctuation retained',
        'limitations': ['A dictionary is a discovery vocabulary, not proof of ownership or advertising for each entry.',
                       'A newly observed entry is not proof of first historical creation.',
                       'Registration-based date is a user-requested proxy; observation time is independent.',
                       'The first snapshot is a baseline, not evidence that all names were just created.']
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('current', type=Path)
    p.add_argument('--previous', nargs='*', type=Path, default=[])
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--registration-date-proxy', action='store_true', help='Only when requested: attach source-domain registration as a labeled proxy for new entries')
    a = p.parse_args()
    read = lambda path: json.loads(path.read_text(encoding='utf-8-sig'))
    if a.out.resolve() in {path.resolve() for path in [a.current] + a.previous}:
        p.error('--out must not overwrite an input snapshot')
    if a.out.exists():
        p.error('--out must be a new file; preserve prior comparisons')
    result = compare(read(a.current), [read(path) for path in a.previous], a.registration_date_proxy)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result['counts']))
