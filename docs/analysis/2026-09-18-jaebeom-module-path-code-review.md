# 사용자 제공 모듈 운반 지시문 검토와 P3 경로 계산 적용

이 문서는 #229 구현·재검토 당시의 기록이다. 아래 기본값 false와 데모 비활성 설명은 그 커밋 기준이다.
이후 사용자 요청에 따른 v2 기본 활성화 변경은 [별도 검토](2026-09-18-jaebeom-module-default-code-review.md)에 기록한다.

상태: **unreviewed — 구현 후보, Isaac L3·실기 미실행**. 요청자: 임재범.
코드 기준: `main` `4d059baa850b5bf2c619e32204ee25f3e7fbd4f8`.
이번 분석은 사용자에게 전달받은 지시문과 저장소 코드를 대조한 것이다. 외부 지시문을 현장 측정값으로 취급하지 않는다.
ROS 2 Jazzy / Isaac Sim 5.1 프로젝트이며, 이 환경에서는 ROS·Isaac 실행 없이 순수 Python과 노드 대역으로 검사했다.

## 판단

**무부하 자세와 운반 자세 분리, 외축 정지 확인, 파지·해제 피드백 확인은 채택한다.**
제미나이 글은 작업 순서와 안전 요구를 제안하지만 목적함수·기구 모델·충돌 형상·시간 계획이 없으므로
그 자체가 최적 경로 알고리즘은 아니다. 이번 구현은 유한한 후보 집합에서 제약을 만족한 **전체 보충 경로의 예상 이동시간**을 비교한다.
모든 9자유도 연속 경로에 대한 전역 최적해를 주장하지 않는다.

| 원문 주장 | 검토·반영 |
| --- | --- |
| J4·J5·J6 고정으로 수평 유지 | 수정. 관절각 고정과 TCP 자세 고정은 다르다. 파지 후 TCP 쿼터니언을 유지하며 IK를 풀고, 보간 중 자세 오차도 검사한다 |
| 3축 외축의 세 번째 축 불명 | 현재 P3는 `rail_x`, `rail_y`, `rail_z`라는 병진 XYZ다. 순서가 다르거나 회전 외축이면 새 경로를 거부한다 |
| 파지 후 홈으로 접기 | 수정. 완전히 인출하고 들어 올린 운반 자세를 유지한다. 빈손 Tuck은 해제 관측을 받은 뒤에만 사용한다 |
| 100 mm 인출·100 mm 후진 고정 | 수정. 인출 거리는 모듈 앞끝·선반 앞면·여유로 구한다. 삽입 후퇴는 검사한 진입선의 역방향으로 Pre-Place까지다 |
| 파지 직후 바로 인출 | P3 모듈은 선반판 위에 놓여 있으므로 기존 30 mm 들기를 먼저 유지한다. 초기 지지면 접촉만 허용하고 측판·뒷판·윗판 침범은 허용하지 않는다 |
| world 계획 자체가 TF 오류 원인 | 수정. 핵심은 외축 이동 중 사용한 상태가 낡는 것이다. 현재 모델은 회전 없는 베이스 변환이며, 계획 시 레일 위치로 world→base를 변환한다. 실행 중 레일·팔 타임스탬프, 정지·드리프트, 장면 변경을 검사한다 |
| In-Position이면 팔 시작 | 보완. 위치만 맞고 움직이는 경우를 거부한다. 증가하는 source timestamp의 위치·속도 관측이 0.2 sim s 연속 안정돼야 다음 축을 움직인다 |
| 그리퍼는 sleep 후 인출 | 기존 코드는 파지 시 holding을 기다린다. 진짜 누락은 stale holding의 이동 허용, 해제 후 확인 부재다. 새 모드는 close/open 뒤 새 관측을 확인한다 |
| 외력을 감지한 뒤 순응 제어 켜기 | 실기에서 순응/감시를 어떻게 활성화할지 검증할 사항이다. 충돌 후 켜면 충돌을 예방했다는 보장이 없다. 현재 P3에 두산 DRL 제어기·wrench 입력이 없으므로 가짜 API를 추가하지 않는다 |
| 토크 임계치 15 N / 즉시 E-Stop | 단위 오류다. 힘 N과 토크 N·m를 나누고 측정 좌표계·중력/부하 보상·필터·검출 지연을 정해야 한다. 15 N을 승인된 수치로 사용하지 않는다. 소프트웨어 위치 hold는 안전등급 비상정지가 아니다 |
| 삽입구는 수 mm 공차 | 현재 fixture의 모듈 단면은 60×140 mm, 개구는 80×160 mm로 명목상 한쪽 10 mm다. 실물 슬롯 공차로 일반화하지 않는다 |

