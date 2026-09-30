// 튜터 평가표 1:1 대응 덱 — HTML. `node build-html.js <출력 폴더>` → tutor-response.html
const fs = require('fs');
const path = require('path');
const D = require('./data.js');
const OUT = process.argv[2] || '.';

const STATUS = { '계약 합격': '#2e7d32', 'L3 관측': '#2a7f86', '문서': '#6d4c9a', '부분': '#b86e00' };
const esc = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const items = [];
D.sections.forEach(s => s.items.forEach(it => items.push({ ...it, sec: s })));
const chip = st => `<span class="chip" style="background:${STATUS[st] || '#5b6b70'}">${esc(st)}</span>`;
const foot = n => `<div class="foot"><span>${esc(D.asOf)} · ${esc(D.freeze)}</span><span>${n}</span></div>`;

// 7쪽: 평가 항목 하나에 한 쪽. 2절(영상 발표) 요구는 3.6 쪽에 넣는다.
const secs = D.sections.filter(s => s.points);
const video = D.sections.find(s => !s.points);
const slides = secs.map(sec => {
  const its = sec.id === '3.6' ? [...video.items.map(i => ({ ...i, sec: video })), ...sec.items.map(i => ({ ...i, sec }))] : sec.items.map(i => ({ ...i, sec }));
  const cls = its.length >= 4 ? 'g4' : its.length === 3 ? 'g3' : its.length === 2 ? 'g2' : 'g1';
  const nDid = its.length >= 4 ? 0 : its.length === 3 ? 3 : 4;
  const cards = its.map(it => `<div class="card">
      <div class="ch"><b>${esc(it.name)}</b>${chip(it.status)}</div>
      <blockquote>“${esc(it.quote)}”</blockquote>
      <div class="plain">${esc(it.plain)}${nDid ? `<div class="dh">자세히</div><ul>${it.did.slice(0, nDid).map(d => `<li>${esc(d)}</li>`).join('')}</ul>` : ''}</div>
      <div class="key">▸ ${esc(it.key)}</div>
      <div class="ev">${esc(it.evidence[0])}</div>
      <div class="left">남은 것 · ${esc(it.short)}</div>
    </div>`).join('');
  return `<section class="slide">
  <div class="head"><h2><span class="num">${sec.id}</span> ${esc(sec.name)}</h2><span class="pts">${sec.points}점</span></div>
  <div class="cards ${cls}">${cards}</div>`;
});
const body = slides.map((s, i) => `<div class="frame">${s}${foot(i + 1)}</section></div>`).join('\n');
const html = `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>튜터 평가표 대응</title>
<style>
:root{--teal:#0f4c5c;--teal2:#2a7f86;--tint:#eaf3f2;--ink:#16252b;--mute:#5b6b70;--amber:#b86e00;--amberT:#fff3de;--line:#d5e2e0;--bg:#fff;--page:#dfe8e6}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--page:#1b2427}}
:root[data-theme="dark"]{--page:#1b2427}
*{box-sizing:border-box}
body{margin:0;background:var(--page);font-family:"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",Arial,sans-serif;color:var(--ink)}
.frame{width:1280px;height:720px;margin:24px auto;overflow:hidden}
.slide{width:1280px;height:720px;background:var(--bg);position:relative;padding:28px 40px 30px;box-shadow:0 2px 10px rgba(0,0,0,.15);transform-origin:top left}
.slide.dark{background:var(--teal);color:#fff;padding:120px 80px}
.dark h1{font-size:46px;margin:14px 0}.dark .kick,.dark .meta{color:#cfe7e5}.dark .lead{font-size:21px}.dark .big{font-size:44px;font-weight:700;color:#cfe7e5}
.dark .meta{position:absolute;bottom:90px;font-size:14px}
h2{font-size:32px;margin:0}h3{font-size:17px;color:var(--teal);margin:0 0 12px}h4{font-size:14px;color:var(--teal);margin:0 0 8px}
.head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px}
h2{font-size:28px;margin:0}.num{color:var(--teal2)}.pts{font-size:22px;font-weight:700;color:var(--teal)}
.chip{display:inline-block;color:#fff;font-weight:700;font-size:11.5px;padding:3px 10px;border-radius:6px;white-space:nowrap}
.cards{display:grid;gap:14px;height:596px}
.g4{grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr}.g3{grid-template-columns:1fr 1fr 1fr}.g2{grid-template-columns:1fr 1fr}.g1{grid-template-columns:1fr}
.card{border:1px solid var(--line);border-radius:12px;padding:12px 16px;display:flex;flex-direction:column;gap:6px;overflow:hidden}
.ch{display:flex;justify-content:space-between;align-items:center;font-size:17px;color:var(--teal)}
blockquote{margin:0;background:var(--tint);border-radius:8px;padding:6px 10px;font-style:italic;font-size:12.5px;line-height:1.4}
.plain{font-size:14px;line-height:1.55;flex:1}.g1 .plain,.g2 .plain{font-size:18px}.g3 .plain{font-size:15px}
.dh{font-size:12px;font-weight:700;color:var(--teal2);margin:12px 0 4px}.plain ul{margin:0;padding-left:18px}.plain li{font-size:13px;line-height:1.45;margin-bottom:4px;color:var(--ink)}.g1 .plain li,.g2 .plain li{font-size:14.5px}
.key{font-size:14.5px;font-weight:700;color:var(--teal)}.g1 .key,.g2 .key{font-size:17px}
.card ul{margin:0;padding-left:18px;flex:1}.card li{font-size:12.5px;line-height:1.4;margin-bottom:3px}
.g1 .card li,.g2 .card li{font-size:14px;margin-bottom:6px}.g1 blockquote,.g2 blockquote{font-size:14px}
.ev{font-size:11px;color:var(--mute);line-height:1.35}
.left{background:var(--amberT);border-radius:8px;padding:6px 10px;font-size:13px;line-height:1.35;color:var(--ink)}
.foot{position:absolute;left:48px;right:48px;bottom:10px;display:flex;justify-content:space-between;font-size:10px;color:var(--mute)}
@media (max-width:1320px){.frame{width:calc(100vw - 32px);height:calc((100vw - 32px)*0.5625);margin:16px}}
@media print{body{background:#fff}.frame{margin:0;page-break-after:always}.slide{box-shadow:none;transform:none!important}}
</style></head><body>
${body}
<script>
function fit(){document.querySelectorAll('.frame').forEach(f=>{const s=f.firstElementChild;const k=f.clientWidth/1280;s.style.transform=k<1?'scale('+k+')':'none'})}
addEventListener('resize',fit);fit();
</script>
</body></html>
`;
fs.writeFileSync(path.join(OUT, 'tutor-response.html'), html);
console.log('wrote', path.join(OUT, 'tutor-response.html'), slides.length, 'slides');

