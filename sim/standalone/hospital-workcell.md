# 병원 조제실 ROS 실습과 투입구 시각 데모

> **상태: 지난 기록 (2026-09-22 기준).** 지금 병원 한 바퀴는 [병원 전 구간 런카드](../../docs/runbooks/hospital-full.md)와 [sim README 현행 절](../README.md#지금-무엇이-현행인가-v110-병원-한-바퀴)을 따른다.
> 지금은 `--preset hospital --workcell-layout` 을 `tools/demo_v2.sh` 가 띄운다. 아래 `--preset demo-ros-refill-v2` 명령은 9/22 실습31·35 의 구성이다.

#484 병원 배치와 #485 조제기 에셋을 사용한다. 실제 로봇 실습은 `pharmacy_stage.py --workcell-layout`와 기존 `m0609_arm`을 연결한다. 아래의 `hospital_workcell_demo.py`는 별도의 키네마틱 시각 데모다. 색상·데코는 후속 작업이다.

## 기존 알고리즘으로 실행

`prepare_workcell_integration.py`는 선반 67-75의 판 높이·측면·뒷면, 조제기 메시와 투입구를 측정하고 새 외부 폴더에 `base.usda`, `workcell.json`, `measurements.json`을 만든다. 소스 USD는 수정하지 않는다. 9개 선반 각각 원통·모듈 1개, 총 18개다. 기본 물품 치수는 아래 시각 데모와 같다.

```bash
~/isaacsim/python.sh sim/standalone/prepare_workcell_integration.py \
  --base-usd sim/scenes/hospital_navigationv1.usda \
  --dispenser-usd src/rokey_p3_description/models/dispenser/dispenser.usdc \
  --output /absolute/path/to/new-layout
```

이 준비 명령에는 `pxr`이 필요하다. usd-core 가 있는 `python3` 로도 돈다. Isaac `python.sh` 면 준비기가 Kit 를 headless 로 띄운다. 출력은 `base.usda`·`workcell.json`·`measurements.json`·`dispenser-placement.json` 넷이다. 준비 파일과 계획 로그를 같이 보존한다.
9/22 실습 원본은 `--pill-offset .30 -.10 0`(원통 투입구 이동)을 썼다. 저장소 준비기에는 이 인자가 없다. 투입구를 옮기지 않기로 한 결정은 재범 9/22 #496 이다(`prepare_workcell_integration.py` 머리말). 투입구를 옮긴 base 는 조제기 검사에서 physics 시작 전에 멈춘다.

ROS를 source하지 않은 Isaac 셸에서 실행한다. `ROS_DOMAIN_ID`는 다른 실습과 겹치지 않는 값으로 고정하고 Isaac·노드·기록기에 똑같이 준다.

```bash
~/isaacsim/python.sh sim/standalone/pharmacy_stage.py \
  --preset demo-ros-refill-v2 \
  --base-usd /absolute/path/to/new-layout/base.usda \
  --workcell-layout /absolute/path/to/new-layout/workcell.json \
  --amr-combined /absolute/path/to/practice-ridgeback_ur5.usd \
  --robot-usd /absolute/path/to/m0609_gripper.usd \
  --urdf /absolute/path/to/m0609_isaac_sim.urdf \
  --robot-description /absolute/path/to/m0609_description.yaml \
  --respawn-delay-s 600
```

환경 격리와 내부 ROS 라이브러리는 [sim 실행 환경](../README.md)의 절차를 따른다. 이 실습의 정확한 현장 명령은 외부 run의 `launch-stage.sh`, `launch-arm.sh`에 남긴다. 합본은 실습30/31과 같은 `amr_base` 함수로 팔 뒤쪽 이동·받침·트레이를 조립한다. 병원 주행 경로는 이번 adapter에 포함하지 않는다.

별도 시스템 ROS 셸에서 동일 소스의 설치본을 source한 뒤:

```bash
ros2 run rokey_p3_manipulation m0609_arm --ros-args \
  -p use_sim_time:=true -p scene_version:=2 -p v2_seed:=835258728 \
  -p v2_guarded_module_path:=false -p v2_rail_select:=preferred_first
```

`preferred_first`는 저장소에 있는 기존 경로 검사 모드다. 팔을 접은 상태의 레일 이송 경로도 검사하고 필요하면 먼저 올려서 이동한다. `first_feasible`의 고정 레일 팔 경로 검사만으로는 조제기까지 이동하는 중간 간섭을 검출하지 못했던 실패 기록을 보존한다. 관절별 80% 속도, TCP 0.8 m/s, 레일 3축 0.8 m/s 및 가속도 1.0 m/s²는 노드 설정을 사용한다. 레일의 1.0 m/s 기준은 기존 실습의 제안값이며 실물 레일 제조사 사양이 아니다. 값을 확인하려면 `ros2 param dump /m0609_arm`을 저장한다.

같은 ROS 셸에서, 스테이지에 준 것과 **같은** `workcell.json`을 지정한다:

```bash
PYTHONPATH=sim/standalone python3 sim/standalone/run_workcell_refill_trials.py \
  --layout /absolute/path/to/new-layout/workcell.json --output /absolute/path/to/new-trials
```

기록기는 `/m0609/arm/plan_cache`(latched)가 현재 inventory의 모든 칸을 다 풀 때까지 최대 1200 wall s 기다린다(`preflight.json`). 실제 goal을 보낸 뒤의 240 wall s 제한과 구분한다. live inventory의 기하가 `--layout`과 다르면 goal 전에 멈춘다.

> 이 문서의 원본 실습(실습31·35, 9/22 `m2-hospital-integrated-09`)은 브랜치 `feat/hospital-random-pick-practice`의 옛 기록기 `--arm-log <arm 로그>`(로그의 `v2 계획 캐시:` 줄을 기다림)로 돌았다. main 기록기에는 그 인자가 없고 위의 plan_cache 토픽 확인으로 바뀌었다(#490). 재현할 때는 그 회차의 외부 `launch-*.sh`와 브랜치 머리 `8bfd61e`를 쓴다.

기존 노드가 난수로 고른 셀에 `Refill` goal을 최대 3회 순차 요청한다. 첫 실패에서는 후속 goal을 보내지 않는다. `/clock` 단일 발행자 확인, action 결과·feedback·inventory·실제/명령 레일 값·팔 관절·holding을 기록한다. `--observe-only-seconds 60`은 goal 없이 관측만 한다. 원본 `events.jsonl`, `results.json`은 외부 폴더에 유지하고 run manifest에서 해시로 연결한다.

사전 계획만 확인하려면(Isaac/ROS 실행 아님):

```bash
PYTHONPATH=sim/standalone:src/rokey_p3_manipulation \
  python3 sim/standalone/check_workcell_plans.py \
  --layout /absolute/path/to/new-layout/workcell.json \
  --seed 835258728 --rail-select preferred_first --output /absolute/path/to/new-plan.jsonl
```

파지는 기존 시뮬레이터의 **거리 기반 attach**다. 마찰 파지 성능이 아니며, 아래 흡입 애니메이션을 실제 보충 성공으로 대체하지 않는다. 원통 3회 실습과 모듈/AMR 전체 배송 검증도 구분한다.

## 별도 시각 데모

`--conveyor-probe`는 별도 **물리 벨트 진단** 모드다. 아래의 키네마틱 수납과 동시에 실행하지 않는다. 팔·AMR 동작을 포함한 전체 실습 완료를 뜻하지 않는다.

## 기존 실습 합본 1대와 병원 벨트 진단

`--amr-combined /absolute/path/to/ridgeback_ur5.usd`와 `--amr-start X Y`를 함께 주면 합본 1대를 둔다. 경로는 이전 실습과 같다. `amr_base.reference`, 팔 받침 이동, 밑동 프레임, 통짜 트레이다. 원본 병원의 `ridgeback_ur5`는 이 실행에서 비활성화한다. `--view loading`은 합본과 출구 쪽을 보여준다. 위치는 로컬 인자이며 공용 기본값으로 넣지 않는다.

`--conveyor-probe /absolute/path/to/probe.local.json`은 병원에 이미 있는 `IsaacConveyor` 그래프를 사용한다. 별도 직선 벨트나 물품 위치 애니메이션으로 대체하지 않는다. `spawn`과 `end`는 실측한 시작·종점 XYZ, `reroute`는 켤 분기 Boolean 속성 경로 목록, `inventory`는 측정한 전체 진열 JSON(`cells`) 경로다. `end`는 카메라 조준에만 쓰며 도착 판정에는 쓰지 않는다.

물리 시작 전에 팔·AMR 관절과 강체를 고정하고, 기존 벨트 표면만 kinematic rigid body로 활성화한다. 선반 물품은 준비 상태 표시이며 이 진단에서 움직이지 않는다. `shelf_stock.measure_stock`은 실제 판을 측정해 지붕 아래 모든 층에 격자를 만들고 약 1/4을 보라색 모듈로 배치한다. 원형과 모듈의 크기·층간 여유를 검사한다. 앞열만 `front_accessible=true`이며 후열 접근은 검증하지 않았다. 시험 봉투 하나를 시작점에 생성한 뒤 물리 이동을 관측한다. 이 여유는 진단 입력이다. 생산 합격선이 아니고 AMR 적재 가능 판정도 아니다. `terminal_prim`에서 마지막 롤러 표면을 잰다. 표면은 얇고 수평이다. 멈춤은 세 조건을 같이 볼 때다. `terminal_direction`(+x/-x/+y/-y) 쪽 앞면이 끝단에서 `edge_margin_m` 이내. 회전을 반영한 물품 전체 AABB가 표면 XY 안. 밑면이 `height_tolerance_m` 이내. 정착으로 기록하려면 도착 조건과 속도 0.03 m/s 미만을 연속 1초 만족해야 한다. 영역을 벗어나거나 속도가 커지면 정착 대기를 처음부터 센다. 이전의 18 cm 원형 도착 영역은 조기 정지를 만들었으므로 제거했다. 낙하 또는 90 sim s 초과는 실패다. 이것은 ROS 주문 처리·로봇 파지·AMR 적재/주행 검증이 아니다.

`graph_velocities`로 기존 벨트 graph의 속도 속성에만 로컬 진단 후보를 적용할 수 있다. 원본 USD를 수정하지 않으며 후보의 채택은 별도 검토 사항이다.

출력 `amr-placement.json`에 에셋 해시·시작 좌표·구성이 있다. `conveyor-observations.jsonl`은 준비 상태와 10 Hz 봉투 위치·속도·벨트 표면 속도 관측, `conveyor-result.json`은 종료 원인과 성공 여부다. 기록 시작 전 구간은 소급해 녹화했다고 표시하지 않는다. 런타임 입력과 원본 영상·로그는 저장소 밖에 보존한다.

```bash
~/isaacsim/python.sh sim/standalone/hospital_workcell_demo.py \
  --base-usd /absolute/path/to/prepared-hospital-navigationv1.usda \
  --robot-usd /absolute/path/to/m0609_gripper.usd \
  --amr-combined /absolute/path/to/practice-ridgeback_ur5.usd \
  --output /absolute/path/to/new-trial-directory --intake-demo
```

`--base-usd`는 #484 `hospital_navigationv1.usda`의 외부 자산 경로가 해석된 파일이다. `prepare_hospital_scene.py`는 아직 다른 템플릿을 대상으로 하므로 그대로 사용하면 이 장면을 만들지 않는다. 삭제 payload 목록의 경로 두 개를 동일 경로로 치환하면 USD 파싱에 실패한다. 원본 삭제 목록을 보존하고 살아 있는 참조만 해석한다. 로컬 자산 경로·준비 파일·런타임 결과를 git에 넣지 않는다.

`--intake-demo`를 빼면 조제기·레일·M0609 배치만 연다. 넣으면 선반 메시의 수평 윗면 면적을 측정해 0.9 m에 가장 가까운 판을 선택하고, 선반 9개에 원통 약통과 모듈을 하나씩 배치한다. 원통은 지름 0.07/높이 0.12 m, 모듈은 0.06×0.10×0.14 m의 시험용 도형이다. 실제 병원 약통 자산의 크기를 검증한 것이 아니다.

## 기준 조제기 위치 검사

기준 형상은 [조제기 에셋 README](../../src/rokey_p3_description/models/dispenser/README.md)의 원통 왼쪽·모듈 오른쪽 배치다. 병원에 참조한 뒤 열린 stage의 메시·앵커를 검사한다. 입구별 위치 덮어쓰기가 있으면 데모 준비를 중단한다. 출력 `dispenser-placement.json`의 `asset_sha256`과 `anchors_world`로 실제 합성 결과를 확인한다.

`--view dispenser`를 추가하면 조제기 앞을 보여준다. 기본 `overview`는 기존 작업대 전경이다. 위치 유지 검사는 시작 시점에 실행하며, 실행 중 편집이나 로봇 충돌을 계속 감시하지 않는다.

## 투입구 동작

1. 시험 장치가 물품을 선반에서 투입구 감지 위치로 배치한다. **로봇 파지·운반이 아니다.** 물리와 ROS를 시작하지 않는다.
2. 종류, 중심 위치, 방향 오차(10도), 해제 여부, 속도(0.03 m/s 이하)를 확인한다. 연속 0.25초 만족해야 인수를 시작한다.
3. 1초 동안 중심을 정렬하면서 알약은 −Z, 모듈은 +Y로 0.20 m 이동시키고 숨긴다. 실제 흡입력·충돌·내부 이송기구를 모사하지 않는 시각적 수납이다.
4. 로컬 데모에서 물품 ID당 한 번만 저장 완료를 기록한다. reset은 진행 중 인수를 취소하고 대기 시간을 초기화하지만 이미 저장한 ID는 유지한다.

이 시각 동작은 물리적으로 모델 바닥/내벽을 통과한다. #485 에셋에는 아직 collision/내부 통로의 물리 모델이 없다. 따라서 진공흡입·도킹의 실물 성능이나 보충 성공으로 해석하지 않는다. 실제 그리퍼 신호와 재고를 연결할 때는 해제 관측·센서 확인·타임아웃·복구를 별도로 통합해야 한다.

## 기록과 시험

새 출력 폴더만 허용한다. `items.json`에 측정한 배치 좌표, `intake-events.jsonl`에 순번·경과시간·물품·조건·거절 이유·흡입 중 위치·완료를 저장한다. `summary.json`은 정상 18건과 미해제/오정렬/영역 밖/잘못된 종류 4건을 각각 판정한다. 잡힘·각도 값은 시험 시나리오 입력이고, 속도는 프레임별 USD 위치 차이에서 계산한다. 센서에서 온 값이라고 주장하지 않는다.

`layout-overrides.usda`와 `review.usda`는 외부 로컬 재개방용이다. 원본 병원과 제품 좌표 설정을 수정하지 않는다. 기본 M0609 자세와 긴 레일은 정지 배치이며, 선반 전체의 팔 경로·충돌을 검증하지 않았다.

순수 수납 상태 검사:

```bash
python3 -m unittest discover -s sim/tests -p test_inlet_capture.py
```

## 혼합 진열 파지 사전 진단

`check_stock_refill.py`는 기존 `scene_v2` 계획기를 그대로 호출한다. 입력은 v2 inventory 메시지이며 각 cell에 `front_accessible`과 `shelf` 메타데이터를 명시한다. 서로 다른 선반의 앞열 원통 3개를 기존 CellPicker로 선택하고, 매 대상 외의 모든 present 물품을 장애물에 추가한다. ROS/Isaac 명령과 운영 캐시는 건드리지 않는다. 실패도 JSONL에 남긴다.

```bash
PYTHONPATH=sim/standalone:src/rokey_p3_manipulation python3 sim/standalone/check_stock_refill.py \
  --inventory /absolute/path/to/measured-stock-inventory.local.json \
  --output /absolute/path/to/new-plan-results.jsonl --seed 835258728 --rail-select first_feasible
```

이 도구는 #490 런타임의 18칸 제한을 해제하거나 동작 검증을 대체하지 않는다. 실제 결과와 미완료 항목은 [실습38](../../docs/practice/simworld/practice-38.md)에 있다.

## 출구 경사 연결부와 받침대 배출 진단

선택 입력 `outlet_chute`는 마지막 롤러와 실제 받침대 mesh의 월드 범위를 측정해 수동 경사판을 만든다. 원본 USD는 그대로 두고 세션에 충돌 가능한 solid mesh를 추가한다. `receiver_prim`, `entry_overlap_m`, `landing_overlap_m`, `width_margin_m`, `thickness_m`, `static_friction`, `dynamic_friction`을 로컬 입력으로 명시한다. 선택 `entry_recess_m`은 입구 모서리를 낮추는 진단 후보다. 실제 롤러 지지 높이보다 높은 모서리를 겨냥한다. 값은 판 두께보다 작아야 한다. 높이·좌표를 공용 코드에 고정하지 않는다. 표면은 수평이고 축 정렬되어 있다는 전제이며, 이 조건이 아닌 자산에는 사용하지 않는다. 마찰과 겹침 길이는 시험 후보이고 실측 재질값이 아니다.

이 모드에서는 마지막 롤러에 닿아도 벨트를 멈추지 않는다. `receiver_settled`는 받침대에 내려와 멈춘 기록이다. 물품이 경사판을 지난 뒤 받침대 XY 안으로 전부 들어와야 한다. 받침대 높이에서 평평하게 놓이고 속도 0.03 m/s 미만인 상태가 연속 1초 유지돼야 한다. 떨어지거나 제한 시간을 넘기거나 앱을 먼저 닫으면 실패/미완료 결과를 남긴다. 앱 종료 시에도 벨트 속도 입력을 0으로 만든다. 순간 이동이나 경사면 구간의 강제 위치 이동은 없다. 받침대 배출은 AMR 그리퍼 파지·트레이 적재 완료와 다르며 ROS 생산 이벤트를 발행하지 않는다.

## 기존 ROS 연결 검토

공용 연결 코드와 현장 설정의 구분, 담당별 검토 범위는 [병원 월드 연결 로직](workcell-integration-review.md)에 있다. 그 코드는 #490 으로 main 에 들어갔다. 기존 시각 데모의 완료를 실제 파지·이송 검증으로 확대하지 않는다.

## 중도 종료

실행 중 SIGINT(Ctrl+C)는 종료 플래그를 세운다. probe 미완료 결과와 로그를 저장한 뒤 Kit를 닫는다.
Isaac 기본 SIGINT 처리로 먼저 plugin이 해제되면 결과가 누락될 수 있어 `minimal_clock`의 기존 핸들러를 재사용한다.
SIGKILL은 이 정리 경로를 거치지 않는다. 창 닫기 버튼·SIGTERM 경로는 이번 물리 회차에서 검증하지 않았다.
