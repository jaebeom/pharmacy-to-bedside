# 스텁이 가린 진실 — 독립 감사와 acceptance 동결 판단

검토 소스: `jaebeom/ROKEY_P3_A3@83a2a1f1f94b65240851218ddf965cabebb5b82d` (2026-09-21). 현장 실행 SHA·기동 시각·캐시·실효 파라미터: **미확인**. ROS/Isaac 현장 실행: **미실행**.

상태: 검토 제안. 승인된 acceptance protocol이 아니며, 기존 frozen protocol을 변경하지 않는다. 운영 코드·설정·시험 코드는 수정하지 않았다. 다른 감사와 협의하지 않고 소스, 기존 계약, 실습 기록, 기존 이슈를 독립 대조했다. 시작 레인은 **판정 도구·증거·시험 경계**이며 이후 팔·주행·시뮬레이터·웹으로 넓혔다.

## 1. 판단 한 장 — 9/22에 무엇을 동결할 것인가

**현재 이벤트·카운터만으로 9/29의 물리 완주를 합격 판정해서는 안 된다.** 가장 직접적인 반례는 `judge_run.py`다. `REQUEST_ACCEPTED` 세 건만 있고 `DOCKED`, 주문 결과, 나머지 로그가 없는 합성 입력이 예시 기준의 모든 활성 gate를 통과하고 종료 코드 0을 반환했다. 기존 판정 도구 시험 30개는 그대로 통과한다. 따라서 “시험이 초록이다”와 “합격 판정기가 실패를 거부한다”는 현재 다른 주장이다.

예시 YAML은 스스로 실제 합격선이 아니라고 명시한다. 기존 `pharmacy-lap-pilot-v1`도 합격선이 없는 pilot이며, 명시된 성공 정의에는 실제 `DOCKED`와 주문 종결이 필요하다. 위 반례는 **frozen pilot 자체를 통과했다는 뜻이 아니라, 보조 카운터를 protocol 판정 대신 사용할 때 생기는 거짓 통과**다.

| 동결 전 반드시 결정·확인할 것 | 닫힘의 증거 | 닫지 못할 때 protocol에 쓸 제한 |
| --- | --- | --- |
| 완료된 시행과 성공 주문을 실제로 세는 판정선(F01) | 미완료·타임아웃·누락 로그·잘못된 순서·중복 관측이 합격을 만들지 않는 음성 사례 | `judge_run.py` 종료 코드와 `laps`는 보조 집계로만 사용. 독립 판정표와 원본 대조가 없으면 합격 판정 불가 |
| 관측 발행자와 기대값의 독립성(F02, F03) | 실행 inventory, 토픽별 발행자, 실제 파라미터와 기준 SHA를 원본으로 보존 | stub 관측이 섞인 구간은 “논리 통합”으로만 기록. ROS/Isaac 동작·물리 안착·실물 성능으로 승격 금지 |
| 해제 뒤 안착과 보충 재고의 근거(F04, F05, F07) | 같은 대상의 해제 후 연속 관측, 낙하 없음, 보충 대상 슬롯의 실재와 재고 증가 일치 | 해당 구간은 미검증. `POUCH_PLACED`, `REFILL_DONE`, `SUCCESS` 단독으로 합격 불가. 보충을 제외한다면 “재고 사전 설정·보충 제외”를 범위에 명시 |
| 실제 도착·홈 자세·신호 신선도(F06, F08, F09) | 명령 뒤 새 관절/TF/odom 관측으로 수렴·정지를 확인하고 신호 단절 반례는 거부 | 물리 이동 완주를 주장하지 않는다. 홈 값·공차·관측 지속시간이 미측정이면 그 상태로 물리 합격선을 확정하지 않는다 |
| 복수 대상·중간 실패·리셋의 종결(F11, F12, C01) | 두 품목 보충 겹침, 두 침상, 이전 epoch 종료 이벤트, 실패/취소/리셋 중간 사례 | 단일 대상 제한을 사전에 명시. 웹 표시만으로 종료를 판정하지 않고 주문/goal별 원본으로 확인 |

**권고:** 9/22에는 결과를 보기 전에 시스템 범위, 관측 출처, 필수 증거, 실패·미측정 처리, 시행 분모를 먼저 고정한다. 구현 결함을 전부 하루 안에 고치겠다는 약속을 합격선으로 쓰지 않는다. 미해결 구간은 명시적으로 제외하거나 그 구간의 합격을 보류한다. 9/29까지 못 닫은 P0를 조용히 예외로 만들지 않는다. 이미 frozen인 pilot은 그대로 두고 별도 acceptance 문서를 만들며, 동결 후 정정은 새 문서와 `supersedes`로 남긴다.

## 2. 읽는 법과 적용 구성

증거 표기: **[코드]** 해당 SHA에서 직접 확인, **[재현]** 원본 Python 함수에 합성 입력을 넣어 확인, **[기록]** 기존 실습/이슈에 남은 관측, **[추론]** 그 조건이 연결될 때 가능한 결과. 현장 주기·발생률·지연·물리 공차는 이번에 **미측정**이다. 합성 입력의 시간·좌표는 현장 측정값이 아니다.

위험도 P0는 acceptance의 합격 근거 또는 이동 인터락을 직접 무효화할 수 있는 것, P1은 특정 구성·동시성·표시 의존 시 거짓 정상으로 연결되는 것이다. 순서는 대응 우선순위이며 발생 확률 점수가 아니다. “이슈 없음”은 이 감사에서 대응 번호를 확인하지 못했고 새 이슈를 등록하지 않았다는 뜻이다.

| 구성 | 코드에서 확인되는 선택 | 이번 감사에서의 의미 |
| --- | --- | --- |
| 기본 `stub_loop.launch.py` | fleet/arm/detector/sim/M0609 스텁 기본 사용, cabinet 관측 발행 기본 켬 | 논리 계약 시험. 물리 도착·파지·안착의 증거가 아님 |
| `demo_v2.sh`의 emptyworld 경로 | 실제 fleet·UR5와 `use_ur5=true`; `emulate_m0609=false`, `use_stub_m0609=false`; `stub_sim`과 cabinet 발행은 별도 해제하지 않음 | “실제 arm을 켰으니 진실 신호도 전부 실제”가 성립하지 않음. F02/F03 적용 후보 |
| 센서 옵션을 켠 ROS 경로 | `P3_SIM_SENSORS` 기본 0, 켜면 sim 센서·adapter 배선 추가 | 검출 주체를 명시할 수 있으나 stage truth 기반 검출과 카메라 인식 성능은 구분해야 함 |
| stage 내부 UR5 selfdemo | stage가 직접 동작하고 slot 진행 | ROS `PickPouch`·검출·TF·epoch 경로를 통과했다는 근거로 사용 불가 |

