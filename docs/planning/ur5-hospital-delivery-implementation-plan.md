# UR5 약포지 피킹·병원 배송 구현 계획 및 원안 검토

- 작성: 2026-09-19. 상태: **proposed — 구현 착수용 검토안**.
- 검토 기준: `main` `462b143eb38c0faccd3ede63df7878dfe4371517`. 코드 정적 검토이며 Isaac 실행·실측은 하지 않았다.
- 입력: 사용자가 제공한 「P3 조제실 컨베이어 약포지 피킹 및 병원 계층 자율배송 구현 명세서 v1.0.0」.
- 우선순위: [확정 시나리오](scenario.md) → [배송 계약 v1](../architecture/delivery-contract-v1.md) → 이 제안.
- 개정: 목적지 결합·물품 위치 상태·제어권 전환을 재검토했다. [재검토 보고서와 설계 이미지](../analysis/2026-09-19-ur5-delivery-code-review.md)의 R1–R9와 T01–T10을 함께 적용한다.
- 이 PR은 계획·검토 문서와 설계 이미지만 추가한다. 계약 채택, 코드 구현, 배포, L3 합격을 뜻하지 않는다.

![명령·운영 관측·독립 평가 구조](../images/ur5-delivery/architecture.svg)

목표 구조다. 기존 모듈과 추가할 guard를 구분했으며 구현 완료를 나타내지 않는다. 인계·제어권·구현 순서 이미지와 상세 전이는 재검토 보고서에 있다.

## 1. 결론과 구현 범위

목표는 **웹 주문 → 조제실 밖 컨베이어 끝에서 UR5 피킹 → AMR 상판의 지정 칸 적재 → 목적지 인증 → 상판에서 재파지 → 목적지 보관함 안착 → 복귀**다.
원안의 피킹·계층 주행 구분은 채택하되, 기존 ROS 패키지·액션·FSM을 확장한다.
`p3_hospital_delivery`라는 별도 총괄 패키지나 두 번째 주문 FSM은 만들지 않는다.

첫 구현 대상은 **AMR 1대, 동일 층, 약포지 1개, 지정 병상 1곳**이다.
이후 상판 N칸, 병실 내 침상 순회, 병동 스테이션 배송으로 넓힌다. 승강기·다중 AMR 교착 제어·실제 배터리 모델은 별도 범위다.
약품 카세트를 다루는 M0609 외축 보충과 이 UR5 배송은 다른 작업이다.
특히 manipulation의 `pick_plan.py`는 현재 M0609 rail v2 코드이므로 UR5 계획기로 그대로 호출하지 않는다.

### 원안 판단

| 원안 | 판단 | 적용 방향과 이유 |
| --- | --- | --- |
| ROS 2 Humble / Gazebo Classic 또는 Ignition | 변경 | 현행 Ubuntu 24.04 / ROS 2 Jazzy / Isaac Sim 5.1 유지. 시뮬레이터 교체는 별도 프로젝트 |
| 임의 차동·메카넘 베이스, UR5 또는 UR5e | 변경 | 현재 Ridgeback_UR5 자산과 dummy x/y/yaw 주행 모델부터 확정. UR5e 관절·TCP·기구학을 동일하다고 가정하지 않음 |
| 새 JSON 주문·상태 토픽, 마스터 FSM | 대체 | 기존 웹 API, `Deliver`, `trip_fsm.py`, 상태·이벤트 사용 |
| 컨베이어 정지 후 위에서 흡착 | 채택·보완 | 벨트 실제 정지, 주문 QR 일치, 유효한 인지 좌표와 TF, 접촉·흡착 확인이 선행 |
| 일반 바스켓에 0.15 m 높이에서 투하 | 변경 | 주문별 지정 상판 칸에 지지면까지 내려놓고 해제·안착 확인. 재파지 가능성도 검증 |
| 병동·병실 도착 시 즉시 완료 | 거절 | 병동은 스테이션 보관함, 병실은 각 침상 인증·인계까지 완료해야 함 |
| 병상에서 inspect pose·알림 후 완료 | 거절 | 환자 QR 확인 → 해당 약포지 재검증 → 상판 재파지 → 보관함 안착까지 구현 |
| 고정 관절값·질량·마찰·도킹 공차 | 검증 전 보류 | 예시값이며 현장값이 아님. 자산·접촉·시야·도달성 측정 후 버전 관리 |
| 문 앞에서 inflation 0.55→0.35 m | 거절 | 실제 footprint와 통과 여유를 먼저 검증. cost 감소로 물리적 통과 가능성을 만들 수 없음 |
| 실패하면 costmap 초기화·90도 회전·1 m 후퇴 | 거절 | 장애물 관측과 회전·후진 공간이 확인된 제한적 복구만 허용 |
| 흡착 실패 시 무조건 1 cm 하강·벨트 역구동 | 거절 | 재검출·접촉 한계·후퇴 가능성을 확인. 겹침·끼임을 유발하는 맹목적 재시도 금지 |
| 10회 성공 = 성공률 100% 달성 | 변경 | 10/10은 해당 조건의 smoke 결과. 신뢰도·최종 acceptance는 별도 사전 protocol로 판정 |

