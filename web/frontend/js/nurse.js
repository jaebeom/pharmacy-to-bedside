// nurse.js — 간호사 화면. 개발자 화면과 같은 서버·같은 store 를 쓰되, 간호사가 할 일만 남긴다:
//   지금 배송이 어디쯤인지 / 확인할 알림 / 환자별 약이 어떻게 됐는지 / 약 배송 요청.
// 신호·타임라인·로그·seq·epoch 같은 기술 값은 보이지 않는다(개발자 화면 몫).
//
// 판정은 새로 만들지 않는다. 주문 결말은 format.js 의 orderState·isBadOrder 를,
// 단계는 서버의 phase·phase_label 을, 보충은 서버의 paused·refilling 을 그대로 쓴다.
// 여기서 하는 것은 **말을 바꾸는 것**뿐이다.
import { fetchOrderPool, fetchDestinations, fetchQueue, postRequest } from './api.js';
import { createStore } from './store.js';
import { startLive } from './live.js';
import { renderNav } from './nav.js';
import { applyPrefs } from './prefs.js';
import { el, replace } from './dom.js';
import { createFloorMap } from './panels/floormap.js';
import { createCameraView, camerasAvailable } from './panels/cameras.js';
import {
  modeInfo, orderState, isBadOrder, isPharmacySegmentDone,
  PHASE_TRACK, RESET_PHASES, trackIndex, phaseText, acceptWaitSuffix, groupDestinations, roomsOf, bedName, authResult, chargingRobots, simBadge, speedBadge,
  pouchChecks, qrForOrder, shelfText, dispenserStockText,
} from './format.js';

const $ = (id) => document.getElementById(id);
const store = createStore();

/** 촬영 화면(`?film=1`) — 1920 녹화의 오른쪽 반(960×1040)에 맞춘 배치. 기능은 같고 배치·단계 표시만 다르다.
 *  단계는 촬영 계획(docs/presentation/hospital-demo-shotlist.md)의 7 구간으로 보인다. */
const FILM = new URLSearchParams(location.search).get('film') === '1';
if (FILM) document.body.classList.add('is-film');
let live = null;
let floorMap = null;
let camPip = null;        // 촬영 화면: 평면도 위 작은 카메라 창(단계에 맞춰 하나만)
let camNames = [];        // 서버가 켠 카메라(--live-sensors)
let camShown = '';        // 지금 연 카메라 — 바뀔 때만 다시 연다

// ---------------------------------------------------------------- 말 바꾸기

/** 17단계(status_view)를 간호사용 4단계로 접는다. 경계는 PHASE_TRACK 의 zone·phase 로 정한다.
 *  화면에는 이 4단계와 함께 서버 원문(phase_label)을 작게 같이 적는다 — 지어낸 말만 남기지 않는다. */
const NURSE_STEPS = ['약 준비', '병실로 이동', '병상 도착·전달', '끝'];
const WARD_MOVE = new Set(['moving', 'arriving']);
const WARD_HAND = new Set(['arrived', 'unloading', 'auth', 'locked']);
const TRIP_END = new Set(['order_done', 'returning', 'docked']);

/** 촬영용 7 단계. 서버 phase 로만 정하고, 보충은 조제기가 멈춘 동안 켠다.
 *  이름은 작전 카드(9/23 v2): 요청 → 보충 → 조제 → 집기 → 배송 → 도착 → 복귀.
 *  BIG 은 큰 배너에 쓰는 말(지금 무엇을 하는 중인가). */
const FILM_STEPS = ['요청', '보충', '조제', '집기', '배송', '도착', '복귀'];
const FILM_BIG = ['요청 접수', '약 보충 중', '조제 중', '봉투 집는 중', '배송 중', '도착 · 전달 중', '복귀 중'];
const FILM_OF_PHASE = {
  accepted: 0, docked_load: 2, dispensing: 2, loading: 3, load_done: 3, arm_home: 4,
  moving: 4, arriving: 4, arrived: 5, unloading: 5, auth: 5, locked: 5,
  order_done: 6, returning: 6, docked: 6,
};
function filmStep(trip) {
  const i = trackIndex(trip);
  const phase = i >= 0 ? PHASE_TRACK[i].phase : trip.phase;
  return phase in FILM_OF_PHASE ? FILM_OF_PHASE[phase] : -1;
}

/** 촬영 배너가 쓸 단계. **서버의 snapshot.stage(§1.7)를 먼저 쓴다** — 보충을 "이 트립의 약품" 으로
 *  가리는 규칙은 서버에만 있다. 옛 서버(stage 없음)면 trip.phase 묶음과 조제기 PAUSED 로 떨어진다. */
const sawRefill = new Set();   // 보충 단계를 거친 request_id — 지나간 보충 칸을 "완료" 로 칠할 근거
function stageInfo(t, snap) {
  const g = snap.stage;
  if (g) {
    const refillNow = g.key === 'refill';
    if (refillNow && t) sawRefill.add(t.requestId);
    return { step: g.index === null ? -1 : g.index, refillNow, refillIds: g.refillItemIds, server: true };
  }
  // 서버 규칙(§1.7)을 따라 한다: 출발 전(조제까지)에 **이 트립의 약** 이 멈췄을 때만 보충이다.
  // 트립 약을 모르면 보충으로 짐작하지 않는다. 다른 약의 보충은 이 트립의 단계가 아니다(실물 점검 3번 9/23).
  const d = snap.dispenser;
  const step = t ? filmStep(t) : -1;
  const ids = d ? (d.refilling ? d.refillingItemIds : d.pausedItemIds) : [];
  const mine = new Set(t ? t.orders.map((o) => o.itemId).filter(Boolean) : []);
  const hit = ids.filter((id) => mine.has(id));
  const refillNow = !!(d && (d.paused || d.refilling)) && step >= 0 && step <= 2 && hit.length > 0;
  if (refillNow) sawRefill.add(t.requestId);
  return { step: refillNow ? 1 : step, refillNow, refillIds: hit, server: false };
}

function nurseStep(trip) {
  const i = trackIndex(trip);
  const phase = i >= 0 ? PHASE_TRACK[i].phase : trip.phase;
  if (TRIP_END.has(phase)) return 3;
  if (WARD_HAND.has(phase)) return 2;
  if (WARD_MOVE.has(phase)) return 1;
  if (i >= 0) return 0;          // 조제실 단계
  return -1;                     // 모르는 단계 — 막대를 그리지 않고 원문만 적는다
}

/** 주문 결말 → 간호사 말. 색 갈래는 tone 하나로. outcome 은 format.js 가 해석한다. */
const OUTCOME_WORD = {
  accepted:      { ko: '접수됨',        tone: 'info' },
  in_progress:   { ko: '배송 중',       tone: 'info' },
  delivered:     { ko: '전달 완료',     tone: 'ok' },
  pharmacy_done: { ko: '조제실까지 완료', tone: 'ok' },
  held:          { ko: '약제실로 회수',  tone: 'warn' },
  aborted:       { ko: '중단됨',        tone: 'bad' },
  timeout:       { ko: '시간 초과',     tone: 'bad' },
};

