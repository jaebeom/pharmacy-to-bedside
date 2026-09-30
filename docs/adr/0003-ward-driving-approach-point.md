# ADR 0003 — 병동 주행: odom TF, Nav2 는 접근점까지, 마지막 구간은 직접 추종기, 회전은 접근점에서

- 상태: proposed
- 날짜: 2026-09-25
- 결정자: 재범. 골든-4 확정 #576 5801973227. "AMCL 대신 odom"·"Nav2 는 접근점까지"를 따로 정한 결정 댓글은 찾지 못했다(미확인)
- 승인 PR: 없음(이 ADR 의 PR 에서 검토)
- 관련 issue / RFC / evidence review: 이슈 #576(리하·결정 모음, PR 아님), PR #639(471df88), PR #645(49fc2f5), PR #649, [계약 v1 10.4](../architecture/delivery-contract-v1.md#104-gotozone-마지막-구간-정책-924)·[부록 A](../architecture/delivery-contract-v1.md#부록-a-병원-침상-정차접근점-여유-표-924), [병원 주행 L3 런북](../runbooks/hospital-nav-l3.md), [리하 08](../reha/reha-08.md)
- 대체 관계: 없음

## 맥락

- 병상 정차점은 고정물에서 0.05 m 안쪽이다. Nav2 footprint(1.10×0.90 m)로는 그 자리에 들어가는 경로가 없다(3408883, [런북](../runbooks/hospital-nav-l3.md) 109행).
- 어느 병상도 정차점에서 제자리 회전할 여유가 없다. 회전 반경 0.612 m 에 대해 여유가 −0.152·−0.101 m 다([부록 A](../architecture/delivery-contract-v1.md#부록-a-병원-침상-정차접근점-여유-표-924), 수치 #240 5801006935).
- 관측:
  - Nav2 끝까지: 회차2(5be029c) 0/6, 0.56 m 앞에서 멈췄다.
  - AMCL 오차: 회차2 에서 0.31 m, 회차3(d0d9e20) 에서 0.18 m 였다(0/6, "Failed to make progress"). AMCL 오차의 원인은 조사하지 않았다([런북](../runbooks/hospital-nav-l3.md) 136–149행).
  - 마지막 구간에서 회전: 138cbac ord-0005 bed_a3 에서 팔 받침이 D3 탁자에 57회 닿았다(리하 07).
  - 병상에서 Nav2 로 바로 떠나기: 50b658a bed_b1 에서 닿았다. 원인은 추정이다(d137b00 커밋 메시지).

## 대안

| 안 | 내용 | 한계·반증 |
| --- | --- | --- |
| A | Nav2 로 병상 정차점까지, AMCL 위치추정 | 위 회차2·3 에서 0/6. footprint 로 경로가 없다 |
| B | Nav2 는 접근점까지, 마지막 구간은 직접 추종기. 회전은 추종 중 아무 데서나 | 138cbac D3 접촉 57회 |
| C | **B + 회전은 여유 있는 접근점에서만, 정차까지는 방향 고정 옆걸음, 떠날 때도 옆걸음으로 접근점까지** | 옆걸음으로 복도 시간 +6 s(골든-3 72 s → 골든-4 78 s, 작성자 추정). 반증: 정차점에서도 회전 여유가 생기는 배치 |

## 결정과 이유

**C안.** 위치추정은 odom TF 다.

- 위치추정: `localization:=odom` 이면 AMCL 을 띄우지 않는다. map_server 는 남는다(`nav2.launch.py` 71·87–89행). 대신 `dock_origin_tf` 가 map→odom 을 도크 위치만큼 옮긴 정적 TF 로 낸다(3441321, `navigation.launch.py` 37·92–93행). 시뮬 전용 예외다(계약 451행, #514).
- Nav2 는 경로의 마지막 waypoint(`staging_point`)인 접근점까지만 간다. 목표 yaw 는 zone yaw 다(`fleet_node.py` 357–359행).
- 넘김: Nav2 가 접근점 0.5 m 안에 들면 cancel 하고 추종기가 받는다. 그 근처에서 abort 해도 받는다(`fleet_node.py` 392–393·581–586행, 3408883·9381c72).
- 회전: 추종기가 접근점에서 먼저 제자리 회전한다. 정차점까지는 yaw 를 고정한 채 옆으로 간다(`waypoint_follower.py` 179행 `turn_first`, #639). 접근점은 가장자리 여유로 다시 골랐다(9/24 접근점은 모두 ≥ 0.655 m).
- 떠날 때: 들어온 접근점까지 옆걸음으로 물러난 뒤 Nav2 로 넘긴다(`fleet_node.py` 348–355·412행 `_back_out`, #645).
- 넘김 속도: 추종기는 넘김 순간의 odom 속도에서 감속한다(#649, #240 5806153204).

근거 회차(#240 댓글 ID):

| 무엇 | 빌드 | 회차 | 결과 |
| --- | --- | --- | --- |
| 도착(#639) — 골든-4 | aca8840 | 5801268218(회차35 bed_a3)·5801363458(회차36 bed_a1)·5801972839(master02) | 셋 다 5/5 DELIVERED, 접촉 0, ArmRiser 0 |
| 떠남(#645) | 953ff5c | 5805153340(10건 4회차) | 베이스↔침상 탁자 접촉 0 |
| 넘김 속도(#649) | — | 5806153204 | 계약 10.4 |

골든-4(aca8840)는 #639 까지만 담는다. #645 는 그 위에 쌓였다. 그래서 떠남의 근거는 골든-4 가 아니라 953ff5c 회차다.

적용 환경: 병원 월드(`P3_WORLD=hospital`). `tools/demo_v2.sh` 376–378행이 `nav2_final_approach:=true localization:=odom` 을 넘긴다(`tests/test_demo_v2.py` 606행이 본다).

## 결과

- **코드 기본값은 아직 A 다.**
  - `fleet_node.py` 108행과 `navigation_params.yaml` 30행에서 `nav2_final_approach` 가 false 다.
  - launch 기본 `localization` 은 `amcl` 이다(`navigation.launch.py` 64행·`nav2.launch.py` 49행).
  - C 는 병원 기동 인자로만 켜진다. 다른 기동 경로에서 이 결정을 기대하면 안 된다.
- Nav2 목표에 zone yaw 가 실리므로 Nav2 도 접근점으로 가는 길에 돌 수 있다([런북](../runbooks/hospital-nav-l3.md) 109행).
- odom 모드에서는 `DockingState` 를 쓰지 않는다. AMCL 로 바꾸면 다시 정한다(재범 9/24, a951bb3. 댓글 ID 미확인).
- 발표 문구의 범위도 같다: Nav2 는 접근점까지, odom, AMCL 없음(9fd7023, #613).
- 재검토 조건: 실기·다른 지도에서 odom 누적 오차가 정차 허용(부록 A)을 넘을 때. 또는 AMCL 오차 원인이 풀릴 때.

## 롤백

- 병원 기동에서 `nav2_final_approach:=false localization:=amcl` 로 되돌리면 A 다. 코드 기본값이라 코드는 바꾸지 않는다.
- 영향: 병상 정차가 회차2·3 처럼 실패할 수 있다. 접근점 경로(`routes.hospital.yaml`)는 그대로 둬도 A 에 해가 없다.
