// main.js — 배선. 연결 -> store -> 패널. 판정 로직은 여기 두지 않는다.
import { fetchOrderPool, fetchDestinations, postReset, postRequest } from './api.js';
import { startLive } from './live.js';
import { renderNav } from './nav.js';
import { createStore } from './store.js';
import { renderHeader } from './panels/header.js';
import { renderTrip } from './panels/trip.js';
import { renderDispenser } from './panels/dispenser.js';
import { renderSignals } from './panels/signals.js';
import { renderQrReads } from './panels/qr.js';
import { renderAlarms } from './panels/alarms.js';
import { renderTimeline } from './panels/timeline.js';
import { renderLogs, renderLogFilters } from './panels/logs.js';
import { createFloorMap } from './panels/floormap.js';
import { createCameraView, camerasAvailable } from './panels/cameras.js';
import { el, replace, emptyNote } from './dom.js';
import { acceptWaitSuffix, groupDestinations, roomsOf, chargingRobots } from './format.js';

const $ = (id) => document.getElementById(id);

/** 시연 모드는 **URL 파라미터로만** 켠다(`?demo=1`). 폭으로 자동 전환하지 않는다 —
 *  이 모드는 신호·타임라인·로그를 **감춘다.** 정보를 감추는 전환이 창 크기 때문에
 *  저절로 일어나면 안 된다. 좁은 창은 이미 두 칸 배치가 따로 받고 있다.
 *  발표 배치: 1920 한 화면의 왼쪽은 Isaac, 오른쪽 약 960 이 이 화면이다(재범 결정 9/18). */
if (new URLSearchParams(location.search).get('demo') === '1') document.body.classList.add('is-demo');

const store = createStore();
let live = null;         // startLive() 결과 — 연결 상태와 신선도
let activeTab = 'timeline';
let floorMap = null;
let camView = null;      // 카메라 탭 — 탭이 보일 때만 스트림을 연다
let camNames = [];       // 서버가 켠 카메라(--live-sensors). 비면 탭을 감춘다     // 병원 평면도. 서버가 지도를 모르면 칸째 감춘다
let commandsHidden = false; // 서버가 403 을 주면 다시 안 보여준다

// ---------------------------------------------------------------- 그리기

/** 신선도는 데이터가 안 와도 늙어야 하므로, 렌더는 주기적으로도 돈다. */
function render() {
  if (!live) return; // startLive 가 첫 render 를 부르기 전
  const s = store.state;

  // 값의 나이(age_wall_s)는 서버가 준 것을 그대로 쓰고, 여기서는 '갱신이 끊겼는가'만 본다.
  const sinceMsg = live.sinceMsg();
  const fresh = live.fresh();

  renderHeader(s, live.conn, fresh, sinceMsg);
  renderTrip(s, $('trip'), $('trip-meta'), fresh);
  renderDispenser(s, $('dispenser'), $('dispenser-meta'), fresh);
  if (floorMap) floorMap.update(s.snapshot, fresh, chargingRobots(s.events, s.snapshot && s.snapshot.robots));
  renderSignals(s, $('signals'), $('signals-meta'), fresh, sinceMsg);
  renderQrReads(s, $('qr'), $('qr-meta'), fresh);
  // 시연 모드에서 알람 패널은 알람이 있을 때만 자리를 쓴다.
  // **그리기 전에** 바꾼다 — renderAlarms 안의 접힘 계산이 clientHeight 를 읽으므로,
  // 패널이 아직 display:none 이면 전부 접힌 것으로 세고 "아래로 N건 더" 가 붙는다.
  document.body.classList.toggle('has-alarm', !!(s.alarms && s.alarms.length));
  renderAlarms(s, $('alarms'), $('alarms-meta'));

  if (activeTab === 'timeline') renderTimeline(s, $('timeline'));
  else if (activeTab === 'logs') renderLogs(s, $('logs'));

  // 대화상자가 떠 있는 동안 트립·리셋 상태가 바뀌면 보내기 가능 여부도 따라간다.
  if ($('request-dialog').open) updateSubmitState();

  updateCommands(s);
}

// ---------------------------------------------------------------- 명령 (§7)

function updateCommands(s) {
  const box = $('commands');
  const enabled = !commandsHidden && !!s.snapshot && s.snapshot.commandsEnabled;
  box.hidden = !enabled;
}

