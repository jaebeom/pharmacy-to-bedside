// format.js — 값 -> 사람이 읽는 표기. 코드 값의 출처는 DeliveryRequest.msg / OrderStatus.msg / api.md.

export const MODE = {
  0: { short: '1인',       label: 'MODE_SINGLE' },
  1: { short: '긴급',       label: 'MODE_URGENT' },
  2: { short: '병실 묶음',   label: 'MODE_BATCH_ROOM' },
  3: { short: '병동 묶음',   label: 'MODE_BATCH_WARD' },
};

/** mode 는 null 일 수 있다(§1.3 — /deliver 가 액션이라 goal 이 토픽에 안 나온다). */
export function modeInfo(mode) {
  if (mode === null || mode === undefined) {
    return { short: '모드 불명', label: 'UNKNOWN', cls: 'mode-null', unknown: true };
  }
  const m = MODE[mode];
  if (!m) return { short: `모드 ${mode}`, label: `MODE_${mode}`, cls: 'mode-null', unknown: true };
  return { ...m, cls: `mode-${mode}`, unknown: false };
}

export const isUrgent = (mode) => mode === 1;

/** 값을 못 얻은 필드의 표기. 빈 문자열과 구분되게 한다. */
export const UNKNOWN = '알 수 없음';
export const orNull = (v) => (v === null || v === undefined || v === '' ? null : v);

// ---- 주문 상태 --------------------------------------------------------
// 종료 상태의 근거는 ORDER_DONE 이벤트가 아니라 /orders/status 다(api.md §2).

export const ORDER_STATE = {
  0:  { name: 'ACCEPTED',    ko: '접수',      cls: 'ostate-accepted' },
  1:  { name: 'IN_PROGRESS', ko: '진행 중',    cls: 'ostate-inprogress' },
  2:  { name: 'DELIVERED',   ko: '전달 완료',  cls: 'ostate-delivered' },
  10: { name: 'SUCCESS',     ko: '성공',      cls: 'ostate-success' },
  11: { name: 'HOLD_RETURN', ko: '보류 회수',  cls: 'ostate-hold' },
  12: { name: 'ABORT',       ko: '중단',      cls: 'ostate-abort' },
  13: { name: 'TIMEOUT',     ko: '시간 초과',  cls: 'ostate-timeout' },
};

const BY_NAME = Object.fromEntries(
  Object.entries(ORDER_STATE).map(([k, v]) => [v.name, { ...v, code: Number(k) }])
);

/** 서버가 주는 파생 결말(api.md §1.5). 값 7개가 화면이 그리는 7가지와 1:1 이라
 *  **화면은 이것 하나로만 갈래를 친다.** state_name 을 표시용으로 또 보지 않는다. */
const BY_OUTCOME = {
  accepted:      { ko: '접수',           cls: 'ostate-accepted' },
  in_progress:   { ko: '진행 중',         cls: 'ostate-inprogress' },
  delivered:     { ko: '전달 완료',       cls: 'ostate-delivered' },
  pharmacy_done: { ko: '조제실 구간 완료', cls: 'ostate-pharmacy-done' },
  held:          { ko: '보류 회수',       cls: 'ostate-hold' },
  aborted:       { ko: '중단',           cls: 'ostate-abort' },
  timeout:       { ko: '시간 초과',       cls: 'ostate-timeout' },
};

/** 주문 상태 표기.
 *  outcome 이 있으면 그것 하나로 정한다. 없는 서버에서는 state_name -> state 로 떨어진다.
 *  어느 쪽이든 바탕 상태(state_name)는 name 에 남겨 툴팁에서 확인할 수 있다 —
 *  이름을 바꿔 보여주는 것이지 지우는 게 아니다. */
export function orderState(o) {
  if (o.outcome && BY_OUTCOME[o.outcome]) {
    const m = BY_OUTCOME[o.outcome];
    return { name: o.stateName || o.outcome, ko: m.ko, cls: m.cls, code: o.state };
  }
  if (isPharmacySegmentDone(o)) {
    return { name: 'HOLD_RETURN', ko: '조제실 구간 완료', cls: 'ostate-pharmacy-done', code: 11 };
  }
  if (o.stateName && BY_NAME[o.stateName]) return BY_NAME[o.stateName];
  if (o.state !== null && ORDER_STATE[o.state]) return { ...ORDER_STATE[o.state], code: o.state };
  if (o.stateName) return { name: o.stateName, ko: o.stateName, cls: 'ostate-unknown', code: null };
  return { name: 'UNKNOWN', ko: UNKNOWN, cls: 'ostate-unknown', code: null };
}

