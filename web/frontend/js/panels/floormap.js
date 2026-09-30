// 병원 평면도: 지도(maps/*.pgm) 위에 구역(병상·dock·창구)과 AMR 현재 위치·가는 목적지를 그린다.
// 개발자·간호사 화면이 같이 쓴다. 색은 쓰는 쪽 CSS 의 --map-* 토큰에서 읽는다(어두운·밝은 바탕).
//
// 좌표: map 프레임(m). 지도 픽셀 (col,row) 는 x = origin.x + col·res, y = origin.y + (H−1−row)·res.
// PGM 은 맨 윗줄이 y 가 가장 큰 줄이다(ROS map_server 규약). origin 의 yaw 는 0 이라고 본다 —
// 0 이 아니면 그리지 않고 알린다(돌려 그리다 틀리느니).
import { fetchMap, fetchMapImage, fetchZones } from '../api.js';
import { el, replace } from '../dom.js';
import { ageText, speedBadge } from '../format.js';

/** P5(이진)·P2(글자) PGM 을 읽는다. 주석(#)을 건너뛴다. 8비트만. */
export function parsePGM(buf) {
  const b = new Uint8Array(buf);
  let i = 0;
  const token = () => {
    for (;;) {
      while (i < b.length && /\s/.test(String.fromCharCode(b[i]))) i += 1;
      if (b[i] === 0x23) { while (i < b.length && b[i] !== 0x0a) i += 1; continue; } // '#'
      break;
    }
    let t = '';
    while (i < b.length && !/\s/.test(String.fromCharCode(b[i]))) { t += String.fromCharCode(b[i]); i += 1; }
    return t;
  };
  const magic = token();
  const w = Number(token()); const h = Number(token()); const max = Number(token());
  if (!(w > 0 && h > 0 && max > 0 && max < 256)) throw new Error(`PGM 머리 이상 (${magic} ${w}x${h} max ${max})`);
  let data;
  if (magic === 'P5') {
    i += 1; // 머리 끝 공백 한 칸
    data = b.subarray(i, i + w * h);
    if (data.length < w * h) throw new Error('PGM 이 잘렸다');
  } else if (magic === 'P2') {
    data = new Uint8Array(w * h);
    for (let k = 0; k < w * h; k += 1) data[k] = Number(token());
  } else {
    throw new Error(`PGM 이 아니다 (${magic})`);
  }
  return { w, h, max, data };
}

/** map_server 의 trinary 판정: 0 빈칸 · 1 벽 · 2 모름. */
function classify(v, max, meta) {
  const p = meta.negate ? v / max : (max - v) / max;
  if (p > meta.occupiedThresh) return 1;
  if (p < meta.freeThresh) return 0;
  return 2;
}

const ZONE_NAME = { load: '창구', station: '스테이션' };
/** 구역 이름표. 서버 label(D1) → 도크 번호 → 이름 순. 지어내지 않는다 — 모르면 ID 그대로. */
function zoneText(z) {
  if (z.label) return z.label;
  if (z.kind === 'dock') return z.zoneId.replace(/^dock_/, '도크 ');
  return ZONE_NAME[z.kind] ? `${ZONE_NAME[z.kind]}` : z.zoneId;
}

function cssColors(node) {
  const cs = getComputedStyle(node);
  const v = (k, d) => (cs.getPropertyValue(k).trim() || d);
  return {
    free: v('--map-free', '#1b2330'), wall: v('--map-wall', '#8b97a8'), unknown: v('--map-unknown', '#0d1117'),
    bed: v('--map-bed', '#58a6ff'), dock: v('--map-dock', '#8b97a8'), load: v('--map-load', '#d29922'),
    robot: v('--map-robot', '#3fb950'), spare: v('--map-spare', '#a371f7'), dummy: v('--map-dummy', '#f2cc0c'),
    stale: v('--map-stale', '#7d8998'), target: v('--map-target', '#ff7ab6'),
    text: v('--map-text', '#e4e9f0'), halo: v('--map-halo', '#0d1117'), scan: v('--map-scan', '#ff4d6d'),
  };
}