위 표는 저장소의 실행 조합이다. 마스터에서 **지금 떠 있는 조합**으로 단정하지 않는다. 출처: [launch:63][launch63], [launch:110][launch110], [launch:227][launch227], [demo:76][demo76], [demo:203][demo203].

## 3. 위험도 순 목록

| ID·위험도·추적 | 어디 | 무엇을 가리나 | 언제 드러나나·현재 구성 | 지금 상태 | 어떻게 잡나 | 무엇을 가리고 있나 |
| --- | --- | --- | --- | --- | --- | --- |
| **F01 P0** 판정 카운터가 완료·증거를 대신함. 이슈 없음 | [judge:63][judge63], [243][judge243], [303][judge303], [356][judge356], [470][judge470] | 미완료 요청도 `laps`; 로그 부재는 오류/낙하 0; 순서 불일치는 출력해도 gate에 미반영. cabinet 행 수는 고유 성공 주문 수가 아님 | 해당 도구를 acceptance 판정으로 쓰면 즉시. 예시 YAML과 별도 순서 기준으로 각각 재현. 실제 채택 여부 미확인 | **열림·재현**. 예시가 최종 기준이 아니라는 경고는 있으나 도구는 반례를 허용 | 완료·주문 종결·기한·epoch·request를 결합한 시행 판정. 필수 증거 누락은 합격 불가. 중복/사용 불가 관측 제외. 순서 검증 결과를 판정에 연결 | 이 도구를 고치면 뒤의 물리 실패, 누락 로그, aborted/timeout 시행이 비로소 집계에 나타남 |
| **F02 P0** 실제 UR5와 스텁이 같은 holding을 발행. 이슈 없음 | [stub_sim:105][stubsim105], [157][stubsim157], [243][stubsim243], [arm:414][arm414], [stage:2151][stage2151], [demo:203][demo203] | 실제 파지/낙하 신호에 노드 이벤트로 만든 bool이 섞임. 최근 콜백이 물리 관측인지 구별 못함 | emptyworld recipe의 실제 UR5 + 남아 있는 `stub_sim` + bool 관측. 실제 동시 발행·도착 순서는 L3 미측정 | **열려 있으나 통신 순서에 따라 잠복**. `emulate_m0609=false`로 해결되지 않음 | holding 발행자 1개 및 출처 고정. 실제 holding=false와 스텁 true를 엇갈려 넣는 음성 시험. 명령 seq가 있는 관측도 실효 설정 확인 | 신호 오염을 제거하면 실제 미파지·중간 낙하·센서 중단과 F07이 드러남 |
| **F03 P0** 기대값에서 만들어 낸 cabinet 관측. **INT-3 관련** | [stub_sim:243][stubsim243], [run_log:67][runlog67], [judge:303][judge303] | `POUCH_PLACED`를 받으면 주문 풀의 기대 cabinet ID로 `present=true` 생성. 실제 물체 없음도 SUCCESS 근거가 될 수 있음 | `publish_cabinet=true`인 스텁 또는 혼합 조합. 기본 launch와 emptyworld recipe에 남아 있음 | **열림**. 스텁 단독 논리 시험은 의도된 모사지만 acceptance에 그대로 사용하면 가짜 성공 | 실제 물체를 제거하고 운영 이벤트만 주입했을 때 성공 금지. 기대 목적지 조회와 실제 위치 관측 출처 분리 | 독립 관측으로 바꾸면 F04의 유지 확인 부재, INT-3 목적지 검증, 검출 공급자 부재가 드러남 |
| **F04 P0** 한 번의 present가 영구 성공 근거. **INT-3 인접, 유지 판정 이슈 없음** | [run_log:115][runlog115], [129][runlog129], [CabinetObservation:1][cabinet1] | 올바른 보관함에 잠깐 들어갔다가 빠져도 뒤의 false가 성공을 취소하지 않음. 센서 중단도 지속 보관의 증거가 아님 | 독립 evaluator여도 동일 주문의 true→false. 같은 정확한 cabinet으로 **재현**하여 오배송과 분리 | **열림**. “한 번 관측”인 현 계약 구현과 “안정 보관” 요구 사이의 설계 간극 | 해제 후 지정 관측 구간의 최신 상태·지속 존재·낙하를 판정. 관측 소실은 미측정. 동일 주문 관측을 시행/해제와 상관시킴 | 지속 관측을 요구하면 놓은 뒤 미끄러짐, 관측 끊김, 과거 샘플 재사용이 드러남 |
| **F05 P0** M0609 완료가 안착을 증명하지 않음. **#397, #392** | [m0609:1290][m06091290], [1501][m06091501], [refill:132][refill132], [stage:1556][stage1556] | 해제·절차 종료 후 OK를 내고 planner는 선반 데이터로 재고를 채움. 투입구에 안정적으로 남았다는 독립 확인 없음 | 실제 M0609 보충. #397에 투입구 판정 뒤 바닥 접촉과 OK의 공존이 기록됨. 이번 L3 미실행 | **열림**. #397/#392 open. #391 기능·#395 문서 병합은 이 결함의 닫힘이 아님 | release 시점 target 판정 이후에도 안정 구간·바닥 접촉·대상 슬롯 실재 확인. 실패 시 논리 재고 증가 금지. 복구는 별도 검증 | 낙하를 실패로 돌리면 #392 복구/재시도, 선반 소비와 재고 정합성, F11의 실패 표시가 드러남 |
| **F06 P0** UR5 명령 전송 완료를 이동 완료로 간주. 이슈 없음 | [arm:574][arm574], [686][arm686], [702][arm702] | fresh 관절값이 계속 와도 팔이 정지·지연된 경우 목표 수렴 없이 `move_to=True`; `ARM_HOME` 이벤트까지 가능 | 실제 UR5 command 경로. fresh지만 움직이지 않는 관절을 모델링한 원본 메서드 **재현**. 실물 빈도 미측정 | **열림**. joint freshness 검사 자체는 있음. `at_home` heartbeat는 실제 관절 비교이므로 별도 차단 가능 | 새 관절/TCP 값이 목표 공차에 수렴하고 유지되는지 확인. fresh 정지 샘플·제어기 명령 미수행 음성 시험 | 이동 수렴을 검사하면 IK/좌표계/제어기 추종 문제가 드러남. F07/F03이 함께 있으면 이전에는 놓기까지 정상처럼 이어질 수 있음 |
| **F07 P0** bool 파지와 시간 기반 해제. 기존 사례 5, 이슈 없음 | [arm:218][arm218], [627][arm627], [1082][arm1082], [1256][arm1256], [111][arm111] | 닫기 전부터 true였던 holding을 새 파지로 인정. bool 관측 소실은 drop도 feedback_lost도 아님. 열기 후 0.3초로 완료 가능 | 기본 bool + placement 검사 기본 꺼짐. state/placement opt-in 경로와 구별 | **기본 경로 열림·대안 일부 구현**. opt-in 존재를 기본 경로 해결로 판정하지 않음 | 이전 true, 명령 미반영, true 후 단절, 열기 실패, 안착 부재 각각 음성 시험. 명령 seq·freshness·실제 placement 모두 필요 | bool 문제를 닫으면 실제 흡착, 방출, F04 유지, 센서 공급자와 관측 자세 검증이 드러남 |
| **F08 P0** 오래된 정지 누적과 TF로 도착 판정. 이슈 없음 | [fleet:209][fleet209], [362][fleet362], [404][fleet404], [446][fleet446], [488][fleet488], [520][fleet520] | 과거 quiet 누적과 캐시된 목표 위치가 남으면 현재 odom/TF 확인 없이 arrived 가능. 관측 불능을 도착으로 승격 | Nav2 settle 원본 메서드에 odom age 100초와 캐시 목표 pose를 주어 **재현**. waypoints 완료 분기도 같은 freshness 점검 필요 | **열림·단절 시 잠복**. stopped heartbeat와 선택적 DockingState에는 별도 freshness 방어가 있지만 action 결과에 연결되지 않음 | odom·TF를 각각 끊는 시험에서 action 성공 금지. 정지 누적을 연속 fresh 구간으로 제한하고 같은 판정을 결과에 사용 | 강화하면 TF/odom 공급 중단이 정상 복귀 뒤에 숨지 않음. 다음은 소실 시 취소·재시도·복귀 정책 |
| **F09 P0** 누락된 UR5 home 값이 정상 영점. 기존 사례 4, 이슈 없음 | [arm:163][arm163], [276][arm276], [558][arm558], [launch:63][launch63] | 미설정과 측정된 0×6을 구분 못함. 0 자세 fresh 관절은 home=true가 되어 fleet 인터락 통과 가능 | home 필드를 생략한 외부 파라미터 파일. launch는 실제 UR5의 파일명 존재를 요구하지만 실측 home 내용을 증명하지 않음 | **미설정 경로 열림·현장 실효값 미확인**. 저장소 어디에도 home이 없다는 과거 문장은 그대로 재사용하지 않음 | 필드 생략·영점 초기 상태 음성 시험. 도킹 상태에서 측정·검토한 홈과 장착/충돌 조건을 inventory에 고정 | home을 바로잡으면 팔 실제 장착 위치, 주행 시 간섭, 홈 복귀 실패가 드러남. 임의 숫자로 채워서는 안 됨 |
| **F10 P1** 벨트 미측정 속도→0, 소실→비어 있음. 기존 사례 6, 이슈 없음 | [stage:1222][stage1222], [belt:1][belt1], [stage:178][stage178] | 속도 미취득이 정지로 전달되고, fail-closed 미사용 시 물체 소실이 정상 빈 벨트처럼 보임 | `--belt-fail-closed` 기본 끔. 같은 끝 위치에 speed=0 대 None을 주어 at_end 차이 **재현** | **기본 경로 열림·opt-in 방어 있음** | 속도만 누락, pose 소실, 벨트 밖 이탈 각각 관측 UNKNOWN/실패 유지. 잘못된 at_end로 다음 단계 진입 금지 | 벨트가 unknown을 유지하면 공급·검출/픽 배선 부족이 즉시 드러남. 단독으로 전체 배송 성공을 보장하는 결함은 아님 |
| **F11 P1** 보충 종결 누락과 품목 간 상태 덮어쓰기. 기존 사례 7 + 신규 교차 사례, 이슈 없음 | [refill:170][refill170], [web state:290][state290], [alarms:277][alarms277] | 3회 포기 후 명시 terminal이 없고, A·B 요청 뒤 A DONE 한 건이 B의 보충 중 표시와 지연 알람까지 지움 | 복수 품목 요청 가능. A request→B request→A done, B paused, 120초 초과 합성 사례 **재현** | **열림**. 단일 미완료에는 기존 지연 REFILL_FAILED 알람이 있으므로 “실패 표시가 전혀 없음”은 부정확 | 품목/goal별 pending 집합과 terminal 추적. A 성공+B 실패, 3회 포기, clock 중단 각각 시험. sim timeout과 wall watchdog 분리 | UI를 고치면 실제 재고 부족과 #392 복구 불능이 지속 표시됨. 한 성공이 전체 회복이라는 착시 제거 |
| **F12 P1** 과거 DOCKED가 현재 웹 trip을 닫음. 이슈 없음 | [web state:105][state105], [158][state158], [235][state235], [ros_spec:75][rosspec75] | epoch 숫자는 최신으로 유지하면서 이전 request의 종료 이벤트가 현재 작업 표시를 지움 | epoch2 새 요청 뒤 epoch1 옛 DOCKED 지연 수신. **재현** 결과 epoch2 유지, trip=None | **열려 있으나 지연/재연결 때 잠복**. core FSM 성공을 직접 바꾸지는 않음 | 이전 epoch와 다른 request의 terminal을 각각 주입해 현재 trip 유지. UI 완료를 물리 성공 증거로 쓰지 않음 | freshness를 적용하면 실제 진행 중/멈춘 작업이 드러남. 재연결 snapshot·이벤트 정렬 문제가 다음 경계 |
| **F13 P1** 스텁의 물리 거부·시간·실패 차이. 기존 사례 1, 이슈 없음 | [stub_fleet:30][stubfleet30], [76][stubfleet76], [stub_arm:250][stubarm250], [stub_detector:51][stubdetector51], [stub_sim:265][stubsim265] | zones 파일에 없는 형식상 zone, 도달 불가 자세, 없는 물체/캐니스터의 실제 물리 실패를 합성 경로가 보증하지 않음. 주행 시간은 거리와 무관한 기본 1초 | 해당 use_stub 플래그가 켜진 구간. 스텁들도 인터락·취소·리셋 검사가 일부 있으므로 “아무 입력이나 성공”은 아님 | **의도된 모사·최종 증거로 쓰면 열림** | 실제/스텁의 거부 입력 차이를 비교하고 성능 수치·물리 실패 커버리지를 따로 기록. 스텁 성공을 실제 성공 분자에 합치지 않음 | 실제 경로로 교체하면 zone membership, IK, 실제 검출, rail/home 복구가 순서대로 나타남 |
| **F14 P1** selfdemo 성적을 ROS 경로 성적으로 승격. 기존 사례 9, 이슈 없음 | [stage:1892][stage1892], [1942][stage1942], [1956][stage1956], [demo:76][demo76], [stub_detector:51][stubdetector51] | 내부 직접 픽은 성공해도 ROS의 검출 공급·액션·TF·순서 경로는 미검증. selfdemo는 TIMEOUT 후에도 phase/slot을 진행하므로 시도 수와 성공 수도 다름 | stage selfdemo 기록을 ROS 5/5의 근거로 사용하거나 검출 주체 없는 조합을 실행할 때 | **경로 혼동 위험 열림·ROS 센서 배선 일부 구현**. 과거 5/5 자체를 조작된 수치라고 판단하지 않음 | 실제 launch inventory와 ROS action 결과·검출 토픽·stage 관측을 같은 run에서 연결. TIMEOUT·in_slot=false는 시도 완료와 성공을 구분 | 실제 ROS 경로를 돌리면 검출 부재 다음에 F06/F07, 장착 좌표계·DECK source slot 문제가 드러남 |
| **C01 닫힘(소스/L1)** 두 번째 침상 누락. 기존 사례 8, 대응 이슈 번호 미확인 | [trip_fsm:922][trip922], [test_trip_fsm:530][triptest530] | 첫 침상 후 다음 이동 없이 종료하던 분기 | 현재 코드는 다음 stop이 있으면 DEPARTING. 두 침상 이동/인증·첫 침상 인증 실패/낙하·미적재 skip·같은 침상 복수 주문 시험 있음 | **해당 FSM 분기 닫힘**. 관련 순수 시험 본문 9개 직접 실행 통과. 실제 ROS/물리 2침상 완주는 미실행 | 아래 9개 사례의 회귀 유지 + 실제 두 목적지/두 물체로 L2/L3 | 다음은 `SOURCE_DECK`의 source_slot 전달 및 실제 두 번째 물체 선택. 병실 이동 분기 수정만으로 다중 물체 조작까지 닫히지 않음 |

