// prefs.js — 이 브라우저에만 남는 화면 취향(밝기·글자 크기·처음 화면).
// 서버 상태가 아니다. 못 읽거나 못 써도(사생활 보호 창 등) 기본값으로 그대로 돈다.
const KEY = 'p3.prefs.v1';

export const DEFAULTS = { theme: 'light', size: 'normal' };

export function loadPrefs() {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || '{}');
    return { ...DEFAULTS, ...(v && typeof v === 'object' ? v : {}) };
  } catch {
    return { ...DEFAULTS };
  }
}

export function savePrefs(p) {
  try { localStorage.setItem(KEY, JSON.stringify(p)); return true; } catch { return false; }
}

/** 간호사·설정 화면에 적용한다. 개발자 화면은 자기 배치(1920·960 시연)를 지키므로 적용하지 않는다. */
export function applyPrefs(p = loadPrefs()) {
  const root = document.documentElement;
  root.dataset.theme = p.theme === 'dark' ? 'dark' : 'light';
  root.dataset.size = p.size === 'large' ? 'large' : 'normal';
}
