# ADR — 결정 이력

바꾸기 비싼 결정의 맥락·대안·이유·결과·롤백을 짧게 남긴다.
일상 구현 선택은 PR 설명으로 충분하고, 기한이 있는 일정 결정은 [일정](../planning/schedule.md)에 둔다.

1. [템플릿](0000-template.md)을 복사해 NNNN-kebab-title.md를 만든다.
2. proposed로 검토한다. 결정자·승인 PR·근거를 채운 뒤 accepted로 바꾼다.
3. accepted의 결정 내용을 소급해 고치지 않는다. 새 ADR로 대체하고 이전 상태/링크만 연결한다.
4. rejected/superseded도 남긴다. RFC나 LLM 결론은 승인 이력이 아니다.

상태는 문서의 `상태` 줄과 같다. **재범 결정** 칸은 재범이 accepted·rejected 와 결정 댓글 링크를 채운다. 비어 있으면 결정 전이다.

| 번호 | 제목 | 상태 | 재범 결정 |
| --- | --- | --- | --- |
| [0001](0001-orchestrator-trip-fsm.md) | 트립 순서는 오케스트레이터의 명시적 FSM 이 민다 (BT 아님) | proposed | (결정 전. 9/17 스텁 한 바퀴 뒤 정하기로 했다) |
| [0002](0002-isaac-json-topics-and-ros-adapter.md) | Isaac 쪽은 `std_msgs/String` JSON 토픽, 계약 타입은 시스템 ROS 어댑터가 변환한다 | proposed | (결정 전. 9/17 부터 코드가 이 방식을 쓴다) |
| [0003](0003-ward-driving-approach-point.md) | 병동 주행: odom TF, Nav2 는 접근점까지, 마지막 구간은 직접 추종기, 회전은 접근점에서 | proposed | |
| [0004](0004-auth-pick-v0-truth-sensors.md) | 인증·집기 v0 는 참값 센서, 카메라는 v1 옵션 | proposed. [0007](0007-hospital-camera-qr-dock-at-load.md) 로 대체 예정 | |
| [0005](0005-deployment-single-master-default.md) | 배치: 단일 마스터가 기본, `P3_ROLES` 로 두 대 분리 | proposed | |
| [0006](0006-hospital-scene-and-performance-defaults.md) | 병원 씬 채택과 성능 기본값 | proposed | |
| [0007](0007-hospital-camera-qr-dock-at-load.md) | 병원 기본: 카메라 QR 로 집고 인증한다, 도크 = 적재 자리, M0609 레일 후보는 preferred_first | proposed | |

상태 칸은 각 ADR 의 `상태` 줄을 2026-09-30 에 다시 읽고 옮겼다. 일곱 모두 `proposed` 다. `accepted`·`superseded` 로 바뀐 ADR 은 없다.
0007 은 v1.1.0 코드 기본(#784·#790·#796·#797)을 적는다. 재범이 0007 을 accepted 로 바꾸면 0004 는 superseded 가 된다.

## 지금 코드와의 관계

기준은 main `f316197` = 태그 `v1.1.0` 이다. ADR 의 결정 내용은 고치지 않는다. 아래는 지금 코드가 그 결정과 같은지 다른지만 적는다.

| 번호 | 지금 코드 | 근거 |
| --- | --- | --- |
| 0001 | 같다. 트립 순서는 `trip_fsm.py` 의 FSM 이 민다 | `src/rokey_p3_orchestrator/rokey_p3_orchestrator/trip_fsm.py` |
| 0002 | 같다. Isaac 은 `/isaac/*` JSON 토픽을 내고 `isaac_adapter` 가 계약 타입으로 옮긴다 | `sim/standalone/p3sim/bridge.py`, `src/rokey_p3_bringup/rokey_p3_bringup/isaac_adapter.py` |
| 0003 | 같다. 병원 주행은 `localization:=odom nav2_final_approach:=true` 로 띄운다 | `tools/demo_v2.sh` 411–417행 |
| 0004 | **다르다.** v1.1.0 의 병원 기본은 카메라다. 봉투와 병상 인식표를 손 카메라 QR 로 읽는다. 참값 센서 집기는 `P3_CAMERA_POUCHES=0` 을 줄 때만이다 | 재범 9/29 "QR 반드시 찍고"(#784). 카메라 기본은 #784 가 넣었고 #797 이 탁자 정착 프로필로 묶었다. `tools/demo_v2.sh` 126·162행. 대체 ADR 은 [0007](0007-hospital-camera-qr-dock-at-load.md)(proposed)이다 |
| 0005 | 같다. 기본은 한 PC 다. `P3_ROLES`·`P3_PEER` 로 두 대로 나눈다. v1.1.0 에서 두 대 실행은 검증하지 않았다 | `tools/demo_v2.sh` 20–28·262–271행, #772 5891599172 |
| 0006 | 같다. 병원 preset 은 `render_every 2`·`VERIFIED_RAIL_DRIVE` 그대로다. v1.1.0 은 컨베이어 2배(#789)·도크 벽 불투명도 0.35(#792)를 더했다 | `sim/standalone/pharmacy_stage.py` 201–216행, [스테이지 인자·기본값](../architecture/stage-arguments.md) |
| 0007 | 같다. 이 ADR 이 v1.1.0 코드 기본을 적는다 | `tools/demo_v2.sh` 124–183·207·406행 |

ADR 후보: 인계(하역) 모델 선택, 교차로 점유 정책(AMR 2대 채택 시). 각각 결과가 나온 뒤 쓴다.
에이전트 역할 분리와 증거 기록 방식은 사용자 요청으로 도입한 작업 규칙이며
[에이전트 역할](../process/agent-workflow.md)과 [증거 저장](../../evidence/README.md)이 기준 문서다.
