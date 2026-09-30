// 현재 트립: 모드 배지, request_id, 목적지, 단계, 주문(봉투)별 상태.
// orchestrator 는 동시에 한 트립만 받으므로(api.md §1) 한 장을 크게 그린다.
import { el, replace, emptyNote } from '../dom.js';
import { STALE_CLOCK_S } from '../api.js';
import {
  modeInfo, isUrgent, orderState, isBadOrder, isPharmacySegmentDone, isPharmacyLapDone,
  PHASE_TRACK, RESET_PHASES, trackIndex, phaseText, DEMO_ZONE,
  simClock, simStamp, UNKNOWN, acceptWaitSuffix, chargingRobots, pickAttempts, authResult, speedBadge,
  pouchChecks, reasonText,
} from '../format.js';

/** 값을 못 얻은 칸. 빈칸과 구분되게 점선 회색으로. */
const unknownCell = (title) => el('span', { class: 'unknown', title: title || '외부 관찰로 얻을 수 없는 값', text: UNKNOWN });

/**
 * 단계 스텝퍼.
 * 글자는 status_view.py 의 한글 원문(phase_label)을 그대로 쓴다 — 고쳐 쓰지 않는다.
 * 1차 시연 구간은 조제실이라, 병동 단계는 자리만 두고 흐리게 둔다.
 */
function stepper(trip) {
  if (RESET_PHASES.has(trip.phase)) {
    return el('div', { class: 'stepper stepper-unknown' }, [
      el('span', { class: 'step is-current step-reset', text: phaseText(trip) }),
    ]);
  }

  const cur = trackIndex(trip);

  // track 에 없는 단계가 오면(백엔드가 status_view.py 와 대조하며 바꿀 수 있다) 단독 칩으로.
  if (cur < 0) {
    return el('div', { class: 'stepper stepper-unknown' }, [
      el('span', { class: 'step is-current', text: phaseText(trip) }),
      el('span', { class: 'step-note', text: '알려진 단계 목록에 없음' }),
    ]);
  }

  return el('div', { class: 'stepper' }, PHASE_TRACK.map((p, i) => el('span', {
    class: [
      'step',
      i < cur ? 'is-done' : i === cur ? 'is-current' : 'is-future',
      p.zone === DEMO_ZONE ? 'zone-demo' : 'zone-later',
      p.bad ? 'step-bad' : '',
    ].filter(Boolean).join(' '),
    title: `${p.phase}${p.zone === DEMO_ZONE ? '' : ' · 1차 시연 범위 밖(병동)'}`,
    text: p.label,
  })));
}

function orderRow(o, t, events) {
  const st = orderState(o);
  // 환자 확인 결과(AUTH_OK·AUTH_FAIL). 간호사 화면과 같은 규칙(format.js authResult).
  const auth = authResult(events, o.orderId, t.requestId, t.orders.filter((x) => x.orderId).length);
  // 약 QR 확인(#784): 벨트 끝에서 한 번, 병상에서 환자 확인 뒤 한 번(약 ↔ 환자 매칭).
  const pouch = pouchChecks(events, o.orderId, t.requestId);
  const done = isPharmacySegmentDone(o);
  return el('div', { class: `order${isBadOrder(o) ? ' is-bad' : ''}${done ? ' is-done' : ''}` }, [
    el('span', { class: 'order-id', text: o.orderId || '—' }),
    o.patientId ? el('span', { class: 'order-cell', text: o.patientId }) : unknownCell('patient_id — REQUEST_ACCEPTED.detail 이 비면 얻을 수 없다'),
    o.itemId ? el('span', { class: 'order-cell', text: o.itemId }) : unknownCell('item_id — REQUEST_ACCEPTED.detail 이 비면 얻을 수 없다'),
    el('span', {
      class: `ostate ${st.cls}`,
      title: done ? `${st.name} · ${o.reason} — 조제실만 도는 구성에서는 정상 완주다` : st.name,
      text: st.ko,
    }),
    el('span', { class: 'order-reason', title: o.reason }, [
      pouch.belt ? el('span', { class: 'auth-chip is-ok', title: 'POUCH_DETECTED (벨트 끝)', text: '✓ 약 QR' }) : null,
      auth ? el('span', { class: `auth-chip is-${auth}`, title: auth === 'ok' ? 'AUTH_OK' : 'AUTH_FAIL', text: auth === 'ok' ? '✓ 확인' : '✕ 확인 실패' }) : null,
      pouch.bed ? el('span', { class: 'auth-chip is-ok', title: 'POUCH_DETECTED (병상, 환자 확인 뒤)', text: '✓ 약 매칭' }) : null,
      reasonText(o.reason),
    ]),
    el('span', { class: 'order-stamp', text: simStamp(o.stamp) }),
  ]);
}

