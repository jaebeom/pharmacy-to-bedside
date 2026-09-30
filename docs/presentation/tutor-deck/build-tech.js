// 발표 5점 슬라이드 3장 — 로봇별 제어 flowchart · 시스템 아키텍처 · 기술 스택.
// 값은 main 코드(파일:줄)에서 옮겼다. 근거는 tech-3-sources.md.
// `node build-tech.js <출력 폴더>` → tech-3.html
const fs = require('fs');
const path = require('path');
const OUT = process.argv[2] || '.';
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// ---------- 1. flowchart ----------
const LX = 150, CW = 146, LH = 92, TOP = 8;               // 레인 라벨 폭 · 칸 폭 · 레인 높이
const lanes = [
  ['주문 FSM', 'orchestrator'],
  ['M0609', '레일 팔 · 트립과 병렬'],
  ['조제기 · 벨트', 'Isaac 스테이지'],
  ['AMR 팔(UR5)', 'PickPouch'],
  ['AMR 주행', 'fleet · Nav2'],
];
const cols = ['접수', '배출', '벨트', '집기', '출발', '병상', '복귀'];
// [레인, 시작 칸, 칸 수, 제목, 끝 이벤트]
const B = [
  [0, 0, 1, '주문 접수', 'ACCEPTED'],
  [0, 1, 1, 'DOCKED_LOAD', '배출 요청'],
  [0, 2, 1, 'WAIT_BELT', '벨트 60 s'],
  [0, 3, 1, 'PICKING_BELT', 'LOAD_DONE'],
  [0, 4, 1, 'TRANSIT', 'DEPARTED'],
  [0, 5, 1, 'AUTH → DELIVERING', 'ORDER_DONE'],
  [0, 6, 1, 'RETURNING', 'DOCKED'],
  [1, 2, 1, '재고 문턱', 'REFILL_REQUESTED'],
  [1, 3, 1, '칸 선택 · IK', '계획 캐시'],
  [1, 4, 1, '약통 QR 확인', 'check_container'],
  [1, 5, 1, '넣기 · 놓기', 'released'],
  [1, 6, 1, '홈 복귀', 'REFILL_DONE'],
  [2, 1, 1, '/pharmacy/dispense', 'DISPENSED'],
  [2, 2, 1, '벨트 이송 34.6 s', 'sim 측정'],
  [2, 3, 1, 'A1 끝 도착', 'POUCH_AT_END'],
  [3, 3, 1, 'detect → grasp', 'POUCH_PICKED'],
  [3, 4, 1, '트레이 칸', 'POUCH_LOADED'],
  [3, 5, 1, '인증 → 보관함', 'AUTH_OK·PLACED'],
  [4, 0, 1, 'GoToZone(load)', 'ARRIVED'],
  [4, 4, 1, 'GoToZone(병상)', 'Nav2 + 감속기'],
  [4, 5, 1, '마지막 0.5 m', 'ARRIVED'],
  [4, 6, 1, 'GoToZone(dock_1)', 'DOCKED'],
];
const bx = (c, span) => LX + c * CW + 6, by = l => TOP + 26 + l * LH + 10;
const BW = CW - 12, BH = LH - 22;
const center = (l, c) => [bx(c) + BW / 2, by(l) + BH / 2];
// 레인 사이 의존(굵은 화살표)
const deps = [
  [[0, 1], [2, 1]],   // 배출 요청 → dispense
  [[2, 3], [3, 3]],   // POUCH_AT_END → 집기
  [[3, 4], [4, 4]],   // LOAD_DONE → 출발
  [[4, 5], [3, 5]],   // ARRIVED → 인증 · 놓기
];
let svg = `<svg viewBox="0 0 1184 500" width="100%" height="100%" role="img" aria-label="로봇별 제어 flowchart">
<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="#2a7f86"/></marker>
<marker id="ad" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" fill="#c2410c"/></marker></defs>
<g font-family="inherit">`;
cols.forEach((c, i) => { svg += `<text x="${LX + i * CW + CW / 2}" y="${TOP + 16}" text-anchor="middle" font-size="13" fill="#5b6b70">${esc(c)}</text>`; });
lanes.forEach((l, i) => {
  const y = TOP + 26 + i * LH;
  svg += `<rect x="0" y="${y}" width="1184" height="${LH}" fill="${i % 2 ? '#f6f9f9' : '#eef5f4'}"/>`;
  svg += `<text x="10" y="${y + 40}" font-size="15" font-weight="700" fill="#16252b">${esc(l[0])}</text><text x="10" y="${y + 60}" font-size="11.5" fill="#5b6b70">${esc(l[1])}</text>`;
});
// 레인 안 순서 화살표
for (let l = 0; l < lanes.length; l++) {
  const row = B.filter(b => b[0] === l).sort((a, b) => a[1] - b[1]);
  for (let i = 0; i + 1 < row.length; i++) {
    const [x1, y1] = center(l, row[i][1]); const [x2] = center(l, row[i + 1][1]);
    svg += `<line x1="${x1 + BW / 2}" y1="${y1}" x2="${x2 - BW / 2 - 2}" y2="${y1}" stroke="#2a7f86" stroke-width="1.6" marker-end="url(#ah)"/>`;
  }
}
B.forEach(([l, c, s, t, e]) => {
  const x = bx(c), y = by(l);
  svg += `<rect x="${x}" y="${y}" width="${BW * s + (s - 1) * 12}" height="${BH}" rx="8" fill="#ffffff" stroke="#9cc5c1"/>`;
  svg += `<text x="${x + 8}" y="${y + 26}" font-size="13" font-weight="700" fill="#0f4c5c">${esc(t)}</text>`;
  svg += `<text x="${x + 8}" y="${y + 48}" font-size="11.5" fill="#16252b" font-family="ui-monospace,Menlo,monospace">${esc(e)}</text>`;
});
deps.forEach(([[l1, c1], [l2, c2]]) => {
  const [x1, y1] = center(l1, c1), [x2, y2] = center(l2, c2);
  const sy = y1 + (l2 > l1 ? BH / 2 : -BH / 2), ey = y2 + (l2 > l1 ? -BH / 2 - 2 : BH / 2 + 2);
  svg += `<path d="M${x1 + 30},${sy} C${x1 + 30},${(sy + ey) / 2} ${x2 - 30},${(sy + ey) / 2} ${x2 - 30},${ey}" fill="none" stroke="#c2410c" stroke-width="2" stroke-dasharray="5 4" marker-end="url(#ad)"/>`;
});
svg += `</g></svg>`;