/** 조제실만 도는 구성(`pharmacy_only`)에서는 주문이 `HOLD_RETURN` 으로 닫히는 것이 **정상 완주**다.
 *  병동이 없어 배달할 곳이 없으니 회수되는 것이고 실패가 아니다.
 *  9/21 시연이 이 구성이라, 매 바퀴 성공이 경고로 보이면 안 된다.
 *
 *  **서버가 전용 필드를 내기 시작하면 이 함수 안만 바꾼다.** 부르는 쪽은 그대로 둔다.
 *  지금은 (state_name, reason) 조합으로 판정한다. */
export const PHARMACY_ONLY_REASON = 'pharmacy_only';

export function isPharmacySegmentDone(o) {
  // 서버가 outcome 을 내면 그것이 정본이다. 규칙이 서버와 화면 두 곳에 있으면 안 된다.
  if (o.outcome) return o.outcome === 'pharmacy_done';
  // 아직 안 내는 서버용 대체 판정.
  return o.stateName === 'HOLD_RETURN' && o.reason === PHARMACY_ONLY_REASON;
}

/** 이 트립이 조제실 한 바퀴를 정상 완주했는가.
 *  주문이 0건이면 공허하게 참이 되므로 따로 막는다(트립 사이 구간). */
export function isPharmacyLapDone(trip) {
  if (!trip || !trip.orders.length) return false;
  return trip.orders.every(isPharmacySegmentDone);
}

const BAD_STATES = new Set(['HOLD_RETURN', 'ABORT', 'TIMEOUT']);
const BAD_OUTCOMES = new Set(['held', 'aborted', 'timeout']);

/** 주문이 나쁜 결말인가. pharmacy_done 은 정상 완주라 여기서 빠진다. */
export function isBadOrder(o) {
  if (o.outcome) return BAD_OUTCOMES.has(o.outcome);
  if (isPharmacySegmentDone(o)) return false;
  return BAD_STATES.has(o.stateName);
}

// ---- 트립 단계 --------------------------------------------------------

// §1.2 — 단계 표시.
//
// 화면 글자는 status_view.py 의 한글 원문(`phase_label`)을 **그대로** 찍는다.
// 아래 track 은 그 원문들을 진행 순서대로 늘어놓은 것이다. 여기서 한글을 지어내지 않는다.
// 현재 단계는 서버가 준 phase_label 문자열과 정확히 맞춰 찾는다.
//
// 주의: phase(영문) 하나에 label 이 여럿 붙는다(loading -> '픽'/'적재',
// auth -> '인증 실패'/'보관함 배달'). 그래서 phase -> 한글은 함수가 아니다.
// 분기는 phase 로, 표시는 label 로 한다.
export const PHASE_TRACK = [
  { label: '적재 위치로 이동', phase: 'accepted',    zone: 'pharmacy' },
  { label: '배출',            phase: 'docked_load', zone: 'pharmacy' },
  { label: '벨트 이송',       phase: 'dispensing',  zone: 'pharmacy' },
  { label: '벨트 끝 픽',      phase: 'dispensing',  zone: 'pharmacy' },
  { label: '픽',              phase: 'loading',     zone: 'pharmacy' },
  { label: '적재',            phase: 'loading',     zone: 'pharmacy' },
  { label: '적재 끝',         phase: 'load_done',   zone: 'pharmacy' },
  { label: '팔 홈',           phase: 'arm_home',    zone: 'pharmacy' },
  { label: '병동으로 이동',    phase: 'moving',      zone: 'ward' },
  { label: '병동 도착 직전',   phase: 'arriving',    zone: 'ward' },
  { label: '인증',            phase: 'arrived',     zone: 'ward' },
  { label: '보관함 배달',      phase: 'unloading',   zone: 'ward' },
  { label: '인증 실패',        phase: 'auth',        zone: 'ward', bad: true },
  { label: '보관함 잠김',      phase: 'locked',      zone: 'ward' },
  { label: '주문 닫힘',        phase: 'order_done',  zone: 'pharmacy' },
  { label: '도크로 복귀',      phase: 'returning',   zone: 'pharmacy' },
  { label: '대기(도크)',       phase: 'docked',      zone: 'pharmacy' },
];