/** 트립이 없을 때 무엇을 보여줄지.
 *
 *  실습3 에서 사람이 **대기 상태를 "또 멈췄다" 로 읽었다.** 요청이 안 들어와서 가만히
 *  있었을 뿐인데 회색 "진행 중인 트립 없음" 한 줄로는 그게 정상인지 고장인지 알 수 없었다.
 *  9/21 은 사람이 웹에서 요청을 넣으며 진행하므로, **"기다리는 중"과 "멈춘 것"이
 *  한눈에 갈라져야 한다.**
 *
 *  서버가 이미 주는 필드만 쓴다 — 새 필드를 요구하지 않는다.
 */
function idleState(snap, fresh) {
  // 1. 갱신이 끊겼다. 지금 상태를 모르므로 "대기 중" 이라고 말하면 안 된다.
  if (!fresh) {
    return { cls: 'idle-dead', title: '갱신 멎음', body: '아래 값은 마지막으로 받은 것입니다', live: false };
  }
  // 2. 리셋이 도는 중.
  if (snap.resetInProgress) {
    return { cls: 'idle-busy', title: '리셋 중', body: '끝나면 새 요청을 받습니다', live: true };
  }
  // 3. 리셋은 끝났지만 orchestrator 가 아직 요청을 안 받는다(settle).
  if (snap.acceptingRequests === false) {
    return {
      cls: 'idle-busy',
      title: `리셋 뒤 대기 중${acceptWaitSuffix(snap)}`,
      body: '곧 새 요청을 받습니다',
      live: true,
    };
  }
  // 4. 연결은 살아 있는데 시뮬 시간이 멈췄다. 이건 기다리는 게 아니라 이상이다.
  const clockStopped = !snap.clock.alive || snap.clock.ageWallS > STALE_CLOCK_S;
  if (clockStopped) {
    return { cls: 'idle-bad', title: '시뮬 시간이 멈췄습니다', body: '/clock 을 확인하세요 — 기다리는 상태가 아닙니다', live: false };
  }
  // 5. 정상 대기. 요청만 들어오면 바로 돈다.
  return {
    cls: 'idle-ready',
    title: '대기 중',
    body: '새 요청을 기다립니다',
    hint: snap.commandsEnabled ? '상단 "요청 넣기" 로 넣을 수 있습니다' : null,
    live: true,
  };
}

function idlePanel(snap, fresh, charging) {
  const st = idleState(snap, fresh);
  return el('div', { class: `idle ${st.cls}` }, [
    el('div', { class: 'idle-head' }, [
      el('span', { class: `idle-dot${st.live ? ' is-live' : ''}` }),
      el('span', { class: 'idle-title', text: st.title }),
    ]),
    // 마지막 이벤트가 DOCKED 인 AMR — 도크에서 충전 대기. 배터리 수치는 모델이 없어 적지 않는다.
    charging && charging.size
      ? el('div', { class: 'idle-charge' }, [...charging].map((id) => el('span', { class: 'flag flag-charge', text: `${id} 충전 중 ⚡` })))
      : null,
    el('div', { class: 'idle-body', text: st.body }),
    st.hint ? el('div', { class: 'idle-hint', text: st.hint }) : null,
    // 시뮬이 돌고 있다는 증거를 같이 둔다 — "멈췄나?" 에 대한 답이다.
    st.live && snap.clock.alive
      ? el('div', { class: 'idle-proof', text: `시뮬 시간은 흐르고 있습니다 · /clock 생존` })
      : null,
  ]);
}