### 3.1 기존 아홉 사례를 현재 SHA에서 다시 분류

| 원래 사례 | 현재 판단 |
| --- | --- |
| 1. zones 없는 스텁 주행 | 여전히 파일 membership 대신 형식 검사. F13 |
| 2. 동어반복 스텁 evaluator | 여전히 주문 풀에서 관측 cabinet을 구성. F03 |
| 3. 오배송 SUCCESS | INT-3 미해결과 연결. 이 문서의 반례 시나리오에서는 오배송을 제외 |
| 4. home 0×6 | UR5 누락 기본값은 남음. 실효 파라미터와 측정 파일은 현장 확인 필요. F09 |
| 5. 시간 해제·과거 holding | 기본 bool 경로 남음. state/placement 대안 존재를 구별. F07 |
| 6. 벨트 0·소실 | fail-closed 옵션은 있으나 기본 경로 남음. F10 |
| 7. 보충 실패 표시 | 포기 terminal 누락은 남음. 단일 요청 지연 알람은 이미 있음. 복수 요청에는 더 강한 은폐 반례 F11 |
| 8. 두 번째 침상 | 현재 FSM 수정 및 음성/복수 시험 확인. C01. 물리 통합 검증은 별도 |
| 9. selfdemo와 ROS 검출 공백 | ROS 센서 배선이 생겼어도 그 실행 증거가 필요. selfdemo→ROS 성적 전이는 불가. F14 |