// ---------- 2. 아키텍처 ----------
const role = (x, y, w, h, name, launch, nodes) =>
  `<g><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="10" fill="#ffffff" stroke="#9cc5c1"/>
  <text x="${x + 12}" y="${y + 24}" font-size="15" font-weight="800" fill="#0f4c5c">${esc(name)}</text>
  <text x="${x + 12}" y="${y + 42}" font-size="11" fill="#5b6b70" font-family="ui-monospace,Menlo,monospace">${esc(launch)}</text>
  ${nodes.map((n, i) => `<text x="${x + 12}" y="${y + 64 + i * 19}" font-size="12.5" fill="#16252b">· ${esc(n)}</text>`).join('')}</g>`;
const arch = `<svg viewBox="0 0 1184 470" width="100%" height="100%" role="img" aria-label="시스템 아키텍처">
<g font-family="inherit">
<rect x="0" y="0" width="360" height="470" rx="14" fill="#eef5f4"/>
<text x="16" y="28" font-size="16" font-weight="800" fill="#16252b">PC A · P3_ROLES=stage</text>
<text x="16" y="48" font-size="12" fill="#5b6b70">Isaac Sim 5.1 · Python 3.11(env -i)</text>
${role(16, 62, 328, 392, 'stage', 'pharmacy_stage.py(standalone)', ['병원 씬 · 물리(60 Hz)', '조제기 · 씬 컨베이어', 'M0609 · AMR 합본(UR5)', 'RTX 2D 라이다 → /amr_1/scan', 'D455형 손 카메라 · M0609 손 카메라', '참값 센서 · 평가기(보관함)', '단계형 리셋', 'JSON 토픽 /isaac/*  +  /clock'])}
<rect x="400" y="0" width="784" height="470" rx="14" fill="#f6f9f9"/>
<text x="416" y="28" font-size="16" font-weight="800" fill="#16252b">PC B · P3_ROLES="arm nav stack web"</text>
<text x="416" y="48" font-size="12" fill="#5b6b70">ROS 2 Jazzy · Python 3.12 · 기본은 한 PC 에 다섯 역할 전부</text>
${role(416, 62, 246, 170, 'arm', 'm0609_arm', ['/m0609/refill (action)', '약통 QR 확인 요청', '/m0609/arm/at_home'])}
${role(676, 62, 494, 170, 'nav', 'navigation.launch.py', ['fleet · base_driver · zones_tf · dock_origin_tf', 'Nav2: map_server · planner(NavFn) · controller(DWB)', 'behavior · bt_navigator · speed_governor · map_activation_guard', '/amr_1/go_to_zone (action)'])}
${role(416, 246, 494, 208, 'stack', 'stub_loop.launch.py use_isaac_adapter:=true', ['isaac_adapter (JSON ↔ ROS 타입, ADR 0002)', 'orchestrator (트립 FSM · 약 DB · 재고)', 'event_logger (/events · 평가기 보관함 → SUCCESS)', 'arm (UR5 PickPouch · scan_tag)', 'm0609_detector (약통 QR, OpenCV)', 'pouch_detector 는 카메라 집기 옵션일 때만'])}
${role(924, 246, 246, 208, 'web', 'web/backend app.main', ['FastAPI · WebSocket', '/deliver 클라이언트', '/orchestrator/reset', '관제 · 간호사 화면'])}
</g>
<g font-family="inherit"><line x1="360" y1="235" x2="400" y2="235" stroke="#c2410c" stroke-width="3"/>
<text x="380" y="222" text-anchor="middle" font-size="11.5" font-weight="700" fill="#c2410c">DDS</text>
<text x="380" y="256" text-anchor="middle" font-size="10.5" fill="#c2410c">도메인</text><text x="380" y="270" text-anchor="middle" font-size="10.5" fill="#c2410c">131</text></g>
</svg>`;