// md: 같은 데이터의 검토용 원본
const all = [];
D.sections.forEach(s => s.items.forEach(it => all.push({ ...it, sec: s })));
let md = `# 튜터 평가표 1:1 대응 — 발표 원본\n\n> 재범 요청(9/25): 튜터 평가 문서의 요구를 1:1 로 말하고 어떻게 대응했는지 보이는 발표. 평가 항목 7개 = 7쪽이다.\n> 기준: ${D.asOf}. ${D.freeze}. 요구 원문은 [최종 발표 평가](../reference/tutor/final-presentation-evaluation.md) 2·3절 전사 그대로다. 4–8절은 우리 작성 가이드다. 요구로 세지 않는다. 2절(영상 발표)은 3.6 쪽에 넣었다.\n> 발표 파일: [tutor-response.html](tutor-response.html). 이 md 와 html 은 [tutor-deck/](tutor-deck/) 의 같은 데이터에서 만든다. 쪽에는 한 일을 요구마다 앞 세 줄만 싣는다.\n`;
all.forEach(it => {
  md += `\n## ${it.sec.id} ${it.name} — ${it.status}\n\n> 튜터 요구: ${it.quote}\n\n**대응**: ${it.claim}\n\n`;
  it.did.forEach(d => { md += `- ${d}\n`; });
  md += `\n증거: ${it.evidence.join(' · ')}\n\n남은 것: ${it.left}\n`;
});
fs.writeFileSync(path.join(OUT, 'tutor-response.md'), md);
