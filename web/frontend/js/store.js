// store.js — 화면이 들고 있는 상태. seq 커서 / epoch 리셋 / server_run_id 교체를 여기서 처리한다.
//
// 규칙(api.md §0.2, §0.3, §3.1, §3.2)
//  - epoch 이 바뀌면 이벤트·알람을 통째로 버리고 새 snapshot 으로 다시 쌓는다.
//  - server_run_id 가 달라지면 커서를 버리고 처음부터.
//  - 이벤트는 서버가 준 순서(seq 오름차순) 그대로 둔다. 클라이언트에서 재정렬하지 않는다.

import { fetchEvents, fetchLogs } from './api.js';

/** DOM 이 무한정 커지지 않게. 넘치면 오래된 쪽을 버린다(현재 epoch 안에서). */
const MAX_EVENTS = 600;

export function createStore() {
  const s = {
    snapshot: null,      // normalizeSnapshot() 결과
    events: [],          // 현재 epoch 만, seq 오름차순
    alarms: [],          // 현재 epoch 만
    logs: [],
    cursor: 0,           // 본 seq 중 가장 큰 값. 재연결 복구의 since 로만 쓴다
    seen: new Set(),     // 이미 넣은 seq. **중복 판정은 이걸로 한다**
    serverRunId: null,
    epoch: null,
    backfilling: false,
    needsFullBackfill: true,  // 이 세대를 아직 통째로 받아오지 않았다
    truncated: false,    // 오래된 이벤트를 버렸는가
  };

  function hardReset(runId, epoch) {
    s.events = [];
    s.alarms = [];
    s.cursor = 0;
    s.seen = new Set();
    s.needsFullBackfill = true;
    s.truncated = false;
    s.serverRunId = runId;
    s.epoch = epoch;
  }

  /** hello / snapshot 공통 처리. 바뀐 게 있으면 true. */
  function applySnapshot(vm) {
    const runChanged = vm.serverRunId && s.serverRunId && vm.serverRunId !== s.serverRunId;
    const epochChanged = s.epoch !== null && vm.epoch !== null && vm.epoch !== s.epoch;

    if (s.serverRunId === null || runChanged || epochChanged) {
      hardReset(vm.serverRunId || s.serverRunId, vm.epoch);
    }

    s.snapshot = vm;
    if (vm.epoch !== null) s.epoch = vm.epoch;

    // snapshot 의 alarms 는 "현재 살아있는 것" 전체이므로 그대로 진실로 삼는다.
    s.alarms = vm.alarms;

    // snapshot 의 recent_events 를 매번 합친다. 첫 화면을 빈 채로 두지 않고,
    // WS events push 를 놓쳐도 타임라인이 멈추지 않게 한다. 중복은 applyEvents 가 거른다.
    if (vm.recentEvents.length) applyEvents(vm.recentEvents);

    return { runChanged, epochChanged };
  }

  /** 이벤트 합치기.
   *
   *  **중복 판정을 `seq > cursor` 로 하면 안 된다.** seq 는 서버가 *도착 순*으로 매기는데,
   *  전달 순서는 `status_view.event_key`(epoch, 리셋 구분, stamp, 도착 순번) 정렬이다.
   *  `/events` 가 transient_local 이라 붙는 순간 작성자별로 뭉쳐 들어오면
   *  seq 가 25, 26, 1, 2, 9, 10 처럼 뒤죽박죽 오면서 stamp 만 단조 증가한다.
   *  그때 `> cursor` 로 거르면 뒤에 온 낮은 seq 를 통째로 버린다(실물에서 확인).
   *  그래서 본 seq 집합으로 거른다. cursor 는 재연결 복구의 since 로만 쓴다.
   */
  function applyEvents(list) {
    const fresh = list.filter((e) => {
      if (e.epoch !== null && s.epoch !== null && e.epoch !== s.epoch) return false; // 다른 세대는 섞지 않는다
      if (e.seq === null) return true;
      return !s.seen.has(e.seq);
    });
    if (!fresh.length) return false;

    for (const e of fresh) if (e.seq !== null) s.seen.add(e.seq);
    s.events = s.events.concat(fresh);
    s.cursor = maxSeq(fresh, s.cursor);
    trim();
    return true;
  }

  /** WS alarms push 는 델타가 아니라 **현재 살아있는 전체 목록**이다(api.md §3).
   *  통째로 갈아 끼운다 — 사라진 알람이 남지 않는다. */
  function applyAlarms(list) {
    s.alarms = list.filter((a) => a.epoch === null || s.epoch === null || a.epoch === s.epoch);
    return true;
  }

  function trim() {
    if (s.events.length <= MAX_EVENTS) return;
    s.events = s.events.slice(s.events.length - MAX_EVENTS);
    s.truncated = true;
  }

  /** 이 세대의 이벤트를 받아온다.
   *
   *  처음 붙었거나 epoch 이 바뀌었으면 **since=0 부터** 통째로 받는다.
   *  recent_events 는 마지막 12개뿐이라 그것만 믿으면 앞쪽이 비고,
   *  seq 가 순서대로 오지 않으므로 max(seq) 를 since 로 쓰면 앞쪽을 영영 못 받는다.
   *  그 뒤 재연결 복구는 cursor 부터 메운다(§3.1).
   */
  async function backfillEvents() {
    if (s.backfilling || s.epoch === null) return false;
    s.backfilling = true;
    const full = s.needsFullBackfill;
    let since = full ? 0 : s.cursor;
    let changed = false;
    // 전체 백필은 서버가 정렬해 준 순서를 그대로 쓴다. 이어붙이면 늦게 받은 앞쪽 이벤트가
    // 뒤에 붙어 stamp 가 거꾸로 간다(실물에서 RESET_BEGIN 이 DOCKED 뒤에 붙었다).
    const page = [];
    try {
      for (let i = 0; i < 10; i += 1) {
        const r = await fetchEvents({ epoch: s.epoch, since, limit: 500 });
        if (full) page.push(...r.events);
        else if (r.events.length && applyEvents(r.events)) changed = true;
        const next = r.nextSince || 0;
        if (!r.hasMore || next <= since) break;
        since = next;
      }

      if (full && page.length) {
        // 서버 순서로 통째 교체. 그 사이 WS 로 들어온 더 새 이벤트는 뒤에 다시 붙인다.
        const extra = s.events.filter((e) => e.seq !== null && !page.some((x) => x.seq === e.seq));
        s.events = [];
        s.seen = new Set();
        applyEvents(page);
        if (extra.length) applyEvents(extra);
        changed = true;
      }
      s.needsFullBackfill = false;
    } catch {
      // 백필 실패는 치명적이지 않다. 다음 WS push 부터 이어 받는다.
    } finally {
      s.backfilling = false;
    }
    return changed;
  }

  async function refreshLogs(level = 'warn') {
    try {
      s.logs = await fetchLogs({ level, limit: 200 });
      return true;
    } catch {
      return false;
    }
  }

  return { state: s, applySnapshot, applyEvents, applyAlarms, backfillEvents, refreshLogs };
}

function maxSeq(list, start) {
  return list.reduce((m, e) => (e.seq !== null && e.seq > m ? e.seq : m), start);
}