// ---------- 3. 기술 스택 ----------
const stack = [
  ['OS · GPU', 'Ubuntu 24.04.4 LTS · RTX 5080 Laptop · 드라이버 580.173.02 · CUDA 13.0'],
  ['시뮬레이터', 'NVIDIA Isaac Sim 5.1.0 standalone(Python 3.11) · RTX 라이다 · 카메라 센서'],
  ['미들웨어', 'ROS 2 Jazzy · rmw_fastrtps_cpp · Isaac ↔ ROS 는 JSON 토픽 + isaac_adapter'],
  ['주행', 'Nav2(NavFn · DWB · bt_navigator) · 자체 speed_governor · 도크 기준 odom TF(AMCL 없음)'],
  ['팔 제어', 'MoveIt 없이 자체 IK — M0609 다중 시드 IK 계획 캐시 · UR5 DH + 감쇠 최소자승'],
  ['비전', 'OpenCV QRCodeDetector — v1.0: M0609 약통 QR · 9/29 main: 봉투 · 병상 QR 까지(L3 미실행) · 학습 모델 없음'],
  ['관제 웹', 'FastAPI 0.115 · uvicorn · WebSocket · 바닐라 JS(ES 모듈)'],
  ['빌드 · 검증', 'colcon · GitHub Actions(colcon test · 저장소 · 증거 검사 · ruff · pytest) · Isaac L3 는 마스터 PC'],
  ['증거', 'frozen protocol v4 · tools/evidence.py(append-only run 기록) · aggregate_runs · boot_check · record_qa'],
];
const stackHtml = `<table class="stk"><tbody>${stack.map(r => `<tr><th>${esc(r[0])}</th><td>${esc(r[1])}</td></tr>`).join('')}</tbody></table>`;