/** 트립 진행이 아니라 리셋을 뜻하는 단계. 스텝퍼를 그리지 않는다. */
export const RESET_PHASES = new Set(['reset', 'reset_done']);

/** 현재 단계의 track 위치. label 을 먼저 맞추고, 없으면 phase 로 떨어진다. */
export function trackIndex(trip) {
  if (trip.phaseLabel) {
    const i = PHASE_TRACK.findIndex((p) => p.label === trip.phaseLabel);
    if (i >= 0) return i;
  }
  if (trip.phase) {
    const i = PHASE_TRACK.findIndex((p) => p.phase === trip.phase);
    if (i >= 0) return i;
  }
  return -1;
}

/** 화면에 찍을 단계 이름. 서버의 한글 원문이 있으면 그것, 없으면 영문 키. */
export const phaseText = (trip) => trip.phaseLabel || trip.phase || UNKNOWN;

/** 1차 시연 구간은 조제실(A)이다. 병동 단계는 자리만 두고 흐리게 그린다. */
export const DEMO_ZONE = 'pharmacy';

// ---- 이벤트 강조 ------------------------------------------------------

export const ALARMISH_EVENTS = new Set(['AUTH_FAIL', 'ORDER_DONE', 'DISPENSER_PAUSED', 'REFILL_REQUESTED']);
export const URGENT_EVENTS = new Set(['ARRIVING']);
export const RESET_EVENTS = new Set(['RESET_BEGIN', 'RESET_DONE']);

// ---- 시간 ------------------------------------------------------------

/** sim 초 -> m:ss.s */
export function simClock(sec) {
  if (!Number.isFinite(sec)) return '—';
  const s = Math.max(0, sec);
  return `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, '0')}`;
}

/** 타임라인 왼쪽 칸에 쓰는 sim 초 원값. */
export function simStamp(sec) {
  return Number.isFinite(sec) ? sec.toFixed(1) : '—';
}

export function ageText(sec) {
  if (!Number.isFinite(sec)) return '—';
  if (sec < 10) return `${sec.toFixed(2)}s`;
  if (sec < 100) return `${sec.toFixed(1)}s`;
  return '>99s';
}

/** wall ISO -> HH:MM:SS (로컬). */
export function wallClock(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString('ko-KR', { hour12: false });
}

// ---- 보충 약통·수납 종류 ------------------------------------------------
//
// 색은 Isaac 스테이지(sim/standalone/p3sim/layout.py 의 COLORS)와 **같은 값**이다.
// 같은 물건이 두 화면에 다른 색으로 보이면 안 된다.
//
// 다만 이 값들은 조명을 받는 3D 장면용이라 어두운 UI 에서 글자색으로 쓰면 대비가 모자란다
// (모듈 #8C4CCC 는 3.31:1). 그래서 **색 견본(작은 사각형)으로만** 쓰고 글자는 일반 색으로 쓴다.
// 견본은 색을 보여주는 것이 목적이라 대비 규칙의 대상이 아니다.

export const CANISTER_KIND = {
  cylinder: { ko: '원통형', color: '#F28C26' },
  module:   { ko: '모듈형', color: '#8C4CCC' },
};

export const REFILL_TARGET = {
  round:  { ko: '원형 수납통' },
  module: { ko: '모듈 수납' },
};

/** 보충 한 줄. 아는 것만 찍는다 — 모르는 kind·target 은 서버가 null 로 준다. */
export function refillSummary(r) {
  if (!r) return null;
  const kind = r.kind && CANISTER_KIND[r.kind] ? CANISTER_KIND[r.kind].ko : null;
  const target = r.target && REFILL_TARGET[r.target] ? REFILL_TARGET[r.target].ko : null;
  const head = kind && target ? `${kind} → ${target}` : (kind || target || null);
  const where = r.cell ? `칸 ${r.cell}` : null;
  const what = [r.item, r.slot].filter(Boolean).join(' ');
  return {
    color: r.kind && CANISTER_KIND[r.kind] ? CANISTER_KIND[r.kind].color : null,
    what,                                   // "drug-amox A"
    // 타임라인은 좁아서 약품·슬롯을 빼고 종류·칸만 쓴다. 약품은 조제기 패널에 이미 있다.
    short: [head, where].filter(Boolean).join(' · '),
    text: [what, head, where].filter(Boolean).join(' · '),
    tip: [
      r.seed !== null && r.seed !== undefined ? `seed ${r.seed}` : null,
      r.draw !== null && r.draw !== undefined ? `draw ${r.draw}` : null,
      r.clearance !== null && r.clearance !== undefined ? `clearance ${r.clearance} m` : null,
    ].filter(Boolean).join(' · '),
  };
}

