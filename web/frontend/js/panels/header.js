// 상단바: 연결 상태, epoch, sim 시간, /clock 생존.
import { simClock, ageText, simBadge, deploymentText } from '../format.js';
import { el, replace } from '../dom.js';
import { STALE_CLOCK_S } from '../api.js';

const $ = (id) => document.getElementById(id);

export function renderHeader(store, conn, fresh, sinceMsg) {
  const live = conn.state === 'open';
  const snap = store.snapshot;

  $('conn-dot').className = 'dot ' + (live ? 'ok' : conn.state === 'connecting' ? 'warn' : 'error');
  $('conn-text').textContent = live ? '연결됨' : conn.state === 'connecting' ? '연결 중…' : '끊김';

  // 끊긴 동안 옛 값을 살아 있는 것처럼 보이면 안 된다(요건 3).
  $('disconnect-banner').hidden = live;
  document.body.classList.toggle('is-disconnected', !live);
  $('disconnect-detail').textContent = conn.detail || '';
  $('disconnect-text').textContent = snap
    ? '연결 끊김 — 아래 값은 마지막으로 받은 것이며 갱신되지 않습니다'
    : '연결 끊김 — 아직 받은 데이터가 없습니다';

  // 고장 흉내가 켜져 있으면 숨기지 않는다. 시연에서 실수로 켠 채 띄우는 사고를 막는다.
  // Play/Stop·다중 PC — 서버가 필드를 주면 단다(§1.10·§1.11). 한 대·받은 적 없음이면 비운다.
  const sb = snap ? simBadge(snap.simRunning) : null;
  const dep = snap ? deploymentText(snap.deployment) : null;
  replace($('ops'), [
    sb ? el('span', { class: `ops-badge is-${sb.tone}`, title: 'sim_running', text: sb.text }) : null,
    dep ? el('span', { class: 'ops-badge is-dep', title: 'deployment', text: dep }) : null,
  ].filter(Boolean));

  const badge = $('fault-badge');
  const faults = snap && snap.mockFaults ? snap.mockFaults : [];
  badge.hidden = !faults.length;
  badge.textContent = faults.length ? `고장 흉내 중 — ${faults.join(', ')}` : '';

  $('source-tag').textContent = [
    snap && snap.serverMode ? snap.serverMode.toUpperCase() : null,
    conn.source || null,
  ].filter(Boolean).join(' · ');

  if (!snap) {
    for (const id of ['stat-epoch', 'stat-simtime', 'stat-seq']) $(id).textContent = '—';
    $('clock-dot').className = 'dot';
    $('clock-text').textContent = '—';
    return;
  }

  $('stat-epoch').textContent = snap.epoch === null ? '—' : String(snap.epoch);
  $('stat-simtime').textContent = simClock(snap.clock.simS);
  $('stat-seq').textContent = String(store.cursor || snap.seq || 0);

  // 서버가 준 나이를 그대로 쓴다. 갱신 자체가 멎었는지는 fresh 가 말해 준다
  // (서버는 변화가 있을 때만 push 하므로, 조용한 구간을 시계 정지로 읽으면 안 된다).
  const age = snap.clock.ageWallS;
  const stopped = !fresh || !snap.clock.alive || age > STALE_CLOCK_S;

  $('clock-dot').className = 'dot ' + (stopped ? 'error' : 'ok');
  $('clock-text').textContent = !live ? 'unknown'
    : !fresh ? `갱신 멎음 (${ageText(sinceMsg)})`
    : stopped ? `멈춤 (${ageText(age)})`
    : `생존 ${ageText(age)}`;
}