/** 403 이면 명령 UI 를 감춘다(요건 4). */
function handleCommandResult(r, label) {
  if (r.forbidden) {
    commandsHidden = true;
    $('commands').hidden = true;
    note(`${label}: 서버가 명령을 받지 않습니다 (403 ${r.code || 'commands_disabled'})`);
    return;
  }
  if (!r.ok) {
    note(`${label} 실패: ${r.code || r.status}${r.message ? ` — ${r.message}` : ''}`);
    return;
  }
  if (label === '리셋') {
    // 202 Accepted — 동기 응답에 epoch 이 없다. 새 epoch 은 WS snapshot 으로 온다(§7.1).
    note('리셋 요청됨 — 새 epoch 은 서버가 보내는 대로 반영됩니다');
    return;
  }
  note(`${label} 보냄`);
}

function note(text) {
  const n = $('toast');
  n.textContent = text;
  n.hidden = false;
  clearTimeout(note._t);
  note._t = setTimeout(() => { n.hidden = true; }, 4000);
}

// ---- 요청 넣기 (§7.2 + §7.3) -----------------------------------------
//
// order_id 는 주문 풀에 있고 미사용이어야 수락된다. 자유 입력은 거의 거부되므로
// 풀에서 고르게 한다. 여러 건을 고르면 묶음 요청이 된다 — 웹이 묶음을 만드는 첫 경로다.

let pool = null;             // {source, problems[], orders[]} · null 이면 아직 못 받았다
let destinations = null;     // {source, destinations[]} — 후보 목록일 뿐 검증용이 아니다
const selected = new Set();  // 고른 order_id
let destTouched = false;     // 사람이 목적지를 직접 고쳤는가

/** request_id 는 새 것이어야 한다(리셋을 지나면 다시 쓸 수 있게 되지만 기다릴 이유가 없다).
 *  접두가 `web-` 이라 발행기의 `r<epoch>-<seq>` 와 겹치지 않고,
 *  epoch 과 시각이 붙어 있어 페이지를 새로 열어도 안 겹친다. */