function hexRGB(c) {
  const m = /^#([0-9a-f]{6})$/i.exec(c.trim());
  if (!m) return [128, 128, 128];
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/**
 * @param root     그릴 자리(높이는 CSS 가 정한다)
 * @param metaRoot 머리 오른쪽 한 줄(선택)
 * @param opts.onAvailable(bool)  지도를 받았는지 — 못 받으면 쓰는 쪽이 칸을 감춘다
 */
export function createFloorMap(root, metaRoot, { onAvailable } = {}) {
  const canvas = el('canvas', { class: 'fmap-canvas', role: 'img', 'aria-label': '병원 평면도' });
  const note = el('div', { class: 'fmap-note' });
  replace(root, [canvas, note]);

  let meta = null;        // fetchMap()
  let pgm = null;         // parsePGM()
  let zones = [];         // fetchZones().zones
  let crop = null;        // {c0, r0, c1, r1} 픽셀 범위 — 모르는 바깥을 잘라 낸다
  let base = null;        // 색칠한 지도 캔버스(팔레트가 바뀌면 다시)
  let baseKey = '';
  let last = { robots: [], target: null, fresh: true, charging: new Set() };
  // AMR 보간. 자세는 snapshot 으로 최대 5 Hz(간격 최대 0.42 s, api.md §1.6)라 그대로 그리면 뚝뚝 끊긴다.
  // 새 자세가 오면 지금 보이는 자리에서 그 자리까지 한 간격 동안 미끄러지게 그린다. 3 m 넘게 뛰면 보간하지 않는다
  // (리셋·순간이동을 미끄러지는 것처럼 보이면 거짓말이다). 보간은 **그리는 자리만** 바꾸고 값은 서버 것이다.
  const motion = new Map(); // robot_id -> {from:{x,y,yaw}, to:{x,y,yaw}, t0, span}
  let raf = 0;
  let failed = null;

  const toPx = (x, y) => [(x - meta.originX) / meta.resolution, meta.height - 1 - (y - meta.originY) / meta.resolution];

  function computeCrop() {
    let c0 = pgm.w; let r0 = pgm.h; let c1 = 0; let r1 = 0;
    for (let r = 0; r < pgm.h; r += 1) {
      for (let c = 0; c < pgm.w; c += 1) {
        if (classify(pgm.data[r * pgm.w + c], pgm.max, meta) !== 2) {
          if (c < c0) c0 = c; if (c > c1) c1 = c; if (r < r0) r0 = r; if (r > r1) r1 = r;
        }
      }
    }
    for (const z of zones) {
      const [c, r] = toPx(z.x, z.y);
      c0 = Math.min(c0, c); c1 = Math.max(c1, c); r0 = Math.min(r0, r); r1 = Math.max(r1, r);
    }
    const pad = 1.0 / meta.resolution; // 1 m
    if (c1 < c0) return { c0: 0, r0: 0, c1: pgm.w - 1, r1: pgm.h - 1 };
    return {
      c0: Math.max(0, Math.floor(c0 - pad)), r0: Math.max(0, Math.floor(r0 - pad)),
      c1: Math.min(pgm.w - 1, Math.ceil(c1 + pad)), r1: Math.min(pgm.h - 1, Math.ceil(r1 + pad)),
    };
  }

  function buildBase(col) {
    const key = `${col.free}|${col.wall}|${col.unknown}`;
    if (base && key === baseKey) return;
    const cv = document.createElement('canvas');
    cv.width = pgm.w; cv.height = pgm.h;
    const ctx = cv.getContext('2d');
    const img = ctx.createImageData(pgm.w, pgm.h);
    const pal = [hexRGB(col.free), hexRGB(col.wall), hexRGB(col.unknown)];
    for (let k = 0; k < pgm.w * pgm.h; k += 1) {
      const [r, g, bb] = pal[classify(pgm.data[k], pgm.max, meta)];
      img.data[k * 4] = r; img.data[k * 4 + 1] = g; img.data[k * 4 + 2] = bb; img.data[k * 4 + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    base = cv; baseKey = key;
  }

  async function load() {
    try {
      meta = await fetchMap();
      if (!(meta.resolution > 0)) throw new Error('resolution 이 없다');
      if (Math.abs(meta.originYaw) > 1e-6) throw new Error(`origin yaw ${meta.originYaw} — 돌아간 지도는 아직 못 그린다`);
      const [img, z] = await Promise.allSettled([fetchMapImage(meta.imageUrl), fetchZones()]);
      if (img.status !== 'fulfilled') throw new Error(`지도 그림을 못 받았다 (${img.reason && img.reason.message})`);
      pgm = parsePGM(img.value);
      // 메타와 그림 크기가 다르면 좌표가 어긋난다. 그림 크기를 믿는다.
      meta.width = pgm.w; meta.height = pgm.h;
      zones = z.status === 'fulfilled' ? z.value.zones : [];
      crop = computeCrop();
      if (onAvailable) onAvailable(true);
      draw();
    } catch (err) {
      failed = err && err.status === 404 ? '서버가 지도를 모릅니다' : `지도를 받지 못했습니다 — ${err.message}`;
      note.textContent = failed;
      if (onAvailable) onAvailable(false, err);
    }
  }

  function draw() {
    if (!pgm) return;
    const col = cssColors(root);
    buildBase(col);

    // 칸 안쪽 크기(padding 뺀 것)로 맞춘다. 그림이 칸을 키우면 안 된다.
    const cs = getComputedStyle(root);
    const cw = root.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
    const ch = root.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
    if (cw < 10 || ch < 10) return;
    const sw = crop.c1 - crop.c0 + 1; const sh = crop.r1 - crop.r0 + 1;
    const scale = Math.min(cw / sw, ch / sh);
    const w = Math.round(sw * scale); const h = Math.round(sh * scale);
    const dpr = window.devicePixelRatio || 1;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(base, crop.c0, crop.r0, sw, sh, 0, 0, w, h);

    // 월드(m) → 캔버스(px)
    const P = (x, y) => { const [c, r] = toPx(x, y); return [(c - crop.c0 + 0.5) * scale, (r - crop.r0 + 0.5) * scale]; };
    const m = scale / meta.resolution; // 1 m 가 몇 px
    const font = Math.max(10, Math.min(16, 0.55 * m));

    const label = (text, x, y, color) => {
      ctx.font = `700 ${font}px system-ui, "Noto Sans KR", sans-serif`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.lineWidth = 3; ctx.strokeStyle = col.halo; ctx.strokeText(text, x, y);
      ctx.fillStyle = color; ctx.fillText(text, x, y);
    };

    // 구역. 같은 자리의 구역(창구 load 와 dock_1 처럼)은 점 하나에 이름을 이어 적는다.
    const targetId = last.target;
    const spots = new Map();
    for (const z of zones) {
      const key = `${z.x.toFixed(2)},${z.y.toFixed(2)}`;
      if (!spots.has(key)) spots.set(key, []);
      spots.get(key).push(z);
    }
    for (const group of spots.values()) {
      const z = group.find((g) => g.zoneId === targetId) || group.find((g) => g.kind === 'bed') || group[0];
      const hit = group.some((g) => g.zoneId === targetId);
      const [x, y] = P(z.x, z.y);
      const color = z.kind === 'bed' ? col.bed : group.some((g) => g.kind === 'load') ? col.load : col.dock;
      const s = Math.max(6, 0.5 * m);
      ctx.fillStyle = color;
      ctx.globalAlpha = hit ? 1 : 0.8;
      if (z.kind === 'bed') ctx.fillRect(x - s / 2, y - s / 2, s, s);
      else { ctx.beginPath(); ctx.arc(x, y, s / 2, 0, Math.PI * 2); ctx.fill(); }
      ctx.globalAlpha = 1;
      // 좁으면(1 m 가 14 px 미만) 이름표가 겹친다. 목적지와 창구만 적고 나머지는 점만 둔다.
      const roomy = m >= 14;
      const names = group.filter((g) => roomy || g.zoneId === targetId || g.kind === 'load');
      if (names.length) label(names.map(zoneText).join('·'), x, y - s / 2 - font * 0.7, hit ? col.target : col.text);
    }

    // 목적지 — 고리. 로봇에서 점선.
    const target = targetId ? zones.find((z) => z.zoneId === targetId) : null;
    if (target) {
      const [tx, ty] = P(target.x, target.y);
      const pulse = 0.5 + 0.5 * Math.sin(performance.now() / 300);
      ctx.strokeStyle = col.target; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.arc(tx, ty, Math.max(10, 0.6 * m) + pulse * 4, 0, Math.PI * 2); ctx.stroke();
      // 목적지 점선은 주 AMR(주문을 싣는 차)에서만 긋는다. 여벌·더미는 주문이 없다.
      const main = last.robots.filter((r) => (r.kind || 'amr') === 'amr');
      const r0 = shownPose(main.find((r) => !r.stale) || main[0] || {});
      if (Number.isFinite(r0.x)) {
        const [rx, ry] = P(r0.x, r0.y);
        ctx.setLineDash([6, 5]); ctx.lineWidth = 2;
        ctx.beginPath(); ctx.moveTo(rx, ry); ctx.lineTo(tx, ty); ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    // 라이다 스캔(§1.8). map 좌표일 때만 찍는다 — lidar_link 좌표를 지도에 찍으면 거짓 위치다. 멎었으면 흐리게.
    const sc = last.scan;
    if (sc && sc.frame === 'map' && sc.points.length) {
      ctx.fillStyle = col.scan;
      ctx.globalAlpha = sc.stale ? 0.25 : 0.8;
      const d = Math.max(1.5, 0.06 * m);
      for (const [x0, y0] of sc.points) { const [x, y] = P(x0, y0); ctx.fillRect(x - d / 2, y - d / 2, d, d); }
      ctx.globalAlpha = 1;
    }

    // AMR
    for (const r0 of last.robots) {
      const r = shownPose(r0);
      const [x, y] = P(r.x, r.y);
      const rad = Math.max(7, 0.45 * m);
      // 주 AMR 초록, 여벌 AMR 보라, 더미 노랑(재범 결정 9/27). 멎었으면 회색.
      const color = r.stale || !last.fresh ? col.stale
        : r.kind === 'dummy' ? col.dummy : r.kind === 'spare_amr' ? col.spare : col.robot;
      ctx.fillStyle = color; ctx.strokeStyle = col.halo; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(x, y, rad, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      if (Number.isFinite(r.yaw)) {
        // 캔버스 y 는 아래로 자라므로 yaw 부호를 뒤집는다.
        ctx.strokeStyle = col.halo; ctx.lineWidth = 3;
        ctx.beginPath(); ctx.moveTo(x, y);
        ctx.lineTo(x + Math.cos(-r.yaw) * rad * 1.1, y + Math.sin(-r.yaw) * rad * 1.1); ctx.stroke();
      }
      label(`${r.robotId || 'AMR'}${last.charging && last.charging.has(r.robotId) ? ' ⚡' : ''}`, x, y + rad + font * 0.8, color);
    }
  }

  /** 매 render 마다 부른다. target 은 서버 goal_zone → trip.destination_id 순. */
  const lerpAngle = (a, b, k) => {
    let d = b - a;
    while (d > Math.PI) d -= 2 * Math.PI;
    while (d < -Math.PI) d += 2 * Math.PI;
    return a + d * k;
  };

  /** 지금 그릴 자세(보간 중이면 중간값). */
  function shownPose(r) {
    const m = motion.get(r.robotId);
    if (!m) return r;
    const k = Math.min(1, (performance.now() - m.t0) / m.span);
    if (k >= 1) return { ...r, x: m.to.x, y: m.to.y, yaw: m.to.yaw };
    return {
      ...r,
      x: m.from.x + (m.to.x - m.from.x) * k,
      y: m.from.y + (m.to.y - m.from.y) * k,
      yaw: Number.isFinite(m.from.yaw) && Number.isFinite(m.to.yaw) ? lerpAngle(m.from.yaw, m.to.yaw, k) : m.to.yaw,
    };
  }

  function track(robots) {
    const now = performance.now();
    for (const r of robots) {
      const m = motion.get(r.robotId);
      if (m && m.to.x === r.x && m.to.y === r.y && m.to.yaw === r.yaw) continue; // 같은 자세 — 새 값 아님
      const from = m ? shownPose(r) : r;
      const jump = Math.hypot(r.x - from.x, r.y - from.y) > 3;
      // 간격은 실제로 받은 간격을 따르되 0.1–0.45 s 로 묶는다.
      const span = m ? Math.min(450, Math.max(100, now - m.t0)) : 200;
      motion.set(r.robotId, { from: jump ? r : { x: from.x, y: from.y, yaw: from.yaw }, to: { x: r.x, y: r.y, yaw: r.yaw }, t0: now, span });
    }
    if (!raf) raf = requestAnimationFrame(tick);
  }

  function tick() {
    raf = 0;
    draw();
    const now = performance.now();
    const moving = [...motion.values()].some((m) => now - m.t0 < m.span);
    // 목적지 고리가 깜빡이므로 목적지가 있으면 계속 그린다. 둘 다 없으면 쉰다(render 가 250 ms 마다 부른다).
    if (moving || last.target) raf = requestAnimationFrame(tick);
  }

  function update(snap, fresh, charging = new Set()) {
    if (failed) return;
    const mainRobots = snap && snap.robots ? snap.robots : [];
    const robots = [...mainRobots, ...(snap && snap.dummies ? snap.dummies : [])];
    track(robots);
    const goal = robots.map((r) => r.goalZone).find(Boolean) || null;
    const trip = snap && snap.trip;
    last = { robots, target: goal || (trip && trip.destinationId) || null, fresh, charging, scan: snap ? snap.scan : null };

    if (metaRoot) {
      const r = mainRobots.find((x) => (x.kind || 'amr') === 'amr') || robots[0];
      const spares = mainRobots.filter((x) => x.kind === 'spare_amr').length;
      const dummies = robots.length - mainRobots.length;
      replace(metaRoot, [
        !snap ? null
          : !robots.length ? el('span', { class: 'fmap-meta-warn', text: 'AMR 위치 모름' })
          : r.stale ? el('span', { class: 'fmap-meta-warn', text: `위치 오래됨 ${ageText(r.ageWallS)}` })
          : el('span', { text: `위치 ${ageText(r.ageWallS)}` }),
        last.target ? el('span', { class: 'fmap-meta-target', text: `→ ${targetName(last.target)}` }) : null,
        ...(() => { const sb = snap ? speedBadge(snap.speedLimit) : null; return sb ? [el('span', { class: `fmap-speed is-${sb.tone}`, text: sb.text })] : []; })(),
        spares || dummies ? el('span', { class: 'fmap-meta-fleet', text: [spares ? `여벌 ${spares}` : null, dummies ? `더미 ${dummies}` : null].filter(Boolean).join(' · ') }) : null,
      ].filter(Boolean));
    }
    note.textContent = pgm && snap && !robots.length ? 'AMR 위치를 서버가 아직 주지 않습니다' : (failed || '');
    draw();
  }

  function targetName(id) {
    const z = zones.find((x) => x.zoneId === id);
    return z ? (z.label ? `${z.label} (${id})` : id) : id;
  }

  if (typeof ResizeObserver === 'function') new ResizeObserver(() => draw()).observe(root);
  load();
  return { update, reload: load };
}