## 코드에서 확인한 문제

- `scene_v2.plan_refill`: 파지 후 `fold`에 빈손 홈 관절값을 넣는다. 운반 중 자세가 크게 달라질 수 있다.
- `plan_leg`: 잡기 구간 전체에 `carrying=False`를 전달해 파지 뒤 들기·인출에서 모듈 형상을 검사하지 않는다.
- 기존 후보 선택은 목표까지 어깨 도달거리 순서의 첫 통과 후보다. 전체 레일 이송·복귀 시간 최적화가 아니다.
- 기존 `plan_leg`는 한 레일 위치의 팔 경로만 검사한다. 레일 이동 중 모듈·팔·승강 기둥의 전체 경로 검사가 별도로 필요하다.
- `m0609_arm_node._warn_rail_drift`는 경고만 내고, 해제는 `_release_settle` 대기만 한다.
- 기존 종료 경로는 실패·취소 뒤 홈으로 돌아간다. 모듈을 잡았거나 센서가 끊긴 상황의 자동 복귀에는 별도 판단이 필요하다.

## 구현

### 1. `module_path.py`: 계산

모듈 전용이며 기존 원통 경로와 구분한다. ROS import나 명령 발행 없이 실행할 수 있다.

1. 장면·외축 축 순서·유한수·충돌 형상·TCP 변환·슬롯 방향과 깊이를 검사한다.
2. 선반 진입 위치 후보를 만들되 인출 후에도 팔이 지나치게 접히지 않도록 베이스 거리를 구한다.
3. 빈손 레일 이동 → Pre-Pick → 직선 접근 → 파지 → 들기 → 완전 인출 → 운반 자세를 만든다.
4. 직행 및 전방 Y 통로·상승을 거치는 이송 후보를 만든다. 각 후보의 팔·그리퍼·파지물과 환경·이동 레일 부품을 검사한다.
5. Pre-Place → 정렬된 직선 삽입 → 해제 → 같은 선을 따라 후퇴까지 검사한다.
   슬롯 앞에서 즉시 전 관절을 홈으로 돌리면 조제기·원형 통과 간섭하는 후보가 있어, J1을 유지한 빈손 접기,
   검사한 운반 높이까지 외축 상승, 전방 통로 이동, 홈 방향 회전, 레일 원점 복귀로 나눠 검사한다.
   홈 방향으로 회전할 위치도 슬롯 X부터 원점 X까지 간격이 `min_reach` 이하인 유한 후보를 만들고
   진입·회전·복귀를 모두 검사해 가장 짧은 후보를 선택한다. 원점 X도 자동으로 안전하다고 보지 않는다.
6. 가능한 후보 모두를 시간 계획한 뒤 이동시간 합이 작은 것을 선택한다. 동률이면 검사한 여유 하한이 큰 것을 선택한다.

목적함수는 `sum(segment.seconds)`다. 센서 확인·settle 대기와 실제 제어기의 추종 지연은 예측 이동시간에 포함하지 않는다.
시간 보간이 원래 폴리라인의 꼭짓점을 건너 새 관절 직선을 만들면, 그 연결 구간의 충돌·자세·LIN 이탈을 다시 검사한다.
같은 원래 직선 내부의 점은 기존 검사 경로에 포함된다. 새 연결 구간이 제약을 어기면 후보를 거부한다.
관절·레일 속도 및 가속은 현재 노드 설정을 받는다. 정밀 구간과 부하 팔 이동은 TCP 0.05 m/s 이하로 제한한다.
샘플 속도·가속을 정지 전후까지 확인하며 시간을 늘린다. jerk 제한이나 실물 적재 가속 한계를 검증했다는 의미는 아니다.