## 4. 재현 결과와 해석의 경계

합성 probe는 제품 소스를 고치지 않고 원본 순수 함수를 호출했다. ROS import가 필요한 `ArmNode.move_to`와 `FleetNode._check_settled`는 AST로 해당 메서드 본문만 추출하고 입력 객체를 대체했다. 따라서 **분기의 반례**이며 ROS 스케줄링, 실제 actuator, TF 수명, 물리 성공률을 재현한 것은 아니다.

| Probe | 입력·호출 | 실제 출력 | 입증하는 범위 |
| --- | --- | --- | --- |
| J1 | 이벤트 3개 모두 REQUEST_ACCEPTED, 서로 다른 request. 그 외 run 파일·6종 로그 없음. 예시 YAML로 `judge.main` | exit=0, laps=3, 세 trip 모두 end_stamp=null. 모든 활성 gate true | 완료 없이 예시 판정 통과. 필수 증거 존재 여부 미반영 |
| J2 | 실제 ACCEPTED→DOCKED, 기준 ACCEPTED→LOAD_DONE→DOCKED, laps min=1 | mismatch={at:1, expected:LOAD_DONE, got:DOCKED}, exit=0 | 순서 오류를 알아도 실패 종료하지 않음 |
| J3 | 동일 주문 present=true 행 3개, 모두 used=false·pre_reset=true | cabinet_present=3, 고유 주문=1 | 성공 주문 수 대신 raw 관측 행 수 집계. 예시에서 이 gate는 주석 상태이므로 활성화 시 위험 |
| L1 | 같은 정확한 cabinet에서 true 다음 false | observed=true, state=SUCCESS 유지 | 오배송 없이도 보관 유지 실패를 은폐 |
| N1 | `_check_settled`: 캐시 pose=목표, quiet 충족, odom age=100초 | settle_message=arrived, event set | action settle 분기가 odom age를 사용하지 않음. 100초는 합성값 |
| M1 | `move_to`: 측정 관절은 계속 0, 목표는 각 0.1 rad, 송신·시간 대기 함수 성공 | commands_sent=4, returned=true, measured_joints=0×6 | 최종 수렴 검사가 없음. 송신 함수의 freshness 검사 자체를 부정하는 시험은 아님 |
| W1 | A 요청→B 요청→A 완료, B paused. now=200, timeout=120 | refilling=(false, []), alarms=[] | 한 요청의 완료가 다른 미완료와 지연 알람을 가림 |
| W2 | epoch2/new ACCEPTED 후 epoch1/old DOCKED | epoch=2, trip=None | epoch 최대값 유지 시험으로는 stale side effect를 잡지 못함 |
| B1 | 동일 벨트 끝 pose를 관측; 속도만 0 또는 None | 0이면 at_end=true, None이면 false | missing→0 변환이 정상 정지 판정을 만들어냄 |

