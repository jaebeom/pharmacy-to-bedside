// nav.js — 세 화면(간호사·개발자·설정)을 잇는 내비게이션.
// 서버를 가리키는 쿼리(api·ws·fixture·file)는 화면을 옮겨도 그대로 따라간다.
// `demo` 는 개발자 화면 전용이라 넘기지 않는다.
import { el, replace } from './dom.js';

export const PAGES = [
  { key: 'nurse',    href: 'nurse.html',    label: '간호사' },
  { key: 'dev',      href: 'index.html',    label: '개발자' },
  { key: 'settings', href: 'settings.html', label: '설정' },
];

const CARRY = ['api', 'ws', 'fixture', 'file'];

function carryQuery() {
  const now = new URLSearchParams(location.search);
  const out = new URLSearchParams();
  for (const k of CARRY) if (now.has(k)) out.set(k, now.get(k));
  const q = out.toString();
  return q ? `?${q}` : '';
}

/** `root` 에 링크 셋을 그린다. `active` 는 PAGES 의 key. */
export function renderNav(root, active) {
  if (!root) return;
  const q = carryQuery();
  root.setAttribute('aria-label', '화면');
  replace(root, PAGES.map((p) => el('a', {
    class: `nav-link${p.key === active ? ' is-active' : ''}`,
    href: p.href + q,
    'aria-current': p.key === active ? 'page' : null,
    text: p.label,
  })));
}