충돌 검사는 박스의 분리축 간격을 사용한다. 이는 실제 거리의 **보수적인 하한**이며, 반복 계산이 덜 끝난 근접점 거리를
여유의 증거로 사용하지 않는다. 모듈은 실제 크기와 파지 오프셋으로 TCP에 붙인다. 모듈 대 로봇·그리퍼 충돌도 검사하며
물체와 접촉하는 두 손가락 형상만 예외다. 장착된 base_link 대 레일 부품의 접촉도 예외다.
기존 `DispenserFront*` 전체를 파지물 검사에서 제외하는 규칙을 사용하지 않는다.
출력 `clearance`는 비접촉 환경·레일 부품에 대한 검사 여유의 최소 하한이다.
파지물 대 로봇·그리퍼 여유는 별도의 충돌 제약으로 검사한다.

### 2. `module_execution.py`: 실행

- 시작은 빈손·팔 홈·레일 홈 관측을 요구한다. `open_loop`를 허용하지 않는다.
- 빈손 확인 뒤 open 명령을 내고 새 관측을 받은 다음 선반으로 출발한다.
- 명령 스트림마다 고정돼야 할 축, 파지 상태, 관측의 최신성·시계 일치, 장면 식별자를 확인한다.
- guarded 명령 스트림은 검사한 점을 순서대로 모두 발행한다. 지연된 틱에서 중간 점을 건너뛰거나 몰아서 보내지 않는다.
  각 명령 뒤 최소 계획 주기를 기다리므로, 30 Hz 등의 계단형 시계에서는 계획의 이상적 시간보다 오래 걸릴 수 있다.
- 팔이 움직일 때 레일은 정지 상태를 유지한다. 레일이 움직일 때 팔은 검사한 운반/빈손 자세에 머문다.
- 도착 위치만 확인하지 않고 관측 속도까지 안정된 후 전환한다. 대기는 wall 시간 상한도 갖는다.
- close/open 뒤 새 holding 관측을 확인하기 전에는 인출·후퇴를 진행하지 않는다.
- 센서 소실·레일 밀림·취소·타임아웃·장면 변경은 실패를 래치한다. 최신 실측 위치로 hold를 요청하고 그리퍼를 임의로 열지 않는다.
- 실패 후 자동 홈 복귀·새 goal 수락을 막는다. RESET_DONE은 관측을 비우고 다시 초기 상태를 확인하게 한다.
- 실행 전 inventory·계획·시한 확인 실패는 명령을 보내지 않고 종료하며, 기존 위치와 파지 상태를 유지한다.
  이 경우 모듈 실행 실패를 래치하지 않는다. 실제 guarded 실행에 진입한 뒤의 실패에만 HOLD 정책을 적용한다.
- 성공 시에는 파지·해제 확인 이력과 빈손·팔 홈·레일 홈의 최신 정지 관측을 확인한다.
  노드가 `REFILL_DONE`과 action 성공을 내기 직전에도 홈 관측을 재확인한다.
- `at_home` 토픽도 새 모드에서는 팔·레일·빈손의 최신 정지 관측을 요구한다. 관측이 없으면 true를 내지 않는다.
- 계획 계산 중 취소·리셋은 executor 진입 전에 다시 확인한다. 리셋 세대를 넘긴 옛 작업은 HOLD·fault 재래치·완료 이벤트를 내지 않는다.
- 예상 이동시간과 최소 정지 관측 시간만으로도 남은 goal 시한을 넘으면 첫 동작 전에 거부한다.

### 3. 실제 노드 연결

`m0609_arm_node`의 `v2_guarded_module_path` 파라미터를 추가했다. 기본 **false**다.
켜면 v2 `module` 칸에 새 계산기와 실행기를 사용한다. 후보가 없다고 기존 계획으로 되돌아가지 않는다.
`cylinder`, 기존 v0·v1, 기존 v2 기본 경로는 이 변경의 적용 대상이 아니다.
메시지·액션 스키마, `REFILL_DONE.detail` 필드를 바꾸지 않는다.