/** 요청을 다시 받기까지 남은 시간을 붙일 꼬리말. 모르면 빈 문자열.
 *
 *  **브라우저 시계를 쓰지 않는다.** 예전에는 `accept_after_wall - Date.now()` 로 뺐는데,
 *  그러면 사용자 PC 시계가 30초 틀어져 있을 때 화면이 "약 33.5초" 라고 **거짓말한다.**
 *  신선도를 서버가 `age_wall_s` 로 계산해 주는 것과 같은 이유다.
 *
 *  1순위는 서버가 세어 주는 `accept_in_s`.
 *  없으면 `accept_after_wall - server_time` — **둘 다 서버 값이라** 시계가 틀어져도 맞는다.
 *  둘 다 없으면 숫자를 안 쓴다. 지어내느니 말을 안 하는 쪽이 낫다. */
export function acceptWaitSuffix(snap) {
  if (!snap) return '';

  if (snap.acceptInS !== null && snap.acceptInS !== undefined) {
    return snap.acceptInS > 0 ? ` (약 ${snap.acceptInS.toFixed(1)}초)` : '';
  }

  if (!snap.acceptAfterWall || !snap.serverTime) return '';
  const left = (new Date(snap.acceptAfterWall).getTime() - new Date(snap.serverTime).getTime()) / 1000;
  return Number.isFinite(left) && left > 0 ? ` (약 ${left.toFixed(1)}초)` : '';
}

// ---- 목적지 후보 묶기 -------------------------------------------------

export const KIND_LABEL = { bed: '병상', room: '병실', ward: '병동', station: '스테이션' };

/** 목적지 후보(§7.4)를 병동·병실별로 묶는다. 묶음 키·이름표는 서버의 `group`·`group_label` 을 쓰고,
 *  없으면 `kind` 로 묶는다. **ID 모양(bed_a1 → A)을 해석하지 않는다** — 규칙은 서버 한 곳에만 둔다.
 *  서버가 준 순서를 지킨다. 결과: [{label, items: [destination]}] */
export function groupDestinations(list) {
  const groups = new Map();
  for (const d of list || []) {
    const key = d.group !== null && d.group !== undefined ? `g:${d.group}` : `k:${d.kind}`;
    if (!groups.has(key)) {
      groups.set(key, { label: d.groupLabel || KIND_LABEL[d.kind] || d.kind || '기타', items: [] });
    }
    groups.get(key).items.push(d);
  }
  return [...groups.values()];
}

/** 병상들이 걸친 병실(서버 `group`) 이름들. 두 개 이상이면 병실 묶음(2)이 서버에서 400 `mixed_rooms` 다.
 *  **병실을 모르는 병상이 하나라도 있으면 null** — 판정하지 않고 서버에 맡긴다. */
export function roomsOf(beds, list) {
  const byId = new Map((list || []).map((d) => [d.destinationId, d]));
  const rooms = new Set();
  for (const bed of beds) {
    const d = byId.get(bed);
    if (!d || d.group === null || d.group === undefined) return null;
    rooms.add(d.groupLabel || d.group);
  }
  return [...rooms];
}

/** 병상 ID → 사람이 부르는 이름("C2 병실 D5"). 서버가 이름표를 안 주면 ID 그대로. */
export function bedName(bed, list) {
  const d = (list || []).find((x) => x.destinationId === bed);
  if (!d || !d.label) return bed;
  return d.groupLabel ? `${d.groupLabel} ${d.label}` : d.label;
}

// ---- 이벤트로 아는 것(순수 함수) ---------------------------------------
// 오케스트레이터를 바꾸지 않고 기존 26 이벤트만 본다. 이벤트는 현재 epoch 것만 store 에 있다.

/** 도크에 서서 충전 대기 중인 AMR. 그 AMR 의 마지막 이벤트가 DOCKED 면 그렇다고 본다.
 *  배터리 수치는 모델이 없어 모른다 — 배지만 단다. 리셋하면 이벤트가 비므로 배지도 빠진다(모르면 안 단다). */