const S = [
  { id: '발표', name: '로봇별 제어 flowchart — 주문 1건', body: svg,
    foot: '점선 = 레인 사이 의존. 인터락: 주행 goal ⇐ arm/at_home · 집기·스캔·놓기 ⇐ base/stopped · 배출 ⇐ 벨트 비어 있음 · 장착 ⇐ check_container 허가. M0609 보충은 트립과 병렬이고, 재고가 0 이면 DISPENSER_PAUSED → REFILL_DONE 뒤 DISPENSER_RESUMED. 실패: 배출 거부 3회·집기 2회·도크 복귀 10→20→40 s 재시도 · 보충 90 s 시한 3회. 봉투는 스테이지가 스폰. v1.0 판정 기준(집기 좌표 참값). 9/29 main 은 도크 = 적재 자리(GoToZone(load) 생략, #790) · 봉투 · 병상 QR 카메라 확인 필수(#784) — L3 미실행.' },
  { id: '발표', name: '시스템 아키텍처 — PC · 역할 · 노드', body: arch,
    foot: '기동은 tools/demo_v2.sh up 하나(stage → arm → nav → stack → web). 두 대는 P3_ROLES · P3_PEER · P3_DOMAIN. Nav2 는 접근점까지, 마지막 0.5 m 는 fleet 직접 추종(회피·감속기 미적용). 배송 성공은 평가기가 본 보관함으로 기록.' },
  { id: '발표', name: '기술 스택', body: stackHtml,
    foot: '버전은 v1.0 판정 run 의 environment.versions(master01)에서 옮겼다. 쓰지 않은 것: MoveIt · YOLO 가중치 · AMCL · 실물 조제. 9/29 main 은 봉투 · 병상 QR 도 손 카메라 OpenCV 판독(#784, L3 미실행).' },
];
const slides = S.map((s, i) => `<div class="frame"><section class="slide">
  <div class="head"><h2>${esc(s.name)}</h2><span class="pts">발표·시연 5점</span></div>
  <div class="body">${s.body}</div>
  <p class="foot">${esc(s.foot)}</p>
  <div class="pg">${i + 1} / 3</div>
</section></div>`).join('\n');

const html = `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>제어 · 구조 · 스택</title>
<style>
:root{--teal:#0f4c5c;--teal2:#2a7f86;--ink:#16252b;--mute:#5b6b70;--bg:#fff;--page:#dfe8e6}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--page:#1b2427}}
:root[data-theme="dark"]{--page:#1b2427}
*{box-sizing:border-box}
body{margin:0;background:var(--page);font-family:"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",Arial,sans-serif;color:var(--ink)}
.frame{width:1280px;height:720px;margin:24px auto;overflow:hidden}
.slide{width:1280px;height:720px;background:var(--bg);position:relative;padding:30px 48px;box-shadow:0 2px 10px rgba(0,0,0,.15);transform-origin:top left}
.head{display:flex;justify-content:space-between;align-items:baseline}
h2{font-size:30px;margin:0}.pts{font-size:16px;font-weight:700;color:var(--teal)}
.body{margin-top:16px;height:520px;display:flex;align-items:center}
.body svg{width:100%;height:100%}
.stk{width:100%;border-collapse:collapse;font-size:19px}
.stk th{width:170px;text-align:left;color:var(--teal);padding:11px 14px;border-bottom:1px solid #d5e2e0;vertical-align:top}
.stk td{padding:11px 14px;border-bottom:1px solid #d5e2e0;line-height:1.35}
.foot{position:absolute;left:48px;right:48px;bottom:26px;margin:0;font-size:12.5px;line-height:1.45;color:var(--mute)}
.pg{position:absolute;right:48px;bottom:8px;font-size:11px;color:var(--mute)}
@media (max-width:1320px){.frame{width:calc(100vw - 32px);height:calc((100vw - 32px)*0.5625);margin:16px}}
@media print{body{background:#fff}.frame{margin:0;page-break-after:always}.slide{box-shadow:none;transform:none!important}}
</style></head><body>
${slides}
<script>
function fit(){document.querySelectorAll('.frame').forEach(f=>{const s=f.firstElementChild;const k=f.clientWidth/1280;s.style.transform=k<1?'scale('+k+')':'none'})}
addEventListener('resize',fit);fit();
</script>
</body></html>
`;
fs.writeFileSync(path.join(OUT, 'tech-3.html'), html);
console.log('wrote', path.join(OUT, 'tech-3.html'));