## 실행·검증 절차

오프라인 후보 계산(제어기 연결 없음):

```bash
PYTHONPATH=src/rokey_p3_manipulation python3 -m rokey_p3_manipulation.module_path \
  src/rokey_p3_manipulation/test/data/pharmacy_v2.json \
  src/rokey_p3_manipulation/config/m0609_collision.yaml \
  src/rokey_p3_manipulation/config/m0609_rail_teach.yaml \
  --cell upper_right/r0c0 --seeds 12
```

출력은 `candidate`와 후보 수·구간별 예상시간, 또는 `refused`와 충돌/기구학 사유다.
반환 코드 0은 계산 후보가 있다는 뜻이고 Isaac 성공 판정이 아니다. 거부는 2다.
단일 HOME 시드로는 이 칸의 전체 경로를 찾지 못했다. 기본 12개 초기값을 재현 가능한 순서로 시험하며,
같은 관절 해에 수렴한 후보는 중복 검사하지 않는다. 계산은 실시간 제어 루프 밖에서 수행한다.
전체 기본 후보 집합에 대한 성능·성공률 전수 검증은 완료하지 않았다. 아래 자동 검사는 형상을 바꾸지 않고
생산 후보 집합에 포함되는 레일 위치·IK 시드를 제한해 한 완결 경로를 확인한다.

L3 후보 노드(팀이 후보 커밋을 빌드한 뒤, 기존 m0609_arm과 중복 실행하지 않는다):

```bash
ros2 run rokey_p3_manipulation m0609_arm --ros-args \
  -p use_sim_time:=true -p scene_version:=2 -p v2_guarded_module_path:=true
```

먼저 단발 모듈 보충을 확인한다. 각 선반 위치, reset, 파지 관측 소실, 레일 밀림, 해제 실패를 포함한다.
실행 커밋·장면/자산·로그·충돌 접촉·단계 시간·모듈 자세를 기록해야 하며, L1 결과를 L3 성공으로 쓰지 않는다.
기존 `tools/demo_v2.sh`는 이 파라미터를 자동으로 켜지 않는다.
캐시 계산이 끝나기 전에 goal을 보내거나 예상 소요시간이 기본 90 sim s 시한보다 길면 거부될 수 있다.
시한 변경은 후보의 예상시간과 실제 관측을 검토한 뒤 팀이 결정한다.

## 검증 기록

아래는 최초 구현 `abd2243`의 기록이다. 2026-09-18, 위 `main` SHA 위의 로컬 변경분을
매번 새 Python 프로세스로 실행했다. 런타임 노드 캐시는 사용하지 않았다.

| 검사 | 실행 명령·결과 |
| --- | --- |
| 신규 순수 로직·노드 대역 | `python3 -m pytest src/rokey_p3_manipulation/test/test_module_path.py src/rokey_p3_manipulation/test/test_module_execution.py src/rokey_p3_manipulation/test/test_module_node.py -q` → **36 passed in 56.97s** |
| 기존 reset·레일·종료 회귀 | `python3 -m pytest src/rokey_p3_manipulation/test/test_reset_fence.py src/rokey_p3_manipulation/test/test_m0609_rail.py src/rokey_p3_manipulation/test/test_m0609_refill_finish.py -q` → **53 passed in 40.50s** |
| 저장소 단위 검사 | `python3 -m unittest discover -s tests` → **Ran 94 tests / OK** |
| 저장소 경계·문서 링크 | `python3 tools/check_repository.py` → **PASS** |
| 증거 구조 | `python3 tools/evidence.py validate --base origin/main` → **Evidence structure OK: 1 protocols, 0 runs**. 측정·승인 증거가 있다는 뜻이 아님 |
| 린트·공백 | `ruff check .` → **All checks passed!**, `git diff --check` → 출력 없음, 종료 0 |