function orderWord(o) {
  if (o.outcome && OUTCOME_WORD[o.outcome]) return OUTCOME_WORD[o.outcome];
  // outcome 을 안 주는 옛 서버: format.js 의 판정으로 떨어진다.
  if (isPharmacySegmentDone(o)) return OUTCOME_WORD.pharmacy_done;
  const st = orderState(o);
  return { ko: st.ko, tone: isBadOrder(o) ? 'bad' : 'info' };
}

/** 알람 kind → 간호사에게 할 말과 할 일. 여기 없는 kind(신호 끊김·시계 멈춤·리셋 중 등)는
 *  간호사가 손쓸 것이 아니라 "시스템 경고 N건" 한 줄로만 센다. DISPENSER_PAUSED 는 위 띠가 말한다. */
const NURSE_ALARM = {
  URGENT_ARRIVING: { title: '긴급 약이 곧 도착합니다', act: '병상에서 받을 준비를 해 주세요.', tone: 'urgent' },
  AUTH_FAIL:       { title: '병상 앞 확인에 실패했습니다', act: '로봇 앞에서 환자 인식표를 확인해 주세요.', tone: 'bad' },
  HOLD_RETURN:     { title: '약이 약제실로 돌아갑니다', act: '약제실에 문의해 주세요.', tone: 'warn' },
  ABORT:           { title: '배송이 중단됐습니다', act: '약제실에 문의해 주세요.', tone: 'bad' },
  TIMEOUT:         { title: '배송 시간이 초과됐습니다', act: '약제실에 문의해 주세요.', tone: 'bad' },
  REFILL_FAILED:   { title: '약 보충이 늦어지고 있습니다', act: '약제실에 문의해 주세요.', tone: 'warn' },
  RESET_STUCK:     { title: '시스템이 멈췄습니다', act: '담당자를 불러 주세요.', tone: 'bad' },
  // 감속기 정지가 5 s 넘게 이어짐(§4.1) — 복도에 무언가 막고 있다. 도킹·지도 알람은 담당자 몫이라 "시스템 경고" 로 센다.
  OBSTACLE_STOP:   { title: '배송 로봇이 장애물 앞에 멈췄습니다', act: '복도에 막힌 것이 있는지 확인해 주세요.', tone: 'warn' },
};
const QUIET_ALARMS = new Set(['DISPENSER_PAUSED']);
/** 주문이 약 QR 때문에 닫혔을 때(#784: QR 을 반드시 찍는다) 회수·중단 대신 쓰는 말. 사유는 주문의 reason 코드다. */
const NURSE_PICK_QR = {
  qr_mismatch:  { title: '약 봉투가 주문과 달라 멈췄습니다', act: '약제실에 문의해 주세요.', tone: 'bad' },
  not_detected: { title: '약 봉투의 QR 을 읽지 못해 멈췄습니다', act: '약제실에 문의해 주세요.', tone: 'warn' },
};
/** 스냅샷 트립에 있는 주문의 닫힌 사유 코드. 없으면 ''. */
function orderReason(orderId) {
  const t = store.state.snapshot && store.state.snapshot.trip;
  const o = orderId && t && t.orders ? t.orders.find((x) => x.orderId === orderId) : null;
  return o ? o.reason : '';
}

/** 요청 거부 → 간호사 말. **분기는 code 로만 한다**(api.md §0.4). detail 은 없을 수 있다.
 *  개발자 화면(main.js REJECT_HINT)과 같은 code 를 다루지만 말투와 할 일이 다르다 —
 *  api.md 에 code 가 늘면 두 곳을 같이 본다. */
const NURSE_REJECT = {
  refill_in_progress: (d) => `${d && d.item_id ? `${d.item_id} ` : '약 '}보충 중이라 지금은 보낼 수 없어요. 보충이 끝나면 다시 눌러 주세요.`,
  insufficient_stock: (d) => {
    const list = d && Array.isArray(d.shortages) && d.shortages.length ? d.shortages : (d && d.item_id ? [d] : []);
    const say = list.map((x) => `${x.item_id} ${x.requested}개 필요, ${x.available}개 있음`).join(' / ');
    return `약이 모자랍니다${say ? ` (${say})` : ''}. 환자 수를 줄이거나 보충이 끝난 뒤 다시 보내 주세요.`;
  },
  trip_in_progress: () => '다른 배송이 진행 중이에요. 끝나면 다시 눌러 주세요. 고른 내용은 그대로 두었습니다.',
  barrier_running: (d) => `시스템을 준비하는 중이에요${d && typeof d.accept_in_s === 'number' && d.accept_in_s > 0 ? ` (약 ${Math.ceil(d.accept_in_s)}초)` : ''}. 잠시 뒤 다시 눌러 주세요.`,
  duplicate_request_id: () => '요청 번호가 겹쳤어요. 새 번호로 바꿔 두었으니 다시 눌러 주세요.',
  unknown_or_used_order: () => '이미 요청된 환자가 있어요. 목록을 새로 받았으니 다시 골라 주세요.',
  bad_mode_for_orders: () => '보내는 방법이 고른 환자 수와 맞지 않아요. 2번을 다시 골라 주세요.',
  bad_destination: () => '목적지가 올바르지 않아요. 3번에서 병상을 다시 골라 주세요.',
  empty_orders: () => '환자를 한 명 이상 골라 주세요.',
  mixed_rooms: () => '"같은 병실로 한 번에" 는 한 병실만 돕니다. 2번에서 "병동을 돌며 차례로" 를 고르거나 한 병실 환자만 고르세요.',
};

// ---------------------------------------------------------------- 주문 기억

// 서버는 **지금 트립의 주문 상태만** 준다. 트립이 끝나면 그 결말은 snapshot 에서 사라진다.
// 그래서 이 화면이 본 결말을 epoch 안에서 기억한다. 페이지를 연 뒤에 끝난 것만 알 수 있고,
// 그 전에 끝난 것은 "결과 모름" 으로 적는다 — 지어내지 않는다.
let seenEpoch = null;
const seenOrders = new Map();   // order_id -> 마지막으로 본 주문(트립 안)
const seenMode = new Map();     // order_id -> 그 주문이 실린 트립의 mode
const seenReq = new Map();      // order_id -> 그 주문이 실린 request_id(인증 이벤트를 맞출 때)
const seenReqSize = new Map();  // order_id -> 그 요청의 주문 수

// 방금 끝난 트립. 서버는 트립이 끝나면 snapshot.trip 을 비우므로, "지금 배송" 칸이 곧장 대기로
// 돌아가 간호사가 결과를 못 본다. 마지막으로 본 트립을 붙들어 두고 다음 트립이 올 때까지 보여 준다.
let liveTrip = null;       // 지금 보고 있는 트립(마지막으로 본 모습)
let finishedTrip = null;   // {trip, at: Date} — 가장 최근에 끝난 트립

