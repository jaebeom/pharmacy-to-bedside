// live.js — 연결 배선. snapshot -> WS -> store 를 잇고, 끊겼다 붙으면 빈 구간을 메운다.
// 개발자·간호사·설정 화면이 같이 쓴다. 판정 로직은 여기 두지 않는다(store.js·format.js 몫).
import { connect, fetchSnapshot, isFixtureMode, PUSH_GRACE_S } from './api.js';

/**
 * 연결을 시작한다. `render` 는 데이터가 올 때와 250 ms 마다 불린다 — 데이터가 안 와도
 * 신선도는 늙어야 하기 때문이다.
 *
 * @param store  createStore() 결과
 * @param opts.render  다시 그리기
 * @param opts.logs    true 면 경고 이상 로그를 받고 5초마다 다시 받는다(개발자 화면만)
 * @returns {{conn, sinceMsg(): number, fresh(): boolean}}
 */
export function startLive(store, { render, logs = false }) {
  const live = {
    conn: { state: 'connecting', detail: '', attempt: 0, source: isFixtureMode ? 'fixture' : '' },
    lastMessageAt: 0,   // 어떤 WS 메시지든 마지막으로 받은 시각(performance.now)
    /** 마지막 WS 메시지 뒤 흐른 초. 한 번도 못 받았으면 Infinity. */
    sinceMsg() { return live.lastMessageAt ? (performance.now() - live.lastMessageAt) / 1000 : Infinity; },
    /** 서버는 변화가 없어도 1초에 한 번 push 한다. 그래서 소켓의 침묵은 곧 죽음이다. */
    fresh() { return live.conn.state === 'open' && live.sinceMsg() <= PUSH_GRACE_S; },
  };
  const heard = () => { live.lastMessageAt = performance.now(); };

  /** hello 또는 재연결 뒤: 빈 구간을 seq 로 메우고(로그를 쓰면) 로그를 다시 받는다(§3.1). */
  async function afterConnected() {
    await store.backfillEvents();
    if (logs) await store.refreshLogs('warn');
    render();
  }

  // 첫 화면은 GET /api/snapshot 하나면 된다(§1). WS 가 늦거나 죽어 있어도 상태는 보여 주되,
  // 연결이 끊긴 것은 배너·흐림으로 분명히 드러낸다(요건 3).
  if (!isFixtureMode) {
    fetchSnapshot()
      .then((vm) => { store.applySnapshot(vm); render(); })
      .catch(() => { /* 서버가 아직 없으면 WS 쪽에서 재시도한다 */ });
  }

  connect({
    onStatus: (st) => {
      const wasDown = live.conn.state !== 'open';
      live.conn = { ...live.conn, ...st };
      render();
      if (st.state === 'open' && wasDown && !isFixtureMode) {
        // 끊겼다 붙었으면 snapshot 을 한 번 더 받아 현재 상태를 맞춘다.
        fetchSnapshot().then((vm) => { store.applySnapshot(vm); return afterConnected(); }).catch(() => {});
      }
    },

    onHello: (vm) => {
      heard();
      store.applySnapshot(vm);
      render();
      if (!isFixtureMode) afterConnected();
    },

    onSnapshot: (vm) => {
      heard();
      const { runChanged, epochChanged } = store.applySnapshot(vm);
      render();
      // 세대가 바뀌었으면 새 epoch 의 이벤트를 처음부터 다시 받는다(§3.2).
      if (runChanged || epochChanged) afterConnected();
    },

    onEvents: (list) => { heard(); if (store.applyEvents(list)) render(); },
    onAlarms: (list) => { heard(); if (store.applyAlarms(list)) render(); },

    // fixture 모드에서만 쓰인다. 실제 서버에서는 GET /api/logs 로 받는다.
    onLogs: (list) => { store.state.logs = list; render(); },
  });

  setInterval(render, 250);

  // 로그는 push 가 없으므로 주기적으로 다시 받는다.
  if (logs && !isFixtureMode) {
    setInterval(() => { store.refreshLogs('warn').then((ok) => { if (ok) render(); }); }, 5000);
  }

  return live;
}