function suggestRequestId() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  const epoch = store.state.snapshot && store.state.snapshot.epoch !== null
    ? store.state.snapshot.epoch : 0;
  return `web-${epoch}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

// 거부 사유는 error.code 로만 갈래를 친다. message 문구는 바뀔 수 있어 표시 전용이다(§0.4).
// 기다렸다 다시 누르면 되는 것들 — 사람이 입력을 고칠 게 없다.
const TRANSIENT_CODES = new Set(['trip_in_progress', 'barrier_running', 'refill_in_progress']);

/** 코드별로 사람이 다음에 할 일. **분기는 `code` 로만 한다**(api.md §0.4 — `message` 로
 *  분기하지 마라). `detail` 은 "무엇을·언제까지" 를 사람에게 말해 줄 때만 쓰고,
 *  **없을 수 있다** — 대상이 없는 거부에는 키가 아예 안 온다. 없으면 일반 문장으로 떨어진다. */
const REJECT_HINT = {
  // 기다리면 풀리지만 얼마나 걸릴지 모른다(보충 28-34 sim s, 실패할 수도 있다).
  refill_in_progress: (d) => d && d.item_id
    ? `${d.item_id} 보충이 끝나면 다시 눌러 주세요. 조제기 패널에서 진행을 볼 수 있습니다.`
    : '보충이 끝나면 다시 눌러 주세요. 조제기 패널에서 진행을 볼 수 있습니다.',
  // **묶음 안에서 주문끼리 재고를 잡아먹는 경우다**(api.md §0.4). 요청 시점에 이미 0 인
  // 품목은 refill_in_progress 가 먼저 잡고, 이건 "합쳐 보니 모자라다" 쪽이다.
  // 둘 다 기다리면 풀리지만 얼마나 걸릴지는 모른다.
  //
  // `shortages` 는 모자란 품목을 **전부** 담는다. 하나만 말하면 운영자가 하나를 빼고
  // 다시 보내 두 번째 거부를 받는다 — 시연 중에 그러면 안 된다.
  // 옛 서버는 이 키를 안 보내므로, 없으면 대표 한 건으로 떨어진다.
  insufficient_stock: (d) => {
    if (!d) return '재고가 모자랍니다. 보충이 끝나면 다시 눌러 주세요.';
    const list = Array.isArray(d.shortages) && d.shortages.length
      ? d.shortages
      : (d.item_id ? [d] : []);
    if (!list.length) return '재고가 모자랍니다. 보충이 끝나면 다시 눌러 주세요.';
    const say = list
      .map((x) => `${x.item_id} ${x.requested}개 필요 / ${x.available}개 있음`)
      .join(', ');
    return list.length > 1
      ? `${list.length}개 품목이 모자랍니다 — ${say}. 그만큼 주문을 빼거나, 보충이 끝나면 다시 눌러 주세요.`
      : `${say}. 주문을 빼거나, 보충이 끝나면 다시 눌러 주세요.`;
  },
  bad_mode_for_orders: (d) => d && typeof d.order_count === 'number'
    ? `${d.order_count}건에는 그 모드를 쓸 수 없습니다. 모드를 묶음으로 바꾸거나 주문을 하나만 고르세요.`
    : '모드를 묶음으로 바꾸거나 주문을 하나만 고르세요.',
  trip_in_progress: (d) => d && d.request_id
    ? `${d.request_id} 가 끝나면 다시 눌러 주세요. 고를 것은 그대로 두었습니다.`
    : '진행 중인 트립이 끝나면 다시 눌러 주세요. 고를 것은 그대로 두었습니다.',
  // **`accept_in_s` 만 쓴다.** detail 에 `accept_after_wall` 도 오지만 그것은 절대 시각이고,
  // 여기에는 짝이 될 `server_time` 이 안 온다 — 빼려면 브라우저 시계를 써야 한다.
  // `RESET_DONE` 전이면 언제 풀릴지 서버도 모르므로 둘 다 null 이다. 그때는 숫자를 안 쓴다.
  barrier_running: (d) => (d && typeof d.accept_in_s === 'number' && d.accept_in_s > 0)
    ? `리셋 뒤 대기 중입니다 (약 ${d.accept_in_s.toFixed(1)}초). 끝나면 다시 눌러 주세요.`
    : '리셋이 도는 중입니다. 끝나면 다시 눌러 주세요.',
  duplicate_request_id: () => '새 request_id 를 넣어 두었습니다. 그대로 다시 누르시면 됩니다.',
  empty_orders: () => '주문을 하나 이상 고르세요.',
  bad_destination: (d) => d && d.destination_id
    ? `destination_id "${d.destination_id}" 의 모양이 맞지 않습니다.`
    : 'destination_id 모양이 맞지 않습니다.',
  // 병실 묶음(2)은 한 병실 침상만 돈다. 기다려서는 안 풀리고 입력을 고쳐야 한다.
  mixed_rooms: (d) => {
    const rooms = d && Array.isArray(d.rooms) ? d.rooms.map((r) => `${r.room} ${(r.order_ids || []).join('·')}`) : [];
    return `병실 묶음은 한 병실만 돕니다${rooms.length ? ` (${rooms.join(' / ')})` : ''}. 모드를 3 · 병동 묶음으로 바꾸거나 한 병실 주문만 고르세요.`;
  },
  unknown_or_used_order: (d) => d && d.order_id
    ? `${d.order_id} 은 풀에 없거나 이미 쓴 주문입니다. 목록을 다시 받았습니다.`
    : '풀에 없거나 이미 쓴 주문입니다. 목록을 다시 받았습니다.',
};

/** 힌트 한 줄. 모르는 code 면 빈 문자열 — 지어내지 않는다. */
const rejectHint = (code, detail) => {
  const f = REJECT_HINT[code];
  return typeof f === 'function' ? f(detail) : '';
};

/** 409 처리. 코드별로 사람이 다음에 할 일을 정해 준다. */
async function handleRequestRejection(r) {
  const code = r.code || 'rejected';

  // 실물에서는 goal 거부에 사유가 안 실려 온다. 미리 못 잡은 것은 사유 불명으로 온다(§0.4).
  //
  // 사유가 비었을 때는 원인을 추측하지 않고 확인할 로그만 안내한다.
  if (code === 'rejected' && !r.message) {
    showRequestError(
      '거부됨 (사유 없음) — orchestrator 가 사유를 싣지 않았습니다. '
      + '에러 로그 탭에서 orchestrator의 "Deliver goal 거부" 줄을 확인하세요.'
    );
  } else {
    const head = code === 'rejected' ? '거부됐습니다 (사유 불명)' : `거부됨 — ${code}`;
    showRequestError([head, r.message, rejectHint(code, r.detail)].filter(Boolean).join(' · '));
  }

  if (code === 'duplicate_request_id') $('f-request-id').value = suggestRequestId();
  if (code === 'bad_destination') $('f-destination').focus();

  // 남이 그 주문을 먼저 썼을 수 있다. 목록을 다시 받아 고른 것을 정리한다.
  if (code === 'unknown_or_used_order') {
    try {
      pool = await fetchOrderPool();
      for (const o of pool.orders) if (o.used) selected.delete(o.orderId);
      renderPool();
      updateSubmitState();
    } catch { /* 못 받으면 그대로 둔다 */ }
  }

  return TRANSIENT_CODES.has(code);
}

function modeOptions(count) {
  // 1건이면 1인/긴급, 여러 건이면 묶음(병실/병동).
  return count > 1
    ? [{ v: 2, t: '2 · 병실 묶음 (BATCH_ROOM)' }, { v: 3, t: '3 · 병동 묶음 (BATCH_WARD)' }]
    : [{ v: 0, t: '0 · 1인 (SINGLE)' }, { v: 1, t: '1 · 긴급 (URGENT)' }];
}

function renderModeSelect() {
  const sel = $('f-mode');
  const want = modeOptions(selected.size);
  const keep = sel.value;
  replace(sel, want.map((o) => el('option', { value: String(o.v), text: o.t })));
  if (want.some((o) => String(o.v) === keep)) sel.value = keep;
}

function renderPool() {
  const root = $('pool');
  $('pool-source').textContent = pool ? `source: ${pool.source}` : '';

  // 풀 파일이 잘못됐으면 이유를 숨기지 않는다.
  const probs = $('pool-problems');
  if (pool && pool.problems.length) {
    probs.hidden = false;
    probs.textContent = `주문 풀 문제: ${pool.problems.join(' / ')}`;
  } else {
    probs.hidden = true;
  }

  if (!pool) return replace(root, emptyNote('주문 풀을 불러오는 중…'));
  if (!pool.orders.length) {
    return replace(root, emptyNote('주문 풀이 비어 있습니다 (서버가 풀을 모릅니다)'));
  }

  replace(root, pool.orders.map((o) => {
    const id = `pool-${o.orderId}`;
    const box = el('input', {
      type: 'checkbox', id, value: o.orderId,
      disabled: o.used,
      onchange: (ev) => {
        if (ev.currentTarget.checked) selected.add(o.orderId); else selected.delete(o.orderId);
        renderModeSelect();
        autofillDestination();
        updateSubmitState();
      },
    });
    box.checked = selected.has(o.orderId);
    // label 이 input 을 감싸고 있으므로 for 를 걸지 않는다.
    // 둘 다 있으면 체크박스를 직접 눌렀을 때 label 이 한 번 더 넘겨 토글이 상쇄된다.
    return el('label', { class: `pool-row${o.used ? ' is-used' : ''}` }, [
      box,
      el('span', { class: 'pool-id', text: o.orderId }),
      el('span', { class: 'pool-cell', text: o.patientId || '—' }),
      el('span', { class: 'pool-cell', text: o.itemId || '—' }),
      el('span', { class: 'pool-cell', text: o.bed || '—' }),
      o.used ? el('span', { class: 'flag flag-stale', text: '사용됨' }) : null,
    ]);
  }));
}

/** 고른 주문들의 침상. **풀 순서**로 늘어놓는다 — 체크한 순서가 아니다.
 *  같은 주문을 고르면 누가 어떤 순서로 눌렀든 같은 목적지가 채워지게 하려는 것이다. */
function selectedBeds() {
  const orders = pool ? pool.orders : [];
  return [...new Set(orders.filter((o) => selected.has(o.orderId) && o.bed).map((o) => o.bed))];
}

/** 병실 묶음(2)인데 고른 주문들의 병상이 두 병실 이상인가. 규칙은 format.js roomsOf(간호사 화면과 같다).
 *  한 병상이라도 병실을 모르면 판정하지 않는다(null) — 서버가 mixed_rooms 로 말해 준다. */
function mixedRooms() {
  if (!destinations) return null;
  const rooms = roomsOf(selectedBeds(), destinations.destinations);
  return rooms && rooms.length > 1 ? rooms : null;
}

/** 고른 주문의 침상을 목적지에 채워 둔다. 사람이 직접 고친 뒤에는 건드리지 않는다.
 *  1인·긴급은 어차피 서버가 풀의 침상으로 덮어쓰지만, 묶음은 이 값이 그대로 쓰인다.
 *  침상이 갈리면 **첫 주문의 침상**을 채우고 안내 줄이 그 사실을 말한다. 예전에는 빈 칸으로
 *  두었는데, 그러면 보내기가 "destination_id 을(를) 채워야 합니다" 로 막혀 확정 대본의 묶음
 *  (ord-0003 bed_b1 + ord-0004 bed_b2)이 화면에서 안 나갔다(9/19 WEB-3). */
function autofillDestination() {
  if (destTouched) return;
  const beds = selectedBeds();
  $('f-destination').value = beds.length ? beds[0] : '';
}

/** 목적지 후보를 병동·병실별로 묶어 버튼으로 늘어놓는다. 누르면 목적지 칸에 들어간다.
 *  묶기는 format.js 의 groupDestinations 가 한다(간호사 화면과 같은 규칙).
 *  칸 자체는 그대로 두어 후보에 없는 값도 칠 수 있다(§7.4 — 검증이 아니다). */
function renderDestPicker() {
  const root = $('dest-picker');
  if (!destinations || !destinations.destinations.length) return replace(root, []);

  const value = $('f-destination').value.trim();
  const beds = new Set(selectedBeds());

  replace(root, groupDestinations(destinations.destinations).map((g) => el('div', { class: 'dest-group' }, [
    el('span', { class: 'dest-group-label', text: g.label }),
    el('div', { class: 'dest-chips' }, g.items.map((d) => el('button', {
      type: 'button',
      class: 'dest-chip'
        + (d.destinationId === value ? ' is-selected' : '')
        + (beds.has(d.destinationId) ? ' is-order-bed' : ''),
      title: d.label ? `${d.label} (${d.destinationId})` : d.destinationId,
      'aria-pressed': d.destinationId === value ? 'true' : 'false',
      text: d.label || d.destinationId,
      onclick: () => {
        $('f-destination').value = d.destinationId;
        destTouched = true;
        updateSubmitState();
      },
    }))),
  ])));
}

function updateSubmitState() {
  const n = selected.size;
  const mode = Number($('f-mode').value);
  const snap = store.state.snapshot;

  // 눌러 봐야 409 인 상황은 미리 막고 이유를 적는다.
  // 기준은 reset_in_progress 가 아니라 **accepting_requests** 다 —
  // RESET_DONE 뒤에도 orchestrator 가 settle(약 3.5초)까지 더 거부하기 때문이다.
  const blocked = snap && !snap.acceptingRequests
    ? (snap.resetInProgress ? '리셋이 도는 중입니다' : `리셋 뒤 대기 중입니다${acceptWaitSuffix(snap)}`)
    : snap && snap.trip ? `진행 중 트립(${snap.trip.requestId})이 끝나야 넣을 수 있습니다`
    : null;

  // **보충 중인지는 미리 판정하지 않는다.** 예전에는 슬롯 재고를 세어 "거부됩니다" 를
  // 미리 띄웠는데, 그건 서버 규칙을 화면에 복사한 것이었다(같은 규칙이 두 곳에 있으면
  // 어긋난다). 서버가 `refill_in_progress` + `detail.item_id` 로 정확히 말해 주므로
  // 누른 뒤 그 답을 그대로 보여 주는 쪽이 맞다. 조제기 패널에 PAUSED·보충 중이 이미 떠 있다.
  // 병실이 섞인 병실 묶음은 서버가 400 mixed_rooms 로 거부한다. 입력을 고쳐야 풀리므로 미리 막는다.
  const mixed = mode === 2 ? mixedRooms() : null;
  $('request-submit').disabled = n === 0 || !!blocked || !!mixed;
  const note = $('request-note');
  note.textContent = blocked
    || (n === 0 ? '주문을 하나 이상 고르세요'
      : n === 1 ? '1건 — 단건 요청' : `${n}건 — 묶음 요청`);
  note.className = 'dialog-note';
  updateDestinationHint(mode, n, mixed);
}

/** 목적지 칸 아래 안내.
 *  - 1인(0)·긴급(1) 은 서버가 풀의 환자→침상 매핑으로 덮어쓴다. 보낸 값과 다를 수 있다.
 *  - 후보 목록(GET /api/destinations)에 없는 값도 **수락된다**. 검증이 아니라 경고만 한다. */
function updateDestinationHint(mode, count, mixed = null) {
  const hint = $('dest-hint');
  const value = $('f-destination').value.trim();
  const overridden = count > 0 && (mode === 0 || mode === 1);

  const known = destinations
    ? destinations.destinations.some((d) => d.destinationId === value)
    : true; // 목록을 못 받았으면 경고하지 않는다

  // 묶음인데 침상이 갈리고 사람이 아직 안 골랐다 — 채워 둔 값은 첫 주문의 침상이다.
  const beds = selectedBeds();
  const split = count > 1 && beds.length > 1 && !destTouched;

  const parts = [];
  // 트립 중 잠김 문구에 가려지지 않게 이 줄에 적는다. 보내기는 updateSubmitState 가 막는다.
  if (mixed) parts.push(`병실 묶음은 한 병실만 돕니다 — 고른 주문이 ${mixed.join(', ')} 에 걸쳐 있습니다. 3 · 병동 묶음으로 바꾸거나 한 병실 주문만 고르세요`);
  if (split) parts.push(`고른 주문들의 침상이 갈립니다(${beds.join(', ')}) — 첫 주문의 침상 ${beds[0]} 을 채웠습니다. 다른 곳이면 아래에서 고르세요`);
  else if (!value && count > 1) parts.push('묶음 목적지를 아래에서 고르세요');
  if (overridden) parts.push('1인·긴급은 서버가 주문 풀의 침상으로 덮어씁니다');
  if (value && !known) parts.push(`후보 목록에 없는 목적지입니다 — 수락은 되지만 실물에서 GoToZone 이 거부해 HOLD_RETURN 으로 끝날 수 있습니다`);

  hint.hidden = !parts.length;
  hint.className = 'dialog-hint' + (mixed || (value && !known) || split || (!value && count > 1) ? ' is-warn' : '');
  hint.textContent = parts.join(' · ');
  renderDestPicker();
}

function showRequestError(text) {
  const box = $('request-error');
  box.textContent = text || '';
  box.hidden = !text;
}

/** 요청 창 입력을 처음으로 되돌린다. **보내기가 수락됐을 때만** 부른다 —
 *  취소·Esc 로 닫았다 다시 열면 고른 주문·모드·목적지·request_id 가 그대로 남는다.
 *  예전에는 열 때마다 지워서, 주문을 잘못 골라 닫았다 열면 목적지를 다시 쳐야 했다. */
function resetRequestForm() {
  selected.clear();
  destTouched = false;
  $('f-destination').value = '';
  $('f-request-id').value = '';
}

async function openRequestDialog() {
  showRequestError('');
  if (!$('f-request-id').value.trim()) $('f-request-id').value = suggestRequestId();
  renderModeSelect();
  updateSubmitState();
  renderPool();
  $('request-dialog').showModal();

  const [poolRes, destRes] = await Promise.allSettled([fetchOrderPool(), fetchDestinations()]);

  pool = poolRes.status === 'fulfilled'
    ? poolRes.value
    // §7.3 이 아직 없는 서버면 404 다. 풀 없이도 대화상자는 뜬다.
    : { source: poolRes.reason && poolRes.reason.status === 404 ? 'none (서버에 /api/order_pool 없음)' : `오류 ${poolRes.reason}`, problems: [], orders: [] };

  destinations = destRes.status === 'fulfilled' ? destRes.value : null;
  if (destinations) {
    replace($('dest-list'), destinations.destinations.map((d) =>
      el('option', { value: d.destinationId, label: d.label || d.kind })));
  }

  // 남겨 둔 선택 가운데 그사이 쓰였거나 풀에서 사라진 주문은 뺀다.
  // 빠진 게 있으면 모드 선택지(1건/여러 건)와 채워 둔 목적지도 다시 맞춘다.
  const live = new Set(pool.orders.filter((o) => !o.used).map((o) => o.orderId));
  const before = selected.size;
  for (const id of [...selected]) if (!live.has(id)) selected.delete(id);
  if (selected.size !== before) { renderModeSelect(); autofillDestination(); }

  renderPool();
  updateSubmitState();
}

function wireCommands() {
  $('btn-reset').addEventListener('click', async () => {
    if (!confirm('시뮬을 리셋합니다. 진행 중 트립은 중단됩니다. 계속할까요?')) return;
    try {
      handleCommandResult(await postReset(), '리셋');
    } catch (err) {
      note(`리셋 실패: ${err.message}`);
    }
  });

  $('btn-request').addEventListener('click', openRequestDialog);
  $('request-cancel').addEventListener('click', () => $('request-dialog').close());
  $('f-destination').addEventListener('input', () => { destTouched = true; updateSubmitState(); });
  $('f-mode').addEventListener('change', updateSubmitState);

  $('request-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    showRequestError('');

    const byId = new Map((pool ? pool.orders : []).map((o) => [o.orderId, o]));
    const orders = [...selected].map((id) => {
      const o = byId.get(id);
      return { order_id: id, patient_id: o ? o.patientId : null, item_id: o ? o.itemId : null };
    });
    const req = {
      request_id: $('f-request-id').value.trim(),
      mode: Number($('f-mode').value),
      destination_id: $('f-destination').value.trim(),
      orders,
    };
    const missing = [
      !orders.length ? '주문(1건 이상)' : null,
      !req.destination_id ? 'destination_id' : null,
      !req.request_id ? 'request_id' : null,
    ].filter(Boolean);
    if (missing.length) {
      showRequestError(`${missing.join(' · ')} 을(를) 채워야 합니다`);
      return;
    }
    const what = orders.length > 1 ? `묶음 ${orders.length}건` : '1건';
    if (!confirm(`요청 ${req.request_id} (${what}) 를 ${req.destination_id} 로 보냅니다. 계속할까요?`)) return;

    let r;
    try {
      r = await postRequest(req);
    } catch (err) {
      showRequestError(`보내기 실패: ${err.message}`);
      return;
    }

    if (r.ok) {
      resetRequestForm();
      $('request-dialog').close();
      // 서버가 목적지를 덮어썼으면 그 사실을 알린다 — 보낸 값과 다를 수 있다.
      const changed = r.appliedDestinationId && r.appliedDestinationId !== req.destination_id;
      note(changed
        ? `요청 ${req.request_id} 보냄 (${what}) — 목적지는 ${r.appliedDestinationId} 로 적용됨 (${r.destinationSource || '출처 미상'})`
        : `요청 ${req.request_id} 보냄 (${what})`);
      return;
    }
    if (r.forbidden) {
      $('request-dialog').close();
      handleCommandResult(r, '요청');
      return;
    }
    await handleRequestRejection(r);
  });
}

// ---------------------------------------------------------------- 탭

function wireTabs() {
  for (const tab of document.querySelectorAll('.tab')) {
    tab.addEventListener('click', () => {
      activeTab = tab.dataset.tab;
      for (const t of document.querySelectorAll('.tab')) t.classList.toggle('is-active', t === tab);
      $('timeline').hidden = activeTab !== 'timeline';
      $('logs').hidden = activeTab !== 'logs';
      $('cameras').hidden = activeTab !== 'cameras';
      // 카메라는 탭이 보일 때만 스트림을 연다(서버 부하 규칙, api.md §1.8).
      if (activeTab === 'cameras') camView.open(camNames); else camView.close();
      $('timeline-filters').hidden = activeTab !== 'timeline';
      $('log-filters').hidden = activeTab !== 'logs';
      render();
    });
  }
  camView = createCameraView($('cameras'));
  // 카메라가 켜진 서버에서만 탭을 보인다. 서버가 다시 뜰 수 있으니 10초마다 다시 묻는다.
  const checkCams = () => camerasAvailable().then((list) => {
    camNames = list;
    $('tab-cameras').hidden = !list.length;
    if (!list.length && activeTab === 'cameras') document.querySelector('.tab[data-tab="timeline"]').click();
  });
  checkCams();
  setInterval(checkCams, 10000);
  renderLogFilters($('log-filters'), render);
  $('log-filters').hidden = true;
}

// ---------------------------------------------------------------- 시작

function start() {
  renderNav($('nav'), 'dev');
  wireTabs();
  wireCommands();
  floorMap = createFloorMap($('map'), $('map-meta'), {
    onAvailable: (ok) => { $('map-panel').hidden = !ok; },
  });
  live = startLive(store, { render, logs: true });
  render();
}

start();
