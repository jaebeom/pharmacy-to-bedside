// 본 발표 7쪽 — 평가 항목 하나에 한 쪽. 왼쪽 큰 숫자, 오른쪽 캡처, 아래 세 줄(과제 → 방법 → 결과).
// 세부 근거 · 증거 번호는 부록 tutor-response.html(질의응답용)에 있다.
// `node build-main.js <출력 폴더>` → tutor-main.html
const fs = require('fs');
const path = require('path');
const OUT = process.argv[2] || '.';

const S = [
  { id: '3.1', name: '디지털 트윈 설계 및 납품 품질', pts: 20, img: 'stills/0924/m1-floor_top.png', cap: '병원 전체 — 조제실 · 복도 · 병실',
    kpi: [['14/14', 'v1.0 판정 회전 · 병원 전 구간'], ['10/10', '병상 D1–D10 배송(v0.5.0)']],
    lines: ['병원 약이 조제실에서 병상까지 가는 과정을, 실제로 실험하기 위험한 병동 대신 시뮬레이션에서 검증한다',
      '확정 시나리오 한 흐름 · 통과 기준을 실행 전에 동결(protocol v4) · 실행 명령과 자산 해시를 저장소에',
      'v1.0 회전 7 에서 한 PC 로 14 attempt 모두 판정선(다섯 장면 · 배송 · 접촉 0 · 녹화) 통과. 다중 PC 두 칸은 미실행'] },
  { id: '3.2', name: '시뮬레이션 환경 구성', pts: 10, img: 'stills/0924/m2-m0609_shelf.png', cap: '레일 위 M0609 가 약통 선반에서 보충',
    kpi: [['419,292 → 0', 'PhysX 경고(한 회차)'], ['5 → 0', '레일 물리 멈춤']],
    lines: ['선반 충돌 메시가 매 스텝 경고를 내고, 레일 팔 구동이 물리 스텝을 멈췄다',
      '충돌체를 실측 판 두께 상자로 · 레일 구동 강성 조정 · /clock 하나 · tf · 라이다 · 카메라를 ROS2 로',
      'Play/Stop 뒤 자동 복구 → 리셋 → 같은 주문이 다시 배송 완료(여러 회차)'] },
  { id: '3.3', name: '개별 로봇 제어', pts: 25, img: 'stills/0924/m2-a1_pick.png', cap: 'UR5 가 컨베이어 끝 봉투를 집어 트레이에',
    kpi: [['57 → 0', '팔 받침 ↔ 협탁 접촉'], ['113 → 72 s', '복도 주행 시간(sim)']],
    lines: ['세 로봇(M0609 보충 · UR5 집기 · AMR 운반)이 각자 일을 안정적으로 끝내야 한다',
      '팔 속도는 제조사 사양의 80 % · 병상에서 도는 자리를 접근점으로 옮김 · 감속기가 실제 벽까지 거리로 속도를 정함',
      '병상 10곳 모두 배송, 접촉 0. 경로 계획의 안전 여유(팽창 반경)는 그대로 두고 빨라졌다. 감속기 정지 규칙은 v1.0.1 로 미룸(#752)'] },
  { id: '3.4', name: 'AI 비전 인식 및 활용', pts: 10, img: 'stills/0924/m2-m0609_dispenser.png', cap: 'M0609 손 카메라(D455)가 약통 QR 을 확인하고 장착',
    kpi: [['3/3 → 판독', '못 읽던 약통 QR'], ['허용 · 거부', '인식 결과가 동작을 결정']],
    lines: ['M0609 손 카메라가 약통 QR 을 읽지 못했다(모듈 3/3 판독 실패)',
      'QR 을 카메라가 보는 면으로 · 네 점 원근 보정 뒤 재판독 · 작으면 2배 확대 재판독 · 로봇이 멈춘 뒤 읽기',
      '맞는 약이면 끼우고, 틀리거나 유효기간이 지나면 거부한다(v1.0 판정). 9/29 main 은 봉투 QR · 병상 QR 도 카메라로 맞춰야 집고 내려놓는다 — 검증 전'] },
  { id: '3.5', name: '시스템 통합 및 동적 대응 검증', pts: 35, img: '../architecture/system-overview.svg', cap: '역할 분리 구조(P3_ROLES) — 기본은 한 PC. 다중 PC 판정은 회전 1–3 에만 있고 v1.0 에서는 미실행',
    kpi: [['10/10', '주문 10건 연속 · 접촉 0'], ['53/63 → 14/14', '판정 run: v0.5.0 → v1.0']],
    lines: ['로봇 셋이 한 시나리오를 끊김 없이 돌고, 배치가 바뀌거나 급한 주문이 끼어들어도 버텨야 한다',
      '로봇 사이 인터락 · 진열 무작위(seed 11 · 23) · 긴급 주문 · Play/Stop 복구 · AMR 2대 · 같은 16 attempt 판정을 버전마다',
      '10건 시험이 4/10 회귀를 잡아 10/10 으로. v0.5.0 실패 10건은 분류(robot 1 · infra 6 · operator 3)해 남기고, v1.0 은 14/14'] },
  { id: '3.6', name: '발표 및 시연', pts: 5, img: 'stills/0924/m1-bed_a1.png', cap: '병상 보관함에 약을 넣는 장면(9/24 정지 캡처)',
    kpi: [['300 s', '영상 158 s · 슬라이드 142 s'], ['run 6개', '컷마다 run ID · 배속 표기']],
    lines: ['5분 안에 기능이 눈에 보이게 전달해야 한다',
      'flowchart · 시스템 구조도 · 기술 스택을 실제 코드와 같게 · 등록 run 녹화를 이어 붙이고 배속 · run ID 를 화면에',
      '본 발표 7쪽 + 제어 · 구조 · 스택 3쪽 + 질의응답용 근거 부록(증거 · 회차 · 한계 전부)'] },
  { id: '3.7', name: '챌린지', pts: 5, chart: true, cap: '렌더 주기 하나만 바꿔 잰 결과 — 물리는 60 Hz 그대로',
    kpi: [['0/6 → 6/6', '병원 Nav2 도착'], ['0.42 → 0.69', '시뮬 속도 rtf(같은 PC)']],
    lines: ['병원에서 Nav2 가 한 곳도 도착하지 못했고, 시뮬레이션은 실제 속도의 1/3 이었다',
      '원인을 한 층씩 잘라 한 번에 한 변수만 바꿔 잼(지도 · 위치 추정 · 넘김 · 충돌체 · 렌더 주기)',
      '두 편의 기술 리포트 — 주행 0/6 → 6/6, rtf 0.42 → 0.69(같은 PC, 장비별 표)'] },
];

