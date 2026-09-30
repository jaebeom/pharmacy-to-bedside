// api.js — 서버 접촉을 모으는 유일한 모듈. 대상: 백엔드 API v0.1 (web/api.md).
//
// api.md 가 바뀌면 **이 파일만** 고친다. 패널(js/panels/*)은 아래 화면 모델만 안다.
//   - 엔드포인트/봉투  -> connect(), fetchSnapshot(), fetchEvents(), fetchLogs()
//   - 서버 필드 매핑   -> normalizeSnapshot() 과 map* 들
//   - 명령            -> postReset(), postRequest()
//
// 시간 규약(§0.1): 정렬·판정은 sim_s + epoch, 신선도는 wall. 섞지 않는다.

const params = new URLSearchParams(location.search);

/** `?api=http://127.0.0.1:8000` 로 백엔드를 가리킬 수 있다(개발 중 :8000 과 정적 서버가 다를 때). */
const API_BASE = (params.get('api') || '').replace(/\/$/, '');

/** fixture 모드는 명시적 opt-in 만. 끊긴 걸 가짜 데이터로 덮으면 안 된다(요건 3). */
export const isFixtureMode = params.get('fixture') === '1';

const apiUrl = (path) => `${API_BASE}${path}`;

function wsUrl() {
  const q = params.get('ws');
  if (q) return q;
  if (API_BASE) return API_BASE.replace(/^http/, 'ws') + '/ws';
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}/ws`;
}

export const STALE_TOPIC_S = 1.0; // §1.1
export const STALE_CLOCK_S = 2.0; // §1.1

/** 서버는 변화가 없어도 **1초에 한 번은** snapshot 을 push 한다(§3).
 *  그래서 소켓의 침묵은 곧 죽음이다 — "지금 아무 일도 안 일어난다"가 아니다.
 *  실측 push 간격: 중앙값 1007 ms, 최대 1208 ms. 지터를 감안해 3배로 잡는다.
 *
 *  주의: age_wall_s 에 "스냅샷을 받은 뒤 흐른 시간"을 더하지 않는다(§3).
 *  서버가 보낸 값을 그대로 쓰고, 끊겼는지는 이 유예로만 따로 판정한다. */
export const PUSH_GRACE_S = 3.0;
const RECONNECT_MIN_MS = 500;
const RECONNECT_MAX_MS = 8000;

/** signals 의 5개 키는 고정이다(§1). 표시 순서도 여기서 정한다. */
export const SIGNAL_KEYS = ['arm_at_home', 'base_stopped', 'gripper_holding', 'belt', 'm0609_at_home'];
export const SIGNAL_LABEL = {
  arm_at_home: 'AMR 팔 원위치',
  base_stopped: 'AMR 정지',
  gripper_holding: '그리퍼 파지',
  belt: '벨트',
  m0609_at_home: 'M0609 원위치',
};

// ---------------------------------------------------------------- 매핑

const num = (v, d = NaN) => (typeof v === 'number' && Number.isFinite(v) ? v : d);
/** 나이는 **음수일 수 없다.** 음수가 왔다는 것은 그 값의 시각이 스냅샷보다 미래라는
 *  뜻이고, 실제로는 서버 시계가 뒤로 뛰었다는 뜻이다(백엔드 확인: 서버가 나이를
 *  steady clock 이 아니라 시스템 벽시계로 잰다 — api.md §1.1 의 알려진 차이).
 *
 *  그 방향이 위험하다. **낡은 신호가 싱싱해 보인다.** 서버의 `stale` 도 같은 뺄셈에서
 *  나오므로 그것도 같이 틀린다 — 서버 판정만 믿으면 초록이 뜬다.
 *  나이를 모른다고 말하는 쪽이 맞다. Infinity 로 보내면 화면이 UNKNOWN 으로 그린다. */
const age = (v) => { const n = num(v, Infinity); return n < 0 ? Infinity : n; };
const str = (v, d = '') => (typeof v === 'string' ? v : d);
const bool = (v) => v === true;
const arr = (v) => (Array.isArray(v) ? v : []);
/** null 을 살려서 넘긴다 — "알 수 없음"으로 그려야 하는 값들(§1.3). */
const nullable = (v) => (v === undefined ? null : v);

function mapOrder(o) {
  return {
    orderId: str(o.order_id),
    patientId: nullable(typeof o.patient_id === 'string' ? o.patient_id : null),
    itemId: nullable(typeof o.item_id === 'string' ? o.item_id : null),
    state: typeof o.state === 'number' ? o.state : null,
    // 종료 상태의 근거는 이벤트가 아니라 이것이다(§2).
    stateName: str(o.state_name),
    reason: str(o.reason),
    // 서버가 주는 파생 결말. state/state_name/reason 은 ROS 원본이고 이것은 그 위의 판정이다.
    // 아직 안 내는 서버도 있으므로 빈 문자열이면 화면이 (state_name, reason)으로 떨어진다.
    outcome: str(o.outcome),
    stamp: num(o.stamp),
  };
}

function mapTrip(t) {
  if (!t || typeof t !== 'object') return null; // 진행 중 트립 없음(§1)
  return {
    requestId: str(t.request_id),
    mode: typeof t.mode === 'number' ? t.mode : null,   // null 가능(§1.3)
    modeName: str(t.mode_name),
    modeSource: nullable(typeof t.mode_source === 'string' ? t.mode_source : null),
    destinationId: nullable(typeof t.destination_id === 'string' && t.destination_id ? t.destination_id : null),
    robotId: str(t.robot_id),
    phase: str(t.phase),
    // status_view.py 의 한글 원문. 화면에는 이것을 그대로 찍는다(§1.2). 고쳐 쓰지 않는다.
    phaseLabel: str(t.phase_label),
    phaseSource: nullable(typeof t.phase_source === 'string' ? t.phase_source : null),
    startedSimS: num(t.started_sim_s),
    lastEventSimS: num(t.last_event_sim_s),
    orders: arr(t.orders).map(mapOrder),
  };
}

function mapDispenser(d) {
  if (!d || typeof d !== 'object') return null; // 아직 한 번도 못 받음(§1)
  return {
    paused: bool(d.paused),
    pausedItemIds: arr(d.paused_item_ids).map(String),
    // refilling 은 이벤트 이름만으로 판정하므로 정확하다.
    // refilling_item_ids 는 detail 에서 긁는 표시 전용이라 비어 있을 수 있다(§4.1).
    refilling: bool(d.refilling),
    refillingItemIds: arr(d.refilling_item_ids).map(String),
    queueLength: num(d.queue_length, 0),
    beltOccupied: bool(d.belt_occupied),
    slots: arr(d.slots).map((s) => ({
      itemId: str(s.item_id),
      slot: typeof s.slot === 'number' ? s.slot : null,
      slotName: str(s.slot_name),
      lotId: str(s.lot_id),
      expiry: str(s.expiry),
      count: num(s.count, 0),
      active: bool(s.active),
    })),
    stamp: num(d.stamp),
    wall: str(d.wall),
    stale: bool(d.stale),
    // 현재 epoch 의 마지막 REFILL_DONE 요약. 리셋하면 null 로 돌아간다(api.md §6.1).
    lastRefill: mapLastRefill(d.last_refill),
    // 보충 **중** 대상(§6.1) — refilling_item_ids 와 같은 순서. 옛 서버는 키가 없다 → 빈 배열.
    refillTargets: arr(d.refill_targets).map((t) => ({
      itemId: str(t.item_id),
      slotName: typeof t.slot_name === 'string' && t.slot_name ? t.slot_name : null,
      kind: typeof t.kind === 'string' && t.kind ? t.kind : null,
      target: typeof t.target === 'string' && t.target ? t.target : null,
    })),
    // M0609 손 카메라의 마지막 약통 QR 판독. 약통 확인을 켠 기동에서만 온다. 허용·거부 판정은 없다(§6.1).
    containerRead: d.container_read && typeof d.container_read === 'object' ? {
      tagId: str(d.container_read.tag_id),
      status: str(d.container_read.status),
      stamp: num(d.container_read.stamp),
      ageWallS: age(d.container_read.age_wall_s),
    } : null,
    // 재고 한눈에(§6.1 `stock`, 재범 9/29 N3). 옛 서버는 키가 없다 → null.
    stock: mapStock(d.stock),
  };
}

/** `dispenser.stock`. 선반은 종류마다 {present, total}, 모르면 null. */
function mapStock(s) {
  if (!s || typeof s !== 'object') return null;
  const shelf = s.shelf && typeof s.shelf === 'object' ? {} : null;
  if (shelf) {
    for (const [kind, v] of Object.entries(s.shelf)) {
      if (v && typeof v === 'object') shelf[kind] = { present: num(v.present, 0), total: num(v.total, 0) };
    }
  }
  const pouches = {};
  for (const [item, n] of Object.entries(s.pouches_by_item && typeof s.pouches_by_item === 'object' ? s.pouches_by_item : {})) {
    pouches[item] = num(n, 0);
  }
  const refills = {};
  for (const [kind, n] of Object.entries(s.refills && typeof s.refills === 'object' ? s.refills : {})) refills[kind] = num(n, 0);
  return { shelf, canistersLoaded: num(s.canisters_loaded, 0), pouchesByItem: pouches, refills };
}

/** parsed 가 거짓이면 stamp 만 있고 나머지는 null 이다.
 *  parsed 는 **JSON 파싱이 됐는가**일 뿐 장면 버전이 아니다(api.md §6.1). */
function mapLastRefill(r) {
  if (!r || typeof r !== 'object') return null;
  const base = mapRefill(r) || {};
  return { ...base, stamp: num(r.stamp), parsed: bool(r.parsed) };
}

function mapBelt(b) {
  if (!b || typeof b !== 'object') return null;
  return {
    occupied: bool(b.occupied),
    atEnd: bool(b.at_end),
    orderId: str(b.order_id),
    stamp: num(b.stamp),
    wall: str(b.wall),
    stale: bool(b.stale),
  };
}

function mapCabinet(c) {
  if (!c || typeof c !== 'object') return null;
  return {
    orderId: str(c.order_id),
    cabinetId: str(c.cabinet_id),
    present: bool(c.present),
    wall: str(c.wall),
  };
}

/** 스캔 점. 숫자가 아닌 점은 버린다. 없으면 null. */
function mapScan(sc) {
  if (!sc || typeof sc !== 'object') return null;
  return {
    robotId: str(sc.robot_id),
    frame: str(sc.frame),
    stamp: num(sc.stamp),
    ageWallS: age(sc.age_wall_s),
    stale: bool(sc.stale) || !Number.isFinite(age(sc.age_wall_s)),
    rangeMax: num(sc.range_max),
    points: arr(sc.points).filter((p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1])),
  };
}

/** 일곱 단계. index 는 0–6, 트립 밖(idle·reset)은 null. */
function mapStage(g) {
  if (!g || typeof g !== 'object' || typeof g.key !== 'string') return null;
  return {
    key: g.key,
    label: str(g.label),
    index: typeof g.index === 'number' ? g.index : null,
    phase: typeof g.phase === 'string' ? g.phase : null,
    refillItemIds: arr(g.refill_item_ids).map(String),
  };
}

/** QR 판독 한 줄(§1.12). 요약 `info` 는 종류마다 키가 달라 그대로 두되 문자열·배열만 남긴다. */
function mapQrRead(r) {
  if (!r || typeof r !== 'object' || typeof r.tag_id !== 'string' || !r.tag_id) return null;
  const info = {};
  for (const [k, v] of Object.entries(r.info && typeof r.info === 'object' ? r.info : {})) {
    info[k] = Array.isArray(v) ? v.map(String) : (typeof v === 'string' && v ? v : null);
  }
  return {
    robot: str(r.robot), kind: str(r.kind), tagId: r.tag_id, count: num(r.count, 0),
    ageWallS: age(r.age_wall_s), stamp: num(r.stamp), info,
  };
}

function mapSpeedLimit(v) {
  if (!v || typeof v !== 'object') return null;
  return {
    pct: typeof v.speed_limit_pct === 'number' ? v.speed_limit_pct : null,   // m/s 로 온 값이면 null
    stopReason: typeof v.stop_reason === 'string' && v.stop_reason ? v.stop_reason : null,
    ageWallS: age(v.age_wall_s),
    stale: bool(v.stale) || !Number.isFinite(age(v.age_wall_s)),
  };
}

/** 더미 한 대. 평면도가 AMR 과 같은 모양으로 다루도록 robotId 로 맞춘다. */
function mapDummy(r) {
  if (!r || typeof r !== 'object') return null;
  const x = num(r.x); const y = num(r.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return {
    robotId: str(r.id), kind: 'dummy', x, y, yaw: num(r.yaw),
    ageWallS: age(r.age_wall_s),
    stale: bool(r.stale) || !Number.isFinite(age(r.age_wall_s)),
    goalZone: null, docked: null, source: str(r.source),
  };
}

/** AMR 한 대의 위치. 좌표가 숫자가 아니면 버린다 — 엉뚱한 곳에 그리느니 안 그린다. */
function mapRobot(r) {
  if (!r || typeof r !== 'object') return null;
  const x = num(r.x); const y = num(r.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return {
    robotId: str(r.robot_id),
    // "amr" = 주 AMR(TF, 주문을 싣는다) · "spare_amr" = 여벌 AMR(fleet_poses, 주문 없음). 옛 서버는 키가 없다 → amr.
    kind: str(r.kind) || 'amr',
    x, y,
    yaw: num(r.yaw),                 // 없으면 NaN — 방향 화살표를 안 그린다
    frame: str(r.frame, 'map'),
    ageWallS: age(r.age_wall_s),
    stale: bool(r.stale) || !Number.isFinite(age(r.age_wall_s)),
    // Nav 목표 구역. 서버가 모르면 null — 화면은 단계로 추측하지 않는다.
    goalZone: typeof r.goal_zone === 'string' && r.goal_zone ? r.goal_zone : null,
    // 도크에 서 있는가(백엔드 제안 9/24). true·false·null(모름). 옛 서버는 키가 없다 → null.
    docked: typeof r.docked === 'boolean' ? r.docked : null,
    source: str(r.source),
  };
}

/** signals 는 객체(고정 5키) -> 표시 순서가 정해진 배열로. */
function mapSignals(s) {
  const src = s && typeof s === 'object' ? s : {};
  return SIGNAL_KEYS.map((key) => {
    const v = src[key];
    if (!v || typeof v !== 'object') {
      return { key, value: null, ageWallS: Infinity, stale: true, present: false };
    }
    return {
      key,
      value: typeof v.value === 'boolean' ? v.value : null,
      ageWallS: age(v.age_wall_s),
      // 나이가 음수면 서버의 stale 판정도 같은 뺄셈에서 나온 것이라 못 믿는다.
      stale: bool(v.stale) || !Number.isFinite(age(v.age_wall_s)),
      present: true,
    };
  });
}

/** REFILL_DONE 의 v2 detail(compact JSON)을 서버가 파싱해 준 것(api.md §2.2).
 *  v1 이거나 파싱이 깨지면 null 이고, 그때는 detail 원문을 그대로 찍는다. */
function mapRefill(r) {
  if (!r || typeof r !== 'object') return null;
  return {
    item: str(r.item),
    slot: str(r.slot),              // 서버가 slot_name 과 같게 대문자로 정규화해 준다
    kind: nullable(typeof r.kind === 'string' ? r.kind : null),     // cylinder | module | null
    cell: str(r.cell),
    target: nullable(typeof r.target === 'string' ? r.target : null), // round | module | null
    seed: typeof r.seed === 'number' ? r.seed : null,
    draw: typeof r.draw === 'number' ? r.draw : null,
    clearance: typeof r.clearance === 'number' ? r.clearance : null,
  };
}

export function mapEvent(e) {
  return {
    seq: typeof e.seq === 'number' ? e.seq : null,
    name: str(e.name),
    requestId: str(e.request_id),
    orderId: str(e.order_id),
    robotId: str(e.robot_id),
    epoch: typeof e.epoch === 'number' ? e.epoch : null,
    detail: str(e.detail), // 표시 전용. 판정에 쓰지 않는다(§2).
    // REFILL_DONE 에만 붙는다. 다른 이벤트에는 키 자체가 없다.
    refill: mapRefill(e.refill),
    stamp: num(e.stamp),
    wall: str(e.wall),
  };
}

export function mapAlarm(a) {
  const level = str(a.level, 'info').toLowerCase();
  return {
    id: str(a.id),
    level: ['info', 'warn', 'error'].includes(level) ? level : 'info',
    kind: str(a.kind),
    message: str(a.message),
    requestId: nullable(typeof a.request_id === 'string' ? a.request_id : null),
    orderId: nullable(typeof a.order_id === 'string' ? a.order_id : null),
    stamp: num(a.stamp),
    epoch: typeof a.epoch === 'number' ? a.epoch : null,
  };
}

export function mapLog(l) {
  const level = str(l.level, 'info').toLowerCase();
  return {
    level,
    levelValue: num(l.level_value, 0),
    node: str(l.node),
    message: str(l.message),
    stamp: num(l.stamp),
    wall: str(l.wall),
  };
}

/** §1 snapshot -> 화면 모델. */
export function normalizeSnapshot(raw) {
  const d = raw && typeof raw === 'object' ? raw : {};
  const clock = d.clock && typeof d.clock === 'object' ? d.clock : {};
  return {
    serverRunId: str(d.server_run_id),
    serverTime: str(d.server_time),
    serverMode: str(d.mode),          // "mock" | "ros"
    // 개발용 고장 주입이 켜져 있으면 그 이름들이 들어온다. 비어 있어야 정상이다.
    // 화면의 빨간 알람이 진짜인지 흉내인지 사람이 구분할 수 있어야 한다.
    mockFaults: arr(d.mock_faults).map(String),
    commandsEnabled: bool(d.commands_enabled),
    seq: typeof d.seq === 'number' ? d.seq : 0,
    epoch: typeof d.epoch === 'number' ? d.epoch : null,
    resetInProgress: bool(d.reset_in_progress),
    // 요청을 받을 수 있는지. RESET_DONE 만으로는 부족하다 — orchestrator 가 settle(약 3.5초)까지 더 거부한다.
    // 서버가 필드를 안 주는 옛 버전이면 막지 않는다(undefined -> true).
    acceptingRequests: d.accepting_requests === undefined ? true : bool(d.accepting_requests),
    // 풀리는 시각(wall, ISO). null 이면 기다릴 게 없거나 언제 풀릴지 모른다.
    acceptAfterWall: typeof d.accept_after_wall === 'string' ? d.accept_after_wall : null,
    // 요청을 다시 받기까지 남은 초. **서버가 센다.** 브라우저 시계로 빼지 않는다(format.js).
    acceptInS: typeof d.accept_in_s === 'number' && Number.isFinite(d.accept_in_s) ? d.accept_in_s : null,
    clock: {
      simS: num(clock.sim_s),
      alive: bool(clock.alive),
      ageWallS: age(clock.age_wall_s),
    },
    trip: mapTrip(d.trip),
    dispenser: mapDispenser(d.dispenser),
    belt: mapBelt(d.belt),
    cabinet: mapCabinet(d.cabinet),
    signals: mapSignals(d.signals),
    // 손 카메라 QR 판독과 그 내용 요약(§1.12). 최근 것부터. 옛 서버는 키가 없다 → 빈 배열.
    qrReads: arr(d.qr_reads).map(mapQrRead).filter(Boolean),
    // Isaac 타임라인 Play/Stop(§1.11). null = 받은 적 없음. stale(3 s) = Isaac 없음.
    simRunning: d.sim_running && typeof d.sim_running === 'object' ? {
      value: typeof d.sim_running.value === 'boolean' ? d.sim_running.value : null,
      ageWallS: age(d.sim_running.age_wall_s),
      stale: bool(d.sim_running.stale) || !Number.isFinite(age(d.sim_running.age_wall_s)),
    } : null,
    // 한 대인가 두 PC 인가(§1.10). 옛 서버는 키가 없다 → null.
    deployment: d.deployment && typeof d.deployment === 'object' ? {
      multiPc: bool(d.deployment.multi_pc),
      roles: Array.isArray(d.deployment.roles) ? d.deployment.roles.map(String) : null,
      peer: typeof d.deployment.peer === 'string' && d.deployment.peer ? d.deployment.peer : null,
      domainId: typeof d.deployment.domain_id === 'number' ? d.deployment.domain_id : null,
    } : null,
    // 감속기(§1.9). signals 안에 있지만 모양이 달라(value 없음) 따로 읽는다. 받은 적 없으면 키가 없다 → null.
    speedLimit: mapSpeedLimit(d.signals && d.signals.speed_limit),
    // AMR 위치(평면도). 서버가 모르면 빈 배열. 옛 서버는 키가 없다.
    robots: arr(d.robots).map(mapRobot).filter(Boolean),
    // 더미(가짜 AMR, 스테이지 --traffic-dummies). /isaac/fleet/poses 에서 온다(§1.6). 없으면 빈 배열.
    dummies: arr(d.dummies).map(mapDummy).filter(Boolean),
    // 촬영 화면의 일곱 단계(§1.7). 옛 서버는 키가 없다 — null 이면 화면이 trip.phase 로 떨어진다.
    stage: mapStage(d.stage),
    // 라이다 스캔(§1.8, --live-sensors 일 때만). frame 이 map 이 아니면 평면도가 그리지 않는다.
    scan: mapScan(d.scan),
    recentEvents: arr(d.recent_events).map(mapEvent),
    alarms: arr(d.alarms).map(mapAlarm),
    receivedAt: performance.now(),
  };
}

// ---------------------------------------------------------------- REST

async function getJson(path) {
  const res = await fetch(apiUrl(path), { cache: 'no-store' });
  if (!res.ok) {
    let body = null;
    try { body = await res.json(); } catch { /* 본문 없음 */ }
    const code = body && body.error ? body.error.code : `HTTP ${res.status}`;
    const err = new Error(code);
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return res.json();
}

export async function fetchSnapshot() {
  return normalizeSnapshot(await getJson('/api/snapshot'));
}

/** §2. epoch 를 넘기면 그 세대만. since 는 배타(seq > since). */
export async function fetchEvents({ epoch = null, since = 0, limit = 500 } = {}) {
  const q = new URLSearchParams();
  if (epoch !== null) q.set('epoch', String(epoch));
  q.set('since', String(since));
  q.set('limit', String(limit));
  const d = await getJson(`/api/events?${q}`);
  return {
    epoch: typeof d.epoch === 'number' ? d.epoch : null,
    nextSince: num(d.next_since, since),
    hasMore: bool(d.has_more),
    events: arr(d.events).map(mapEvent),
  };
}

/** §5. /rosout 의 WARN 이상. */
export async function fetchLogs({ level = 'warn', limit = 200 } = {}) {
  const q = new URLSearchParams({ level, limit: String(limit) });
  const d = await getJson(`/api/logs?${q}`);
  return arr(d.logs).map(mapLog);
}

export async function fetchAlarms() {
  const d = await getJson('/api/alarms');
  return arr(d.alarms).map(mapAlarm);
}

// ---------------------------------------------------------------- WS

/**
 * WS /ws 구독. 서버는 붙자마자 hello(전체 snapshot) 를 한 번 보낸다(§3).
 * @param {{onHello, onSnapshot, onEvents, onAlarms, onStatus}} h
 */
export function connect(h) {
  if (isFixtureMode) return connectFixture(h);

  const url = wsUrl();
  let ws = null;
  let attempt = 0;
  let timer = null;
  let closedByUs = false;

  function open() {
    h.onStatus({ state: 'connecting', detail: url, attempt });
    try {
      ws = new WebSocket(url);
    } catch (err) {
      return scheduleReconnect(String(err && err.message ? err.message : err));
    }

    ws.onopen = () => { attempt = 0; h.onStatus({ state: 'open', detail: url, attempt }); };

    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      dispatch(msg, h);
    };

    ws.onerror = () => { /* onclose 가 이어서 온다 */ };
    ws.onclose = (ev) => {
      if (closedByUs) return;
      scheduleReconnect(ev.reason || `code ${ev.code}`);
    };
  }

  function scheduleReconnect(detail) {
    attempt += 1;
    const wait = Math.min(RECONNECT_MAX_MS, RECONNECT_MIN_MS * 2 ** (attempt - 1));
    h.onStatus({ state: 'closed', detail: `${detail} · ${(wait / 1000).toFixed(1)}s 후 재연결 (${attempt}회)`, attempt });
    clearTimeout(timer);
    timer = setTimeout(open, wait);
  }

  open();
  return { close() { closedByUs = true; clearTimeout(timer); if (ws) ws.close(); } };
}

/** §3 공통 봉투 { type, seq, server_time, data }. */
function dispatch(msg, h) {
  if (!msg || typeof msg !== 'object') return;
  const data = msg.data;
  switch (msg.type) {
    case 'hello':
      h.onHello(normalizeSnapshot(data));
      break;
    case 'snapshot':
      h.onSnapshot(normalizeSnapshot(data));
      break;
    case 'events':
      h.onEvents(arr(data).map(mapEvent));
      break;
    case 'alarms':
      h.onAlarms(arr(data).map(mapAlarm));
      break;
    default:
      break; // 모르는 type 은 무시. 새 type 이 생기면 여기에 갈래를 친다.
  }
}

/** fixture 모드: 정적 JSON 한 장을 hello 로 재생. 시간은 흐르지 않는다.
 *  `?fixture=1&file=dev-fixture-unknown.json` 으로 다른 fixture 를 볼 수 있다. */
function connectFixture(h) {
  // 페이지에 fixture 가 박혀 있으면(스크린샷용 미리보기 파일) 그걸 동기로 쓴다.
  const inline = document.getElementById('fixture-data');
  if (inline) {
    let raw = null;
    try { raw = JSON.parse(inline.textContent); } catch { raw = null; }
    if (raw) {
      h.onStatus({ state: 'open', detail: 'inline fixture (가짜 데이터, 서버 없음)', attempt: 0 });
      if (h.onLogs && Array.isArray(raw.logs)) h.onLogs(raw.logs.map(mapLog));
      const push = () => h.onHello(normalizeSnapshot(raw));
      push();
      const t = setInterval(push, 500);
      return { close() { clearInterval(t); } };
    }
  }

  const file = params.get('file') || 'dev-fixture.json';
  // 경로 주입을 막는다 — 같은 디렉터리의 .json 파일만.
  const safe = /^[\w.-]+\.json$/.test(file) ? file : 'dev-fixture.json';

  h.onStatus({ state: 'connecting', detail: safe, attempt: 0 });
  let timer = null;
  fetch(safe, { cache: 'no-store' })
    .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then((raw) => {
      h.onStatus({ state: 'open', detail: `${safe} (가짜 데이터, 서버 없음)`, attempt: 0 });
      if (h.onLogs && Array.isArray(raw.logs)) h.onLogs(raw.logs.map(mapLog));
      const push = () => h.onHello(normalizeSnapshot(raw)); // 신선도가 늙지 않게 계속 다시 민다
      push();
      timer = setInterval(push, 500);
    })
    .catch((err) => h.onStatus({ state: 'closed', detail: `fixture 로드 실패: ${err.message}`, attempt: 1 }));
  return { close() { clearInterval(timer); } };
}

// ---------------------------------------------------------------- 명령 (§7, 기본 403)

async function post(path, body) {
  const res = await fetch(apiUrl(path), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  let payload = null;
  try { payload = await res.json(); } catch { /* 본문 없음 */ }
  return {
    ok: res.ok,
    status: res.status,
    forbidden: res.status === 403,
    code: payload && payload.error ? payload.error.code : null,
    message: payload && payload.error ? payload.error.message : null,
    // 무엇 때문에 막혔나(api.md §0.4). **대상이 없는 거부에는 키가 아예 없다** —
    // 빈 객체를 만들면 호출부가 있는 줄 알고 들여다본다. 없으면 null 로 둔다.
    detail: payload && payload.error && payload.error.detail
      && typeof payload.error.detail === 'object' ? payload.error.detail : null,
    body: payload,
  };
}

export const postReset = () => post('/api/reset', {});

/** §7.3 — 주문 풀. 없으면 404 이므로 호출부가 조용히 넘어간다. */
export async function fetchOrderPool() {
  const d = await getJson('/api/order_pool');
  return {
    source: str(d.source, 'none'),
    // 풀 파일이 잘못됐을 때 이유가 들어온다. 비어 있지 않으면 화면에 보여준다.
    problems: arr(d.problems).map(String),
    orders: arr(d.orders).map((o) => ({
      orderId: str(o.order_id),
      patientId: nullable(typeof o.patient_id === 'string' ? o.patient_id : null),
      itemId: nullable(typeof o.item_id === 'string' ? o.item_id : null),
      // 풀이 아는 침상. 1인·긴급은 서버가 이 값으로 destination_id 를 덮어쓴다.
      bed: nullable(typeof o.bed === 'string' ? o.bed : null),
      modeValue: typeof o.mode_value === 'number' ? o.mode_value : null,
      used: bool(o.used),
    })),
  };
}

/** §7.4 — 목적지 후보 목록. **검증용이 아니다.**
 *  orchestrator 는 zones.yaml 을 안 읽고 정규식으로만 거르므로 목록 밖 값도 수락된다.
 *  목록에 없는 목적지는 실물에서 GoToZone 이 거부해 HOLD_RETURN 으로 끝날 수 있어 경고만 띄운다. */
export async function fetchDestinations() {
  const d = await getJson('/api/destinations');
  return {
    source: str(d.source, 'none'),
    destinations: arr(d.destinations).map((x) => ({
      destinationId: str(x.destination_id),
      kind: str(x.kind),
      // 병동·병실 묶음과 이름표. 서버가 안 주면 null — 화면은 kind 로 묶고 ID 를 그대로 쓴다.
      // ID 모양(bed_a1 → A)을 화면이 해석하지 않는다. 규칙은 서버 한 곳에만 둔다.
      group: typeof x.group === 'string' && x.group ? x.group : null,
      groupLabel: typeof x.group_label === 'string' && x.group_label ? x.group_label : null,
      label: typeof x.label === 'string' && x.label ? x.label : null,
      ward: typeof x.ward === 'string' && x.ward ? x.ward : null,
      wardLabel: typeof x.ward_label === 'string' && x.ward_label ? x.ward_label : null,
    })),
  };
}
/** 응답의 destination_id 는 보낸 값과 다를 수 있다 —
 *  1인·긴급은 서버가 풀의 환자→침상 매핑으로 덮어쓴다(destination_source 가 말해 준다). */
export async function postRequest(req) {
  const r = await post('/api/requests', req);
  const b = r.body || {};
  return {
    ...r,
    appliedDestinationId: typeof b.destination_id === 'string' ? b.destination_id : null,
    destinationSource: typeof b.destination_source === 'string' ? b.destination_source : null,
    modeSource: typeof b.mode_source === 'string' ? b.mode_source : null,
  };
}

// ---------------------------------------------------------------- 평면도

/** 지도 메타(maps/*.yaml 을 서버가 JSON 으로). 지도가 없으면 404 → 호출한 쪽이 지도를 감춘다. */
export async function fetchMap() {
  const d = await getJson('/api/map');
  const origin = arr(d.origin);
  return {
    source: str(d.source, 'none'),
    frame: str(d.frame, 'map'),
    imageUrl: str(d.image_url, '/api/map/image'),
    width: num(d.width, 0),
    height: num(d.height, 0),
    resolution: num(d.resolution, 0),
    originX: num(origin[0], 0),
    originY: num(origin[1], 0),
    originYaw: num(origin[2], 0),
    negate: num(d.negate, 0) === 1,
    occupiedThresh: num(d.occupied_thresh, 0.65),
    freeThresh: num(d.free_thresh, 0.196),
  };
}

/** 지도 그림(PGM 원본 바이트). 캔버스로 그리는 것은 floormap.js 가 한다. */
export async function fetchMapImage(url) {
  const res = await fetch(apiUrl(url), { cache: 'force-cache' });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.arrayBuffer();
}

/** 전 구역 좌표 — 배송 목적지만이 아니라 dock·load(창구)까지. */
export async function fetchZones() {
  const d = await getJson('/api/zones');
  return {
    frame: str(d.frame, 'map'),
    zones: arr(d.zones).map((z) => ({
      zoneId: str(z.zone_id),
      kind: str(z.kind),
      x: num(z.x), y: num(z.y), yaw: num(z.yaw),
      group: typeof z.group === 'string' && z.group ? z.group : null,
      label: typeof z.label === 'string' && z.label ? z.label : null,
    })).filter((z) => z.zoneId && Number.isFinite(z.x) && Number.isFinite(z.y)),
  };
}

/** 촬영 화면 주문 큐(§7.7): 풀 순서로 대기·진행·완료. WS 로는 안 오니 1 Hz 정도로 부른다. */
export async function fetchQueue() {
  const d = await getJson('/api/queue');
  const row = (o) => ({
    orderId: str(o.order_id),
    patientId: typeof o.patient_id === 'string' ? o.patient_id : null,
    itemId: typeof o.item_id === 'string' ? o.item_id : null,
    bed: typeof o.bed === 'string' ? o.bed : null,
    group: typeof o.group === 'string' && o.group ? o.group : null,
    label: typeof o.label === 'string' && o.label ? o.label : null,
    mode: str(o.mode),
    requestId: typeof o.request_id === 'string' ? o.request_id : null,
    outcome: typeof o.outcome === 'string' ? o.outcome : null,
  });
  return {
    epoch: typeof d.epoch === 'number' ? d.epoch : null,
    waiting: arr(d.waiting).map(row),
    inProgress: arr(d.in_progress).map(row),
    done: arr(d.done).map(row),
  };
}

// ---------------------------------------------------------------- 카메라(§1.8)

/** 카메라 목록·오버레이. 서버가 --live-sensors 없이 떴으면 {enabled:false}. 1 Hz 정도로 부른다. */
export async function fetchCameras() {
  const d = await getJson('/api/cameras');
  const lim = d.limits && typeof d.limits === 'object' ? d.limits : {};
  return {
    enabled: bool(d.enabled),
    maxViewers: num(lim.max_viewers, 3),
    cameras: arr(d.cameras).map((c) => {
      const o = c.overlay && typeof c.overlay === 'object' ? c.overlay : {};
      const tag = o.tag && typeof o.tag === 'object' ? o.tag : null;
      return {
        name: str(c.name),
        label: str(c.label, str(c.name)),
        width: num(c.width), height: num(c.height),
        stamp: typeof c.stamp === 'number' ? c.stamp : null,   // 아직 프레임을 못 받았으면 null
        ageWallS: age(c.age_wall_s),
        stale: bool(c.stale),
        viewers: num(c.viewers, 0),
        tag: tag ? { tagId: str(tag.tag_id), status: str(tag.status), stamp: num(tag.stamp) } : null,
        pouches: arr(o.pouches).map((p) => ({ orderId: str(p.order_id), confidence: num(p.confidence), slotIndex: num(p.slot_index) })),
      };
    }).filter((c) => c.name),
  };
}

/** MJPEG 스트림 주소. <img src> 로 쓴다. 닫을 때 src 를 비워 연결을 끊는다(시청자에서 빠진다). */
export const cameraStreamUrl = (name) => apiUrl(`/api/cameras/${encodeURIComponent(name)}/stream`);
