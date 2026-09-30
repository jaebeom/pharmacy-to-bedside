# 점수표 대응표 — 최종 발표 110점 × 증거

> **기록(동결, 2026-09-28).** main `992dddb`(9/23) 기준 대응표다. `측정 중` 자리와 '다중 PC 실행 0' 등은 그 시각 기준이다. 2026-09-28 기준 사실은 [v1.0.0 배포 기록](../../evidence/deployments/2026-09-28-jaebeom-v1-0-0.md)(회전 7 14/14, 다중 PC 12 · 13 미실행) · [v0.5.0 배포 기록](../../evidence/deployments/2026-09-27-jaebeom-v0-5-0.md)(회전 1–5 63 run · PASS 53 · FAIL 10) 이다. 발표에 쓰지 않는 말은 [tech-3 근거](tech-3-sources.md) 4절이다.
>
> 기준 `main` `992dddb`(2026-09-23). 평가 기준은 [final-presentation-evaluation.md](../reference/tutor/final-presentation-evaluation.md).
> 증거 목록 원본은 #527이다. 이 표는 #527 을 세부 기준 단위로 편 것이다. 실행 원문은 #240.
> **9/28(월) 18:00 증거 동결.** 9/29(화) 편집·리허설, 9/30(수) 발표. 동결 전 수치·영상 자리는 `측정 중(#527 항목명)` 으로 둔다.

## 읽는 법

**상태**는 다섯 가지 중 하나다. 평가 문서 4절 6번(구현·검사·Isaac 확인·미검증 구분)을 따른다.