pytest는 패키지 소스와 `test` 디렉터리를 `PYTHONPATH`에 넣어 ROS 없이 실행했다.
새 검사는 LIN 자세, 단위/NaN 입력, 레일 중간 충돌, 모듈 자기 간섭, 시간 제한,
정지 관측, 오래된 source stamp, 파지·해제 실패와 자동 복귀 차단을 포함한다.
실제 fixture의 제한 후보 검사는 파지 중 수평·속도 제한과 삽입선 역방향 후퇴, 빈손 복귀를 확인한다.
후보 시간 비교는 별도의 합성 무충돌 장면에서 첫 도달 후보보다 전체 시간이 짧은 후순위 후보를 고르는 것으로 검증했다.

개발 중 실패도 남긴다. HOME 단일 시드의 전체 경로가 없었고, 대체 시드로 투입에 성공해도 즉시 Tuck은 조제기 외벽,
제자리 회전은 원형 통, 원점 X에서 높은 자세로 회전하는 것은 선반 측판과 간섭해 거부됐다.
최종 제한 후보 검사는 빈손 접기·상승·검사한 전방 통로의 회전 위치를 거치는 경로로 통과했다.
검사 여유를 줄이거나 fixture 형상을 삭제해 통과시키지 않았다.

ROS `colcon build/test`는 로컬 환경에서 **미실행**이다. GitHub CI 결과는 PR의 Checks와 검증 본문에 기록한다.
Isaac L3와 두산 실기 순응 제어는 **미실행**이다.

## PR 229 재검토와 수정

기준: `abd22437ea7c2f34cc15a5a5781097fd40cb47a2`의 실제 원격 blob과 로컬 파일 9개를 대조했다.
리뷰 의견을 코드와 테스트로 확인했다.
최초 커밋의 ROS CI와
저장소 CI는 모두 통과했지만 아래 경계 검사가 빠져 있었다.

| 확인한 문제 | 수정·재현 검사 |
| --- | --- |
| `_module_request`가 종류 확인 전부터 true여서 inventory 미수신·미등록 품목·계획 없음·시한 부족도 지속 HOLD로 바뀜 | 동작 전 확인 상태와 실제 guarded 실행을 분리했다. 실제 executor 진입 시에만 `_module_request`를 켠다. 확인 실패는 이전 `_left_home`과 파지 상태를 보존하고 legacy 홈 복귀도 호출하지 않는다 |
| 잘못된 inventory가 대기 중에도 fault를 래치하거나 계획 중 바뀐 유효성이 실행에 반영되지 않음 | 최신 inventory의 유효성을 별도로 기록하고 실행 직전에 다시 확인한다. 실행 중 무효화는 HOLD, 실행 전 무효화는 명령 없는 실패로 구분한다 |
| 실행기 반환값만으로 노드가 홈 복귀를 완료한 것으로 처리함 | 빈 경로를 거부하고 파지·해제 관측 이력을 요구한다. 실제 팔·레일 홈 정지와 빈손·source timestamp를 실행기 종료 및 노드 성공 경계에서 확인한다. 복귀 구간 누락과 실행 직후 레일 이동을 주입해 성공 이벤트가 나가지 않는 것을 검사한다 |
| 새 모드의 성공·실패가 `_execute_refill`부터 action/event까지 연결되는 테스트가 없음 | 실제 `_execute_refill` → `_run_v2` → executor를 실행하는 노드 대역 검사를 추가했다. 성공은 goal의 lot과 기존 `REFILL_DONE.detail`을 유지한 단일 이벤트, 실패·취소는 이벤트와 legacy 복귀가 없는 것을 확인한다 |
| `rail_command_rate_hz=0.5`에서 계획은 2초 간격, 실제 스트림은 최소 1Hz 적용으로 1초 간격 | 계획기가 실행기의 `_period()`를 사용하게 했다. 낮은 설정과 기본 50Hz에서 계획·실행 주기가 일치하는 것을 검사한다 |

수정 전 추가한 노드·실행기 회귀 검사에서는 **13 failed, 18 passed**로 문제를 재현했다.
주기 불일치는 별도 설정 검사에서 **1 failed, 1 passed**, 계획 2.0초 대 실행 1.0초로 재현했다.
충돌 형상·여유·속도/가속 상한을 완화하지 않았으며, 모듈 기능 기본값은 계속 false다.
수정본은 같은 로컬 소스에서 매번 새 Python 프로세스로 검사했다. 런타임 노드 캐시는 사용하지 않았다.