function rememberTrip(snap) {
  if (!snap) return;
  if (snap.epoch !== seenEpoch) {
    seenEpoch = snap.epoch; seenOrders.clear(); seenMode.clear(); seenReq.clear(); seenReqSize.clear();
    liveTrip = null; finishedTrip = null;   // 리셋하면 지난 결과는 새 세대의 것이 아니다
  }
  const t = snap.trip && !RESET_PHASES.has(snap.trip.phase) ? snap.trip : null;
  if (liveTrip && (!t || t.requestId !== liveTrip.requestId)) {
    finishedTrip = { trip: liveTrip, at: new Date() };
  }
  liveTrip = t;
  if (!t) return;
  for (const o of t.orders) {
    if (!o.orderId) continue;
    seenOrders.set(o.orderId, o);
    seenReq.set(o.orderId, t.requestId);
    seenReqSize.set(o.orderId, t.orders.filter((x) => x.orderId).length);
    if (t.mode !== null) seenMode.set(o.orderId, t.mode);
  }
}

/** 촬영 화면의 카메라 창: 보충·조제 동안은 M0609 손 카메라(약통 QR), 집기·도착 동안은 AMR 손 카메라(트레이 상판).
 *  그 밖에는 닫는다(보이는 동안만 스트림, api.md §1.8). 서버 stage 가 없으면 열지 않는다. */
const CAM_OF_STAGE = { refill: 'm0609_hand', dispense: 'm0609_hand', pick: 'amr_hand', arrive: 'amr_hand' };
function updateCamPip(snap) {
  const key = snap && snap.stage ? snap.stage.key : null;
  const want = key && CAM_OF_STAGE[key] && camNames.includes(CAM_OF_STAGE[key]) ? CAM_OF_STAGE[key] : '';
  if (want === camShown) return;
  camShown = want;
  if (want) camPip.open([want]); else camPip.close();
}

/** 도크에서 충전 대기 중인 AMR 배지(마지막 이벤트가 DOCKED). 배터리 수치는 모델이 없어 적지 않는다. */
function chargeChips() {
  const ids = [...chargingRobots(store.state.events, store.state.snapshot && store.state.snapshot.robots)];
  return ids.length ? el('span', { class: 'n-charge-row' }, ids.map((id) => el('span', { class: 'n-charge', text: `${id} 충전 중 ⚡` }))) : null;
}

/** 트립이 병상에 도착했는가(도착·전달·복귀). 서버 stage(§1.7) 가 있으면 그것, 없으면 phase 묶음. */
function tripArrived(t) {
  if (!t) return false;
  const g = store.state.snapshot && store.state.snapshot.stage;
  if (g && typeof g.index === 'number') return g.index >= 5;
  return nurseStep(t) >= 2;
}

/** 환자 확인(인식표 인증) 결과 — 이번 epoch 의 AUTH_OK·AUTH_FAIL 중 마지막 것. 주문으로 맞추고,
 *  주문 칸이 빈 인증(묶음 정거장, api.md §6)은 그 요청의 주문이 하나일 때만 그 주문 것으로 본다. 그 밖은 모른다(칩 없음).
 *  결과: 'ok' | 'fail' | null */
function authOf(orderId, requestId, ordersInRequest) {
  return authResult(store.state.events, orderId, requestId, ordersInRequest);
}
function authChip(orderId, requestId, ordersInRequest) {
  const a = authOf(orderId, requestId, ordersInRequest);
  if (!a) return null;
  const auth = el('span', { class: `n-auth is-${a}`, title: a === 'ok' ? 'AUTH_OK' : 'AUTH_FAIL', text: a === 'ok' ? '환자 확인됨' : '환자 확인 실패' });
  // 병상에서 환자 확인 뒤 약 QR 을 읽어 맞췄다(#784 "병상 QR → 약 QR 매칭 → 내려놓기").
  if (a !== 'ok' || !pouchChecks(store.state.events, orderId, requestId).bed) return auth;
  return el('span', { class: 'n-checks' }, [
    auth, ' ', el('span', { class: 'n-auth is-ok', title: 'POUCH_DETECTED (환자 확인 뒤)', text: '약 확인됨' }),
  ]);
}

/** 이번 epoch 에 ORDER_DONE 이 지나간 주문. 결말은 모르지만 "끝났다" 는 안다. */
function doneOrderIds() {
  const out = new Set();
  for (const e of store.state.events) if (e.name === 'ORDER_DONE' && e.orderId) out.add(e.orderId);
  return out;
}

// ---------------------------------------------------------------- 그리기

let pool = null;          // GET /api/order_pool
let destinations = null;  // GET /api/destinations
let commandsHidden = false;

function render() {
  if (!live) return;
  const s = store.state;
  const snap = s.snapshot;
  const up = live.conn.state === 'open';
  rememberTrip(snap);

  $('conn').className = 'n-conn ' + (up && live.fresh() ? 'is-ok' : up ? 'is-warn' : 'is-bad');
  $('conn-text').textContent = !up ? (live.conn.state === 'connecting' ? '연결 중…' : '연결 끊김')
    : live.fresh() ? '실시간' : '갱신 멈춤';
  document.body.classList.toggle('is-disconnected', !up);

  $('btn-request').hidden = commandsHidden || !(snap && snap.commandsEnabled);
  // 시뮬이 멈췄거나 없으면 연결 표시 옆에 적는다(실행 중이면 비운다 — 늘 보이는 초록은 눈을 끌지 않는다).
  const sb = snap ? simBadge(snap.simRunning) : null;
  $('sim-state').hidden = !sb || sb.tone === 'run';
  $('sim-state').textContent = sb ? sb.text : '';

  renderBanner(snap, up);
  renderStock(snap);
  renderNow(snap);
  if (FILM) updateCamPip(snap);
  if (floorMap) floorMap.update(snap, live.fresh(), chargingRobots(store.state.events, store.state.snapshot && store.state.snapshot.robots));
  renderAlerts(s.alarms || []);
  renderPatients(snap);
  // 250 ms 마다 목록을 다시 그리면 누르던 체크박스의 초점을 뺏는다. 여기서는 보내기 가능 여부만.
  if ($('request-dialog').open) updateSummary();
}

/** 위 띠 하나 — 가장 급한 것 하나만. 끊김 > 리셋 중 > 요청 대기 > 보충 중.
 *  리셋 멈춤(RESET_STUCK)은 알림 칸이 말한다. */
/** 약제실 재고 한 줄(§6.1 `stock`, 재범 9/29 N3): "약제실 재고 — 약통 8/9 · 모듈 9/9 · 조제기 약통 2개 …". */
function renderStock(snap) {
  const box = $('stock');
  const s = snap && snap.dispenser ? snap.dispenser.stock : null;
  const shelf = shelfText(s);
  box.hidden = FILM || !s;
  box.textContent = s ? `약제실 재고 — ${[shelf, dispenserStockText(s)].filter(Boolean).join(' · ')}` : '';
}

