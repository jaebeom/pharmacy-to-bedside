// 카메라 칸: AMR 손 카메라(트레이 쪽 상판 비전)·M0609 손 카메라(약통 QR)의 MJPEG 스트림과 글자 오버레이(api.md §1.8).
// 개발자 화면(카메라 탭)과 촬영 화면(평면도 위 작은 창)이 같이 쓴다.
//
// 부하 규칙: **보이는 동안만** 스트림을 연다. 닫으면 <img> 의 src 를 비워 연결을 끊는다 — 서버는 마지막 시청자가
// 나가면 구독을 푼다. 한 카메라 시청자는 3명까지다(429). 목록·오버레이는 열려 있는 동안만 1 Hz 로 받는다.
// 픽셀 박스는 없다(검출 메시지에 박스가 없다). QR 판독·봉투 order_id·신뢰도만 글자로 얹는다.
import { fetchCameras, cameraStreamUrl } from '../api.js';
import { el, replace } from '../dom.js';
import { ageText } from '../format.js';

const RETRY_MS = 3000;

/**
 * @param root  칸 자리
 * @param opts.compact  촬영 화면용(카메라 하나, 머리글 짧게)
 * @returns {{ open(names: string[]): void, close(): void, isOpen(): boolean }}
 */
export function createCameraView(root, { compact = false } = {}) {
  let names = [];            // 지금 보여 줄 카메라 이름
  let info = new Map();      // name -> 마지막 /api/cameras 항목
  let timer = 0;
  const tiles = new Map();   // name -> {box, img, meta, over, retry}

  function tileFor(name) {
    if (tiles.has(name)) return tiles.get(name);
    const img = el('img', { class: 'cam-img', alt: name });
    const meta = el('span', { class: 'cam-meta' });
    const over = el('div', { class: 'cam-over' });
    const msg = el('div', { class: 'cam-msg', hidden: true });
    const box = el('figure', { class: `cam${compact ? ' is-compact' : ''}` }, [
      el('div', { class: 'cam-frame' }, [img, over, msg]),
      el('figcaption', { class: 'cam-cap' }, [el('span', { class: 'cam-label', text: name }), meta]),
    ]);
    const t = { box, img, meta, over, msg, retry: 0, label: box.querySelector('.cam-label') };
    // 429(시청자 초과)·끊김·아직 프레임 없음은 전부 onerror 로 온다. 열려 있는 동안만 다시 붙는다.
    img.addEventListener('error', () => {
      if (!names.includes(name)) return;
      t.msg.hidden = false;
      t.msg.textContent = '스트림 없음 — 다시 붙는 중 (시청자 3명 초과이거나 프레임이 아직 없음)';
      clearTimeout(t.retry);
      t.retry = setTimeout(() => { if (names.includes(name)) start(name); }, RETRY_MS);
    });
    img.addEventListener('load', () => { t.msg.hidden = true; });
    tiles.set(name, t);
    return t;
  }

  function start(name) {
    const t = tileFor(name);
    t.img.src = `${cameraStreamUrl(name)}?t=${Date.now()}`; // 캐시된 끊긴 연결을 다시 쓰지 않게
  }

  function stop(name) {
    const t = tiles.get(name);
    if (!t) return;
    clearTimeout(t.retry);
    t.img.removeAttribute('src');   // 연결을 끊는다 → 서버 시청자에서 빠진다
    t.img.src = '';
  }

  function drawOverlay(name) {
    const t = tileFor(name);
    const c = info.get(name);
    t.label.textContent = c ? c.label : name;
    // 연 직후 첫 프레임 전에는 stamp 가 null 이고 stale 이다(api.md §1.8) — 멎은 것이 아니라 붙는 중이다.
    const waiting = c && c.stamp === null;
    t.meta.textContent = !c ? '' : waiting ? '연결 중…' : c.stale ? '프레임 멎음' : `${ageText(c.ageWallS)}`;
    t.box.classList.toggle('is-stale', !!(c && c.stale && !waiting));
    const lines = [];
    if (c && c.tag) {
      const ok = c.tag.status === 'ok';
      lines.push(el('span', { class: `cam-tag ${ok ? 'is-ok' : 'is-bad'}`, text: ok ? `QR ${c.tag.tagId}` : 'QR 못 읽음' }));
    }
    for (const p of (c ? c.pouches : [])) {
      const pct = Number.isFinite(p.confidence) ? ` ${Math.round(p.confidence * 100)}%` : '';
      lines.push(el('span', { class: 'cam-tag', text: `${p.orderId || '봉투'}${pct}` }));
    }
    replace(t.over, lines);
  }

  async function poll() {
    try {
      const d = await fetchCameras();
      info = new Map(d.cameras.map((c) => [c.name, c]));
    } catch { /* 한 번 못 받으면 지난 값을 둔다 */ }
    names.forEach(drawOverlay);
  }

  function open(want) {
    const next = want.filter(Boolean);
    for (const n of names) if (!next.includes(n)) stop(n);
    for (const n of next) if (!names.includes(n)) start(n);
    names = next;
    replace(root, names.map((n) => tileFor(n).box));
    if (!timer && names.length) { poll(); timer = setInterval(poll, 1000); }
    if (!names.length) close();
  }

  function close() {
    for (const n of names) stop(n);
    names = [];
    clearInterval(timer); timer = 0;
    replace(root, []);
  }

  return { open, close, isOpen: () => names.length > 0 };
}

/** 서버에 카메라가 켜져 있는가(--live-sensors). 못 물으면 false. 카메라 이름 목록도 준다. */
export async function camerasAvailable() {
  try {
    const d = await fetchCameras();
    return d.enabled ? d.cameras.map((c) => c.name) : [];
  } catch {
    return [];
  }
}