Isaac 5.1은 Jazzy 설치 경로를 제공한다([공식 설치 안내](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_ros.html)).
Gazebo Classic은 2025년 1월 지원 종료를 안내한다([공식 공지](https://classic.gazebosim.org/)). 이 계획에서 새 의존성으로 도입하지 않는다.

## 2. 현재 구현과 실제 공백

아래의 “있음”은 파일·로직 존재 확인이다. 모바일 장면에서의 통합 성공을 의미하지 않는다.

| 영역 / 확인한 코드 | 현재 상태 | 다음 구현에서 메울 공백 |
| --- | --- | --- |
| [웹 API](../../web/api.md), [trip_fsm.py](../../src/rokey_p3_orchestrator/rokey_p3_orchestrator/trip_fsm.py) | `/api/requests`, 4가지 배송 모드, 정거장 구성·액션·종료 처리 있음 | 계층 경유점과 기존 인계 정거장 연결, 잘못된 계층·중복 주문 거부 검증 |
| [arm_node.py](../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py), [UR5 기구학](../../src/rokey_p3_manipulation/rokey_p3_manipulation/ur5_kinematics.py) | `PickPouch` 양방향 골격, IK와 관절 보간, 파지 heartbeat 수신 있음 | goal에 목적지 zone이 없어 고정 cabinet_frame 사용. 목적지/원본 칸 결합, 실측 종단·충돌 검증, 연속 파지 감시, 해제·안착 관측. 현재 해제 후 시간 대기로 `POUCH_LOADED/PLACED` 발행 |
| [ur5_cell.py](../../sim/standalone/p3sim/ur5_cell.py) | 고정 받침 UR5 셀·자체 동작 코드 있음 | 이동 베이스에 종속된 articulation·TCP·센서·상판과 ROS 명령 경로의 통합 검증 |
| [pouch_detector_node.py](../../src/rokey_p3_perception/rokey_p3_perception/pouch_detector_node.py), [pouch_geometry.py](../../src/rokey_p3_perception/rokey_p3_perception/pouch_geometry.py) | RGB·CameraInfo, QR/검출, 설정 폭·거리 기반 위치 추정 | 실제 깊이 또는 보정한 지지 평면, 가림·반사·잘못된 깊이 거부, 이동 후 재검출 |
| [fleet_node.py](../../src/rokey_p3_navigation/rokey_p3_navigation/fleet_node.py), [base_driver_node.py](../../src/rokey_p3_navigation/rokey_p3_navigation/base_driver_node.py) | `GoToZone`→Nav2, 수락 시 홈 확인, 도착 후 정착 확인, base_driver watchdog | 실행 중 permit/홈 소실·RESET_BEGIN guard, 실제 map·계층 경로, 종단 정렬, loaded 속도와 footprint 검증 |
| [zones.yaml](../../src/rokey_p3_description/config/zones.yaml), [maps](../../src/rokey_p3_navigation/config/maps/README.md) | zones의 위치·공차 모두 미측정 0, map 준비 안내만 있음 | 활성 장면에서 좌표·지도 추출, 공차 측정. 0 공차를 정상 설정으로 실행하면 안 됨 |
| [nav2_params.yaml](../../src/rokey_p3_navigation/config/nav2_params.yaml) | 원형 반경 0.6 m, inflation 0.7 m, goal checker 0.25 m / 0.25 rad | 적재한 전체 형상 및 작업 도킹 공차와 일치시키기 |
| [Isaac adapter](../../src/rokey_p3_bringup/rokey_p3_bringup/isaac_adapter.py), [ADR 0002](../adr/0002-isaac-json-topics-and-ros-adapter.md) | Isaac JSON ↔ 시스템 ROS 타입 변환 코드 존재 | 신규 관측의 버전·epoch·명령 상관관계 추가 시 양쪽과 stub 동시 갱신. ADR의 승인 상태는 별도 확인 |

## 3. 유지할 인터페이스와 제안할 변경

### 기존 경로를 재사용

| 입력/작업 | 사용할 경계 | 소유권 |
| --- | --- | --- |
| 주문 접수·진행 표시 | `POST /api/requests`, snapshot/events, `Deliver(DeliveryRequest)` | 웹은 변환·표시, orchestrator만 트립·주문 상태 변경 |
| 배출·벨트 | `/pharmacy/dispense`, `/pharmacy/belt` | orchestrator가 요청, Isaac이 실제 상태 발행 |
| 검출·인증 | `PouchDetectionArray`, `TagRead`, `ScanTag` | perception 관측, arm/오케스트레이터가 작업별 검증 |
| 벨트→상판 | `PickPouch(order_id, SOURCE_BELT, target_slot >= 0)` | arm이 실행과 국소 인터록 담당 |
| 상판→보관함 | `PickPouch(order_id, SOURCE_DECK, target_slot = -1)` | 목적지 인증 후 arm 실행 |
| 주행 | `/amr_1/go_to_zone`의 `GoToZone` → fleet → Nav2 | fleet만 Nav2 goal 소유; 웹·arm이 직접 goal을 보내지 않음 |
| 관절·흡착·정지 | 계약의 robot namespace별 command, holding, at_home, base/stopped | 실행 주체가 자신의 명령·관측만 관리 |
| 성공 평가 | `/evaluator/cabinet` → event_logger | 운영 노드 구독 금지. simulator의 독립 관측으로 평가 |

정확한 필드·QoS·이벤트 발행자는 [계약 §2–§4](../architecture/delivery-contract-v1.md)를 따른다.
입력 주문의 `request_id`, `order_id`, `patient_id`, `destination_id`를 끝까지 보존한다.
`dispense_trigger=true` 같은 외부 입력으로 벨트 점유·도킹·재고 guard를 건너뛰지 않는다.
배터리 센서가 없으면 가짜 잔량을 발행하지 않는다.

### PR-A에서 먼저 확정할 계약 차이

기존 Bool heartbeat만으로는 소스 시각·epoch·명령 확인을 표현할 수 없고, PickPouch에는 목적지 zone과 원본 상판 칸이 없다.
[재검토 §3](../analysis/2026-09-19-ur5-delivery-code-review.md#3-액션관측의-구체적인-변경안)의 선택안을 적용한다. 액션 이름·소유자는 유지하지만 ROS 필드 확장은 wire 호환이 아니므로 모든 client/server/stub을 일괄 빌드·배포한다.
아래는 **새 인터페이스 제안**이며 현재 메시지에 이미 있는 필드가 아니다.

| 제안 | 최소 데이터 / 규칙 | 호환성 작업 |
| --- | --- | --- |
| 목적지·인증 결합 | PickPouch에 request/epoch/operation, source_slot, destination_zone_id/cabinet_slot, auth_seq, scene_revision 추가 | 기본값으로 목적지를 추정하지 않음. arm과 orchestrator가 같은 작업 문맥을 확인 |
| 흡착 command/관측 보강 | 양쪽 epoch/operation/command_seq, 관측 stamp/seq와 last_applied_command_seq, 실제 상태 | command ACK와 HELD 구분. 신규 타입·JSON 버전·adapter·stub 동시 변경; Bool fallback으로 물리 경로 허가 금지 |
| MotionPermit | orchestrator가 HOLD/ARM/DRIVE와 epoch/generation을 발행; 실행기 수신 TTL·연속 guard | 모드 사이 실제 정지 확인, RESET_BEGIN 즉시 fence. 별도 총괄 FSM을 만들지 않음 |
| 운영용 상판·안착 관측 | slot, 관측된 주문 식별자, occupied, stamp, confidence. 인지로 확인 불가능하면 unknown | 카메라/슬롯 센서 기반. 평가용 cabinet ground truth 재사용 금지 |
| 물품 위치·안착 결과 | custody(SOURCE/GRIPPER/TARGET/UNKNOWN), observation_seq와 placement_unconfirmed/feedback_lost/motion_fault 제안 | UNKNOWN은 PAUSED_RECONCILE. 재시도·HOLD_RETURN 자동 변환 금지. arm·FSM·stub·웹 동시 변경 |
| 계층 경유점 실행 | `GoToZone` 최종 정거장 전에 fleet가 내부 경유 경로를 실행 | 외부 action 유지가 우선. 종단 도착 판정과 중간 경유 통과 판정 분리 |

`DELIVERED`는 운영 상태, 평가 `SUCCESS`는 독립 보관함 관측이다.
현행 `Deliver.success`는 모든 주문이 DELIVERED이고 도크 복귀까지 되었는지를 나타내므로, 도착 알림이나 팔 전개 성공으로 바꾸지 않는다.

## 4. 장면·좌표·인지 준비

빈월드·세준 병원 씬의 구체적 이식 순서와 USD 앵커/지도/토폴로지 산출 설계는 [4단계 통합 계획](mock-hospital-world-integration-plan.md)에 둔다. 이 문서의 A–G와 같은 계약·산출물을 사용하며 별도 구현 사슬을 만들지 않는다.

1. **자산 고정:** USD/URDF 경로·해시, 실제 UR5/UR5e 종류, 관절 이름/한계/축 방향, base→arm→TCP, 상판 칸·카메라 변환을 manifest로 남긴다. FK와 USD TCP를 여러 자세에서 대조한다.
2. **이동 장착 검증:** 베이스 x/y/yaw를 바꾸면 팔·센서·상판이 같은 강체 기준을 따르는지 확인한다. 고정 셀의 world anchor를 그대로 둔 채 베이스만 움직이지 않는다.
3. **map 추출:** #215의 병원 하위 배치·역변환과 비활성 prim을 반영한 최종 합성 장면에서 지도와 zones를 만든다. 원본 병원 USD 좌표를 무변환으로 복사하지 않는다.
4. **TF 소유권:** `map→odom`은 localization, `odom→base_link`는 base_driver, 로봇 내부는 계약의 Isaac 경로, zone 고정 프레임은 zones_tf가 한 번만 발행한다. 이동 상판을 world 고정 프레임으로 발행하지 않는다.
5. **검출 좌표:** 이미지 시각의 CameraInfo·TF와 정렬된 깊이를 사용한다. 깊이가 없으면 보정된 벨트/상판/보관함 지지 평면과 광선 교차를 별도 검증한다. 일정 깊이를 모든 위치에 적용하지 않는다.
6. **유효성:** NaN/Inf, 영 깊이, 미래/과거 관측, 불명 QR, 겹친 대상, 평면 밖 좌표, 낮은 신뢰도는 실행 거부. ROS quaternion xyzw와 USD 경계의 순서·m/rad를 명시적으로 변환한다.
7. **재관측:** 벨트 정지 후와 AMR 이동 후에는 새 좌표를 얻는다. 과거 camera pose를 최신 TF에 섞지 않는다. 카메라 손목 장착 시 촬영 자세도 충돌·시야 검증 대상이다.

원안의 봉투 0.12×0.08×0.015 m / 0.05 kg, 마찰 0.8, 바스켓 치수는 자산 후보값으로만 보관한다.
초기 rigid-body 약포지는 변형·주름·흡착 누설을 재현하지 않는다.
Isaac Surface Gripper는 attachment용 D6 joint를 관리한다([5.1 API](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/py/api/classisaacsim_1_1robot_1_1surface__gripper_1_1_surface_gripper_component.html)).
이를 실물 진공 압력 모델로 표현하지 않는다. 강제 pose 추종/가상 attach 시험은 배선 시험으로 표시하고 물리 피킹 합격 집계에서 분리한다.

## 5. 실행 순서와 인터록

| 단계 | 실행 | 다음 단계 허용 조건 |
| --- | --- | --- |
| 준비·접수 | 유효한 지도/자산/설정, clock·TF·관측 초기화; 중복 요청 검사 | 초기 UNKNOWN을 false로 위조하지 않고 필요한 초기 관측을 시한 내 확보 |
| 조제실 이동 | 팔 수납 확인 후 `GoToZone(load)`; AMR은 조제실 밖 대기 | Nav2 결과 + 작업 공차 + 실제 정지 유지, fresh 상태 |
| 배출·정지 | 빈 벨트·재고·배정 주문 확인 후 Dispense; 끝 센서로 정지 | at_end, belt order 일치와 실제 정지. SetBool 응답만으로 정지 확정 금지 |
| 벨트 피킹 | 새 검출·QR 확인 → 상면 법선 정렬 → 사전 접근 → 제한된 접촉 → 흡착 | 명령 이후의 fresh HELD 확인. 이후 lift/transfer 전체에서 파지 감시 |
| 상판 적재 | 칸 예약 → 충돌 없는 이송 → 지지면에 내려놓기 → 해제 | 실제 해제와 칸 안착/주문 일치 확인 후 `POUCH_LOADED`. 이후 후퇴·홈 실측 |
| 병원 이송 | 적재 확인·팔 홈 확인 후 계층 경로 실행 | 팔/상판/적재물 전체 형상, 적재 속도·가속도 제한, 국소 watchdog 유지 |
| 목적지 인계 | 최종 정렬 → 환자/스테이션 QR → 해당 상판 칸 재검출·약포지 QR → PickPouch(DECK,-1) | QR 일치와 새 pose; 보관함 해제·안착 확인 후 `POUCH_PLACED` |
| 복귀·보고 | 홈 확인 → 도크 복귀 → 트립 결과; 평가기는 독립 판정 | 도착·검사 자세·알림을 인계 완료로 사용하지 않음 |

### 팔 경로

- 임의 관절 배열을 복사하지 않는다. 자산에 맞는 홈·촬영·접근·회피 자세를 FK/IK·충돌·카메라 시야로 선정한다.
- B가 보정한 capsule/box geometry를 제공하고 C의 신규 `ur5_path_validator.py`가 FK와 보수적 형상 거리로 기존 IK+관절 경로를 검증한다. 자기 충돌, 베이스/기둥, 벨트, 상판 칸, 보관함, cup와 파지물의 swept volume을 포함한다.
- 첫 범위는 정지한 베이스에서 검증된 이송 회랑과 Cartesian 접근/인출이다. 회랑으로 해결되지 않으면 MoveIt 등 충돌 계획기 도입을 별도 ADR로 비교한다. 검증되지 않은 관절 직선 보간을 우회 경로로 쓰지 않는다. 샘플 간 최대 링크/파지물 이동과 오차 예산으로 여유를 검사하며 상한을 만들 수 없으면 reject한다.
- 접근·인출은 TCP 방향과 물품 자세를 제한한다. J4–J6 값을 고정하는 것은 TCP orientation constraint와 동치가 아니다.
- IK 연속성·관절 한계·특이점 여유와 속도/가속도 제한을 확인한다. 부하 이송 자세와 빈손 수납 자세를 분리하되, AMR 주행은 봉투를 상판에 놓고 팔을 수납한 뒤에만 한다.
- 중간 경유점은 검증된 연속 궤적으로 연결한다. 접촉·흡착·해제·베이스/팔 제어권 전환에는 정착 확인이 필요하다. 모든 내부 waypoint에 고정 0.2 s 대기를 붙이지 않는다.
- 현행 `move_to`의 명령 점 발행 완료를 실측 도달로 보지 않는다. 종단 정착 후 ARM_HOME을 발행하고, `_execute_pick` finally의 무조건 홈 복귀를 custody 기반 허가로 바꾼다. 놓기 후 후퇴 실패를 무조건 직선 홈 복귀로 덮지 않는다. 물품·팔 위치가 확인된 검증 경로만 복구에 사용한다.

### 피드백·시간·실패

- `holding`은 grip 명령 때만 갱신하지 않고 실제 관측 heartbeat로 갱신한다. 최초 미수신·오래된 값은 UNKNOWN이다. 명령 echo, sleep 경과, 이전 epoch의 true는 파지 증거가 아니다.
- freshness/watchdog/cancel drain은 monotonic wall time, 이미지·TF는 sim time+epoch로 처리한다. 기존 액션의 sim deadline과 clock-stall guard는 유지하고 서로 다른 시계를 빼지 않는다.
- 이동 완료는 최신 실측으로 확인하고 고정 축 감시의 기준도 검증된 실측으로 잡는다. 계획값 잔차로 다음 구간이 영구 잠기지 않도록 한다.
- 속도 추정은 중복/역행 stamp와 작은 dt를 거부하거나 충분한 관측 구간을 사용한다. 작은 dt를 버렸다는 이유로 정지 상태라고 간주하지 않는다.
- 통신 소실 시 새 명령을 차단하고 구동부 로컬 정지/홀드를 실행한다. 관절 홀드가 필요하면 freshness 판정과 분리한 마지막 유효 실측을 사용하되, 없으면 드라이버 stop 경로로 간다. 흡착 해제·자동 후진은 하지 않는다.
- 시작 시에는 fresh 관측을 기다리고, 실행 중 상실하면 작업을 중단한다. 시작 유예를 주행 중 missing feedback 허용으로 재사용하지 않는다.
- 기존 계약의 `PickPouch` 1회 재시도 소유자는 orchestrator다. 다만 SOURCE가 새 관측으로 확인되고 실행이 안전할 때만 재시도한다. RELEASE_SENT 뒤 응답 유실은 UNKNOWN으로 멈추고 TARGET 확인 시 COMMIT만 한 번 수행한다. arm 내부 재접촉을 추가하려면 PR-A에서 총 시도 수·시한을 함께 개정한다. 각 계층이 독립 retry하여 횟수가 곱해지면 안 된다.
- 일반 취소는 하위 goal 종료 확인 후 완료한다. reset은 계약상 drain 10 s 초과 후 진행할 수 있으나, 그 상한을 다음 작업 시작 허가로 사용하지 않는다. RESET_BEGIN으로 명령 차단·캐시 폐기, matching RESET_DONE 후 새 관측 확보. 이전 epoch/cancelled goal의 callback은 상태를 변경하지 못한다.
- 소프트웨어 fault를 하드웨어 비상 정지로 명명하지 않는다. 이 계획은 교육용 시뮬레이션 범위다.

## 6. 계층 경로와 도킹

### 토폴로지와 목적지 의미

`rokey_p3_description/config/hospital_topology.yaml`을 **신규 제안**한다.
좌표는 `zones.yaml` 한 곳에 두고 토폴로지는 기존 zone ID를 참조한다. 스키마는 다음 관계를 표현한다.

| 항목 | 내용 |
| --- | --- |
| revision | map·USD transform·zones의 버전/해시와 연결 |
| ward | 병동 ID, 복도 checkpoint zone, station zone, 소속 room 목록 |
| room | 소속 ward, 문 접근 zone, 내부 경유 zone, 소속 bed 목록 |
| bed | 소속 room, 최종 docking zone, patient/인증·cabinet 참조 |
| edge | from/to zone, 방향, 통과 가능 조건, 거리·예상 시간 비용, 차단 상태 |

새 checkpoint ID가 현행 `zones.py` 정규식에 맞는지 검사하고 필요한 kind 확장은 PR-A에서 합의한다.
실제 좌표를 모르는 상태에서 원안의 예시 좌표를 채우지 않는다. 허용오차는 양수여야 하지만 원점 좌표 0 자체는 유효할 수 있다. 별도 준비 상태·버전으로 미설정 여부를 구분한다.
로드 시 없는 참조, 중복 ID, 계층 순환, 다른 병실의 침상, 통과 불가능한 edge, 도달 불가능한 목적지를 거부한다.

배송 모드는 그대로 유지한다. single/urgent는 지정 침상, batch_room은 주문별 침상을 순회하며 각각 환자를 인증한다.
batch_ward는 병동 스테이션 인증과 보관함 적재다. “room”은 room_center에 두고 끝내라는 뜻이 아니다.

### 경로 계산

`rokey_p3_navigation/topology.py`에 ROS 없는 resolver/graph 로직을 추가한다.
입력은 시작 zone, 요청 목적지, topology revision, 차단 edge 집합, 적재 상태이고 출력은 **순서 있는 zone ID + terminal/through 구분**이다.
계층 조상 경로를 무조건 모두 왕복하지 않고 허용 edge에서 Dijkstra로 최소 비음수 비용 경로를 구한다.
기본 비용은 거리 또는 검증된 예상 주행 시간이며, 좁은 문·회전의 가산 비용은 설정으로 고정한다.
동일 비용에는 zone ID tie-break를 사용하고, edge가 막히면 현재 위치에서 재계획한다.
이는 지정 그래프 비용의 최단 경로이며, 병실 다중 정거장 순회나 연속 공간의 전역 최적성을 주장하지 않는다.
첫 batch_room 방문 순서는 기존 FSM의 주문 그룹 순서를 보존한다. 순회 순서 최적화는 별도 측정 후 추가한다.

fleet의 신규 물리 모드는 Dijkstra → `ComputePathThroughPoses` → 허용 구역/footprint 경로 검증 → `FollowPath` 순서로 실행하고 최종 작업 위치에서만 `arrived=true`를 반환한다. 기존 NavigateToPose/BT와 동시에 하위 goal을 소유하지 않는다. 실제 Jazzy 필드와 버전 근거는 [재검토 §6](../analysis/2026-09-19-ur5-delivery-code-review.md#6-충돌-검증과-경로-실행의-구체화)에 있다.
문 앞 대기·양보가 필요한 노드는 through가 아닌 필수 정지점으로 표시한다.
외부 GoToZone은 유지한다. 허용 구역은 global/local costmap에도 동일 적용하며 최초 경로뿐 아니라 추종·재계획을 제한한다. 현재 pose→첫 edge 연결, 종단 goal_checker_id 선택, 전체 deadline·취소 전파를 Jazzy 설치 버전에서 검증한다.

### footprint·도킹·복구

- 전역/지역 costmap 모두 수납 팔·상판·적재물을 포함하는 검증된 polygon을 사용한다. 센서 높이에서 안 보이는 상판·침대와 팔 간섭은 장면 collision 검증으로 보완한다.
- 실제 형상을 쓰라는 [Nav2 Jazzy 안내](https://docs.nav2.org/jazzy/configuration_and_development/tuning_guide/)에 따라 planner/controller의 footprint 지원도 확인한다. inflation은 장애물 비용 확장이며 형상 대체가 아니다.
- 첫 버전은 보수적인 고정 footprint/profile로 시작한다. 문 너비가 필요한 여유보다 작으면 경로 불가로 처리한다. 동적 inflation은 측정으로 필요성이 확인된 후 적용·실패·취소 시 복구까지 별도 PR로 다룬다.
- 기존 0.25 m/rad goal checker로 도착한 뒤 fleet에서 0.03/0.05 m만 요구하면 추가 보정 없이 timeout될 수 있다. 최종 작업별 goal checker/제한된 정렬 동작과 fleet 판정을 같은 공차로 연결한다.
- 3 cm/5 cm는 원안의 후보 목표다. 위치뿐 아니라 yaw, 정지 유지, localization 불확실성, UR5 도달 여유를 함께 측정해 공차를 확정한다.
- 재계획은 현재 장애물 정보를 유지한다. 회전·후진은 swept footprint, 센서 범위, rear clearance가 확인된 경우에만 제한된 시한으로 실행한다. 복구 소유자는 Nav2/fleet 하나이며 총 budget을 초과하면 대기/실패한다.
- cmd_vel 단발 0으로 끝내지 않는다. 명령 발행자 중재와 기존 로컬 watchdog을 유지하고, 팔 전개·센서 소실·취소·reset에서도 정지를 검증한다.

## 7. 구현 PR 분할과 선행 조건

아래 파일명 중 “신규”는 생성 계획이다. 각 PR은 계약·launch·adapter·stub·테스트의 변경 여부를 본문과 수정 댓글에 함께 기록한다. [재검토 §7–§8](../analysis/2026-09-19-ur5-delivery-code-review.md#7-구현-의존성과-출구-조건)의 추가 작업·T01–T10도 각 완료 gate에 포함한다.
담당은 기존 패키지 소유 역할이며 실제 사람 배정은 이슈에서 한다.

| PR / 담당 | 선행 조건 | 구체적 변경 | 완료 기준 |
| --- | --- | --- | --- |
| A: 계약·준비 검사 / 기록·각 소유자 | 이 계획 검토 | 배송 계약의 관측·outcome·경유 의미 확정; 신규 topology schema 및 readiness validator; 자산/지도/설정 manifest 정의 | L1: 미설정·틀린 참조·중복/오배송 입력 거부. 계약·JSON 버전·stub 변경표 리뷰 |
| B: 이동 자산·흡착 배선 / Simu·bringup | A | `sim/standalone/p3sim/ur5_cell.py`, `pouch.py`, `bridge.py` 및 필요한 모바일 셀 모듈; Isaac adapter·launch 연결 | L2: sequence/epoch/heartbeat/timeout. L3: 이동 장착 FK, 명령→실제 흡착·해제·파손/소실 관측. 가상 attach와 분리 |
| C: 고정 베이스 양방향 피킹 / manipulation | A+B | `arm_node.py`, `pick_permission.py`, UR5 전용 경로 검증 모듈 신규, 자세·cup/payload collision 설정 | L1: 도달 불가·충돌·관측 소실 거부. L2: action/cancel/해제 실패. L3는 D 실제 관측 연동 후 벨트→칸 및 칸→보관함, 안전 후퇴 |
| D: 실제 인지·인증 / perception | A+B | `pouch_detector_node.py`, `pouch_geometry.py`, `qr_payload.py`, 깊이/평면 calibration 설정 | L1/L2: 잘못된 깊이·QR·stamp·TF 거부. L3: 이동 후 재검출·가림·반사·오인식, ground truth 제어 차단 |
| E: 지도·계층 주행·도킹 / navigation·description | A+B, 실측 지도 | `hospital_topology.yaml` 신규, `zones.yaml`, map 자산, `topology.py` 신규, `fleet_node.py`, `nav2_params.yaml` | L1: 경로/차단/계층 검증. L2: Nav2 cancel·timeout. L3: 적재 footprint 문 통과·종단 공차·정지·경로 차단 |
| F: 주문 전 과정 / orchestrator·웹 | C+D+E | `trip_fsm.py`, `orchestrator_node.py`, 신규 custody/motion_mode 로직, 상태/오류 변환, `web/api.md`, 기존 launch/stub 확장 | 네 배송 모드 L2; 실제 1개 주문 L3에서 인증·안착·복귀·독립 판정 일치. 중복 접수·재연결 포함 |
| G: 평가·확장 / 기록·마스터 | F pilot 통과 | 신규 pilot→acceptance protocol, runbook·집계 보강, N칸·다중 침상 조건 확대 | 사전 frozen protocol 기반 결과·실패·원본 해시. 승인 후 지원 장면의 신규 경로 활성화 |

순서는 **A→B→C/D/E→F→G**다. C의 물리 완료에는 D 관측 연동이 필수이며 mode permit 최소 배선은 B/C/E에서 함께 준비한다. C/D/E는 계약이 고정된 뒤 독립 작업 가능하지만 F 전에 통합한다.
첫 코드 PR은 A의 준비 검사부터 시작한다. 원안 숫자로 빈 설정을 채우거나 검증 실패를 기본값으로 우회하지 않는다.
신규 물리 배송 경로는 pilot 동안 명시적 launch 선택으로 켠다. 기존 지원 장면의 활성 기능·M0609 기본값을 변경하지 않는다.
G에서 지원 자산·필수 관측·지도 조건을 만족한 경로만 기본 활성화하고, 회귀 시 직전 검증 커밋/프로필로 롤백한다.

## 8. 검증 설계와 실행 산출물

| 계층 | 필수 사례 | 기대 결과 |
| --- | --- | --- |
| L1 경로·요청 | ward/room/bed 매핑, 다른 방 침상, 중복 주문, 미설정 zones, 차단/단절 그래프 | 유효 경로만 결정적으로 생성. 목적지/주문 변조·도달 불가를 실행 전에 거부 |
| L1 팔·관측 | IK 실패, payload 충돌, stamp 역행/작은 dt, initial UNKNOWN, stale HELD | 잘못된 동작 허가 없음. 실패가 timeout까지 무한 대기하지 않음 |
| L2 인터페이스 | 긴 이송 중 heartbeat, 누락/지연, 흡착 echo, 해제 실패, 취소 중 늦은 응답, reset | 지속 관측은 만료되지 않고 소실은 제한 시간 내 차단. 이전 goal/epoch가 새 주문을 완료시키지 못함 |
| L2 트립 | 네 모드, 중복 웹 요청, 목적지 QR 불일치, Nav2 실패, 팔 홈 미확인 | retry 횟수·terminal 상태·이벤트 소유권 일치. 도착만으로 DELIVERED 없음 |
| L3 피킹 | 위치/yaw·마찰/질량 조건별 벨트→상판→보관함, 다른 QR·가림·낙하 | 최초 시도/최종 성공 분리, 충돌·낙하·오배송·관측 누락 기록 |
| L3 주행 | 적재 문 통과, 장애물 등장, 뒤 공간 없음, 통신 소실, 정렬 불가 | 무검증 회전/후진·팔 전개 중 주행 없음. x/y/yaw와 정지 지연 실측 |
| L3 전체 | 웹 1개 주문부터 N칸·room·ward 확장, 재시작/취소/복귀 실패 | 제어 상태와 독립 cabinet 관측 대조; 실패·timeout도 분모에 포함 |

기존 계약의 base/stopped 기준(속도·유지 시간), 상태 freshness와 재시도 횟수는 초기 기준으로 사용한다.
새 흡착/안착 timeout·최대 정지 지연·접촉 깊이·속도·가속도·도킹 공차는 PR-A/B의 calibration 항목이다.
값·측정법·허용 범위를 정하지 못한 항목은 acceptance 진행을 막는다. 테스트 결과를 보고 금지 조건을 완화하지 않는다.

각 run은 commit, scene/map/설정 hash, 자산 종류, seed, 물리 timestep, 센서 주기, reset/epoch, 요청/주문 ID, 장애 주입 시점, 이벤트·관측 원본을 남긴다.
지표는 모든 시작 트립 기준 성공/실패/timeout, 첫 파지 성공·재시도 후 성공, 피킹/적재/주행/복귀 시간, 도킹 x/y/yaw, 정지 지연, 낙하·충돌·오배송 수다.
수집 누락을 0으로 바꾸지 않고 누락 수·이유를 보존한다. arm의 완료 이벤트로 평가용 정답을 합성하지 않는다.

[측정 정책](../policy/metrics.md)에 따라 pilot과 acceptance를 분리한다.
기존 frozen protocol은 수정하지 않고 새 버전을 검토·머지한 다음 실행한다.
클라우드는 L1/L2·PR, 마스터는 지정 커밋의 L3·관측을 담당한다.

## 9. 이 계획 PR의 검토 요청

1. 기존 네 배송 모드와 인증·보관함 인계를 유지하는 범위에 동의하는가?
2. PR-A의 실제 관측/epoch 보강을 어떤 호환 경계로 도입할 것인가?
3. 모바일 UR5 자산, 활성 병원 장면, 지도·카메라 calibration 산출물을 누가 제공하는가?
4. 첫 L3를 AMR 1대·약포지 1개·침상 1곳으로 제한하고 통과 후 확장하는가?

미해결: 실제 이동 자산·TCP, 유효한 병원 지도/좌표, 흡착·안착 관측 수단, 검증된 공차/속도/시한.
이 문서에는 그 값을 추측해 채우지 않았다. 저장소 검사 결과는 PR 본문·댓글에 기록하고, ROS/Isaac 동작 검증은 **미실행**으로 구분한다.
