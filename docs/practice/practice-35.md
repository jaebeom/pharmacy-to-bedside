# 실습35 — 병원 통합 전 잘못된 별도 파지 루틴과 AMR 교정

2026-09-22 master02, 임재범 요청. 기준 main `2ba1bdd` (#488 포함).

**미완료. 이 회차는 기존 실습 알고리즘의 병원 통합 검증이 아니다.**
임재범은 실습30/31에서 사용한 알고리즘과 AMR 합본을 최신 병원 씬에서 실행하고,
선반을 무작위 선정해 알약 파지를 3회 하도록 요청했다. 기존 ROS 계획/제어 경로 대신
별도 Lula IK·마찰 파지 루틴을 만들어 실행한 것은 요청과 다른 구현이었다.
임재범이 팔 비틀림·속도 차이를 지적했고, 이 루틴은 후속 통합 경로로 채택하지 않는다.

## 실제 관측

- 난수 시드 `835258728`, 중복 없이 선반 `74 → 75 → 69` 선정.
- 물리 접촉/약통 자세를 기록했지만 세 회 모두 `motion_target_unreached`: 0/3 성공.
- 사용한 임시 속도는 관절 0.45 rad/s, 레일 0.5 m/s, TCP 0.08 m/s였다.
  기존 `m0609_arm_node.py`의 관절별 80% 상한, 레일/TCP 0.8 m/s, 가감속 경로와 다르다.
- 기존 실습은 `scene_v2`의 다중 시드 IK·여유 평가·접힘 경유와 실제 ROS 노드 명령,
  시뮬레이터의 거리 기반 부착을 사용한다. 이 별도 회차의 마찰 파지를 그 실습과 비교할 수 없다.
- 3회 종료 후 Isaac 물리는 pause 상태다. 자동 재시도하지 않았다.
- PhysX material face-index 경고가 발생했다. 실패 회차의 원본 로그를 보존한다.

## AMR 교정

병원 저작 씬은 팔이 몸체 중앙에 있고 기존 실습의 받침·트레이 조립이 빠져 있었다.
`workcell_preview.build_practice_amr`가 실제 `amr_base.reference`, `move_arm_mount`,
`build_arm_base_frame`, `build_tray_on_base`를 호출하도록 추가했다.

- 실습31과 동일한 `ridgeback_ur5.usd` SHA-256:
  `908061d3b9627baa5bb6880acfa8b341d5b322d31e016f639f1fff2e40f85f3e`.
- 팔 이동 `(-0.35, 0, +0.15)` m, 받침 0.30×0.30×0.129 m.
- 트레이 안치수 0.60×0.64 m, 턱 0.03 m, 놓는 자리 3개.
- 병원 원래 AMR의 XY `(1.995591579, 1.999799265)`를 유지하고 기존 프림은 비활성화.
- 자산/조립 교정 완료. 병원 내 AMR 주행·적재·배송 검증은 **미실행**.

## 원본 및 후속

외부 원본은 `/home/rokey/markle_tmp/m2-hospital-pick3-01/`의
`plan.json`, `events.jsonl`, `summary.json`, `trial.mkv`, `ready.png`에 있다.
AMR 교정 근거는 `/home/rokey/markle_tmp/m2-pr484-test/amr-before.json`,
`amr-corrected.json`; 통합 뷰어 로그는 같은 폴더의 `viewer-r3.log`다.

현재 브랜치의 `shelf_pick_trial.py`는 이 실패를 재현하는 중간 작업본이며 통합 완료 코드가 아니다.
기존 알고리즘의 노드·재고·좌표 어댑터를 연결하는 후속 구현이 필요하다.

## Git 보존 점검

원본 위치·크기·전체 해시는 [외부 원본 목록](../analysis/hospital-integration-artifacts.json)에 기록했다.
임시 스크립트 35개의 원문은 [소스 스냅샷](../analysis/hospital-integration-source-snapshot.md),
해시는 [소스 목록](../analysis/hospital-integration-source-manifest.json)에 보존했다.
로컬에만 남았던 실습31 기록도 이 브랜치에 함께 반영했다.

중간 작업본 검사: 저장소 188개 OK, sim 648개 OK(13 skipped), repository/evidence 검사와 Ruff PASS.
이 정적 검사는 실패한 파지 0/3을 성공으로 바꾸지 않는다.
