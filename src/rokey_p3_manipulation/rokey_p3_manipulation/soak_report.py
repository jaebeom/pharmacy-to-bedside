"""연속 구동기(refill_soak)의 순수 부분: 팔 feedback 의 계획 줄 읽기와 요약. ROS 없이 테스트한다."""


#: 팔(v2)이 칸을 고른 뒤 내는 feedback phase 의 머리. `plan cell=<id> kind=<kind> seed=<n> draw=<n>`.
PLAN_PREFIX = 'plan '


def parse_plan(phase):
    """`plan cell=A kind=B …` → {'cell': 'A', 'kind': 'B', …}. 아니면 None."""
    if not phase.startswith(PLAN_PREFIX):
        return None
    fields = {}
    for token in phase[len(PLAN_PREFIX):].split():
        key, _, value = token.partition('=')
        if value:
            fields[key] = value
    return fields


def summarize(rows):
    """줄 목록 → 요약 dict. rows 는 {'kind', 'success', 'seconds', 'reason'} 를 가진다."""
    done = [r for r in rows if r['success']]
    failed = {}
    for row in rows:
        if not row['success']:
            failed[row['reason']] = failed.get(row['reason'], 0) + 1
    kinds = {}
    for row in rows:
        stat = kinds.setdefault(row.get('kind') or '?', [0, 0])
        stat[0] += 1
        stat[1] += int(row['success'])
    seconds = [r['seconds'] for r in rows]
    return {'sent': len(rows), 'succeeded': len(done), 'failed': failed,
            'mean_s': round(sum(seconds) / len(seconds), 2) if seconds else 0.0,
            'max_s': round(max(seconds), 2) if seconds else 0.0,
            'by_kind': {k: {'sent': v[0], 'succeeded': v[1]} for k, v in sorted(kinds.items())}}