추가 경계: 기존 낙하 fixture의 `touch` impulse만 0으로 바꾸면 `drops`가 1→0이 된다([judge:165][judge165]). **0 impulse가 실제 낙하를 뜻하는지는 이번에 미측정**이므로 독립 결함 수에 넣지 않았다. 다만 접촉 로그 의미와 완전성을 먼저 정의해야 “drops=0”을 사용할 수 있다. contact watcher가 없거나 로그가 없어서 0인 경우는 F01의 미측정 문제다.

### 4.1 판정기 핵심 반례를 다시 실행하는 방법

기준 SHA를 checkout한 저장소 루트에서 다음을 실행한다. 임시 디렉터리 외에 쓰지 않는다. 이 입력은 실제 run 기록이 아니라 음성 시험용이다.

```bash
python3 - <<'PY'
import json
import pathlib
import subprocess
import tempfile

with tempfile.TemporaryDirectory() as temp:
    root = pathlib.Path(temp)
    run = root / 'run'
    run.mkdir()
    events = [dict(name='REQUEST_ACCEPTED', request_id=f'r{i}',
                   epoch=1, stamp=float(i), stale=False) for i in range(3)]
    (run / 'events.jsonl').write_text(
        ''.join(json.dumps(row) + '\n' for row in events))
    result = subprocess.run([
        'python3', 'tools/judge_run.py', '--logs', str(root),
        '--stamp', 'missing', '--run', str(run),
        '--criteria', 'tools/judge_criteria.example.yaml',
    ], check=False)
    print('exit_code =', result.returncode)
PY
```

이 감사에서 출력된 결과는 `laps=3`, 활성 gate 전부 통과, `exit_code = 0`이다. 기대하는 수정 후 결과는 완료 0건 및 증거 불충분으로 **합격 불가**다. 숫자 3은 저장소 예시 YAML의 값을 재현한 것이며, 최종 acceptance 시행 수를 새로 승인한 것이 아니다.

## 5. 시험이 있는데 그 경로는 비어 있는 곳

| 시험군 | 이미 확인하는 것 | 이 감사에서 빠져 있거나 별도 검증이 필요한 경로 |
| --- | --- | --- |
| `tests/test_judge_run.py` | 파서·미완료 trip 표현·순서 mismatch·로그 부재 처리 | 그 결과가 최종 합격/exit code를 반드시 막는지. 현재 30개 통과와 J1/J2 거짓 통과가 공존 |
| `test_ur5_pick_characterization.py` | 모션을 대체한 기본 bool 흐름, 기존 완료/취소/낙하 동작 | 파일 자체가 현행 동작의 characterization이라고 명시. 실제 추종/안착의 정답 시험으로 승격 불가 |
| `test_ur5_pick_gripper_state.py`, `test_ur5_pick_placement.py` | opt-in 관측·placement의 음성 사례 | 실제 launch에서 해당 모드 활성, 단일 관측 공급자, 카메라/관측 자세, ROS 동시성 |
| navigation `test_docking_state.py` | stale odom을 UNKNOWN으로 만드는 보조 관측 판정 | 실제 `GoToZone` 성공 분기도 같은 UNKNOWN을 따르는지. F08의 분기가 별개 |
| 웹 refill/state 시험 | 단일 보충, epoch 최대값·표시·정렬 등 | A/B 겹침에서 한 DONE, 기존 epoch DOCKED의 현재 상태 변경, 3회 포기 terminal |
| trip FSM batch 시험 | 다음 침상 이동, 인증, 낙하·미적재 분기까지 확장됨 | 실제 ROS 두 대상 실행, DECK source 선택, 서로 다른 물체를 집는 증거 |
| stub loop 시험 | 스텁 계약 순서·인터락·리셋 등 논리 경로 | 실제 물리의 거부 입력·이동 시간·낙하·센서 단절. 스텁의 기대 성공 자체로는 잡을 수 없음 |

직접 실행한 C01 시험 본문 9개는 `test_batch_room_makes_one_stop_per_bed`, `test_batch_ward_makes_one_station_stop`, `test_batch_room_moves_and_authenticates_at_every_bed`, `test_batch_room_first_bed_done_sends_the_next_move_not_the_next_pick`, `test_batch_room_auth_failure_at_first_bed_still_visits_the_second`, `test_batch_room_dropped_pouch_at_first_bed_still_moves_before_the_next_pick`, `test_batch_room_skips_a_bed_whose_order_was_not_loaded`, `test_batch_room_two_orders_for_one_bed_authenticate_once`, `test_batch_ward_authenticates_the_station_once_and_places_every_order`다. pytest 전체 suite 실행 수치가 아니라, 원본의 순수 함수·도우미를 로드해 이 9개 assert 본문을 호출한 결과다.

“음성 시험이 하나도 없다”는 식으로 패키지를 통째로 평가하지 않았다. 새 방어와 그 시험이 있어도 **기본 경로·실효 설정·호출 경계까지 연결되는지**가 이번 감사의 초점이다.

## 6. 지시문 1에 넣을 비오배송 반례 시나리오

아래의 “통과”는 잘못 설계된 acceptance 또는 기존 신호를 그대로 합격으로 사용했을 때의 반례다. 아직 채택되지 않은 최종 protocol이 실제로 통과했다고 주장하지 않는다.

