// 조제기: 약별 슬롯, 재고, PAUSED, 보충 중. 벨트·보관함도 같이 본다.
// 1차 시연 구간(조제실)의 핵심 패널이라 보충 진행을 따로 드러낸다.
import { el, replace, emptyNote } from '../dom.js';
import {
  wallClock, refillSummary, CANISTER_KIND, REFILL_TARGET, ageText, simStamp, shelfText, dispenserStockText,
  refillCountText,
} from '../format.js';

/** 보충 흐름 띠의 칸. **서버의 `dispenser.paused`·`dispenser.refilling` 으로만 단계를 정한다**(#560).
 *  예전에는 이벤트(정지·보충 요청·보충 완료·재개) 가운데 마지막 것 하나로 정했는데, 두 품목이
 *  같이 보충 중이면 A 의 REFILL_DONE 이 B 가 아직 도는데도 띠를 "보충 완료" 로 옮겼다 — 서버가
 *  #477 에서 고친 짝맞춤을 화면이 따로 틀리게 하고 있었다. 짝맞춤은 서버 한 곳에만 둔다.
 *  서버 값 둘로는 "보충 완료" 와 "재개" 를 가를 수 없어 칸을 셋으로 줄였다.
 *  `재개` 는 현재 칸이 되지 않는다 — 둘 다 풀리면 띠 자체가 사라진다. */
const REFILL_FLOW = [
  { key: 'paused', label: '정지', title: 'dispenser.paused — 보충 요청 전이거나 재개를 기다림' },
  { key: 'refilling', label: '보충 중', title: 'dispenser.refilling — 열린 REFILL_REQUESTED 가 있음' },
  { key: 'resumed', label: '재개', title: 'paused·refilling 이 둘 다 풀리면 이 띠가 사라진다' },
];

function slotBox(s) {
  const empty = s.count <= 0;
  return el('div', { class: `slot${s.active ? ' is-active' : ''}${empty ? ' is-empty' : ''}` }, [
    el('div', { class: 'slot-top' }, [
      el('span', { class: 'slot-letter', text: s.slotName || (s.slot === null ? '?' : String(s.slot)) }),
      s.active ? el('span', { class: 'slot-active-tag', text: 'ACTIVE' }) : null,
    ]),
    // 용량이 계약에 없으므로 비율 막대를 그리지 않는다. 숫자 자체를 크게 보여준다.
    el('div', { class: 'slot-count', text: String(s.count) }),
    el('div', { class: 'slot-lot', title: s.expiry ? `유효기한 ${s.expiry}` : '', text: s.lotId || '—' }),
    empty ? el('div', { class: 'slot-empty-tag', text: '빈 슬롯' }) : null,
  ]);
}

/** 서버는 슬롯을 평평한 배열로 준다. 화면에서는 약(item_id)으로 묶는다. */
function groupByItem(slots) {
  const map = new Map();
  for (const s of slots) {
    if (!map.has(s.itemId)) map.set(s.itemId, []);
    map.get(s.itemId).push(s);
  }
  return [...map.entries()].map(([itemId, list]) => ({ itemId, slots: list }));
}

function itemBox(item, d) {
  const isPaused = d.pausedItemIds.includes(item.itemId);
  // refilling_item_ids 는 비어 있을 수 있다. 그때는 약품 미상 보충으로 패널 머리에서 알린다.
  const isRefilling = d.refillingItemIds.includes(item.itemId);
  const allEmpty = item.slots.every((s) => s.count <= 0);
  return el('div', { class: `disp-item${isPaused ? ' is-paused' : ''}` }, [
    el('div', { class: 'disp-head' }, [
      el('span', { class: 'disp-name', text: item.itemId || '—' }),
      el('span', { class: 'disp-flags' }, [
        isPaused ? el('span', { class: 'flag flag-paused', text: 'PAUSED' }) : null,
        isRefilling ? el('span', { class: 'flag flag-refill', text: '보충 중' }) : null,
        allEmpty && !isPaused ? el('span', { class: 'flag flag-empty', text: '재고 0' }) : null,
      ]),
    ]),
    el('div', { class: 'slots' }, item.slots.map(slotBox)),
  ]);
}