| 상태 | 뜻 |
| --- | --- |
| **Isaac 확인** | Isaac Sim 에서 실제로 돈 기록이 있다(#240 댓글, `docs/practice/`, `evidence/runs/`) |
| **L1L2** | 단위·ROS 인터페이스·스텁 테스트까지. Isaac 에서 돈 기록은 없다 |
| **구현** | 코드·문서는 있다. 검사나 실행 기록은 없다 |
| **미검증** | 주장할 만한 부분 기록은 있으나 기준을 채우지 못했다 |
| **없음** | 코드도 기록도 없다 |

`#240/<번호>` 는 `#240#issuecomment-<번호>` 다.
**참값 센서**는 스테이지가 prim 자세를 읽어 봉투·인식표를 내는 시뮬 센서다(`sim/standalone/p3sim/truth_sensors.py`). 카메라 이미지를 쓰지 않는다.

## 한눈에

| 항목 | 배점 | 가장 강한 증거 | 가장 큰 빈칸 |
| --- | ---: | --- | --- |
| 설계·납품 | 20 | 확정 시나리오, 계약, README 스텁 한 바퀴 docker 재현 | **Isaac 실행 절차가 README 에 없다.** M0609 자산이 저장소 밖. 깨끗한 클론 재현 기록 없음 |
| 환경 | 10 | 빈월드·병원 씬, `/clock`·TF·라이다 연동, 단계형 리셋 30회 ABORT 0 | Play/Stop 동일 초기 상태를 자세로 대조한 기록 없음. 마찰 미측정 |
| 개별 제어 | 25 | M0609 보충 다회, UR5 픽 18/18, 병원 Nav2 1→7회차 | 병원 Nav2 통과 1회(머지 전 트리). 튜닝 근거가 흩어져 있다 |
| AI 비전 | 10 | 비전 노드 L1L2, 카메라 부하 on/off 비교 | **통합 시연의 인식은 참값 센서였다.** 카메라 인식이 Isaac 에서 동작을 바꾼 기록 0 |
| 통합·동적 | 35 | 빈월드 ①–⑩ 연속 3바퀴 ×3회(9/9), 판정선 결과 전 고정 | **다중 PC 실행 0.** 랜덤 스폰 정량 없음. AMR 1대 |
| 발표·시연 | 5 | — | flowchart·아키텍처·기술 스택 슬라이드(작업 중), 리허설 시간 |
| 챌린지 | 5 | [챌린지 리포트 초안](challenge-hospital-nav2.md) | 8회차(반복·참값) 결과 |

---

## 3.1 디지털 트윈 설계 및 납품 품질 — 20점

| 세부 기준 | 발표할 주장 | 증거 | 상태 | 빈칸 |
| --- | --- | --- | --- | --- |
| 문제 정의 | 병원 약제의 보충→출고→병동 전달→복귀를 한 흐름으로 정의했고, 종료 상태(SUCCESS·HOLD_RETURN·ABORT·TIMEOUT)를 정했다 | [scenario.md](../planning/scenario.md) 3행(9/16 확정, PR #21), 10–27행 흐름, 183–196행 종료 상태 | 구현(확정 문서) | **"왜 디지털 트윈인가"가 확정 문서에 없다.** 기획서(결정 아님) 29–35행에만 있고, 17행은 "현실 디지털 트윈이라 주장하지 않는다"고 적었다. 발표 문장 확정 필요 |
| 현실 반영도 — 작업 흐름 | Isaac 에서 M0609 보충과 AMR(Ridgeback+UR5) 1대의 적재→주행→인증→보관함→도킹→리셋을 연속 3바퀴 돌렸다 | [실습30](../practice/practice-30.md), #240/5758609237(lap14)·5759013132(lap15)·5759211441(lap16) | Isaac 확인 | 문서 스스로 `INTEGRATION_ONLY`: 참값 센서·거리 판정 흡착·고정 경로·빈월드. 시나리오의 AMR 여러 대 중 Isaac 에는 1대 |
| 현실 반영도 — 검증 목표 | 지표·분모·누락 처리를 결과 전에 정했다. 조제실 pilot protocol frozen, 6/6 | [metrics.md](../policy/metrics.md) 23–60행, [pharmacy-lap-pilot-v1.json](../../experiments/protocols/pharmacy-lap-pilot-v1.json)(frozen 2026-09-19T17:44Z), `evidence/runs/` 6건 | Isaac 확인(조제실 구간 pilot) | 병동 acceptance protocol 은 `proposed`, run 0. 합격선(성공률 목표) 미정. metrics.md 43행은 pilot 을 proposed 로 적어 JSON 과 어긋난다 |
| 저장소 완결성 | 7개 패키지·씬·preset·자산 해시가 저장소에 있다. 커스텀 자산은 릴리스 ZIP+sha256 | [sim/README.md](../../sim/README.md) 24–46행, [sim/scenes/README.md](../../sim/scenes/README.md), [host-inventory.md](../setup/host-inventory.md) 39–40행 | 구현 | ① M0609 USD/URDF 가 저장소 밖(`master02-pharmacy-stack.md` 41행 `/home/rokey/cobot3_ws/...`) ② `P3_*` 환경 변수 약 30종이 runbook 마다 흩어져 한 표가 없다 ③ 패키지 버전 전부 0.0.0 ④ 병원 USD 가 NVIDIA S3 원격 자산 74곳을 참조(인터넷 필요) |
| 실행 재현성 | README 순서만으로 Isaac 없이 스텁 한 바퀴가 docker 에서 재현된다. CI 가 같은 빌드·테스트를 돈다 | [README](../../README.md) 확인 출처 표(`7ac85b7`: 225 tests 0 failures, `SUCCESS`), `.github/workflows/ci.yml` | L1L2 | **Isaac 절차는 README 에 없다고 README 가 적었다.** 다른 PC·깨끗한 클론으로 Isaac 까지 돈 기록 없음. 코드 기본값 절대 경로 1건(`sim/standalone/verify_authored_pouches.py` 12행). `측정 중(#527 설계·납품: 깨끗한 클론 재현)` |

## 3.2 시뮬레이션 환경 구성 — 10점

| 세부 기준 | 발표할 주장 | 증거 | 상태 | 빈칸 |
| --- | --- | --- | --- | --- |
| 씬 구성 — 빈월드 | 코드로 만드는 조제실: 선반 4·약통 16·3축 레일 M0609·조제기·컨베이어·시연 카메라 | `sim/standalone/pharmacy_stage.py`(preset `demo-ros-refill-v2`), `p3sim/scene.py`, 실습 6–9 | Isaac 확인 | 배치도 캡처(슬라이드용) |
| 씬 구성 — 병원 | 병원 USD 위에 AMR 합본·RTX 2D 라이다, zones·routes 는 USD 에서 뽑는다 | `sim/scenes/hospital_navigationv1.usda`, `zones.hospital.yaml`·`routes.hospital.yaml`, [병원 주행 런북](../runbooks/hospital-nav-l3.md) | Isaac 확인(주행만) | 병원 씬에서 컨베이어·픽·전달 전 구간 없음(#527 재범 결정 (가)/(나)). 새 씬 #523·#524 머지 전 |
| 물리 속성 | 강체·충돌·질량을 코드에서 명시: 벨트 kinematic+collider, 레일 Base 50 kg·Carriage 10 kg, 약통 0.1 kg, 봉투 0.02 kg, dt 1/60 s | `p3sim/scene.py` 104–107·128–145·245–260행, `pharmacy_stage.py` 196·806·407행. 벨트 속도 `ratio=1.000` 5/5([sim/README.md](../../sim/README.md) 179행) | 구현(벨트 속도만 Isaac 확인) | **마찰은 0.5단계 스크립트에만, 값은 "not measured"**(`m0609_refill_stage.py` 71행). 주력 스테이지에 마찰 재질 없음. 파지는 물리가 아니라 attach. 물리 속성 표(발표 자료로 만든다) |
| ROS2 연동 | `/clock`(OmniGraph, 59.999 Hz, rtf 0.990), TF, 손 카메라, RTX 라이다 `/amr_1/scan` 16 Hz. 그 밖의 계약 메시지는 JSON 토픽 → 어댑터 | `minimal_clock.py` 172–194행, `p3sim/amr_base.py`, `p3sim/bridge.py`, [ADR 0002](../adr/0002-isaac-json-topics-and-ros-adapter.md), #240/5787139396(scan 16.0 Hz) | Isaac 확인 | 손 카메라는 9/17 2.855 Hz(목표 10)로 뜬 뒤 시연에서 빠졌다 |
| 재현성 — Play/Stop | 타임라인을 멈추지 않는 단계형 리셋(epoch). 리셋 30회 ABORT 0, 사람이 누른 STOP 5/5 복구, 연속 3바퀴 epoch 2→3→4 | `p3sim/reset.py`, [sim/README.md](../../sim/README.md) 132행, [실습1](../practice/practice-01.md) 75행, #240/5759211441 | Isaac 확인 | **"같은 초기 상태"를 prim 자세로 대조한 기록 없음.** Stop→Play 뒤 `/clock` 단조성 시험 미실행. `측정 중(#527 환경: Play/Stop 반복 재현 — 병원 8회차)` |

## 3.3 개별 로봇 제어 — 25점

로봇은 셋이다. **M0609**(3축 레일, RG2 손가락 그리퍼, 약통 보충), **UR5**(Ridgeback 위, 흡착으로 봉투 픽·플레이스), **AMR**(Ridgeback 주행). M0617 은 씬에서 뺐다(#233).

| 세부 기준 | 발표할 주장 | 증거 | 상태 | 빈칸 |
| --- | --- | --- | --- | --- |
| M0609 보충 — 완수 | 조제실에서 보충을 여러 회차 반복했다. 실습19 6/6, 실습20 A 13/13, 실습21 79회 중 ok 78 | #240/5748162014·5751030882·5754620387, [실습20](../practice/practice-20.md), `evidence/runs/` 6건(refill_s 21.3–23.2 s) | Isaac 확인(조제실) | 실습20 B(`preferred_first`) 첫 보충 3연속 실패, 원인 미확정. 병원 배치는 원통 3/3 뿐이고 "통합 합격 아님"([실습37](../practice/simworld/practice-37.md)) |
| M0609 — 튜닝 근거 | 관절·TCP 속도는 두산 사양의 80%. 명령 시각을 sim 시간에 맞춰(#228) 보충 1회 40–52 s → 18.6–21.4 s. 수납통 안지름 0.10→0.12(#198), 받침 0.30→0.55 로 16/16칸 계획 가능(#188) | `m0609_arm_node.py` 176·182행, manipulation README "레일 위 M0609", PR #228·#198·#188 | Isaac 확인 | 가속 4/6 rad/s² 근거 없음. **실습37 레일 X 최고 2.30 m/s 가 설정 0.8 을 넘었다**(원인 미확정) |
| UR5 픽·플레이스 — 완수 | 빈월드 AMR 합본 연속 3바퀴 ×3회: 픽 18/18 첫 시도, `in_slot=True` 9/9, 흡착 거리 0.004–0.0063 m | #240/5758609237·5759013132·5759211441, [실습30](../practice/practice-30.md) | Isaac 확인(통합 한계) | 흡착은 거리 판정 attach. 병원 씬 UR5 0회. 흡착 압력(`/amr_1/gripper/pressure`)은 계약만 있고 코드 0 |
| UR5 — 튜닝 근거 | lap13 흡착이 0.55 s 늦게 붙어 실패 → 확인 시한 2.0 s(#469) 뒤 9/9. 경유 자세 v4 여유 +0.023(v2 −0.003) | PR #469, `arm_node.py` 331행 주석 | Isaac 확인 | v4 경유 자세·`approach_height_m` 0.08 이 저장소 config 가 아니라 runbook 에만 있다 |
| AMR 주행 — 완수 | 빈월드 waypoints 6/6(d_xy 0.018–0.019). 병원 waypoints 6/6(2회차). 병원 Nav2 7회차 6/6·touch 0 | #240/5755737538·5787139396·5788371477, [챌린지 리포트](challenge-hospital-nav2.md) | Isaac 확인(waypoints) / **미검증(Nav2: 통과 1회, 머지 전 트리 `cb6eaa5`)** | `측정 중(#527 개별 제어: 병원 8회차 3바퀴·참값)` |
| AMR — 튜닝 근거 | 속도·가속을 Nav2 상한의 80%(#453). 도착 공차 0.02 로 정차 오차 0.14→0.019(#407). 경로 반경 0.56(#504), 넘김 반경 0.5·`localization:=odom`(#514), 로컬 static layer | `navigation_params.yaml` 주석, #240/5756853381, `p3sim/hospital_nav.py` 36–41행, `nav2_params.yaml` 139–142행 | Isaac 확인 | **footprint 1.10×0.90·inflation 0.65·goal 공차 0.2 근거 문서 없음.** 튜닝 근거 한 장 정리(발표 자료), 속도 두 배(#526) 9회차 `측정 중(#527 개별 제어)` |
| 설계-구현 일치 | 계약의 인터락(`arm/at_home`·`base/stopped` 1.0 s), PickPouch outcome 7종, GoToZone 정지 판정이 코드와 같다. 센서가 결정을 바꾼다: `holding`→파지·낙하, `joint_states`→도착, `at_home`→출발 거부, `/amr_1/scan`→Nav2 costmap | [delivery-contract-v1.md](../architecture/delivery-contract-v1.md) 136–143·241–270·562–582행, `arm_node.py` 1443행, `fleet_node.py` 290·589행 | Isaac 확인 | 계약과 코드가 다른 곳이 셋이다. (1) Refill: 계약은 결과 뒤 홈, 코드는 홈 뒤 결과(#99). (2) Nav2→추종기 넘김은 계약에 없다. (3) 계약은 scan 을 AMCL 입력으로 적는다. 통과 구성은 `localization:=odom` 이다. 발표 전에 계약을 고칠지, 슬라이드에 「계약 뒤 변경」으로 밝힐지 고른다 |

## 3.4 AI 비전 인식 및 활용 — 10점

**먼저 밝힐 것.** 빈월드 통합 시연(lap12–16)의 봉투 검출과 인식표 판독은 **참값 센서**였다(`tools/demo_v2.sh` 231행 `pouch_source:=sim scan_tag_source:=sim`). 카메라 비전 노드(`pouch_detector_node.py`)는 구현·L1L2 까지이고, #240 에 이 노드가 Isaac 에서 돈 기록이 없다. #527 의 "lap14–16 이 참값이었는지" 질문의 답이다.

| 세부 기준 | 발표할 주장 | 증거 | 상태 | 빈칸 |
| --- | --- | --- | --- | --- |
| 인식 안정성 — 비전 노드 | OpenCV QR 다중 판독, YOLO 허용 class fail-closed, HSV 색 폴백. 픽셀+폭 기반 깊이로 봉투 자세 | `src/rokey_p3_perception/rokey_p3_perception/pouch_detector_node.py` 185–324행, PR #254(perception 33 tests) | L1L2 | **YOLO 가중치 없음·학습 안 함**(PR #254). 카메라 판독률 N/M 없음. L3 런카드 VA-2(판독 거리)·VA-3 미실행([l3-arm-perception.md](../runbooks/l3-arm-perception.md) 52·65행) |
| 인식 안정성 — Isaac 영상 | Isaac 봉투 윗면 QR 을 OpenCV 로 해독(`ord-9001`) | [실습39](../practice/emptyworld/practice-39.md) 73–77행(PR #510) | Isaac 확인(GUI 캡처 1장, ROS 카메라 경로 아님) | 거리·각도별 판독률. `측정 중(#527 AI 비전: 한 장 찍기 판독률)` |
| 인식 결과 활용 | 검출 자세 → 팔 파지 좌표(order_id 일치 때만). 인식표 ID → AUTH_OK / AUTH_FAIL 분기. 멈추지 않은 봉투는 검출로 내지 않아 파지 오차 0.0988 m(lap5)를 없앴다 | `arm_node.py` 1482–1523행, `trip_fsm.py` 1015–1022행, `truth_sensors.py` 26–34행, lap12–16 | Isaac 확인(**참값 입력**) | **카메라 인식이 로봇 동작을 바꾼 L3 기록 0.** QR→약 DB 조회는 계약 #521, 구현 PR #522 미머지. 사람 인식→감속·회피 없음 |
| 처리 효율 | 카메라 ≤10 Hz frameSkip·640×480, BEST_EFFORT depth 2, 1 s 넘은 검출 폐기, 이벤트는 봉투당 1회. 손 카메라를 끄면 rtf 0.925→0.992, GPU 99→74 % | `p3sim/sensors.py` 42–46행, `pouch_detector_node.py` 42·328–343행, `arm_node.py` 322행, #240/5755273685(실습24) | 구현 / Isaac 확인(부하 비교) | 프레임당 처리 지연(ms)·처리 Hz 없음. "정지 뒤 한 장만 찍기"(`CaptureFrame`)는 계약만([qr-db-camera-contract-v1.md](../architecture/qr-db-camera-contract-v1.md)) |

## 3.5 시스템 통합 및 동적 대응 검증 — 35점

| 세부 기준 | 발표할 주장 | 증거 | 상태 | 빈칸 |
| --- | --- | --- | --- | --- |
| 다중 PC ROS2 | 유선 폐쇄망에서 두 마스터 사이 토픽 왕복(9/17, ping 0.3–1.0 ms) | [ros2-wired-network.md](../setup/ros2-wired-network.md) 214–233행 | **미검증**(chatter 만) | **노드를 여러 PC 에 나눠 한 시나리오를 돈 기록 0.** README 가 "여러 PC 로 돌린 기록은 아직 없다"고 적었다. 모든 lap 은 master02 한 대. `측정 중(#527 통합·동적: 다중 PC)` |
| 전 구간 연결 | 빈월드에서 주문→조제→벨트 픽→주행→인증→보관함→복귀→리셋(①–⑩)이 끊김 없이 이어졌다. 한 바퀴 162.0 / 164.5 s(sim) | #240/5758317635(lap13 2/3)·5758609237·5759013132·5759211441, [실습30](../practice/practice-30.md) | Isaac 확인(한 PC, 빈월드) | 병원 씬 전 구간 없음(#527 재범 결정). 빈월드 lap 의 run manifest 가 `evidence/runs/` 에 없다(master02 로컬) |
| 다중 로봇 조율 | UR5↔AMR 인터락(`arm/at_home`·`base/stopped`). M0609 보충이 트립과 병렬(재고 0→`REFILL_REQUESTED`→`REFILL_DONE`→재개) | `orchestrator_node.py` 239–251행, `refill_planner.py`, #240/5755953693, 실습19 보충 6/6 | Isaac 확인 | **M0609 보충과 AMR 합본 한 바퀴를 같은 장면에서 동시에 돈 기록 없음.** AMR 2대 없음 |
| 완료 뒤 재실행 | 리셋 barrier(epoch)로 늦게 온 결과를 버리고 다음 트립. 연속 3바퀴 epoch 2→3→4, stale·late 0 | `trip_fsm.py` 15–29·460행, lap14·16 | Isaac 확인 | — |
| 동적 대응 — 랜덤 스폰 | 봉투를 벨트 방향 0.05–0.15 m·옆 ±0.04 m·yaw ±0.3 rad 에서 `(seed, epoch, index)` 로 뽑는다. M0609 보충 칸도 시드로 무작위 선택 | `p3sim/pouch.py` 25–31행, `pharmacy_stage.py` 1414–1439행, `pick_plan.py` 31–57행 | 구현 | **스폰 좌표 분포·위치별 성공률 기록 없음.** evidence notes "시드 미적용". `측정 중(#527 통합·동적: 랜덤 스폰 범위)` |
| 동적 대응 — 외부 이벤트 | 긴급 주문은 큐 맨 앞, 도착 전 `ARRIVING`. 웹·curl 요청(1인·묶음), 재고 임계로 보충 자동 요청 | `order_pool.py` 173–181행, `trip_fsm.py` 431행, [web/api.md](../../web/api.md), #240/5753738506(실습14b 묶음 22.9 s), 실습21 요청 16/16 | Isaac 확인(조제실 구간) | 진행 중 트립 선점 없음(busy 면 거부). 긴급 주문 장면 영상 `측정 중(#527 통합·동적: 긴급 주문)` |
| 검증 및 분석 | 판정선을 결과 전에 고정했다(#240/5755830894). 조제실 pilot 은 6/6 이다. 빈월드 lap13–16 은 11/12 바퀴다. #469 뒤는 9/9 다. 첫 회차–lap12 의 14회가 끊긴 단계는 적재 픽 7, 적재 도킹 2, 인증 2, 전달 1, 기동·스테이지 사망 2 다. 번호는 한 바퀴 ①–⑩ 단계다. 원인과 고친 PR 은 실습30 표에 있다 | [실습30](../practice/practice-30.md) 60–77행, `evidence/runs/`, #240/5757290294(결정 50) | Isaac 확인 | 성공률 표(시행·실패·원인) 한 장 정리. 표본이 작아 신뢰구간 없음. acceptance(12회) 미실행. `측정 중(#527 통합·동적: 성공률 표)` |

## 3.6 발표 및 시연 — 5점

| 세부 기준 | 준비물 | 상태 | 빈칸 |
| --- | --- | --- | --- |
| flowchart | 주문→DELIVERED FSM(`trip_fsm.py` 39–50·803–1045행) | 작업 중 | — |
| 시스템 아키텍처 | 계획 배치(계약 1절)와 **실제 실행(한 마스터에 전부)** 을 나눠 그린다 | 작업 중 | 다중 PC 결과에 따라 그림이 바뀐다 |
| 기술 스택 | Ubuntu 24.04·ROS 2 Jazzy(rmw_fastrtps)·Isaac Sim 5.1.0·Python 3.11/3.12·Nav2·OpenCV·(YOLO 선택)·M0609·Ridgeback+UR5·RTX 5080 Laptop | 근거: [host-inventory.md](../setup/host-inventory.md), `src/*/package.xml` | — |
| 시간 준수 | 발표 시간·지정 목차·영상 규격 | **미확인**(평가 문서 8절) | 강사 공지 확인 필요 |

## 3.7 챌린지 — 5점

| 주장 | 증거 | 상태 | 빈칸 |
| --- | --- | --- | --- |
| 병원 Nav2 주행을 0/6 에서 원인을 한 층씩 잘라 7회차 6/6·touch 0 | [챌린지 리포트 초안](challenge-hospital-nav2.md), #240/5787005979…5788371477, PR #504·#508·#511·#514·#523·#524 | Isaac 확인(n=1) | `측정 중(#527 챌린지: 8회차 반복·참값)` |

---

## 빈칸 → 담당

발표 자료로 채울 것은 **발표**, 나머지는 #527 담당이다.

| # | 빈칸 | 필요한 증거 | 담당 |
| --- | --- | --- | --- |
| 1 | 다중 PC 한 시나리오 | 노드를 두 PC 이상에 나눠 한 바퀴, 호스트별 노드 목록·`ros2 node list` | — |
| 2 | 깨끗한 클론 재현 | 새 폴더 clone → README 순서 → Isaac 까지, 막힌 곳 기록 | master02 |
| 3 | 카메라 인식이 동작을 바꾸는 장면 | 참값 센서 대신 `pouch_detector` 로 한 바퀴 또는 VA-2 판독률 N/M | 비전 |
| 4 | 랜덤 스폰 정량 | 시드 N 개 × 스폰 좌표 × 성공·실패 | — |
| 5 | Play/Stop 동일 초기 상태 | 리셋 전후 prim 자세 대조, 병원 8회차 | — |
| 6 | 병원 Nav2 반복 | 8회차 3바퀴, 참값 d_xy, **main 에 머지된 SHA** | — |
| 7 | 계약↔코드 어긋남 3건 | 계약 문구 고침 PR 또는 발표에서 밝힐지 결정 | — |
| 8 | "왜 디지털 트윈인가" 문장 | 확정 문서에 없다 — 발표 문장만 쓸지, 시나리오에 넣을지 | 발표(초안) → 재범 |
| 9 | 물리 속성 표·튜닝 근거 한 장·성공률 표 | 위 3.2·3.3·3.5 증거를 모은 표 | 발표 |
| 10 | 발표 시간·영상 규격 | 강사 공지 | 재범 |
