"""Read-only preflight checks for one isolated, unchanged workcell trial batch."""
import json
import math


HEARTBEAT_S = 0.2
HOME_SAMPLE_MAX_AGE_S = 1.0


def geometry_key(inventory):
    """Ignore dynamic presence, release and stamp, but retain every planning input."""
    cells = [{k: v for k, v in c.items() if k != 'present'} for c in inventory['cells']]
    data = {key: inventory[key] for key in ('v', 'scene', 'source', 'items', 'rail', 'targets', 'obstacles')}
    data['cells'] = sorted(cells, key=lambda c: c['cell'])
    return json.dumps(data, sort_keys=True, allow_nan=False)


def plan_cache_payload(entries, source, computed_generation, live_generation):
    """Producer snapshot. None if inventory moved on before publish."""
    if computed_generation != live_generation:
        return None
    ok = [cid for cid, entry in entries.items() if getattr(entry, 'steps', None) is not None]
    failed = {cid: entry.why for cid, entry in entries.items() if getattr(entry, 'steps', None) is None}
    return {'solved': len(ok), 'total': len(entries), 'failed': failed, 'source': source,
            'generation': computed_generation, 'ready': True}


def plan_cache_invalidate(source, generation):
    """Latched not-ready after the cache is cleared for a new inventory source."""
    return {'solved': 0, 'total': 0, 'failed': {}, 'source': source, 'generation': generation, 'ready': False}


def cache_ready(cache, inventory):
    """Require a complete /m0609/arm/plan_cache for this inventory source.

    Inventory may republish after the cache; do not compare receipt times.
    An invalidate payload (ready false) is never treated as ready.
    """
    if not cache or not inventory or cache.get('ready') is False:
        return False
    if cache.get('source') != inventory.get('source'):
        return False
    solved, total, failed = cache.get('solved'), cache.get('total'), cache.get('failed')
    if (not isinstance(solved, int) or not isinstance(total, int) or not isinstance(failed, dict)
            or total != len(inventory['cells']) or solved+len(failed) != total):
        return False
    ids = {cell['cell'] for cell in inventory['cells']}
    if not set(failed).issubset(ids):
        return False
    eligible = [c for c in inventory['cells'] if c['type'] == 'cylinder' and c['item'] == 'drug-amox'
                and c['present'] and c['cell'] not in failed]
    return len({c['shelf'] for c in eligible}) >= 3


def home_confirmed(samples, result_time, now, heartbeat_s=HEARTBEAT_S, max_age_s=HOME_SAMPLE_MAX_AGE_S):
    """Use a fresh at_home sample. Stale true is not a return-home proof.

    samples are (monotonic_wall, value). A true sample from the same spin as the
    result is accepted after one heartbeat if that sample is still within max_age_s.
    """
    if not samples or not math.isfinite(result_time) or not math.isfinite(now):
        return False

    def usable(sample):
        return bool(sample[1]) and 0 <= now-sample[0] <= max_age_s

    after = [sample for sample in samples if sample[0] >= result_time]
    if after:
        return usable(after[-1])
    if now-result_time < heartbeat_s:
        return False
    before = [sample for sample in samples if result_time-heartbeat_s <= sample[0] < result_time]
    return bool(before) and usable(before[-1])


def clock_problem(samples, publishers, now, last_advance_wall):
    """Samples are simulation seconds; freshness uses monotonic wall seconds."""
    if publishers != 1:
        return 'requires exactly one /clock publisher'
    if len(samples) < 2 or any(not math.isfinite(t) for t in samples):
        return 'requires finite live clock samples'
    if any(b < a for a, b in zip(samples, samples[1:], strict=False)):
        return 'simulation clock moved backwards'
    if samples[-1] <= samples[0] or last_advance_wall is None or now-last_advance_wall > 1.:
        return 'simulation clock stopped advancing'
    return None
