// settings.js — 설정 화면. 바꿀 수 있는 것은 이 브라우저의 화면 취향(밝기·글자 크기)뿐이다.
// 서버 설정(주문 풀·병상 목록·명령 허용)은 **보여 주기만** 한다 — 바꾸는 곳은 서버 기동 인자다.
import { fetchOrderPool, fetchDestinations } from './api.js';
import { createStore } from './store.js';
import { startLive } from './live.js';
import { renderNav } from './nav.js';
import { loadPrefs, savePrefs, applyPrefs } from './prefs.js';
import { el, replace } from './dom.js';
import { groupDestinations, simBadge, deploymentText } from './format.js';

const $ = (id) => document.getElementById(id);
const store = createStore();
let live = null;
let prefs = loadPrefs();

// ---------------------------------------------------------------- 화면 취향

const THEME = [{ v: 'light', t: '밝게' }, { v: 'dark', t: '어둡게' }];
const SIZE = [{ v: 'normal', t: '보통' }, { v: 'large', t: '크게' }];

function seg(root, options, key) {
  replace(root, options.map((o) => el('button', {
    type: 'button',
    class: `n-seg-btn${prefs[key] === o.v ? ' is-on' : ''}`,
    'aria-pressed': prefs[key] === o.v ? 'true' : 'false',
    onclick: () => {
      prefs = { ...prefs, [key]: o.v };
      const kept = savePrefs(prefs);
      applyPrefs(prefs);
      renderPrefs();
      if (!kept) $('pref-note').textContent = '이 브라우저가 저장을 막고 있어, 새로고침하면 원래대로 돌아갑니다.';
    },
  }, el('span', { class: 'n-seg-t', text: o.t }))));
}

function renderPrefs() {
  seg($('pref-theme'), THEME, 'theme');
  seg($('pref-size'), SIZE, 'size');
}

// ---------------------------------------------------------------- 읽기 전용

const row = (key, value, hint) => el('div', { class: 's-row' }, [
  el('span', { class: 's-key', text: key }),
  el('div', { class: 's-val' }, [
    typeof value === 'string' ? el('span', { text: value }) : value,
    hint ? el('span', { class: 's-hint', text: hint }) : null,
  ]),
]);
const tag = (text, tone) => el('span', { class: `n-tag is-${tone}`, text });

function renderServer() {
  const snap = store.state.snapshot;
  const up = live.conn.state === 'open';
  $('conn').className = 'n-conn ' + (up && live.fresh() ? 'is-ok' : up ? 'is-warn' : 'is-bad');
  $('conn-text').textContent = !up ? (live.conn.state === 'connecting' ? '연결 중…' : '연결 끊김')
    : live.fresh() ? '실시간' : '갱신 멈춤';

  const q = new URLSearchParams(location.search);
  const faults = snap ? snap.mockFaults : [];
  replace($('server'), [
    row('서버 주소', el('span', { class: 'n-mono', text: q.get('api') || location.origin }),
      q.get('api') ? '주소 뒤 ?api= 로 지정했습니다' : '이 화면을 연 주소와 같습니다'),
    row('연결', up ? tag(live.fresh() ? '실시간으로 받는 중' : '연결됐지만 갱신이 멈춤', live.fresh() ? 'ok' : 'warn')
      : tag(live.conn.state === 'connecting' ? '연결 중' : '끊김', 'bad'),
    live.conn.detail || null),
    row('서버 종류', snap ? (snap.serverMode === 'mock' ? tag('연습용 (mock)', 'warn') : snap.serverMode === 'ros' ? tag('실제 시스템 (ROS)', 'ok') : tag(snap.serverMode || '모름', 'idle')) : '—',
      snap && snap.serverMode === 'mock' ? '녹화 데이터를 재생하는 서버입니다. 실제 로봇과 연결돼 있지 않습니다.' : null),
    row('요청 넣기', snap ? (snap.commandsEnabled ? tag('허용됨', 'ok') : tag('막혀 있음', 'idle')) : '—',
      '서버를 --allow-commands 로 띄워야 요청·리셋 버튼이 보입니다'),
    faults.length ? row('고장 흉내', tag(faults.join(', '), 'bad'), '시험용 고장이 켜져 있습니다. 시연 전에 꺼야 합니다') : null,
    row('시뮬(Isaac)', snap && simBadge(snap.simRunning) ? tag(simBadge(snap.simRunning).text, { run: 'ok', stop: 'warn', off: 'bad' }[simBadge(snap.simRunning).tone]) : '—',
      '/p3/sim_running 이 3 s 넘게 안 오면 Isaac 없음이다'),
    row('배포', snap && snap.deployment ? (deploymentText(snap.deployment) || '한 대') : '—',
      snap && snap.deployment && snap.deployment.domainId !== null ? `ROS_DOMAIN_ID ${snap.deployment.domainId}` : null),
    row('서버 실행 ID', el('span', { class: 'n-mono', text: snap && snap.serverRunId ? snap.serverRunId : '—' }), '서버를 다시 띄우면 바뀝니다'),
  ].filter(Boolean));
}