function renderBanner(snap, up) {
  const b = $('banner');
  let text = null;
  let tone = 'info';
  if (!up) {
    text = snap ? '연결이 끊겼습니다 — 아래 내용은 마지막으로 받은 것이고, 지금과 다를 수 있습니다.'
      : '서버에 연결하는 중입니다…';
    tone = 'bad';
  } else if (snap && snap.resetInProgress) {
    text = '시스템을 다시 준비하는 중입니다. 잠시 기다려 주세요.';
  } else if (snap && !snap.acceptingRequests) {
    text = `곧 새 요청을 받습니다${acceptWaitSuffix(snap)}.`;
  } else if (!FILM && snap && snap.dispenser && (snap.dispenser.paused || snap.dispenser.refilling)) {
    // 조제기 전체 상태다 — 지금 트립의 약과 상관없다. 그래서 촬영 화면에서는 띄우지 않는다(배너의 단계·보충 칸이
    // 서버 stage 로 "이 트립 약의 보충" 만 말한다, 실물 점검 9절 3번 9/23).
    // 보충이 끝났는데(REFILL_DONE) 조제기가 아직 재개를 안 알린 구간이 있다(실물 약 8–14 s). 그때는 "보충 중" 이 아니다.
    const d = snap.dispenser;
    const ids = d.refilling ? d.refillingItemIds : d.pausedItemIds;
    const what = ids.length ? ` — ${ids.join(', ')}` : '';
    text = d.refilling
      ? `약 보충 중${what}. 이 약이 든 요청은 보충이 끝난 뒤에 보낼 수 있습니다.`
      : `조제기 재개 대기${what}. 보충은 끝났고 곧 다시 조제합니다.`;
    tone = 'warn';
  }
  b.hidden = !text;
  b.className = `n-banner is-${tone}`;
  b.textContent = text || '';
}

function renderNow(snap) {
  const root = $('now');
  if (!snap) return replace(root, el('p', { class: 'n-empty', text: '아직 받은 정보가 없습니다.' }));
  if (FILM) return replace(root, filmBanner(snap));

  const t = snap.trip;
  if (!t || RESET_PHASES.has(t.phase)) {
    const ready = snap.acceptingRequests && !snap.resetInProgress;
    return replace(root, [
      finishedTrip ? finishedCard(finishedTrip) : null,
      el('div', { class: 'n-idle' }, [
        el('div', { class: `n-idle-title${ready ? ' is-ok' : ''}`, text: ready ? '배송 로봇 대기 중' : '준비 중' }),
        chargeChips(),
        el('div', { class: 'n-idle-sub', text: ready ? '새 요청을 바로 받을 수 있습니다.' : `잠시 뒤 요청을 받을 수 있습니다${acceptWaitSuffix(snap)}.` }),
      ]),
    ]);
  }

  const m = modeInfo(t.mode);
  const step = nurseStep(t);
  const known = t.orders.filter((o) => o.orderId);
  const bad = known.some(isBadOrder);

  replace(root, [
    el('div', { class: 'n-now-head' }, [
      el('span', { class: `n-mode n-mode-${t.mode === null ? 'x' : t.mode}`, text: m.unknown ? '방식 모름' : m.short }),
      el('span', { class: 'n-dest', title: t.destinationId || '', text: t.destinationId ? `→ ${bedText(t.destinationId)}` : '→ 목적지 모름' }),
    ]),
    FILM ? filmSteps(t, snap, bad) : el('ol', { class: 'n-steps', 'aria-label': '배송 단계' }, NURSE_STEPS.map((label, i) => el('li', {
      class: `n-step-item ${step < 0 ? 'is-future' : i < step ? 'is-done' : i === step ? (bad ? 'is-bad' : 'is-current') : 'is-future'}`,
      'aria-current': i === step ? 'step' : null,
      text: label,
    }))),
    el('div', { class: 'n-phase', title: t.phase }, [
      el('span', { class: 'n-phase-label', text: '지금: ' }),
      el('span', { text: phaseText(t) }),
    ]),
    el('ul', { class: 'n-now-orders' }, known.length
      ? known.map((o) => {
        const w = orderWord(o);
        return el('li', {}, [
          el('span', { class: 'n-who', text: patientText(o.patientId, o.orderId) }),
          el('span', { class: 'n-what', text: o.itemId || '약 모름' }),
          authChip(o.orderId, t.requestId, known.length),
          el('span', { class: `n-tag is-${w.tone}`, text: w.ko }),
          qrLine(o),
        ]);
      })
      : [el('li', { class: 'n-empty', text: '실린 약 정보를 아직 받지 못했습니다.' })]),
  ]);
}

/** 이 주문을 로봇 카메라가 QR 로 읽은 내용(§1.12, 재범 9/29 "QR 에 포함된 정보를 간략하게"). 없으면 null.
 *  약 봉투 QR → 약 이름, 환자 인식표 QR → 환자 번호·병상. QR 그림이 아니라 그 안의 정보다. */
function qrLine(o) {
  const snap = store.state.snapshot;
  const row = pool && pool.orders ? pool.orders.find((x) => x.orderId === o.orderId) : null;
  const q = qrForOrder(snap && snap.qrReads, o.orderId, o.patientId || (row && row.patientId));
  const parts = [];
  if (q.pouch) parts.push(`약 QR: ${q.pouch.info.drug || q.pouch.info.item_id || q.pouch.tagId}`);
  if (q.patient) parts.push(`환자 QR: ${q.patient.tagId}${q.patient.info.bed ? ` (${bedText(q.patient.info.bed)})` : ''}`);
  if (!parts.length) return null;
  return el('div', { class: 'n-qr', title: [q.pouch && q.pouch.tagId, q.patient && `pt-${q.patient.tagId}`].filter(Boolean).join(' · '),
    text: `▣ ${parts.join('  ·  ')}` });
}

/** 병상 이름. 병원 zones 면 "C2 병실 D5", 이름표가 없으면 ID 그대로. */
const bedText = (bed) => (bed ? bedName(bed, destinations ? destinations.destinations : []) : '병상 모름');

/** 촬영 화면의 큰 배너: 지금 단계 한 마디를 크게, 그 아래 목적지·환자, 맨 아래 7 단계 막대.
 *  트립이 없으면 방금 끝난 결과(전달 완료 등)나 대기, 보충 중이면 보충을 크게 적는다. */
