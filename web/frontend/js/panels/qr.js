// QR 판독(§1.12): 손 카메라가 읽은 QR 과 그 안 ID 를 주문 풀·약 카탈로그로 푼 요약. 재범 9/29.
// 판독은 "주문과 맞았다"는 뜻이 아니다 — 맞았는지는 트립 칸의 칩(✓ 약 QR·✓ 확인·✓ 약 매칭)이 말한다.
import { el, replace } from '../dom.js';
import { ageText, QR_KIND_KO, qrRobotText, qrSummary } from '../format.js';

export function renderQrReads(store, root, metaRoot, fresh, bedLabel) {
  const reads = (store.snapshot && store.snapshot.qrReads) || [];
  replace(metaRoot, reads.length ? [el('span', { text: `${reads.length}건` })] : []);
  if (!reads.length) {
    return replace(root, [el('div', { class: 'qr-empty', text: '이번 세대에 읽은 QR 이 아직 없습니다.' })]);
  }
  replace(root, reads.map((r) => el('div', { class: `qr-row qr-${r.kind}`, title: `${r.tagId} · ${r.count}회 · sim ${r.stamp}` }, [
    el('span', { class: 'qr-kind', text: QR_KIND_KO[r.kind] || r.kind }),
    el('span', { class: 'qr-id', text: r.tagId }),
    el('span', { class: 'qr-sum', text: qrSummary(r, bedLabel) }),
    el('span', { class: 'qr-cam', text: qrRobotText(r.robot) }),
    el('span', { class: 'qr-age', text: fresh ? ageText(r.ageWallS) : '—' }),
  ])));
}
