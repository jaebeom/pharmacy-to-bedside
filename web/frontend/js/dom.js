// dom.js — 아주 작은 DOM 헬퍼. 텍스트는 전부 textContent 로 넣어 서버 문자열을 그대로 신뢰하지 않는다.

/**
 * el('div', {class:'x', title:'t'}, [child, 'text'])
 */
export function el(tag, props = null, children = null) {
  const node = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = String(v);
      else if (k === 'dataset') Object.assign(node.dataset, v);
      else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2).toLowerCase(), v);
      else node.setAttribute(k, v === true ? '' : String(v));
    }
  }
  if (children != null) {
    for (const c of Array.isArray(children) ? children : [children]) {
      if (c === null || c === undefined || c === false) continue;
      node.appendChild(typeof c === 'object' && c.nodeType ? c : document.createTextNode(String(c)));
    }
  }
  return node;
}

/** 자식을 한 번에 갈아 끼운다. */
export function replace(container, nodes) {
  container.replaceChildren(...(Array.isArray(nodes) ? nodes : [nodes]).filter(Boolean));
}

export function emptyNote(text) {
  return el('div', { class: 'empty', text });
}