function filmBanner(snap) {
  const t = snap.trip && !RESET_PHASES.has(snap.trip.phase) && !(snap.stage && snap.stage.index === null) ? snap.trip : null;
  const info = stageInfo(t, snap);
  const d = snap.dispenser;
  // 트립 밖의 보충은 서버 stage 가 말하지 않는다(idle). 조제기가 멈춰 있으면 그것을 크게 적는다.
  const refilling = t ? info.refillNow : !!(d && (d.paused || d.refilling));
  const refillIds = t ? info.refillIds : d ? (d.refilling ? d.refillingItemIds : d.pausedItemIds) : [];

  if (!t) {
    let big; let tone; let sub;
    if (finishedTrip) {
      const card = finishedSummary(finishedTrip);
      big = card.head; tone = card.tone; sub = card.sub;
    } else if (snap.resetInProgress || (snap.stage && snap.stage.key === 'reset')) {
      big = '리셋 중'; tone = 'idle'; sub = '시스템을 다시 준비합니다';
    } else if (!snap.acceptingRequests) {
      big = '준비 중'; tone = 'idle'; sub = `곧 요청을 받습니다${acceptWaitSuffix(snap)}`;
    } else {
      big = '대기'; tone = 'idle'; sub = '새 요청을 기다립니다';
    }
    // 트립 밖에서 조제기가 멈춰 있으면 크게 적는다. 보충이 끝나고 재개만 기다리는 동안은 "보충 중" 이라 쓰지 않는다.
    if (refilling && !finishedTrip) {
      big = d && d.refilling ? '약 보충 중' : '조제기 재개 대기'; tone = 'refill'; sub = refillIds.join(', ') || sub;
    }
    return el('div', { class: `f-banner is-${tone}` }, [
      el('div', { class: 'f-big-row' }, [el('span', { class: 'f-big', text: big }), chargeChips()]),
      el('div', { class: 'f-sub', text: sub }),
      filmSteps(null, snap, false),
    ]);
  }

  const step = info.step;
  const known = t.orders.filter((o) => o.orderId);
  const bad = known.some(isBadOrder);
  const m = modeInfo(t.mode);
  const who = known.map((o) => `${patientText(o.patientId, o.orderId)} ${o.itemId || ''}`.trim()).join(' · ');
  return el('div', { class: `f-banner ${bad ? 'is-bad' : 'is-live'}${t.mode === 1 ? ' is-urgent' : ''}` }, [
    el('div', { class: 'f-big-row' }, [
      el('span', { class: 'f-big', text: step >= 0 && step < FILM_BIG.length ? FILM_BIG[step] : phaseText(t) }),
      refilling ? el('span', { class: 'f-chip is-refill', text: `보충 중 ${refillIds.join(', ')}`.trim() }) : null,
      // 감속기: 배송 중에 앞 장애물로 서거나 줄이면 화면에서 바로 보이게(§1.9).
      ...(() => { const sb = speedBadge(snap.speedLimit); return sb ? [el('span', { class: `f-chip is-speed-${sb.tone}`, text: sb.text })] : []; })(),
    ]),
    el('div', { class: 'f-sub' }, [
      el('span', { class: `n-mode n-mode-${t.mode === null ? 'x' : t.mode}`, text: m.unknown ? '방식 모름' : m.short }),
      el('span', { class: 'f-dest', text: t.destinationId ? `→ ${bedText(t.destinationId)}` : '→ 목적지 모름' }),
      el('span', { class: 'f-who', text: who }),
    ]),
    filmSteps(t, snap, bad),
    el('div', { class: 'f-phase', title: t.phase, text: `지금: ${phaseText(t)}` }),
  ]);
}

/** 촬영용 7 구간 막대. ② 보충은 트립 단계와 따로 돈다(조제기가 멈추면 켜진다). */
function filmSteps(t, snap, bad) {
  // 트립이 없으면 막대는 모두 꺼 둔다. 방금 끝났으면 전부 지나간 것으로 칠한다.
  const info = t ? stageInfo(t, snap) : null;
  const step = t ? info.step : (finishedTrip ? FILM_STEPS.length : -1);
  const refilling = t ? info.refillNow : false;
  const refilled = t ? sawRefill.has(t.requestId) : (finishedTrip && sawRefill.has(finishedTrip.trip.requestId));
  return el('ol', { class: 'n-steps n-steps-film', 'aria-label': '구간' }, FILM_STEPS.map((label, i) => {
    let cls = step < 0 ? 'is-future' : i < step ? 'is-done' : i === step ? (bad ? 'is-bad' : 'is-current') : 'is-future';
    // 보충은 이 트립이 실제로 거쳤을 때만 "완료" 로 칠한다. 안 거쳤으면 흐리게(건너뜀).
    if (i === 1) cls = refilling ? 'is-current is-refill' : refilled && step > 1 ? 'is-done' : 'is-skip';
    return el('li', { class: `n-step-item ${cls}`, 'aria-current': i === step ? 'step' : null, text: label });
  }));
}

/** 방금 끝난 배송 한 장. 결말은 마지막으로 본 주문 상태(orderWord)로만 말한다 — 트립이 사라졌다고
 *  성공으로 읽지 않는다(ORDER_DONE 은 끝났다는 뜻일 뿐, api.md §2). */
/** 끝난 트립 한 줄 요약 — 머리말·색·부제. 촬영 배너와 간호사 카드가 같이 쓴다. */
function finishedSummary({ trip, at }) {
  const known = trip.orders.filter((o) => o.orderId);
  const words = known.map(orderWord);
  const tone = words.some((w) => w.tone === 'bad') ? 'bad'
    : words.length && words.every((w) => w.tone === 'ok') ? 'ok'
    : words.some((w) => w.tone === 'warn') ? 'warn' : 'idle';
  const delivered = known.length && known.every((o) => o.outcome === 'delivered');
  const head = delivered ? '전달 완료 · DELIVERED' : tone === 'ok' ? '배송 완료' : tone === 'bad' ? '배송 실패' : tone === 'warn' ? '약제실로 회수' : '배송 끝남 (결과 모름)';
  const p = (n) => String(n).padStart(2, '0');
  const sub = [trip.destinationId ? `→ ${bedText(trip.destinationId)}` : null,
    known.map((o) => patientText(o.patientId, o.orderId)).join(' · ') || null,
    `${p(at.getHours())}:${p(at.getMinutes())} 끝남`].filter(Boolean).join('  ');
  return { known, words, tone, head, sub };
}

function finishedCard({ trip, at }) {
  const { known, words, tone, head } = finishedSummary({ trip, at });
  const p = (n) => String(n).padStart(2, '0');
  return el('div', { class: `n-done is-${tone}` }, [
    el('div', { class: 'n-done-head' }, [
      el('span', { class: 'n-done-title', text: head }),
      el('span', { class: 'n-done-time', text: `${p(at.getHours())}:${p(at.getMinutes())} 끝남` }),
    ]),
    el('div', { class: 'n-done-dest', text: trip.destinationId ? `→ ${bedText(trip.destinationId)}` : '' }),
    el('ul', { class: 'n-now-orders' }, known.map((o, i) => el('li', {}, [
      el('span', { class: 'n-who', text: patientText(o.patientId, o.orderId) }),
      el('span', { class: 'n-what', text: o.itemId || '약 모름' }),
      authChip(o.orderId, trip.requestId, known.length),
      el('span', { class: `n-tag is-${words[i].tone}`, text: words[i].ko }),
    ]))),
  ]);
}

function patientText(patientId, orderId) {
  if (patientId) return `환자 ${patientId}`;
  const p = pool && pool.orders.find((o) => o.orderId === orderId);
  return p && p.patientId ? `환자 ${p.patientId}` : '환자 모름';
}