const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const chart = `<svg viewBox="0 0 560 360" width="100%" height="100%" role="img" aria-label="rtf 계단">
  <g font-family="inherit" font-size="15" fill="#16252b">
  ${[['매 스텝 렌더', 0.418], ['2 스텝에 1번 렌더', 0.690]].map((b, i) => {
    const h = b[1] / 0.75 * 240, x = 110 + i * 220;
    return `<rect x="${x}" y="${300 - h}" width="130" height="${h}" rx="8" fill="${i === 1 ? '#0f4c5c' : '#9cc5c1'}"/><text x="${x + 65}" y="${290 - h}" text-anchor="middle" font-weight="700" font-size="20">${b[1].toFixed(3)}</text><text x="${x + 65}" y="325" text-anchor="middle">${b[0]}</text>`;
  }).join('')}
  <text x="30" y="30" font-weight="700" fill="#2a7f86">rtf(1.0 = 실제 속도) · 같은 코드 · 같은 PC(master01)</text></g></svg>`;

const slides = S.map((s, i) => `<div class="frame"><section class="slide">
  <div class="head"><h2><span class="num">${s.id}</span> ${esc(s.name)}</h2><span class="pts">${s.pts}점</span></div>
  <div class="mid">
    <div class="kpis">${s.kpi.map(k => `<div class="kpi"><div class="v">${esc(k[0])}</div><div class="l">${esc(k[1])}</div></div>`).join('')}</div>
    <figure class="vis">${s.chart ? chart : `<img src="${s.img}" alt="${esc(s.cap)}">`}<figcaption>${esc(s.cap)}</figcaption></figure>
  </div>
  <ol class="three">
    <li><b>과제</b>${esc(s.lines[0])}</li>
    <li><b>방법</b>${esc(s.lines[1])}</li>
    <li><b>결과</b>${esc(s.lines[2])}</li>
  </ol>
  <div class="foot"><span>근거 부록: tutor-response.html</span><span>${i + 1} / 7</span></div>
</section></div>`).join('\n');

const html = `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>튜터 평가 대응</title>
<style>
:root{--teal:#0f4c5c;--teal2:#2a7f86;--tint:#eaf3f2;--ink:#16252b;--mute:#5b6b70;--line:#d5e2e0;--bg:#fff;--page:#dfe8e6}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--page:#1b2427}}
:root[data-theme="dark"]{--page:#1b2427}
*{box-sizing:border-box}
body{margin:0;background:var(--page);font-family:"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",Arial,sans-serif;color:var(--ink)}
.frame{width:1280px;height:720px;margin:24px auto;overflow:hidden}
.slide{width:1280px;height:720px;background:var(--bg);position:relative;padding:34px 48px;box-shadow:0 2px 10px rgba(0,0,0,.15);transform-origin:top left}
.head{display:flex;justify-content:space-between;align-items:baseline}
h2{font-size:32px;margin:0}.num{color:var(--teal2)}.pts{font-size:24px;font-weight:700;color:var(--teal)}
.mid{display:grid;grid-template-columns:430px 1fr;gap:32px;margin-top:22px;height:400px}
.kpis{display:flex;flex-direction:column;gap:18px;justify-content:center}
.kpi{background:var(--tint);border-radius:14px;padding:22px 26px}
.kpi .v{font-size:46px;font-weight:800;color:var(--teal);line-height:1.1;letter-spacing:-0.5px}
.kpi .l{font-size:17px;color:var(--mute);margin-top:6px}
.vis{margin:0;display:flex;flex-direction:column;height:400px}
.vis img{flex:1;min-height:0;width:100%;object-fit:contain;background:#f3f6f6;border-radius:12px}
.vis svg{flex:1;min-height:0;background:#f3f6f6;border-radius:12px}
figcaption{font-size:13px;color:var(--mute);margin-top:6px}
.three{list-style:none;margin:20px 0 0;padding:0;display:grid;gap:8px}
.three li{font-size:17px;line-height:1.4;display:flex;gap:14px}
.three b{flex:0 0 52px;color:var(--teal2)}
.foot{position:absolute;left:48px;right:48px;bottom:12px;display:flex;justify-content:space-between;font-size:11px;color:var(--mute)}
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
fs.writeFileSync(path.join(OUT, 'tutor-main.html'), html);
console.log('wrote', path.join(OUT, 'tutor-main.html'), S.length, 'slides');