const SOURCE_WORD = {
  file: '지정한 파일', repo_default: '저장소 기본 파일', mock: 'mock 기본값', fixture: '저장소 밖 fixture', none: '모름',
};

async function renderWorld() {
  const [p, d] = await Promise.allSettled([fetchOrderPool(), fetchDestinations()]);
  const out = [];

  if (d.status === 'fulfilled') {
    const groups = groupDestinations(d.value.destinations);
    out.push(row('병상·목적지', el('div', {}, [
      el('span', { text: `${d.value.destinations.length}곳 · ${SOURCE_WORD[d.value.source] || d.value.source}` }),
      el('ul', { class: 's-list' }, groups.map((g) => el('li', {}, [
        el('b', { text: `${g.label} ` }),
        el('span', { class: 'n-mono', text: g.items.map((x) => x.label || x.destinationId).join(', ') }),
      ]))),
    ]), '서버의 --zones-file 이 정합니다. 병원 월드는 zones.hospital.yaml 입니다'));
  } else {
    out.push(row('병상·목적지', tag('받지 못함', 'bad'), String(d.reason && d.reason.message || '')));
  }

  if (p.status === 'fulfilled') {
    const pool = p.value;
    const open = pool.orders.filter((o) => !o.used).length;
    out.push(row('주문 목록', `${pool.orders.length}건 (요청 가능 ${open}건) · ${SOURCE_WORD[pool.source] || pool.source}`,
      '서버의 --order-pool 이 정합니다. 리셋하면 요청 가능으로 돌아갑니다'));
    if (pool.problems.length) {
      out.push(row('주문 목록 문제', el('ul', { class: 's-list' }, pool.problems.map((x) => el('li', { text: x }))),
        '파일에서 버려진 항목입니다. 약제실·개발자에게 알려 주세요'));
    }
  } else {
    out.push(row('주문 목록', tag('받지 못함', 'bad'), String(p.reason && p.reason.message || '')));
  }
  replace($('world'), out);
}

function renderLinks() {
  const q = new URLSearchParams(location.search);
  q.delete('demo');
  const base = q.toString();
  const demo = new URLSearchParams(base);
  demo.set('demo', '1');
  replace($('links'), [
    el('a', { class: 'n-btn', href: `index.html?${demo}`, text: '개발자 화면 — 시연 모드 (?demo=1)' }),
    el('a', { class: 'n-btn', href: `index.html${base ? `?${base}` : ''}`, text: '개발자 화면 — 전체' }),
  ]);
}

// ---------------------------------------------------------------- 시작

function start() {
  applyPrefs(prefs);
  renderNav($('nav'), 'settings');
  renderPrefs();
  renderLinks();
  live = startLive(store, { render: () => { if (live) renderServer(); } });
  renderServer();
  renderWorld();
}

start();