function renderAlerts(alarms) {
  const root = $('alerts');
  const shown = [];
  let tech = 0;
  for (const a of alarms) {
    if (QUIET_ALARMS.has(a.kind)) continue;
    let say = NURSE_ALARM[a.kind];
    if ((a.kind === 'HOLD_RETURN' || a.kind === 'ABORT') && NURSE_PICK_QR[orderReason(a.orderId)]) {
      say = NURSE_PICK_QR[orderReason(a.orderId)];
    }
    if (!say) { tech += 1; continue; }
    // "곧 도착" 은 그 트립이 도는 동안만 뜻이 있다. 알람은 epoch 이 바뀔 때까지 남으므로(api.md §6)
    // 트립이 끝났거나 다른 트립이면 간호사에게 보이지 않는다. 개발자 화면에는 그대로 남는다.
    if (a.kind === 'URGENT_ARRIVING' && !(liveTrip && a.requestId && a.requestId === liveTrip.requestId)) continue;
    // 도착한 뒤에는 "곧 도착" 이 아니다. 회차46(66450ae) 녹화에서 복귀 중에도 떠 있었다(알람은 epoch 끝까지 남는다).
    if (a.kind === 'URGENT_ARRIVING' && tripArrived(liveTrip)) continue;
    shown.push({ a, say });
  }
  // 급한 것부터: 긴급 도착 > 실패·중단 > 나머지
  const rank = { urgent: 0, bad: 1, warn: 2 };
  shown.sort((x, y) => (rank[x.say.tone] ?? 3) - (rank[y.say.tone] ?? 3));

  $('alerts-count').textContent = shown.length ? String(shown.length) : '';
  // 촬영 화면에서는 알림이 없으면 칸을 비워 두지 않고 접는다(지도가 그 자리를 받는다).
  // 촬영 화면은 기술 경고 줄도 감추므로, 간호사 알림이 없으면 빈 칸이다.
  root.closest('section').classList.toggle('is-empty', !shown.length && (FILM || !tech));
  // 반쪽 폭(녹화)에서는 간호사 알림이 없으면 칸을 접는다. 기술 경고 한 줄만 있는 칸은 녹화에 쓸모가 없다.
  root.closest('section').classList.toggle('no-nurse-alert', !shown.length);
  const rows = shown.map(({ a, say }) => {
    const p = a.orderId && pool ? pool.orders.find((o) => o.orderId === a.orderId) : null;
    const where = [p && p.patientId ? `환자 ${p.patientId}` : null, p && p.bed ? p.bed : null].filter(Boolean).join(' · ');
    return el('div', { class: `n-alert is-${say.tone}`, title: a.message }, [
      el('div', { class: 'n-alert-title', text: say.title }),
      where ? el('div', { class: 'n-alert-where', text: where }) : null,
      el('div', { class: 'n-alert-act', text: say.act }),
    ]);
  });
  if (tech) {
    rows.push(el('a', {
      class: 'n-alert-tech', href: `index.html${location.search}`,
      text: `시스템 경고 ${tech}건 — 담당자용 개발자 화면에서 볼 수 있습니다`,
    }));
  }
  replace(root, rows.length ? rows : [el('p', { class: 'n-empty is-ok', text: '확인할 알림이 없습니다.' })]);
}

function renderPatients(snap) {
  const root = $('patients');
  if (!pool) return replace(root, el('p', { class: 'n-empty', text: '환자 목록을 불러오는 중…' }));
  if (!pool.orders.length) return replace(root, el('p', { class: 'n-empty', text: '서버가 주문 목록을 모릅니다.' }));

  $('patients-sub').textContent = `${pool.orders.filter((o) => !o.used).length}명 요청 가능`;
  const tripIds = new Set(snap && snap.trip ? snap.trip.orders.map((o) => o.orderId) : []);
  const done = doneOrderIds();
  if (FILM) return replace(root, queue ? serverQueue(tripIds) : filmQueue(tripIds, done));

  replace(root, el('table', { class: 'n-table' }, [
    el('thead', {}, el('tr', {}, ['환자', '약', '병상', '상태'].map((h) => el('th', { scope: 'col', text: h })))),
    el('tbody', {}, pool.orders.map((o) => {
      const seen = seenOrders.get(o.orderId);
      const word = poolWord(o, done);
      const urgent = seenMode.get(o.orderId) === 1 || (!seen && o.mode === 'urgent');
      return el('tr', { class: tripIds.has(o.orderId) ? 'is-live' : '' }, [
        el('td', {}, [
          el('span', { class: 'n-who', text: o.patientId ? `환자 ${o.patientId}` : '환자 모름' }),
          urgent ? el('span', { class: 'n-urgent-dot', title: '긴급', text: '긴급' }) : null,
        ]),
        el('td', { class: 'n-mono', text: o.itemId || '—' }),
        el('td', { title: o.bed || '', text: o.bed ? bedText(o.bed) : '—' }),
        el('td', { class: 'n-state' }, [
          el('span', { class: `n-tag is-${word.tone}`, text: word.ko }),
          authChip(o.orderId, seen ? seenReq.get(o.orderId) : null, seen ? seenReqSize.get(o.orderId) : 0),
        ]),
      ]);
    })),
  ]));
}

/** 주문 한 건의 간호사 말. 환자 표와 촬영 큐가 같이 쓴다. */
function poolWord(o, done) {
  const seen = seenOrders.get(o.orderId);
  if (!o.used && !seen) return { ko: '요청 전', tone: 'idle', rank: 2 };
  if (seen) {
    const w = orderWord(seen);
    return { ...w, rank: w.tone === 'info' ? 1 : 3 };
  }
  if (done.has(o.orderId)) return { ko: '끝남 (결과 모름)', tone: 'idle', rank: 3 };
  return { ko: '요청됨', tone: 'info', rank: 1 };
}

/** 서버 큐(§7.7) — 진행 → 대기 → 완료. 완료는 outcome 으로 가른다(held·aborted 도 "완료" 칸에 있다). */
let queue = null;
function serverQueue(tripIds) {
  const bedOf = (o) => (o.group && o.label ? `${o.group} ${o.label}` : o.bed ? bedText(o.bed).replace(/ 병실 /, ' ') : '—');
  const item = (o, tag) => el('li', { class: tripIds.has(o.orderId) ? 'is-live' : '' }, [
    el('span', { class: 'f-q-who', text: o.patientId ? `환자 ${o.patientId}` : o.orderId }),
    el('span', { class: 'f-q-bed', text: bedOf(o) }),
    tag,
  ]);
  const word = (o) => (o.outcome && OUTCOME_WORD[o.outcome] ? OUTCOME_WORD[o.outcome] : { ko: '요청됨', tone: 'info' });
  return el('ol', { class: 'f-queue' }, [
    ...queue.inProgress.map((o) => item(o, tripIds.has(o.orderId)
      ? el('span', { class: 'n-tag is-info', text: '지금' })
      : el('span', { class: `n-tag is-${word(o).tone}`, text: word(o).ko }))),
    ...queue.waiting.map((o) => item(o, el('span', { class: 'n-tag is-idle', text: '요청 전' }))),
    ...queue.done.map((o) => item(o, el('span', { class: `n-tag is-${word(o).tone}`, text: word(o).ko }))),
  ]);
}