/** 보충이 어디까지 갔는지 — 서버 상태 두 개만 본다(이벤트는 읽지 않는다). */
function refillStrip(d) {
  if (!d.paused && !d.refilling) return null;
  const at = d.refilling ? 1 : 0;
  // 보충 중이 아니면 refilling_item_ids 는 늘 비어 있다(§6.1). 그때는 멈춘 품목을 적는다.
  const ids = d.refilling ? d.refillingItemIds : d.pausedItemIds;

  return el('div', { class: 'strip strip-refill' }, [
    el('span', { class: 'strip-label', text: '보충' }),
    el('div', { class: 'refill-flow' }, REFILL_FLOW.map((f, i) => el('span', {
      class: `step ${i < at ? 'is-done' : i === at ? 'is-current' : 'is-future'}`,
      title: f.title,
      text: f.label,
    }))),
    el('span', { class: 'strip-spacer' }),
    ids.length
      ? el('span', { class: 'strip-note', text: targetText(d, ids) })
      : el('span', { class: 'strip-note', text: '약품 미상' }),
  ]);
}

/** 보충 중 대상 한 줄 — "drug-ibu → A · 원통형 → 원형 수납통". 서버 refill_targets(§6.1)가 없거나 칸이 null 이면
 *  아는 만큼만 적는다. 끝난 뒤의 실제 값은 "마지막 보충" 줄이다. */
function targetText(d, ids) {
  const byItem = new Map((d.refillTargets || []).map((t) => [t.itemId, t]));
  return ids.map((id) => {
    const t = d.refilling ? byItem.get(id) : null;
    if (!t) return id;
    const kind = t.kind && CANISTER_KIND[t.kind] ? CANISTER_KIND[t.kind].ko : null;
    const target = t.target && REFILL_TARGET[t.target] ? REFILL_TARGET[t.target].ko : null;
    return [`${id}${t.slotName ? ` → ${t.slotName}` : ''}`, kind && target ? `${kind} → ${target}` : kind || target].filter(Boolean).join(' · ');
  }).join(', ');
}

/** 약통 QR 판독(M0609 손 카메라 마지막 한 건). 약통 확인을 켠 기동에서만 온다. 허용·거부 판정은 서버도 모른다. */
function containerLine(d) {
  const c = d.containerRead;
  if (!c) return null;
  const ok = c.status === 'ok';
  return el('div', { class: `strip strip-container${ok ? '' : ' is-bad'}` }, [
    el('span', { class: 'strip-label', text: '약통 QR' }),
    el('span', { class: `chip ${ok ? 'chip-on' : 'chip-bad'}`, text: ok ? '판독' : '못 읽음' }),
    el('span', { class: 'strip-note mono', text: ok && c.tagId ? c.tagId : '—' }),
    el('span', { class: 'strip-spacer' }),
    el('span', { class: 'strip-age', title: `sim ${simStamp(c.stamp)}`, text: ageText(c.ageWallS) }),
  ]);
}

/** 마지막 보충이 무엇을 어디에 넣었는지 한 줄.
 *  v1 이거나 파싱이 깨졌으면(parsed=false) 이 줄을 그리지 않는다 — 지어낼 값이 없다. */
/** 재고 한눈에(§6.1 `stock`, 재범 9/29 N3): 선반 약통·모듈 남은 수, 조제기 약통·봉투, 이번 세대 보충 횟수. */
function stockLine(d) {
  const s = d.stock;
  if (!s) return null;
  const shelf = shelfText(s);
  return el('div', { class: 'strip strip-stock' }, [
    el('span', { class: 'strip-label', text: '재고' }),
    el('span', { class: 'strip-note', text: shelf ? `선반 ${shelf}` : '선반 모름' }),
    el('span', { class: 'strip-note', text: dispenserStockText(s) }),
    el('span', { class: 'strip-spacer' }),
    el('span', { class: 'strip-note', text: refillCountText(s) }),
  ]);
}