| 검사 | 실행 명령·결과 |
| --- | --- |
| 전체 manipulation 패키지 | `python3 -m pytest src/rokey_p3_manipulation/test -q --tb=short` → **182 passed in 202.43s** |
| 저장소 단위 검사 | `python3 -m unittest discover -s tests` → **Ran 94 tests / OK** |
| 저장소 경계·문서 링크 | `python3 tools/check_repository.py` → **PASS** |
| 증거 구조 | `python3 tools/evidence.py validate --base origin/main` → **Evidence structure OK: 1 protocols, 0 runs** |
| 린트·공백 | `ruff check .` → **All checks passed!**, `git diff --check` → 출력 없음, 종료 0 |

새 커밋의 ROS CI 결과는 PR 본문과 Checks에 기록한다. Isaac L3·실기는 미실행이며 기능 기본값은 false다.

## PR 229 두 번째 재검토

기준 커밋은 `44bccf8865a5ad54d4770c1e158c2d9d8f997dac`이며 로컬 HEAD와 원격 PR HEAD가 일치했다.
이 커밋의 ROS CI는
**543 tests, 0 errors, 0 failures, 0 skipped**였다. 추가 리뷰 댓글은 없었고 실행 경계를 직접 다시 확인했다.

| 재현한 문제 | 수정·검사 |
| --- | --- |
| `at_home`이 팔만 보고 레일 이탈·파지 중·레일 관측 없음에도 true | guarded 상태 토픽도 팔·레일 홈 정지와 빈손을 함께 확인한다. 관측이 없으면 unknown, 조건이 다르면 false다 |
| 시간이 걸린 계획 계산 중 취소·리셋을 받아도 실행기로 넘어가 HOLD·fault 발생 | 계산이 끝난 뒤 취소·리셋·시한을 다시 검사한다. 명령 없이 종료하고 동작 전 상태를 보존한다 |
| RESET_DONE의 대기 상한을 넘겨 끝난 옛 실행기가 새 상태에 HOLD를 보내고 fault를 다시 래치함 | 실행 시작 세대를 전달하고 리셋이 작업을 대체하면 HOLD와 finally 래치를 생략한다. feedback reset 번호도 비교해 확인과 fault 기록 사이에 리셋이 끼어들어도 옛 fault를 복구하지 않는다 |
| 열린 barrier만 검사하면 RESET_DONE 뒤 옛 작업의 명령 발행을 구분할 수 없음 | 팔·레일·그리퍼·이벤트 발행을 리셋 세대 확인과 같은 잠금 안에서 수행한다. barrier가 다시 열린 뒤에도 옛 세대의 발행은 차단한다 |
| 실행기 종료 직후 리셋되면 옛 작업이 REFILL_DONE·성공을 발행 | 완료 이벤트 발행 직전에도 취소·세대를 확인한다. 리셋을 끼워 넣으면 이벤트 없이 실패로 끝난다 |
| 시간 보간이 꺾인 경로의 꼭짓점을 건너면서 미검사 직선을 만들 수 있음 | 원래 구간을 넘는 새 직선은 충돌·파지 자세·LIN 편차를 재검사한다. L자 경로 안쪽 장애물과 비선형 FK의 직선 이탈을 합성 장면으로 검사한다 |
| 기존 스트리머가 지연 틱에서 마지막 점만 보내 검사한 중간 점을 생략함 | guarded 실행은 다음 점 하나만 보내고 다음 주기를 기다린다. 30 Hz 시계와 0.2초 시계 점프에서도 점 순서·간격을 보존한다. 기존 모드는 기존 시간 추종 방식을 유지한다 |

수정 전 첫 회귀 묶음은 **9 failed, 38 deselected**였다. 완료 직후 리셋 검사를 추가했을 때에도
**1 failed, 1 passed, 47 deselected**로 잘못된 성공 처리를 확인했다. 발행 직전의 세대 확인 누락도
**4 failed, 28 deselected**로 재현했다. 검사는 제어기를 움직이지 않는 노드 대역과 합성 장면이다.
수정본의 최종 소스를 새 Python 프로세스에서 검사했다. 런타임 노드 캐시는 사용하지 않았다.