/** 옛 서버(/api/queue 없음)용 — 주문 풀과 이 화면이 본 상태로 만든다. 지금 도는 것 → 요청됨 → 요청 전 → 끝난 것 순. 두 칸, 한 줄에 환자·병상·상태. */
function filmQueue(tripIds, done) {
  const rows = pool.orders.map((o, i) => {
    const w = poolWord(o, done);
    return { o, w, rank: tripIds.has(o.orderId) ? 0 : w.rank, i };
  }).sort((a, b) => a.rank - b.rank || a.i - b.i);
  return el('ol', { class: 'f-queue' }, rows.map(({ o, w, rank }) => el('li', { class: rank === 0 ? 'is-live' : '' }, [
    el('span', { class: 'f-q-who', text: o.patientId ? `환자 ${o.patientId}` : o.orderId }),
    el('span', { class: 'f-q-bed', text: o.bed ? bedText(o.bed).replace(/ 병실 /, ' ') : '—' }),
    rank === 0 ? el('span', { class: 'n-tag is-info', text: '지금' }) : el('span', { class: `n-tag is-${w.tone}`, text: w.ko }),
  ])));
}

// ---------------------------------------------------------------- 요청

const picked = new Set();      // 고른 order_id
let how = null;                // 고른 mode (0 1인 · 1 긴급 · 2 병실 묶음 · 3 병동 묶음)
let dest = '';                 // 묶음 목적지
let destTouched = false;

const HOW_SINGLE = [
  { v: 0, t: '일반', sub: '환자 침상으로 보냅니다' },
  { v: 1, t: '긴급', sub: '먼저 보냅니다' },
];
const HOW_BATCH = [
  { v: 2, t: '같은 병실로 한 번에', sub: '병실 묶음' },
  { v: 3, t: '병동을 돌며 차례로', sub: '병동 묶음' },
];