export function chargingRobots(events, robots) {
  // 서버가 robots[].docked 를 주면 그것을 쓴다(리셋 직후 도크 자세까지 안다). 규칙은 서버 한 곳에만 둔다.
  const told = (robots || []).filter((r) => r.docked !== null && r.docked !== undefined);
  if (told.length) return new Set(told.filter((r) => r.docked).map((r) => r.robotId));
  const last = new Map();
  for (const e of events || []) if (e.robotId && e.robotId.startsWith('amr')) last.set(e.robotId, e.name);
  return new Set([...last].filter(([, name]) => name === 'DOCKED').map(([id]) => id));
}

/** 이 요청의 집기 시도 횟수(PICK_ATTEMPT 개수 — 재시도는 개수로 센다, Event.msg). */
export function pickAttempts(events, requestId) {
  if (!requestId) return 0;
  return (events || []).filter((e) => e.name === 'PICK_ATTEMPT' && e.requestId === requestId).length;
}

/** 환자 확인(인식표 인증) 결과: 'ok' | 'fail' | null. 주문으로 맞추고, 주문 칸이 빈 인증(묶음 정거장)은
 *  그 요청의 주문이 하나일 때만 그 주문 것으로 본다. 그 밖은 모른다. */
export function authResult(events, orderId, requestId, ordersInRequest) {
  let last = null;
  for (const e of events || []) {
    if (e.name !== 'AUTH_OK' && e.name !== 'AUTH_FAIL') continue;
    const mine = e.orderId ? e.orderId === orderId
      : (requestId && e.requestId === requestId && ordersInRequest === 1);
    if (mine) last = e.name === 'AUTH_OK' ? 'ok' : 'fail';
  }
  return last;
}

// ---- 약 QR 확인(재범 9/29, #784: QR 을 반드시 찍고 집는다) -----------------------

/** 주문이 닫힌 사유 코드 → 사람 말. 서버 알람 문구(alarms.py REASON_TEXT)와 같은 말이다. 모르는 코드는 그대로. */
export const REASON_KO = { qr_mismatch: '약 QR 이 주문과 다름', not_detected: '약 QR 을 못 읽음' };
export const reasonText = (reason) => (reason && REASON_KO[reason]) || reason || '';

/** 이 주문의 약 QR 확인(`POUCH_DETECTED`, 검출기가 봉투 QR 을 읽으면 낸다): 환자 확인(AUTH_OK) 전이면 벨트 끝,
 *  뒤면 병상에서 약을 맞춘 것이다. 반환 {belt, bed}. 주문 칸이 빈 AUTH_OK(묶음 정거장)는 같은 요청이면 본다. */
export function pouchChecks(events, orderId, requestId) {
  const out = { belt: false, bed: false };
  if (!orderId) return out;
  let authed = false;
  for (const e of events || []) {
    if (e.name === 'AUTH_OK' && (e.orderId ? e.orderId === orderId : (requestId && e.requestId === requestId))) {
      authed = true;
    } else if (e.name === 'POUCH_DETECTED' && e.orderId === orderId) {
      out[authed ? 'bed' : 'belt'] = true;
    }
  }
  return out;
}

// ---- 재고 한눈에(§6.1 `stock`, 재범 9/29 N3 "현재 알약통 N개·모듈 N개·지금 조제기에 N개") ----------

/** 선반 요약 "약통 8/9 · 모듈 9/9". 선반을 모르면 null. */
export function shelfText(stock) {
  if (!stock || !stock.shelf) return null;
  const part = (kind, word) => (stock.shelf[kind] ? `${word} ${stock.shelf[kind].present}/${stock.shelf[kind].total}` : null);
  return [part('cylinder', '약통'), part('module', '모듈')].filter(Boolean).join(' · ') || null;
}

/** 조제기 요약 "조제기 약통 2개 · 봉투 amox 2 · ibu 5". */
export function dispenserStockText(stock) {
  if (!stock) return null;
  const items = Object.entries(stock.pouchesByItem || {}).map(([item, n]) => `${item.replace(/^drug-/, '')} ${n}`);
  return [`조제기 약통 ${stock.canistersLoaded}개`, items.length ? `봉투 ${items.join(' · ')}` : null]
    .filter(Boolean).join(' · ');
}