function lastRefillLine(d) {
  const r = d.lastRefill;
  if (!r || !r.parsed) return null;
  const sum = refillSummary(r);
  if (!sum || !sum.text) return null;
  return el('div', { class: 'strip strip-lastrefill', title: sum.tip }, [
    el('span', { class: 'strip-label', text: '마지막 보충' }),
    sum.color ? el('span', { class: 'kind-swatch', style: `background:${sum.color}` }) : null,
    el('span', { class: 'refill-text', text: sum.text }),
    el('span', { class: 'strip-spacer' }),
    el('span', { class: 'strip-age', text: Number.isFinite(r.stamp) ? r.stamp.toFixed(1) : '—' }),
  ]);
}

export function renderDispenser(store, root, metaRoot, fresh) {
  const snap = store.snapshot;
  if (!snap) {
    replace(metaRoot, []);
    return replace(root, emptyNote('데이터 없음'));
  }

  const d = snap.dispenser;
  const b = snap.belt;
  const c = snap.cabinet;

  // 서버가 준 stale 은 snapshot 을 만든 순간의 판정이다.
  // 갱신 자체가 멎었으면(fresh=false) 무엇이든 못 믿는다(요건 3).
  const dispStale = !fresh || !d || d.stale;
  const beltStale = !fresh || !b || b.stale;

  replace(metaRoot, d ? [
    el('span', { text: `대기열 ${d.queueLength}` }),
    d.paused ? el('span', { class: 'flag flag-paused', text: 'PAUSED' }) : null,
    d.refilling ? el('span', { class: 'flag flag-refill', text: '보충 중' }) : null,
    dispStale ? el('span', { class: 'flag flag-stale', text: 'STALE' }) : null,
  ].filter(Boolean) : [el('span', { class: 'flag flag-stale', text: '수신 없음' })]);

  const blocks = [];

  if (!d) {
    blocks.push(emptyNote('조제기 상태를 아직 못 받았습니다'));
  } else {
    const items = groupByItem(d.slots);
    if (!items.length) blocks.push(emptyNote('슬롯 정보 없음'));
    else blocks.push(...items.map((it) => itemBox(it, d)));

    const refill = refillStrip(d);
    if (refill) blocks.push(refill);
    const cq = containerLine(d);
    if (cq) blocks.push(cq);
    const last = lastRefillLine(d);
    if (last) blocks.push(last);
    const stock = stockLine(d);
    if (stock) blocks.push(stock);
  }

  blocks.push(el('div', { class: `strip${beltStale ? ' is-stale' : ''}` }, [
    el('span', { class: 'strip-label', text: '벨트' }),
    el('span', {
      class: `chip ${!fresh || !b ? 'chip-unknown' : b.occupied ? 'chip-on' : 'chip-off'}`,
      text: !fresh || !b ? 'unknown' : b.occupied ? 'OCCUPIED' : 'EMPTY',
    }),
    el('span', { class: `chip ${!fresh || !b ? 'chip-unknown' : b.atEnd ? 'chip-on' : 'chip-off'}`, text: 'AT_END' }),
    b && b.orderId ? el('span', { class: 'strip-note', text: b.orderId }) : null,
    el('span', { class: 'strip-spacer' }),
    el('span', { class: 'strip-age', text: b ? wallClock(b.wall) : '—' }),
  ]));

  blocks.push(el('div', { class: 'strip zone-later', title: '병동 구간 — 1차 시연 범위 밖' }, [
    el('span', { class: 'strip-label', text: '보관함' }),
    c
      ? el('span', { class: `chip ${!fresh ? 'chip-unknown' : c.present ? 'chip-on' : 'chip-off'}`, text: !fresh ? 'unknown' : c.present ? 'PRESENT' : 'EMPTY' })
      : el('span', { class: 'chip chip-unknown', text: '수신 없음' }),
    c && c.cabinetId ? el('span', { class: 'strip-note', text: c.cabinetId }) : null,
    c && c.orderId ? el('span', { class: 'strip-note', text: c.orderId }) : null,
    el('span', { class: 'strip-spacer' }),
    el('span', { class: 'strip-age', text: c ? wallClock(c.wall) : '—' }),
  ]));

  replace(root, blocks);
}
