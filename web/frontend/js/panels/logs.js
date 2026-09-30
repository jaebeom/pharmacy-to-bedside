// 에러 로그 탭: /rosout 의 WARN 이상. 노드 이름 + level 필터(api.md §5).
import { el, replace, emptyNote } from '../dom.js';
import { simStamp, wallClock } from '../format.js';

// 서버는 "이 레벨 이상"으로 준다. 화면 필터는 받아 온 것 안에서 추린다.
const LEVELS = ['fatal', 'error', 'warn'];
const active = new Set(LEVELS);
let nodeFilter = '';

export function renderLogFilters(root, onChange) {
  replace(root, [
    el('div', { class: 'filters' }, [
      ...LEVELS.map((lv) => el('button', {
        class: `filter-chip${active.has(lv) ? ' is-on' : ''}`,
        type: 'button',
        dataset: { level: lv },
        onclick: (ev) => {
          if (active.has(lv)) active.delete(lv); else active.add(lv);
          ev.currentTarget.classList.toggle('is-on', active.has(lv));
          onChange();
        },
        text: lv,
      })),
      el('input', {
        class: 'node-filter',
        type: 'search',
        placeholder: '노드 이름',
        oninput: (ev) => { nodeFilter = ev.currentTarget.value.trim().toLowerCase(); onChange(); },
      }),
    ]),
  ]);
}

function logRow(l) {
  return el('div', { class: `err err-${l.level}` }, [
    el('span', { class: 'err-stamp', title: wallClock(l.wall), text: simStamp(l.stamp) }),
    el('span', { class: 'err-level', text: l.level }),
    el('span', { class: 'err-node', title: l.node, text: l.node || '—' }),
    el('span', { class: 'err-msg', text: l.message || '' }),
  ]);
}

export function renderLogs(store, root) {
  const all = store.logs;
  if (!all.length) return replace(root, emptyNote('로그 없음 (WARN 이상만 수집합니다)'));

  const rows = all.filter((l) =>
    active.has(l.level) && (!nodeFilter || l.node.toLowerCase().includes(nodeFilter))
  );
  if (!rows.length) return replace(root, emptyNote('이 필터에 해당하는 로그 없음'));

  // 서버가 준 순서를 유지한다.
  replace(root, rows.map(logRow));
}