/** 이번 세대 보충 횟수 "보충 약통 1 · 모듈 0". */
export function refillCountText(stock) {
  if (!stock || !stock.refills) return null;
  const r = stock.refills;
  return `보충 약통 ${r.cylinder || 0} · 모듈 ${r.module || 0}`;
}

// ---- QR 판독 내용(§1.12, 재범 9/29 "QR 에 포함된 정보를 간략하게") ---------------

export const QR_KIND_KO = { pouch: '약 봉투', patient: '환자', station: '스테이션', container: '약통', module: '모듈' };
export const QR_ROBOT_KO = { m0609: 'M0609 카메라' };
export const qrRobotText = (robot) => QR_ROBOT_KO[robot] || `${robot || 'AMR'} 카메라`;

/** 판독 한 줄의 요약(사람 말). `bedLabel` 은 병상 ID → 화면 이름(없으면 ID). 모르는 값은 빼고, 남는 게 없으면 ID. */
export function qrSummary(r, bedLabel = (b) => b) {
  const i = r.info || {};
  const parts = {
    pouch: [i.drug || i.item_id, i.patient_id ? `환자 ${i.patient_id}` : null, i.bed ? bedLabel(i.bed) : null],
    patient: [`환자 ${i.patient_id || r.tagId}`, i.bed ? bedLabel(i.bed) : null,
      i.order_ids && i.order_ids.length ? `주문 ${i.order_ids.join(', ')}` : null],
    station: [i.zone ? bedLabel(i.zone) : r.tagId],
    container: [i.drug || i.item_id, i.lot_id, i.expiry ? `유효 ${i.expiry}` : null],
    module: [i.drug || i.item_id, i.lot_id, i.expiry ? `유효 ${i.expiry}` : null],
  }[r.kind] || [];
  const text = parts.filter(Boolean).join(' · ');
  return text || r.tagId;
}

/** 이 주문의 봉투 판독과 이 환자의 인식표 판독(간호사 카드용). 없으면 null. */
export function qrForOrder(qrReads, orderId, patientId) {
  const reads = qrReads || [];
  return {
    pouch: orderId ? reads.find((r) => r.kind === 'pouch' && r.tagId === orderId) || null : null,
    patient: patientId ? reads.find((r) => r.kind === 'patient' && r.tagId === patientId) || null : null,
  };
}

// ---- 운영 상태: Play/Stop(§1.11)·다중 PC(§1.10) ------------------------

/** Isaac 타임라인 배지: {text, tone} 또는 null(받은 적 없음 — 옛 서버이거나 아직 1 s 안). */
export function simBadge(sr) {
  if (!sr) return null;
  if (sr.stale) return { text: 'Isaac 없음', tone: 'off' };
  if (sr.value === true) return { text: '▶ 시뮬 실행 중', tone: 'run' };
  if (sr.value === false) return { text: '⏸ 시뮬 멈춤', tone: 'stop' };
  return null;
}

/** 배포 한 줄: 두 PC 면 "다중 PC · 도메인 131 · 이 PC: arm, nav", 한 대면 null(적지 않는다). */
export function deploymentText(dep) {
  if (!dep || !dep.multiPc) return null;
  return ['다중 PC', dep.domainId !== null ? `도메인 ${dep.domainId}` : null,
    dep.roles && dep.roles.length ? `이 PC: ${dep.roles.join(', ')}` : null,
    dep.peer ? `상대 ${dep.peer}` : null].filter(Boolean).join(' · ');
}

// ---- 감속기(§1.9) ----------------------------------------------------

const STOP_REASON = { obstacle_ahead: '앞 장애물' };

/** 감속기 배지 하나: {text, tone} 또는 null(제한 없음이거나 받은 적 없음).
 *  정지(stop_reason) > 감속(pct < 100) 순. 3 s 넘게 멎었으면 값을 믿지 않고 "감속기 멎음" 으로 흐리게. */
export function speedBadge(sl) {
  if (!sl) return null;
  if (sl.stale) return { text: '감속기 멎음', tone: 'stale' };
  if (sl.stopReason) return { text: `정지 — ${STOP_REASON[sl.stopReason] || sl.stopReason}`, tone: 'stop' };
  if (sl.pct !== null && sl.pct < 100) return { text: `감속 ${Math.round(sl.pct)}%`, tone: 'slow' };
  return null;
}