export function renderTrip(store, root, metaRoot, fresh) {
  const snap = store.snapshot;
  if (!snap) {
    replace(metaRoot, []);
    return replace(root, emptyNote('아직 받은 데이터가 없습니다'));
  }

  // 리셋이 멈춘 것(RESET_STUCK)은 저절로 안 풀린다. '리셋 중' 과 구분해서 보여준다.
  const stuck = store.alarms.some((a) => a.kind === 'RESET_STUCK');
  // 조제실만 도는 구성에서는 주문이 전부 HOLD_RETURN(pharmacy_only)으로 닫히는 것이 정상 완주다.
  // 하나라도 다른 결말이면 완주가 아니므로 표시하지 않는다.
  const lapDone = isPharmacyLapDone(snap.trip);
  replace(metaRoot, [
    stuck ? el('span', { class: 'flag flag-stuck', text: '리셋 멈춤 — 사람 개입 필요' })
      : snap.resetInProgress ? el('span', { class: 'flag flag-reset', text: '리셋 중' })
      : null,
    !stuck && snap.acceptingRequests === false
      ? el('span', { class: 'flag flag-stale', text: '요청 대기' }) : null,
    lapDone ? el('span', { class: 'flag flag-done', text: '조제실 한 바퀴 완료' }) : null,
    // 감속기(§1.9): 감속·정지일 때만. 제한 없음(100 %)이면 비운다.
    ...(() => { const sb = speedBadge(snap.speedLimit); return sb ? [el('span', { class: `flag flag-speed is-${sb.tone}`, title: 'signals.speed_limit', text: sb.text })] : []; })(),
  ].filter(Boolean));

  const t = snap.trip;
  if (!t) return replace(root, idlePanel(snap, fresh, chargingRobots(store.events, snap.robots)));

  const m = modeInfo(t.mode);
  const urgent = isUrgent(t.mode);
  const attempts = pickAttempts(store.events, t.requestId);

  const head = el('div', { class: 'trip-head' }, [
    el('span', { class: `mode-badge mode-big ${m.cls}`, title: m.label, text: m.short }),
    el('div', { class: 'trip-ids' }, [
      el('div', { class: 'trip-id', text: t.requestId || '—' }),
      el('div', { class: 'trip-sub' }, [
        t.destinationId
          ? el('span', { class: 'trip-dest', text: t.destinationId })
          : unknownCell('destination_id — REQUEST_ACCEPTED.detail 이 비면 얻을 수 없다'),
        t.robotId ? el('span', { class: 'trip-robot', text: t.robotId }) : null,
        // 집기 재시도는 PICK_ATTEMPT 개수로 센다(Event.msg). 한 번이면 적지 않는다.
        attempts >= 2 ? el('span', { class: 'trip-attempts', title: 'PICK_ATTEMPT', text: `집기 시도 ${attempts}회` }) : null,
      ]),
    ]),
    // 현재 단계 — status_view.py 한글 원문 그대로.
    el('div', { class: 'phase-now' }, [
      el('span', { class: 'phase-now-label', text: '현재 단계' }),
      el('span', { class: 'phase-now-value', text: phaseText(t) }),
    ]),
    el('div', { class: 'trip-times' }, [
      el('div', { class: 'kv' }, [el('span', { text: '시작' }), el('b', { text: simClock(t.startedSimS) })]),
      el('div', { class: 'kv' }, [el('span', { text: '최근 이벤트' }), el('b', { text: simClock(t.lastEventSimS) })]),
    ]),
  ]);

  const sourceNote = el('div', { class: 'source-note' }, [
    m.unknown
      ? el('span', { class: 'note-warn', text: '모드·목적지·주문 상세를 외부 관찰로 얻지 못했습니다 (mode_source: null)' })
      : el('span', { text: `모드 출처: ${t.modeSource || UNKNOWN}` }),
    t.phaseSource ? el('span', { class: 'note-dim', text: `단계 출처: ${t.phaseSource}` }) : null,
  ]);

  const ordersBlock = t.orders.length
    ? el('div', { class: 'orders' }, [
        el('div', { class: 'order order-th' }, [
          el('span', { text: 'order_id' }), el('span', { text: 'patient_id' }), el('span', { text: 'item_id' }),
          el('span', { text: '상태' }), el('span', { text: '사유' }), el('span', { text: 'sim' }),
        ]),
        ...t.orders.map((o) => orderRow(o, t, store.events)),
      ])
    : emptyNote('주문 없음');

  replace(root, [
    el('article', { class: `trip${urgent ? ' is-urgent' : ''}${m.unknown ? ' is-mode-unknown' : ''}` }, [
      head, stepper(t), sourceNote,
    ]),
    ordersBlock,
  ]);
}
