# 미결 설계 결정표 (9/24) — G6

- 근거: `docs/analysis/2026-09-24-design-gap-plan.md` G6. **재범 결정 9/24 13:30 "미결 권고대로 진행"**(#576 댓글).
- 이 표는 결정 기록이다. 반영은 담당 문서 PR 에서 하며, 반영 전에는 각 문서의 옛 표식이 남아 있을 수 있다.

| # | 항목 | 있던 곳 | 현황(관측) | 결정 | 반영 담당 |
| --- | --- | --- | --- | --- | --- |
| 1 | 결정 28 상판 칸 번호 매김 | delivery-contract §3 | 코드는 `slots_in_world` 캐시 순서로 동작 | **확정** — 현재 구현 번호를 §3 에 기록 | `sim/`(#657 계열) |
| 2 | 결정 44 K5 UR5 인증·전달 v0 | k5-delivery-interface | proposed, `--mode ros` UR5 미실행 | **확정** — v0 = 참값 인증(ScanTag/CabinetObservation), 카메라 인증은 v1 옵션 | 비전(#654 계열) |
| 3 | DockingState `amcl_max_age_s` 기본 0(늘 UNKNOWN) | delivery-contract-v1-status | 병원은 odom 모드 | **미사용 명시** — odom 모드에서 미사용, AMCL 전환 시 재결정 | `sim/` |
| 4 | POUCH_LOST·BELT_AT_END_TIMEOUT 이벤트 | delivery-contract-v1-status | "확정 전에는 내지 않는다" | **보류** — 관측 이벤트로만, v2 뒤 | 백엔드(G1-B) |
| 5 | 웹 도메인 118 | web-console | 실제 131/141(P3_DOMAIN) | **확정** — 118 삭제, 런북 P3_DOMAIN 값으로 | 백엔드(G1-B) |
| 6 | 이력 저장소 | web-console "미결정" | 메모리에만 | **확정(한계 명시)** — 발표 범위에선 메모리, 영속화는 후속 | 백엔드(G1-B) |
| 7 | 트립 시한 | ADR 0001 180 s 미해결 / FSM 600 sim s / 도구 900 wall s×정거장 | 두 시계 혼재 | **확정** — FSM 600 sim s 유지, 도구 wall 은 관측 한도로 구분(대체 아님) | 백엔드(G1-B §7) |
| 8 | 자산 일반 공개 여부 | G7 | 비공개 첨부로 G8 충족(#651) | **보류** — 발표 뒤 | 재범 |

미실행: 이 문서는 결정 기록이며 코드·회차를 바꾸지 않는다.