| 검사 | 실행 명령·결과 |
| --- | --- |
| 전체 manipulation 패키지 | `python3 -m pytest src/rokey_p3_manipulation/test -q --tb=short` → **198 passed in 211.43s** |
| 저장소 단위 검사 | `python3 -m unittest discover -s tests` → **Ran 94 tests / OK** |
| 저장소 경계·문서 링크 | `python3 tools/check_repository.py` → **PASS** |
| 증거 구조 | `python3 tools/evidence.py validate --base origin/main` → **Evidence structure OK: 1 protocols, 0 runs** |
| 린트·공백 | `ruff check .` → **All checks passed!**, `git diff --check` → 출력 없음, 종료 0 |

새 커밋의 ROS CI 결과는 PR 본문과 Checks에 기록한다.

계획의 `motion_seconds`는 이상적인 명령 주기 기준의 후보 비교값이며 실제 완료시간 상한이 아니다.
점 보존으로 늘어날 수 있는 시간·센서 대기·시계 지연을 포함한 Isaac L3 검증은 여전히 미실행이다.
기능 기본값 false와 충돌·속도·가속 기준은 유지한다.

## 남은 범위와 출처

- 명목 FK와 보수적인 collision bbox, 유한한 경로 샘플을 사용한다. 전신 자기 충돌 전체나 연속 시간 충돌의 수학적 증명이 아니다.
- 이 검사는 inventory의 장애물과 운반 모듈을 다룬다. inventory 장애물 목록 밖의 사람·동적 물체나 다른 재고 물체의 정확한 형상은 검증하지 않는다.
- 실제 관절 추종 오차, 열린/닫힌 손가락 형상 차이, 객체의 접촉·미끄러짐·중력·진동은 Isaac L3에서 확인할 사항이다.
- holding Bool에는 command ID가 없다. 새 관측과 상태 전환을 요구하지만 실기 PLC의 명령별 ACK와 같다고 볼 수 없다.
- 실물 조제기에 완전히 장착됐다는 센서가 없다. 현재 P3의 정해진 삽입 깊이에 도착하고 해제를 관측하는 구현이다.
- 실제 힘/토크 인터록·안전 PLC/watchdog·순응 제어·질량/관성 설정·캘리브레이션은 실기 어댑터의 후속 범위다.
  통신이 끊긴 장치의 정지를 원격 hold 요청만으로 보장하지 않는다.

공식 문서(검토일 2026-09-18):

- [Doosan task_compliance_ctrl, 3.2.0](https://manual.doosanrobotics.com/en/programming-manual/3.2.0/publish/task_compliance_ctrl-stx-time):
  기준 좌표계에 따른 순응 제어 시작 함수이며 로봇 없는 시뮬레이션에서 정상 동작하지 않을 수 있음을 명시한다.
  P3에 이 펌웨어가 설치됐다는 뜻이 아니다.
- [Doosan check_force_condition, API 1.33.3](https://doosanrobotics.github.io/doosan-robotics-api-manual/GL013303/mode/common/force_compliance/check_force_condition.html):
  지정 축의 힘/모멘트 크기를 비교하는 조건 함수다. 방향·기준 좌표와 제어 모드의 계약은 별도로 확인해야 한다.
- [MoveIt orientation constraints](https://moveit.picknik.ai/main/doc/examples/planning_with_approximated_constraint_manifolds/planning_with_approximated_constraint_manifolds_tutorial.html):
  JointConstraint와 OrientationConstraint는 별도 제약이다. 말단 자세 제약을 관절 셋의 고정으로 대체하지 않는다.
- [MoveIt planning around objects](https://moveit.picknik.ai/main/doc/tutorials/planning_around_objects/planning_around_objects.html):
  명시적인 프레임·형상으로 장애물을 계획 장면에 넣는 흐름을 설명한다. 이번 PR은 MoveIt 도입 PR이 아니다.
