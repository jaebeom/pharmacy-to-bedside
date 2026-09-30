// 알람: level 색, kind, 메시지. 최신이 위. URGENT_ARRIVING 은 눈에 띄게.
import { el, replace, emptyNote } from '../dom.js';
import { simStamp } from '../format.js';

const URGENT_KINDS = new Set(['URGENT_ARRIVING']);

// 저절로 안 풀리는 알람 — 사람이 손대야 한다. 화면에서 가장 세게 다룬다.
// 저절로 안 풀리는 것 — 사람이 손대야 한다. 맨 위에 고정한다(§4.1: 도킹 포기·지도 미수신은 다음 리셋까지 남는다).
const CRITICAL_KINDS = new Set(['RESET_STUCK', 'DOCK_GIVEUP', 'MAP_GUARD_GIVEUP']);

function alarmRow(a) {
  const ref = [a.requestId, a.orderId].filter(Boolean).join(' · ');
  const critical = CRITICAL_KINDS.has(a.kind);
  return el('div', {
    class: `alarm alarm-${a.level}`
      + (URGENT_KINDS.has(a.kind) ? ' is-urgent' : '')
      + (critical ? ' is-critical' : ''),
  }, [
    el('span', { class: 'alarm-stamp', text: simStamp(a.stamp) }),
    el('div', { class: 'alarm-main' }, [
      el('div', { class: 'alarm-top' }, [
        el('span', { class: 'alarm-kind', text: a.kind || '—' }),
        ref ? el('span', { class: 'alarm-ref', text: ref }) : null,
      ]),
      el('div', { class: 'alarm-msg', text: a.message || '' }),
      critical ? el('div', { class: 'alarm-action', text: '저절로 풀리지 않습니다 — 사람이 개입해야 합니다' }) : null,
    ]),
  ]);
}

export function renderAlarms(store, root, metaRoot) {
  const list = store.alarms;
  if (!store.snapshot) {
    replace(metaRoot, []);
    return replace(root, emptyNote('데이터 없음'));
  }
  if (!list.length) {
    replace(metaRoot, [el('span', { style: 'color:var(--ok)', text: '이상 없음' })]);
    return replace(root, emptyNote('살아있는 알람 없음'));
  }

  // 표시 요건이 "최신이 위" 이므로 stamp 내림차순(동률은 원래 순서 유지).
  const shown = list
    .map((a, i) => ({ a, i }))
    .sort((x, y) => {
      // 사람이 손대야 하는 것은 접히면 안 되므로 맨 위로. 그 외에는 최신이 위.
      const cx = CRITICAL_KINDS.has(x.a.kind) ? 1 : 0;
      const cy = CRITICAL_KINDS.has(y.a.kind) ? 1 : 0;
      if (cx !== cy) return cy - cx;
      const sx = Number.isFinite(x.a.stamp) ? x.a.stamp : -Infinity;
      const sy = Number.isFinite(y.a.stamp) ? y.a.stamp : -Infinity;
      return sy - sx || x.i - y.i;
    })
    .map((p) => p.a);

  const counts = { error: 0, warn: 0, info: 0 };
  for (const a of shown) counts[a.level] += 1;

  replace(metaRoot, [
    counts.error ? el('span', { style: 'color:var(--error)', text: `error ${counts.error}` }) : null,
    counts.warn ? el('span', { style: 'color:var(--warn)', text: `warn ${counts.warn}` }) : null,
    counts.info ? el('span', { text: `info ${counts.info}` }) : null,
  ].filter(Boolean));

  replace(root, shown.map(alarmRow));

  // 벽 화면에는 아무도 스크롤하지 않는다. 화면 밖으로 밀린 알람이 있으면 그 사실을 남긴다.
  markOverflow(root);
}

/** 접힌 알람 수를 패널 바닥에 고정 표시한다. 없으면 표시도 없다.
 *
 *  **다음 프레임에 잰다.** 방금 줄을 넣은 그 순간에 재면 패널 높이가 아직 안 정해져
 *  있어서 전부 접힌 것으로 세고, fixture 처럼 데이터가 안 바뀌면 다시 그릴 일이 없어
 *  그 틀린 수가 화면에 그대로 남는다(시연 배치에서 "아래로 12건 더" 로 걸렸다). */
function markOverflow(root) {
  if (root._overflowRaf) cancelAnimationFrame(root._overflowRaf);
  root._overflowRaf = requestAnimationFrame(() => {
    root._overflowRaf = 0;
    root.querySelector('.overflow-note')?.remove();
    countOverflow(root);
  });
}

function countOverflow(root) {
  const rows = [...root.children].filter((n) => n.classList.contains('alarm'));
  if (!rows.length) return;

  // 패널이 아직 안 보이면(높이 0) 아무것도 세지 않는다 — 전부 접힌 것으로 잡힌다.
  if (!root.clientHeight) return;

  // **offsetTop 을 쓰면 안 된다.** offsetTop 은 offsetParent 기준인데 이 스크롤 통에는
  // position 이 없어서 기준이 <body> 가 된다. 1920 배치에서는 알람 패널이 위쪽이라
  // 우연히 맞았고, 시연 배치에서 아래로 내려가자 두 건 다 "접힘" 으로 세었다.
  // getBoundingClientRect 는 둘 다 같은 기준(뷰포트)이라 이 문제가 없다.
  const fold = root.getBoundingClientRect().bottom;
  const isFolded = (r) => r.getBoundingClientRect().bottom > fold + 1;
  const folded = rows.filter(isFolded);
  const hidden = folded.length;
  if (!hidden) return;

  // 마지막으로 접힌 것 중 가장 센 level 을 같이 알린다 — 잘린 게 error 면 알아야 한다.
  const worst = folded.some((r) => r.classList.contains('alarm-error')) ? 'error' : 'warn';

  root.appendChild(el('div', {
    class: `overflow-note overflow-${worst}`,
    text: `아래로 ${hidden}건 더${worst === 'error' ? ' (error 포함)' : ''}`,
  }));
}