| 시나리오 | 기존 신호만 보면 왜 통과하는가 | 실제로 안 된 것 | protocol 차단 문구 |
| --- | --- | --- | --- |
| **S1. 출발만 세 번**: reset 후 요청들을 시작하고 완료 전에 기록 중단. 나머지 로그 누락 | `laps>=3`, drops/errors=0, exit=0(F01) | 종료된 트립·주문 0건 | “성공 분자는 같은 시행에서 시작·종결·주문 결과·제한시간을 모두 충족한 경우만 센다. 미완료와 증거 누락은 합격이 아니다.” |
| **S2. 팔은 안 움직였는데 적재 완료**: fresh 관절은 고정, 송신 성공; 과거/스텁 holding=true; 해제 명령만 발행 | `move_to` 성공, bool hold 통과, 0.3초 후 POUCH_LOADED(F02/F06/F07) | 대상 물체의 실제 이송·해제·상판 안착 | “명령 이후의 독립 관측으로 목표 수렴·새 파지·해제·대상 칸 잔류를 확인한다. 이벤트만으로 물리 적재를 인정하지 않는다.” |
| **S3. 정확한 보관함에 잠깐 들어갔다가 빠짐**: 올바른 cabinet true 다음 false | ledger SUCCESS 유지; 반복 true는 카운터도 부풀릴 수 있음(F04/F01) | 보관 상태의 유지. 오배송이 아님 | “한 프레임 present로 성공을 확정하지 않는다. 사전 고정한 해제 후 관측 구간에 존재·낙하 없음이 확인돼야 한다.” |
| **S4. 바닥의 캐니스터, 채워진 소프트웨어 재고**: release 때 target=module, 그 뒤 낙하 | REFILL_DONE/OK 후 inventory refill(F05). 누락된 contact 로그라면 drops=0(F01) | 실제 투입구 안착·후속 배출 가능 재고 | “REFILL_DONE은 절차 주장이다. 해당 캐니스터·슬롯의 안정 안착을 독립 확인하기 전에는 보충 성공으로 세지 않는다.” |
| **S5. 관측이 끊긴 복귀를 도착으로 인정**: 마지막 TF는 목표, quiet 누적 뒤 odom/TF 중단 | cached pose·quiet로 arrived, 상위에서 DOCKED(F08) | 판정 시점의 실제 위치·정지 확인 | “도착은 같은 판정 창의 fresh TF와 odom으로 확인한다. 어느 하나라도 소실되면 도착 성공을 내지 않는다.” |
| **S6. A 보충만 끝났는데 전체 정상 화면**: A/B 요청 후 A만 완료 | refilling=false, B 지연 알람 없음(F11) | B 재고 회복·보충 종결 | “보충의 성공·실패·미완료를 품목/goal별로 판정한다. 다른 품목의 완료는 미완료 항목을 해소하지 않는다.” |

S1·S3·S5·S6은 위 합성 probe로 해당 판정/표시 분기를 직접 확인했다. S2는 개별 확인된 분기들을 연결한 **통합 반례 설계**이며 L2/L3 미실행이다. S4의 실제 낙하와 OK 공존은 #397의 **기존 기록**이며 이번 재실행 결과가 아니다.

### 6.1 protocol에 넣을 공통 조항 초안

1. **출처:** 실행 SHA, 기동 시각, install/cache 식별, effective parameters, stage/asset/config 식별, 각 action 서버·관측 토픽의 발행자와 stub 여부를 시행 묶음의 원본으로 남긴다. 구성 변경 뒤의 결과는 같은 성공률로 합치지 않는다.
2. **시행:** reset barrier 이후의 epoch와 request/order를 묶는다. request 없는 arm/stage 이벤트는 사전 정의한 epoch·order 상관 규칙으로만 연결한다. 이전 epoch·다른 request의 terminal은 현재 시행을 닫지 못한다.
3. **완료와 성공:** 시작 건수, 종료 건수, 성공 건수를 별도로 센다. 모든 대상 주문의 요구 결과, 종료 사건, 기한을 확인한다. aborted/timeout/failed는 정한 분모에서 사후 삭제하지 않는다. 자료 부족은 이유와 함께 미판정으로 남기고 성공으로 세지 않는다.
4. **증거 완전성:** 필수 파일·관측 기간·발행자/collector 생존을 확인한다. `없음`, `끊김`, `검사 꺼짐`은 측정된 0이 아니다. empty cabinet 로그가 정상인 pharmacy-only와 병동 안착 평가를 구별한다.
5. **물리 사실:** 제어 명령과 ACK, 운영 노드의 완료 이벤트, evaluator 관측을 분리한다. 실제 위치·파지·해제·안착은 명령 이후의 fresh 관측으로 확인한다. stage truth는 Isaac 상태 확인의 근거이고 실물 카메라 성능의 근거가 아니다.
6. **안착:** 해제 후 유지 구간과 허용 공차를 실행 결과를 보기 전에 고정한다. 적합한 수치는 현장 측정·설계 확인 전까지 **미측정**이다. 숫자를 임의로 채우거나 관측 없이 0.3초를 안정성 기준으로 재사용하지 않는다.
7. **범위:** selfdemo, 스텁 논리 통합, ROS/Isaac 통합, 실제 하드웨어 성능은 각각 검증 범위를 적는다. 제외한 보충·병동·다중 대상 기능을 최종 성공 설명에 다시 포함하지 않는다.
8. **판정기 검증:** S1-S6 및 실제 범위의 거부·타임아웃·취소·reset 음성 사례가 합격을 만들지 않는지 확인한다. 최종 N·성공률·시간 한계는 지시문 1에서 승인한 값과 연결하고, 예시 YAML의 수치를 승인값으로 대신하지 않는다.

## 7. 반복 패턴 이름과 코드 읽기 도구