/** 요청 번호. 개발자 화면(`web-`)·발행기(`r`)와 접두가 달라 서로 겹치지 않는다. */
function newRequestId() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  const epoch = store.state.snapshot && store.state.snapshot.epoch !== null ? store.state.snapshot.epoch : 0;
  return `nurse-${epoch}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}
let requestId = '';

function pickedOrders() {
  return pool ? pool.orders.filter((o) => picked.has(o.orderId)) : [];
}
function pickedBeds() {
  return [...new Set(pickedOrders().map((o) => o.bed).filter(Boolean))];
}
/** 고른 환자들의 병상이 걸친 병실. 모르면 null(format.js roomsOf). */
function pickedRooms() {
  return destinations ? roomsOf(pickedBeds(), destinations.destinations) : null;
}
/** "같은 병실로 한 번에"(2) 를 골랐는데 병실이 섞였다 — 서버가 mixed_rooms 로 거부한다. */
const mixedForRoom = () => how === 2 && (pickedRooms() || []).length > 1;

function renderPick() {
  const root = $('pick');
  if (!pool) return replace(root, el('p', { class: 'n-empty', text: '불러오는 중…' }));
  const open = pool.orders.filter((o) => !o.used);
  if (!open.length) return replace(root, el('p', { class: 'n-empty', text: '지금 요청할 수 있는 환자가 없습니다.' }));
  replace(root, open.map((o) => {
    const box = el('input', {
      type: 'checkbox', value: o.orderId,
      // 고를 때 목록을 다시 그리지 않는다 — 누른 칸이 바뀌어 초점이 사라진다. 칸 색만 바꾼다.
      onchange: (ev) => {
        const on = ev.currentTarget.checked;
        if (on) picked.add(o.orderId); else picked.delete(o.orderId);
        ev.currentTarget.closest('.n-pick-card').classList.toggle('is-on', on);
        onPickChanged();
      },
    });
    box.checked = picked.has(o.orderId);
    return el('label', { class: `n-pick-card${picked.has(o.orderId) ? ' is-on' : ''}` }, [
      box,
      el('span', { class: 'n-pick-who', text: o.patientId ? `환자 ${o.patientId}` : '환자 모름' }),
      el('span', { class: 'n-pick-what', text: o.itemId || '약 모름' }),
      el('span', { class: 'n-pick-bed', title: o.bed || '', text: bedText(o.bed) }),
      o.mode === 'urgent' ? el('span', { class: 'n-urgent-dot', text: '긴급 권장' }) : null,
    ]);
  }));
}

function onPickChanged() {
  const n = picked.size;
  const choices = n > 1 ? HOW_BATCH : HOW_SINGLE;
  if (!choices.some((c) => c.v === how)) {
    // 1명이면 풀이 권하는 방식(긴급 권장이면 긴급), 여러 명이면 병실 묶음.
    // 여러 명인데 병실이 섞였으면 처음부터 "병동을 돌며"(3).
    const only = n === 1 ? pickedOrders()[0] : null;
    const rooms = pickedRooms();
    how = n > 1 ? (rooms && rooms.length > 1 ? 3 : 2) : (only && only.mode === 'urgent' ? 1 : 0);
  }
  if (!destTouched) dest = pickedBeds()[0] || '';
  updateRequestState();
}

function renderHow() {
  const n = picked.size;
  $('how-step').disabled = n === 0;
  const choices = n > 1 ? HOW_BATCH : HOW_SINGLE;
  replace($('how'), choices.map((c) => el('button', {
    type: 'button',
    class: `n-seg-btn${how === c.v ? ' is-on' : ''}${c.v === 1 ? ' is-urgent' : ''}`,
    'aria-pressed': how === c.v ? 'true' : 'false',
    onclick: () => { how = c.v; updateRequestState(); },
  }, [el('span', { class: 'n-seg-t', text: c.t }), el('span', { class: 'n-seg-s', text: c.sub })])));
}

function renderWhere() {
  const n = picked.size;
  const batch = n > 1;
  $('where-step').disabled = n === 0;
  const beds = pickedBeds();

  // 1명(일반·긴급)은 서버가 주문 풀의 환자 침상으로 보낸다(§7.2). 고를 것이 없다.
  if (!batch) {
    $('where-note').textContent = n ? `환자 침상(${bedText(beds[0])})으로 갑니다.` : '먼저 1번에서 환자를 고르세요.';
    $('where-note').className = 'n-where-note';
    return replace($('beds'), []);
  }

  const split = beds.length > 1;
  const mixed = mixedForRoom();
  $('where-note').textContent = mixed
    ? `고른 환자들이 여러 병실(${pickedRooms().join(', ')})에 있어 "같은 병실로 한 번에" 는 보낼 수 없습니다. 2번에서 "병동을 돌며 차례로" 를 고르세요.`
    : split && !destTouched
      ? `고른 환자들의 병상이 다릅니다(${beds.map(bedText).join(', ')}). 첫 환자의 병상 ${bedText(beds[0])} 으로 정해 두었습니다 — 다른 곳이면 아래에서 고르세요.`
      : '로봇이 멈출 곳을 고르세요.';
  $('where-note').className = `n-where-note${mixed || (split && !destTouched) ? ' is-warn' : ''}`;

  const list = destinations ? destinations.destinations : [];
  if (!list.length) {
    return replace($('beds'), el('p', { class: 'n-empty', text: '병상 목록을 받지 못했습니다. 첫 환자의 병상으로 보냅니다.' }));
  }
  const mine = new Set(beds);
  replace($('beds'), groupDestinations(list).map((g) => el('div', { class: 'n-bed-group' }, [
    el('span', { class: 'n-bed-group-label', text: g.label }),
    el('div', { class: 'n-bed-row' }, g.items.map((d) => el('button', {
      type: 'button',
      class: `n-bed${d.destinationId === dest ? ' is-on' : ''}${mine.has(d.destinationId) ? ' is-mine' : ''}`,
      'aria-pressed': d.destinationId === dest ? 'true' : 'false',
      title: `${bedName(d.destinationId, list)} (${d.destinationId})${mine.has(d.destinationId) ? ' — 고른 환자의 병상' : ''}`,
      text: d.label || d.destinationId,
      onclick: () => { dest = d.destinationId; destTouched = true; updateRequestState(); },
    }))),
  ])));
}

/** 누르기 전에 막을 것만 막는다 — 리셋 중·다른 배송 중. 보충 중은 미리 판정하지 않는다
 *  (서버가 refill_in_progress 로 정확히 말해 준다. 개발자 화면과 같은 원칙, #206). */
function blockedReason() {
  const snap = store.state.snapshot;
  if (!snap) return '서버 정보를 기다리는 중입니다';
  if (!snap.acceptingRequests) return snap.resetInProgress ? '시스템을 다시 준비하는 중입니다' : `곧 요청을 받습니다${acceptWaitSuffix(snap)}`;
  if (snap.trip && !RESET_PHASES.has(snap.trip.phase)) return '다른 배송이 끝나면 보낼 수 있습니다';
  return null;
}

function targetOf() {
  return picked.size > 1 ? dest : (pickedBeds()[0] || '');
}

/** 고른 것이 바뀌었을 때 — 2·3번과 요약을 다시 그린다. 1번 목록은 열 때·목록을 새로 받을 때만 그린다. */
function updateRequestState() {
  renderHow();
  renderWhere();
  updateSummary();
}

/** 보내기 가능 여부와 요약 한 줄. 트립·리셋 상태가 바뀔 때마다 불린다. */
function updateSummary() {
  const n = picked.size;
  const blocked = blockedReason();
  const target = targetOf();
  const mixed = mixedForRoom();
  $('request-submit').disabled = n === 0 || how === null || !target || !!blocked || mixed;
  const howText = [...HOW_SINGLE, ...HOW_BATCH].find((c) => c.v === how);
  $('summary').textContent = blocked
    || (n === 0 ? '환자를 골라 주세요'
      : mixed ? '병실이 섞였습니다 — 2번을 바꿔 주세요'
      : `${n}명 · ${howText ? howText.t : ''} · ${target ? bedText(target) : '목적지 없음'}`);
  $('summary').className = `n-summary${blocked || mixed ? ' is-warn' : ''}`;
}

function showRequestError(text) {
  $('request-error').textContent = text || '';
  $('request-error').hidden = !text;
}

async function loadPool() {
  try { pool = await fetchOrderPool(); } catch { /* 없으면 그대로 */ }
  // 그사이 쓰인 환자는 고른 것에서 뺀다.
  if (pool) for (const o of pool.orders) if (o.used) picked.delete(o.orderId);
}

async function openRequest() {
  showRequestError('');
  if (!requestId) requestId = newRequestId();
  $('request-dialog').showModal();
  renderPick();
  updateRequestState();
  const [, d] = await Promise.allSettled([loadPool(), fetchDestinations()]);
  if (d.status === 'fulfilled') destinations = d.value; // 못 받으면 앞서 받은 것을 그대로 쓴다
  renderPick();
  onPickChanged();
}

function resetRequest() {
  picked.clear();
  how = null;
  dest = '';
  destTouched = false;
  requestId = '';
}

async function submitRequest(ev) {
  ev.preventDefault();
  showRequestError('');
  const orders = pickedOrders().map((o) => ({ order_id: o.orderId, patient_id: o.patientId, item_id: o.itemId }));
  const target = targetOf();
  if (!orders.length || how === null || !target) return;

  const howText = [...HOW_SINGLE, ...HOW_BATCH].find((c) => c.v === how).t;
  const who = pickedOrders().map((o) => (o.patientId ? `환자 ${o.patientId}` : o.orderId)).join(', ');
  if (!confirm(`${who} 에게 약을 보냅니다 (${howText}, ${bedText(target)}).\n보낼까요?`)) return;

  let r;
  try {
    r = await postRequest({ request_id: requestId, mode: how, destination_id: target, orders });
  } catch (err) {
    showRequestError(`보내지 못했습니다 — 서버에 닿지 않습니다 (${err.message}).`);
    return;
  }
  if (r.ok) {
    resetRequest();
    $('request-dialog').close();
    toast(`요청했습니다 — ${who}`);
    loadPool().then(render);
    return;
  }
  if (r.forbidden) {
    commandsHidden = true;
    $('request-dialog').close();
    toast('이 화면에서는 요청을 넣을 수 없습니다 (서버가 막아 두었습니다).');
    render();
    return;
  }
  const code = r.code || 'rejected';
  const f = NURSE_REJECT[code];
  showRequestError(f ? f(r.detail) : `요청이 거절됐습니다 (${code}). 담당자에게 알려 주세요.`);
  if (code === 'duplicate_request_id') requestId = newRequestId();
  if (code === 'unknown_or_used_order') { await loadPool(); renderPick(); onPickChanged(); }
}

function toast(text) {
  const t = $('toast');
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { t.hidden = true; }, 5000);
}

// ---------------------------------------------------------------- 시작

function start() {
  applyPrefs();
  if (FILM) $('patients-title').firstChild.textContent = '주문 큐 ';
  renderNav($('nav'), 'nurse');
  $('btn-request').addEventListener('click', openRequest);
  $('request-cancel').addEventListener('click', () => $('request-dialog').close());
  $('request-form').addEventListener('submit', submitRequest);

  // 지도는 AMR 이 어디쯤 가는지 한눈에 보려는 것이다. 서버가 지도를 모르면 칸째 감춘다.
  if (FILM) {
    camPip = createCameraView($('cam-pip'), { compact: true });
    const checkCams = () => camerasAvailable().then((list) => { camNames = list; });
    checkCams();
    setInterval(checkCams, 10000);
  }
  floorMap = createFloorMap($('map'), $('map-meta'), {
    onAvailable: (ok) => { $('map-card').hidden = !ok; },
  });
  live = startLive(store, { render });
  loadPool().then(render);
  // 병상 이름(C2 병실 D5)을 창 밖에서도 쓰려고 시작할 때 한 번 받는다. 못 받으면 ID 로 적는다.
  fetchDestinations().then((d) => { destinations = d; render(); }).catch(() => {});
  // 촬영 화면의 주문 큐는 서버가 가른다(§7.7). WS 로 안 오니 1초마다 받는다. 없으면(404) 풀로 만든다.
  if (FILM) {
    const pull = () => fetchQueue().then((q) => { queue = q; render(); }).catch(() => { queue = null; });
    pull();
    setInterval(pull, 1000);
  }
  // 환자 목록의 "요청 전/요청됨" 은 풀의 used 가 말한다. push 가 없으니 5초마다 다시 받는다.
  setInterval(() => { if (!$('request-dialog').open) loadPool().then(render); }, 5000);
  render();
}

start();
