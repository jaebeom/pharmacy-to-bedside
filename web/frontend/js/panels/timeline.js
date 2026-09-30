// 이벤트 타임라인: 서버가 준 순서(seq 오름차순) 그대로. 클라이언트에서 재정렬하지 않는다.
// epoch 이 다른 이벤트는 섞지 않는다(api.md §0.2) — 목록 머리에 세대 구분선을 둔다.
import { el, replace, emptyNote } from '../dom.js';
import { simStamp, refillSummary, orderState, isBadOrder, ALARMISH_EVENTS, URGENT_EVENTS, RESET_EVENTS } from '../format.js';

/** detail 은 자유 문자열이고 구조 파싱 대상이 아니다.
 *  유일한 예외가 REQUEST_ACCEPTED 의 compact JSON(#104)이라, 그 이벤트에서만 줄여 쓴다. */
function detailText(name, detail) {
  if (name !== 'REQUEST_ACCEPTED') return detail;
  const t = detail.trim();
  if (!t.startsWith('{')) return detail;
  let d;
  try { d = JSON.parse(t); } catch { return detail; }
  if (!d || typeof d !== 'object') return detail;
  const parts = [];
  if (typeof d.mode === 'number') parts.push(`mode=${d.mode}`);
  if (typeof d.destination_id === 'string') parts.push(d.destination_id);
  if (Array.isArray(d.orders)) parts.push(`주문 ${d.orders.length}건`);
  return parts.length ? parts.join(' · ') : detail;
}

function eventRow(e, orders) {
  let cls = 'ev';
  if (RESET_EVENTS.has(e.name)) cls += ' ev-reset';
  else if (URGENT_EVENTS.has(e.name)) cls += ' ev-urgent';
  else if (ALARMISH_EVENTS.has(e.name)) cls += ' ev-alarmish';

  // ORDER_DONE 은 "끝났다"일 뿐 성공이 아니다. 종료 상태는 /orders/status 가 말한다.
  // 그 줄만 보고 성공으로 읽지 않게 주문 상태를 같이 찍는다(알 수 있을 때만).
  const ord = e.name === 'ORDER_DONE' && e.orderId ? orders.get(e.orderId) : null;
  if (ord && isBadOrder(ord)) cls += ' ev-alarmish';

  // REFILL_DONE 은 서버가 파싱해 준 요약이 있으면 그것을 쓴다. 없으면 detail 원문 그대로.
  const sum = e.name === 'REFILL_DONE' ? refillSummary(e.refill) : null;
  const rest = sum && sum.short
    ? [e.robotId, sum.short].filter(Boolean).join(' · ')
    : [e.robotId, e.requestId, e.orderId,
       ord ? orderState(ord).ko : null,
       detailText(e.name, e.detail)].filter(Boolean).join(' · ');

  return el('div', { class: cls, title: e.seq === null ? '' : `seq ${e.seq}` }, [
    el('span', { class: 'ev-stamp', text: simStamp(e.stamp) }),
    el('span', { class: 'ev-name', text: e.name || '—' }),
    el('span', { class: 'ev-rest', title: sum && sum.tip ? `${rest} · ${sum.tip}` : rest }, [
      sum && sum.color ? el('span', { class: 'kind-swatch', style: `background:${sum.color}` }) : null,
      rest,
    ]),
  ]);
}

export function renderTimeline(store, root) {
  const events = store.events;
  if (!store.snapshot) return replace(root, emptyNote('데이터 없음'));
  if (!events.length) return replace(root, emptyNote('이벤트 없음'));

  // 현재 트립의 주문 상태. ORDER_DONE 줄에 결말을 같이 찍는 데 쓴다.
  const trip = store.snapshot.trip;
  const orders = new Map((trip ? trip.orders : []).map((o) => [o.orderId, o]));

  // 새 이벤트를 따라가던 중이면 계속 따라간다. 사람이 위로 올려 읽는 중이면 건드리지 않는다.
  const wasAtEnd = root.scrollHeight - root.scrollTop - root.clientHeight < 40;

  const rows = [];

  // 세대 구분선. 리셋으로 목록을 비웠으므로 지금 목록은 한 epoch 뿐이다.
  rows.push(el('div', {
    class: 'reset-divider',
    text: store.epoch === null ? 'EPOCH —' : `EPOCH ${store.epoch} 시작`,
  }));
  if (store.truncated) {
    rows.push(el('div', { class: 'trunc-note', text: '오래된 이벤트는 잘렸습니다' }));
  }

  // 그래도 한 목록 안에 다른 epoch 가 섞여 들어오면(서버 변경 등) 그 자리에 구분선을 넣는다.
  let prevEpoch = null;
  for (let i = 0; i < events.length; i += 1) {
    const e = events[i];
    if (i > 0 && e.epoch !== null && prevEpoch !== null && e.epoch !== prevEpoch) {
      rows.push(el('div', { class: 'reset-divider', text: `RESET — epoch ${prevEpoch} → ${e.epoch}` }));
    }
    rows.push(eventRow(e, orders));
    if (e.epoch !== null) prevEpoch = e.epoch;
  }

  replace(root, rows);
  if (wasAtEnd) root.scrollTop = root.scrollHeight;
}