| 패턴 이름 | 같은 문제를 의심할 코드 | 확인 질문·음성 입력 |
| --- | --- | --- |
| **명령 완료를 사실 완료로 바꾸기** | publish/ACK→sleep→OK, interpolation loop 종료→ARRIVED | 명령을 버리고 fresh 센서만 계속 보내도 성공하는가? F05-F07 |
| **미측정을 정상값으로 채우기** | `None→0`, missing file→빈 목록, 기본 false로 guard 끄기 | 센서/로그를 하나씩 제거했을 때 fail/unknown인가, 정상 0인가? F01/F09/F10 |
| **정답을 공유하는 평가기** | 기대값과 관측값이 같은 pool/config/event에서 생성 | 물체를 없애고 운영 이벤트만 내도 기대 위치 present가 생기는가? F03 |
| **한 번 참이면 영원히 참** | true만 저장, false/timeout 미반영, 누적 quiet 미초기화 | true→false와 true→silence를 넣었을 때 성공 근거가 사라지는가? F04/F08 |
| **같은 토픽의 서로 다른 진실** | real 노드 켜도 stub publisher 생존, bool 최근값 덮어쓰기 | `ros2 topic info -v`와 실행 inventory가 물리 관측 공급자를 하나로 특정하는가? F02 |
| **마지막 한 건이 전체를 대표** | 전역 refilling bool, latest request 뒤 아무 DONE, epoch=max와 무조건 side effect | A/B 겹침, 옛 epoch terminal, 다른 request terminal을 넣는가? F11/F12 |
| **보조 검사는 엄격하고 성공 경로는 관대** | diagnostic UNKNOWN은 계산하지만 action result는 다른 조건 | 엄격한 함수가 실제 succeed/return OK 호출을 지배하는가? F08 |
| **행 수를 성공 수로 부르기** | `len(events)`, `len(trips)`, repeated present count | 고유 대상·완료·새 epoch·used 여부·기한을 확인했는가? F01 |
| **동작 기록 시험을 정답 시험으로 읽기** | characterization, mock motion=True, 직접 stage 경로 | 기존 버그를 유지해도 시험이 초록인가? 실제 배포 경로의 실패 입력을 넣었는가? F07/F14 |
| **수정된 분기 뒤에 남은 다른 대상** | 1→2 반복 확장, target은 바꾸지만 source slot/관측은 상수 | 두 번째 목적지뿐 아니라 두 번째 물체를 실제로 선택했는가? C01 |

찾는 순서는 `SUCCESS/OK/arrived/REFILL_DONE/POUCH_PLACED/at_home`을 내는 모든 지점에서 **뒤로** 올라가, 마지막으로 읽은 독립 관측·그 시각·대상 식별자·미측정 분기를 확인하는 것이다. 그 다음 기본 launch와 실효 옵션까지 내려가 그 방어가 실제 켜지는지 본다. 각 성공 조건에는 “직전 명령이 실행되지 않았을 때도 이 조건이 참인가?”라는 반례를 붙인다.

## 8. 조사 범위·검증과 미확인 사항

| 영역 | 확인한 연결 | 남은 한계 |
| --- | --- | --- |
| `src/rokey_p3_*/` | 성공/기본값/시간/누락 검색 후 trip FSM, ledger, refill planner, arm/M0609, fleet/base 경계, detector, bringup launch/stubs/adapter 추적 | 모든 분기 전수 실행은 아님. ROS runtime 미설치 |
| `sim/standalone/pharmacy_stage.py`, `p3sim/` | belt 속도·소실, gripper truth, release 판정·respawn, selfdemo/ROS 분리 | 물리 궤적·contact·장착 상태 현장 미측정 |
| `web/backend/` | ROS 변환→순수 상태 반영→trip/refill→alarm | 브라우저/실시간 ROS 재연결 미실행 |
| 계약 v1·pilot·실습 12/13/14/19/20 | 성공 주장과 관측 분리, reset/시계, 스텁과 실제 조합, 기존 문제 노출 경위 대조 | 실습 원본 외부 로그를 이번에 재취득하지 않음. 문서 기록을 새 실측으로 취급하지 않음 |
| 패키지 `test/`, root tests, sim/web tests | 관련 분기·음성 시험·복수 대상 사례의 존재와 실제 호출 경계 검토 | 전체 패키지의 실행 커버리지 수치 없음 |

`isaac_adapter` 전체를 “unknown을 정상으로 바꾸는 변환기”라고 결론내리지는 않았다. 새 센서/상태 경로는 epoch 0·과거 epoch·seq 역행을 거부한다([adapter:349][adapter349], [421][adapter421]). 반면 legacy event 경로의 epoch 보완과 metadata가 적은 bool/CabinetObservation은 별도로 추적해야 한다. 이번에 결정적 반례를 확보하지 않은 adapter 경계를 독립 결함으로 부풀리지 않았다.

기본값이 있다는 이유만으로 전부 결함에 넣지도 않았다. 예를 들어 검출의 불완전한 pose가 실제 arm에서 거부되는 경로는 이미 방어되는 것과 구별했다. 스텁의 취소·리셋·정지 인터락 역시 존재한다. 위 목록은 이들 방어가 있어도 **성공 근거를 우회하거나 정상 표시를 만드는 지점**에 한정했다.

실행 검증:

- `python3 -m unittest discover -s tests -p test_judge_run.py -v`: **30개 통과**.
- 원본 함수에 합성 입력을 넣은 probe: 위 J1-J3/L1/N1/M1/W1-W2/B1의 결과 확인. 테스트용 입력을 운영 run으로 등록하지 않음.
- C01 순수 시험 본문: **9개 통과**. pytest/colcon 전체 실행으로 표시하지 않음.
- `python3 -m unittest discover -s tests`: 168개 실행, **1 error**. `test_demo_v2.test_status_shows_the_tree_at_launch_and_now`가 Git 이력 없는 API 소스 스냅샷에서 `git rev-parse HEAD`를 실행해 실패. 이를 제품 결함이나 전체 통과로 기록하지 않음.
- `python3 tools/check_repository.py`, `python3 tools/evidence.py validate --base origin/main`: 로컬 API 스냅샷에 `.git`이 없어 완료 못 함. 원격 PR의 실제 Git checkout에서 확인 필요.
- `ruff check .`: 로컬 실행 파일 없음으로 미실행. 문서만 변경했으며 원격 CI 결과와 구분.
- ROS L2, `colcon build/test`, Isaac/실물 L3, 9/29 대상 구성의 E2E: **미실행**.

578개 소스 파일은 API tree의 blob SHA와 로컬 내용 일치를 확인했다. 이는 내려받은 소스의 동일성 확인이지 578개 파일의 모든 로직을 검증했다는 뜻이 아니다. 이번 보고서의 위치와 판정은 위 고정 SHA에 한정되며 이후 수정은 새 SHA로 다시 대조한다.

기존 추적 근거: #392 복구 경로, #397 안착 없는 보충 성공, #391 opt-in 레일 선택, #395 경위 문서. INT-3은 저장소의 통합 결함 식별자이며 GitHub 이슈 번호를 임의로 매핑하지 않았다.

## 9. 게시 직전 main 변경 재대조

PR 게시 시 main이 `14dca5a4f0f1e324808c8073e4a10d4d850f34ca`로 전진했다. 위 표의 파일:줄은 최초 감사 SHA `83a2a1f`에 고정한다. 두 SHA 사이의 변경 diff를 확인했으며, 최신 전체 소스를 다시 전수 실행했다는 뜻은 아니다.

