# 슬라이드 3장 근거 — flowchart · 아키텍처 · 기술 스택

> 슬라이드는 [tech-3.html](tech-3.html)이고, `tutor-deck/build-tech.js` 로 만든다(`node docs/presentation/tutor-deck/build-tech.js docs/presentation`).
> 기준은 main `3ade960`(9/28) · v1.0 판정 구성이다. 9/29 main 변경(#784 봉투 · 병상 QR 손 카메라 판독 필수 · #790 도크 = 적재 자리 · #788 감속 0.7 m/s · #789 컨베이어 2배)은 L3 미실행이다(4절). 경로는 저장소 루트 기준이다. 살아 있는 그래프(`ros2 node list`)와의 대조는 미실행이다.

## 1. 로봇별 제어 flowchart(1쪽)

| 레인 | 단계 → 끝 이벤트 | 근거 |
| --- | --- | --- |
| 주문 FSM | `IDLE … DOCKED_LOAD → WAIT_BELT → PICKING_BELT → DEPARTING/TRANSIT → AUTHENTICATING → DELIVERING → RETURNING` | `src/rokey_p3_orchestrator/rokey_p3_orchestrator/trip_fsm.py:39-50`, 주문 상태 `:95-100` |
| M0609 | 재고 문턱 `REFILL_REQUESTED` → `/m0609/refill` → 칸 선택 · 다중 시드 IK → 약통 QR `check_container` → insert · release(`refill_ros released`) → `REFILL_DONE` → `DISPENSER_RESUMED` | `dispenser_inventory.py:149,158-161`, `orchestrator_node.py:694-716`, `m0609_arm_node.py:705-747,1562,1618-1646`, `scene_v2.py:229,470-483`, `sim/standalone/pharmacy_stage.py:2706,2714`, `refill_planner.py:6` |
| 조제기 · 벨트 | `/pharmacy/dispense` → 봉투 풀에서 스폰 · `DISPENSED` → 벨트 34.58 sim s → `POUCH_AT_END` | `trip_fsm.py:907-944,1090-1098`, `pharmacy_stage.py:2223-2296,2381-2395`, `sim/standalone/p3sim/hospital_conveyor.py` 1-13행 |
| AMR 팔(UR5) | `/amr_1/pick_pouch`(BELT) detect → grasp → `POUCH_PICKED` → `POUCH_LOADED`; 병상에서 `/amr_1/scan_tag` → `AUTH_OK`, PickPouch(DECK) → `POUCH_PLACED` → `CABINET_LOCKED` · `ORDER_DONE` | `arm_node.py:1372-1509`, `trip_fsm.py:949-1023,1139-1160` |
| AMR 주행 | `GoToZone(load)` → `ARRIVED`; `GoToZone(병상)` → `DEPARTED` · Nav2 접근점 + 마지막 직접 추종 → `ARRIVED`; `GoToZone(dock_1)` → `DOCKED` | `trip_fsm.py:895-905,971-987,1034-1037`, `fleet_node.py:347-399`, `nav2_params.yaml:62,94`, `speed_governor.py:20-30` |
| 인터락 | 주행 goal ⇐ `arm/at_home` · 집기 · 스캔 · 놓기 ⇐ `base/stopped` · 배출 ⇐ 벨트 비어 있음 · 장착 ⇐ `check_container` | `trip_fsm.py:896,921,951,985,997,1013,1035`, `fleet_node.py:306`, `arm_node.py:1650-1659`, `m0609_arm_node.py:720-747` |
| 실패 | 배출 거부 3회(2 s) · 집기 2회 뒤 ABORT/HOLD_RETURN · 도크 복귀 10 → 20 → 40 s 뒤 DOCK_GIVEUP · 보충 90 s 시한 3회 | `trip_fsm.py:159-166,1099-1125,1181-1197`, `refill_planner.py:15-16,65,104`, [예외 결과표](../architecture/exception-outcomes-v1.md) 33-97행 |

## 2. 시스템 아키텍처(2쪽)

- 역할 다섯 `stage → arm → nav → stack → web` 과 두 대 분리 `P3_ROLES` · `P3_PEER`: `tools/demo_v2.sh:20-22,226,250-264`.
- 기본은 한 PC: `tools/demo_v2.sh:234`, [ADR 0005](../adr/0005-deployment-single-master-default.md).
- 도메인: `P3_DOMAIN` 은 필수 값이다(`tools/demo_v2.sh:14-17`). 다중 PC 판정 구성은 131 이다(protocol v4 §2 · §5).
- [시스템 그림](../architecture/system-overview.md)(9/24, `66450ae`) 대비 이 슬라이드에서 더한 것: `map_activation_guard`(`nav2.launch.py:92`, 9/27 `33a45b86`), `m0609_detector`(`stub_loop.launch.py:378-384`, `P3_CONTAINER_QR=1` 이면 켜짐 `demo_v2.sh:163,431`), 도메인 131.
- 이 슬라이드에서 `stub_detector` 를 뺐다. 골든 구성에서 launch 기본값대로 켜질 수 있다(`stub_loop.launch.py:136,366-367`). 실제로 떠 있는지는 미확인이다.
- 시스템 그림 문서 자체의 "두 대 회차는 한 번"(1절)은 낡았다. 이 슬라이드는 그 문장을 쓰지 않는다. 문서 갱신은 별도다.

## 3. 기술 스택(3쪽)

| 항목 | 근거 |
| --- | --- |
| OS · GPU · ROS · RMW · Isaac 버전 | v1.0 판정 run `evidence/runs/20260928T100416Z-master01-8fd7dbc7.json` environment.versions |
| Nav2 구성 · AMCL 없음 | `nav2.launch.py:84-104`, `nav2_params.yaml:62,94`, `demo_v2.sh:376-382` |
| 팔 제어(MoveIt 아님) | `pick_plan.py:1-8`, `m0609_arm_node.py:217-235`, `ur5_kinematics.py:1-9`, `module_path.py:3` |
| 비전 | `pouch_detector_node.py:61-67,108`, run 기록 `fingerprints.model`("학습 모델을 쓰지 않았다") |
| 웹 | `web/backend/requirements.txt:3-7`, `web/frontend/index.html:164` |
| 빌드 · CI | `.github/workflows/ci.yml:58-120,144-146`, `harness.yml:51-133`, `web-backend.yml:34,49` |
| 증거 도구 | `tools/evidence.py:2`, `tools/README.md:8-23,129-153`, protocol v4 §4(c) · §7 |

## 4. 슬라이드 · 자막에 쓰지 않는 말

| 쓰지 않는 말 | 사실 | 근거 |
| --- | --- | --- |
| (v1.0 증거로) 카메라로 봉투를 집는다 | v1.0 판정 구성(v4)은 참값 센서 좌표로 집는다(`P3_CAMERA_POUCHES=0`). 9/29 main(#784)은 병원 기본을 "손 카메라 봉투 QR 이 주문과 맞을 때만 집기"로 바꿨다. L3 미실행이라 v1.0 결과로 말하지 않는다 | `docs/runbooks/hospital-full.md`, 커밋 `a21f3ff` · `9844bb8` |
| (v1.0 증거로) 카메라로 환자 인식표 인증 | v1.0 판정 구성은 `scan_tag_source:=sim` 이다. 9/29 main(#784)은 병원 기본을 `P3_CAMERA_TAGS` → `scan_tag_source:=camera`(병상 QR → AUTH_OK → 약 QR → 내려놓기)로 바꿨다. L3 미실행 | 커밋 `a21f3ff` |
| 로봇이 배송 성공을 판정 | SUCCESS 는 평가기가 본 보관함으로 event_logger 가 적는다 | `OrderStatus.msg:9-12` |
| 조제기가 조제한다 | 스테이지가 봉투 풀에서 순간이동 스폰 | `pharmacy_stage.py:2245-2256` |
| AMCL · SLAM | 도크 기준 odom TF. 마지막 0.5 m 는 직접 추종(회피 · 감속기 미적용) | [시스템 그림](../architecture/system-overview.md) 4절 |
| 긴급 주문이 진행 중 배송을 선점 | FSM 은 트립 중 새 요청을 거부. 끼어들기는 요청 대기열에서 | `trip_fsm.py:437-438`, `tools/hospital_orders.py:11,13,303` |
| MoveIt · YOLO 사용 | 둘 다 판정 run 에서 쓰지 않았다 | 3절 |
| 다중 PC 로 v1.0 검증 | v1.0 attempt 12 · 13 은 미실행 | `evidence/deployments/2026-09-28-jaebeom-v1-0-0.md` |
