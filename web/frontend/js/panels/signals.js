// 인터락 신호: 값과 신선도. stale 은 회색 unknown. 키 5개는 고정이다(api.md §1).
import { el, replace } from '../dom.js';
import { ageText } from '../format.js';
import { SIGNAL_LABEL, STALE_TOPIC_S } from '../api.js';

export function renderSignals(store, root, metaRoot, fresh, sinceMsg) {
  const snap = store.snapshot;
  if (!snap) {
    replace(metaRoot, []);
    return replace(root, []);
  }

  // 나이는 서버가 스냅샷을 만든 시점의 값을 그대로 쓴다.
  // 여기에 '받은 뒤 흐른 시간'을 더하면, 서버가 변화 없어 조용한 구간에서
  // 멀쩡한 신호가 전부 unknown 으로 뒤집힌다(실측 push 간격 최대 3.2초).
  // 갱신이 정말 멎었는지는 fresh 가 말해 준다.
  let staleCount = 0;
  const rows = snap.signals.map((s) => {
    const stale = !fresh || !s.present || s.value === null || s.stale || s.ageWallS > STALE_TOPIC_S;
    if (stale) staleCount += 1;

    return el('div', { class: `sig-row${stale ? ' is-stale' : ''}` }, [
      el('div', { class: 'sig-names' }, [
        el('span', { class: 'sig-key', text: s.key }),
        el('span', { class: 'sig-ko', text: SIGNAL_LABEL[s.key] || '' }),
      ]),
      el('span', {
        class: `sig-val ${stale ? 'sig-unknown' : s.value ? 'sig-true' : 'sig-false'}`,
        text: stale ? 'unknown' : s.value ? 'TRUE' : 'FALSE',
      }),
      el('span', {
        class: 'sig-age',
        title: `서버가 이 값을 받은 뒤 지난 시간 (stale > ${STALE_TOPIC_S}s)`,
        text: fresh ? ageText(s.ageWallS) : '—',
      }),
    ]);
  });

  // 보드 자체가 얼마나 묵었는지는 따로 밝힌다 — 신호 나이와 섞지 않는다.
  const meta = [];
  if (!fresh) {
    meta.push(el('span', { style: 'color:var(--error)', text: `갱신 멎음 ${ageText(sinceMsg)}` }));
  } else {
    meta.push(staleCount
      ? el('span', { style: 'color:var(--warn)', text: `stale ${staleCount}/${snap.signals.length}` })
      : el('span', { text: `전부 신선 (${snap.signals.length})` }));
    if (sinceMsg > 2) meta.push(el('span', { text: `갱신 ${ageText(sinceMsg)} 전` }));
  }
  replace(metaRoot, meta);
  replace(root, rows);
}