- **#439:** 판정기에 도달 단계 표시가 추가됐다. 새 `judge_run.py`로 J1/J2를 다시 실행한 결과 모두 exit=0이다. J1은 이제 **“도달 ① 요청 접수”와 “laps=3 통과”가 동시에 출력**된다. 진단 표시가 늘었지만 F01의 성공 gate 문제는 남는다.
- **#438:** UR5 기준 프레임 축 보정 파라미터와 stage 이름 대조 시험이 추가됐다. F06의 `move_to` 완료 조건, F07의 bool/해제, F09의 home 기본값을 바꾸는 diff는 아니다. 이 수정의 물리 효과는 이번에 미측정이다.
- **#440:** fleet 종료 중 publish/goal 처리 방어가 추가됐다. F08의 관측 freshness 기반 도착 판정을 고친 변경은 아니다.
- **#441:** emptyworld 자동 주문 발행이 기본 꺼짐으로 바뀌었다. 해당 최신 구성에서는 웹/curl 등 명시 요청으로 시행을 시작해야 한다. F02/F03의 stub holding/cabinet 발행 해제는 이 변경에 포함되지 않는다.
- **#436:** adapter와 stage의 QoS·토픽·필드·이벤트 이름 대조 시험이 추가됐다. 이는 필요한 개선이다. 위의 고정 SHA 시험 범위를 최신 SHA의 시험 부재 주장으로 확대하지 않는다.

<!-- Fixed-SHA source references are generated below; line anchors refer to the audited snapshot. -->

[adapter349]: ../../src/rokey_p3_bringup/rokey_p3_bringup/isaac_adapter.py
[adapter421]: ../../src/rokey_p3_bringup/rokey_p3_bringup/isaac_adapter.py
[alarms277]: ../../web/backend/app/alarms.py
[arm1082]: ../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py
[arm111]: ../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py
[arm1256]: ../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py
[arm163]: ../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py
[arm218]: ../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py
[arm276]: ../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py
[arm414]: ../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py
[arm558]: ../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py
[arm574]: ../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py
[arm627]: ../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py
[arm686]: ../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py
[arm702]: ../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py
[belt1]: ../../sim/standalone/p3sim/belt.py
[cabinet1]: ../../src/rokey_p3_interfaces/msg/CabinetObservation.msg
[demo203]: ../../tools/demo_v2.sh
[demo76]: ../../tools/demo_v2.sh
[fleet209]: ../../src/rokey_p3_navigation/rokey_p3_navigation/fleet_node.py
[fleet362]: ../../src/rokey_p3_navigation/rokey_p3_navigation/fleet_node.py
[fleet404]: ../../src/rokey_p3_navigation/rokey_p3_navigation/fleet_node.py
[fleet446]: ../../src/rokey_p3_navigation/rokey_p3_navigation/fleet_node.py
[fleet488]: ../../src/rokey_p3_navigation/rokey_p3_navigation/fleet_node.py
[fleet520]: ../../src/rokey_p3_navigation/rokey_p3_navigation/fleet_node.py
[judge165]: ../../tools/judge_run.py
[judge243]: ../../tools/judge_run.py
[judge303]: ../../tools/judge_run.py
[judge356]: ../../tools/judge_run.py
[judge470]: ../../tools/judge_run.py
[judge63]: ../../tools/judge_run.py
[launch110]: ../../src/rokey_p3_bringup/launch/stub_loop.launch.py
[launch227]: ../../src/rokey_p3_bringup/launch/stub_loop.launch.py
[launch63]: ../../src/rokey_p3_bringup/launch/stub_loop.launch.py
[m06091290]: ../../src/rokey_p3_manipulation/rokey_p3_manipulation/m0609_arm_node.py
[m06091501]: ../../src/rokey_p3_manipulation/rokey_p3_manipulation/m0609_arm_node.py
[refill132]: ../../src/rokey_p3_orchestrator/rokey_p3_orchestrator/refill_planner.py
[refill170]: ../../src/rokey_p3_orchestrator/rokey_p3_orchestrator/refill_planner.py
[rosspec75]: ../../web/backend/app/ros_spec.py
[runlog115]: ../../src/rokey_p3_orchestrator/rokey_p3_orchestrator/run_log.py
[runlog129]: ../../src/rokey_p3_orchestrator/rokey_p3_orchestrator/run_log.py
[runlog67]: ../../src/rokey_p3_orchestrator/rokey_p3_orchestrator/run_log.py
[stage1222]: ../../sim/standalone/pharmacy_stage.py
[stage1556]: ../../sim/standalone/pharmacy_stage.py
[stage178]: ../../sim/standalone/pharmacy_stage.py
[stage1892]: ../../sim/standalone/pharmacy_stage.py
[stage1942]: ../../sim/standalone/pharmacy_stage.py
[stage1956]: ../../sim/standalone/pharmacy_stage.py
[stage2151]: ../../sim/standalone/pharmacy_stage.py
[state105]: ../../web/backend/app/state.py
[state158]: ../../web/backend/app/state.py
[state235]: ../../web/backend/app/state.py
[state290]: ../../web/backend/app/state.py
[stubarm250]: ../../src/rokey_p3_bringup/rokey_p3_bringup/stubs/stub_arm.py
[stubdetector51]: ../../src/rokey_p3_bringup/rokey_p3_bringup/stubs/stub_detector.py
[stubfleet30]: ../../src/rokey_p3_bringup/rokey_p3_bringup/stubs/stub_fleet.py
[stubfleet76]: ../../src/rokey_p3_bringup/rokey_p3_bringup/stubs/stub_fleet.py
[stubsim105]: ../../src/rokey_p3_bringup/rokey_p3_bringup/stubs/stub_sim.py
[stubsim157]: ../../src/rokey_p3_bringup/rokey_p3_bringup/stubs/stub_sim.py
[stubsim243]: ../../src/rokey_p3_bringup/rokey_p3_bringup/stubs/stub_sim.py
[stubsim265]: ../../src/rokey_p3_bringup/rokey_p3_bringup/stubs/stub_sim.py
[trip922]: ../../src/rokey_p3_orchestrator/rokey_p3_orchestrator/trip_fsm.py
[triptest530]: ../../src/rokey_p3_orchestrator/test/test_trip_fsm.py
