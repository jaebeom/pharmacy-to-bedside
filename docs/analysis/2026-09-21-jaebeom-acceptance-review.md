# P3 acceptance protocol 설계 검토

**검토 제안 · 2026-09-21 · reviewer / acceptance-0921**  
수신: 임재범. 기준 `main@4b506c16059e63b0fc706589e3fb2b8abc43132d`. 결정·승인·현장 검증 완료가 아니다. 아래 선택은 모두 승인 이슈·PR·ADR에 남겨야 한다. 실행 규범의 상세·미확정 값은 [protocol 초안](../../experiments/protocols/ward-lap-b-acceptance-v1.json) `purpose` 0-23절에 있다.

**권고: 현재는 동결 보류.** 합격 조건은 독립 물리 관측, 실제 QR, 모집단 완결성이다. B 12/12와 B+ 묶음은 분리한다.

## 직접 확인한 사실과 지시문 보정

- [일정][schedule]의 B+가 병실 2-3침상 묶음이고, 병동 묶음 하역은 C다. B에는 스테이션 **주행**이 있다. 스테이션 QR·하역까지 B인지 해석 승인이 필요하다. 일정에는 P4(9/22-23) 동결, 요청에는 9/22 동결이라고 적혀 있다.
- frozen pilot 1개, run 6개(서로 다른 SHA·구성 각 3개), 리뷰 0개를 확인했다. 6개 모두 manifest상 `lap_success=1`, `lap_s=12.2667-13.2667 s`다. raw는 직접 검증하지 않았다. “전 구간 약 15 s·전환 약 100 s”의 시계·구성·원본은 미확인이다. README의 “실측 없음”은 파일 현황과 어긋난다.
- 현재 [스폰 코드][pouch]에는 이미 `--seed`가 있으며 `(seed, epoch, spawn index)`가 난수 입력이다. “시드 적용 기능 없음”은 과거 pilot 설명이다.
- [run_log][ledger] 순수 로직을 실행해 **잘못된 cabinet / true 뒤 false / ABORT+true** 세 경우 모두 `SUCCESS`를 재현했다. [스텁][stub]은 `POUCH_PLACED`에서 주문 풀의 목적지로 관측을 만든다. 기대값을 따로 기록해도 실제값의 출처를 바꾸지 않으면 동어반복이다.
- [K5 문서][k5]의 sim tag·칸 TF 픽은 실제 카메라 QR을 대신하는 제안이다. B QR 합격 근거로 삼을 수 없다. [검사기][validator]는 threshold 충족·리뷰·모집단을 판정하지 않으며 기존 집계기는 pilot 전용이다.

## A-D 설계 선택 · 이유 · 버린 대안

| 항목 | 제안과 근거 | 버린 대안·이유 |
|---|---|---|
| **A 성공** | 요청의 **모든 주문**에 적재→실제 이동→환자·봉투 QR 검수→물리 전달→잠금→종료→복귀·실제 도킹. 독립 관측으로 정착·DOCKED 때 잔류, controller `DELIVERED`와 일치해야 한다. 인증·관측·잠금 중 하나라도 없으면 실패다. 사람 수령 서명·물리 잠금은 범위 밖이다. | pilot의 `HOLD_RETURN`, `SUCCESS` 문자열, 일회성 `present=true`는 병동 인도를 입증하지 못함. |
| **A 오배송·묶음** | 기대값=승인된 요청·환자/침상 배정 snapshot. 실제값=Isaac 객체 ID·pose·보관함 기하. logger 대조 후 독립 재계산. B+는 별도 protocol: 2·3침상 각 3seed, **6/6 제안**. 시행=요청. 1/3침상 성공은 주문 1/3·트립 0. | 주문 풀에서 actual 목적지를 재생성하거나 침상 수만큼 트립 성공을 부풀리면 안 됨. |
| **B 횟수·연속** | B: 침상 4곳×3seed=**12/12**, 각 사례 3/3. 별도로 스테이션 주행 3/3·A보충 1회·독립 재현 1회. 표본 수는 **근거 없음, 합의로 정함(제안·미합의)**; 범위 확인용이다. “3연속” 대신 등록한 전 회차 무결점. 예정 reset·seed 블록 사이 재기동만 허용. | 성공할 때까지 반복하면 선택 편향. 각 시행이 서로 독립이고 동일한 성공확률을 갖는다고 가정해도, 12/12의 단측 95% 신뢰하한은 77.9%다. 실제 시행이 이 가정을 만족하는지도 입증하지 않았다. 신뢰성 보증으로 부르지 않는다. |
| **B 시간·부분** | 600 s sim trip limit + reset 직전부터 900 s monotonic watchdog은 **미승인 후보**다. 1차 회신 뒤 reset 예산 + sim 한도/RTF 하한 + 최종 관측 예산으로 다시 검토하도록 보강했다(아래 7절). 모든 예산·RTF 하한은 미확정이며 B 실측 근거 없음. 속도 목표는 추가하지 않음. sim/wall/RTF·전환 시간을 분리. 부분은 `k/n` 참고치, 전체는 `NOT_ACCEPTED`. | 15초 기준·RTF 사후 환산·느린 run 제외는 서로 다른 구성을 섞고 실패를 감춤. |
| **C 분모·스텁·사람** | 등록 슬롯 12개 고정. goal 거부·reset 실패·abort·timeout·raw 누락도 합격 분모에서 제거하지 않음. 미시작은 “미실행”으로 표시. 스텁·참값 인식 우회는 별도 `INTEGRATION_ONLY`. 예정 reset/요청 입력·입증된 화면 이동은 허용; active reset·수동 보조는 실패. | 수락된 요청만 세면 거부가 은폐됨. 창 이동을 무조건 실패로 하면 무관한 개입과 동작 보조를 혼동함. |
| **D 재현·리뷰** | 생성 코드·인자·자산 의존성·실제 배치·물리 설정의 canonical scene manifest SHA, 실제 초기 상태 대조. 실제 seed/epoch/index 적용. raw 주·보조 위치와 hash 복구 확인, 모든 artifact 검증, 작성자 외 run별 `verified` 필수. | USD 없음→N/A, seed를 회차로 대용, master01 로컬만 보존, CI 통과=합격은 불허. hash는 진실을 보증하지 않음. |

## E 9/22까지 무엇을 닫아야 하는가

| 게이트 | 9/22 가능성 판단·완료 증거 | 못 닫으면 |
|---|---|---|
| **F0 범위·수·시간·개입·등급 승인** | 문서 정리 가능성 높음. B/스테이션 해석·수치 선택을 승인 PR/ADR에 남김. 승인 자체는 미확인. | `proposed` 유지. |
| **F1 평가 계약·경계·책임** | 설계 가능. 기대/actual 분리·session/epoch·잔류·claim 충돌 처리 명시. `CabinetObservation`에는 epoch가 없어 관측과 시행 정보를 연결하는 별도 기록(sidecar) 등의 설계가 필요하다. 현장 검증 기한 불명. | `proposed` 유지. |
| **F2 관측 공차·seed 범위** | 포함·정착·신선도·도킹 공차, 스폰 범위 **미측정**. 실제 장면/주기에서 근거 확보 필요. 9/22 완료 보장 불가. | 값을 지어내지 말고 동결 보류. |
| **F3 장면·보존·검토 책임** | 해시 규격은 설계 가능. 실제 자산·저장 위치/권한·복구·검토자 확보는 미확인. protocol schema에는 `supersedes` 필드가 없음. | 새 ID의 `purpose`에 supersedes ID/path/hash·이유와 승인 링크. 해결 전 동결 보류. |
| **Q 실행 자격** | INT-3·sticky true 수정/독립 evaluator, 실제 QR·팔·주행, seed·QoS·원본 두 위치, acceptance 집계기와 아래 반증, 보조 게이트의 **L3 미실행**. 9/22 전부 완료 근거 없음. | F가 닫히면 기준만 동결 가능. Q 전에는 본 12회 시작 불가. 일정 초과 시 축소 규격 별도 승인 또는 B 미달 보고. |

## 오배송 외, 설계를 깨는 8개와 반영한 방어

각 행은 **정상 control 통과 + 변형 거부**를 실제 연결과 로그 재생에서 확인해야 한다. 아래는 시험 설계이며 통과 보고가 아니다.

| 반증 | 허술한 protocol의 가짜 성공 | 초안에 반영한 차단 조건 |
|---|---|---|
| **X1 이전 성공 재생** | 새 epoch에 같은 주문 ID, 늦은 관측을 새 성공으로 사용. | session·epoch·object·seq·reset-empty 연결. 오래된 true만으로 실패. |
| **X2 스쳤다 이탈** | 잠깐 present 뒤 낙하·재파지, ABORT인데 성공 유지. | 해제·정착·최종 잔류 및 claim 일치. false/누락/ABORT면 실패. |
| **X3 카메라 없는 인증** | 영상 가림·판독 실패인데 sim tag/expected ID로 AUTH_OK. | 원본 frame·capture TF·실제 decoded ID와 인과. 가림/다른 태그에서 인증 거부·전달 금지. |
| **X4 이동 없는 완료** | 고정 팔·주행 스텁·teleport가 완료 이벤트와 마지막 위치만 만듦. | 연속 pose/custody·실제 정차·motion/command 대조. 허용 spawn/reset 밖 shortcut 금지. |
| **X5 사라진 시행·침상** | 거부·logger crash 삭제, 묶음 첫 침상만 분모로 100%. | 사전 슬롯·기대 주문 전수 대조. 후속 침상 누락 실패; B 표본으로 B+ 합격 주장 금지. |
| **X6 이중·잘못된 작성자** | 참값이 마지막 도착값으로 갈리거나 잘못된 source 하나를 신뢰. | 토픽별 기대 노드·발행자 식별값(GID)·배포 출처와 단일 작성자를 시작·실행 중에 확인한다. JSON 원본 발행과 ROS 메시지 중계(typed relay)는 별도 토픽으로 검사한다. |
| **X7 광고만 하는 작성자** | 발행자가 하나지만 실제 표본이 없다. 보존된 옛 표본(latched)을 새 성공으로 사용한다. | 현재 epoch와 원본 시각·순번(source stamp/seq)의 진행, 수신 간격, 실제 시간(wall) 기준 무수신을 확인한다. 수치와 유예는 동결 전 확정한다. |
| **X8 이름만 맞는 프레임** | 올바른 frame_id에 다른 기준 좌표를 실어 포함으로 오판. | detector 보고값 대신 실제 월드 객체와 보관함 기하·회전·크기 대조, 실제 배치와 manifest 독립 대조. |

**검증:** 기준 소스에서 세 평가 결함을 직접 재현. 동봉 JSON은 동일 기준 `tools/evidence.py::validate_protocol` 통과(`proposed`, `acceptance`, 10개 metric). 물리 실험·artifact 검증·독립 리뷰·운영 집계 구현은 미실행. 제품 코드·기존 frozen 파일은 변경하지 않았다. 이 PR은 설계 문서와 proposed protocol만 추가한다.

[schedule]: ../planning/schedule.md
[pouch]: ../../sim/standalone/p3sim/pouch.py
[ledger]: ../../src/rokey_p3_orchestrator/rokey_p3_orchestrator/run_log.py
[stub]: ../../src/rokey_p3_bringup/rokey_p3_bringup/stubs/stub_sim.py
[k5]: ../architecture/k5-delivery-interface.md
[validator]: ../../tools/evidence.py


## 검토·인계

- 임재범 본인의 결정·승인을 대리 표기하지 않는다. 협업 창구는 #239.
- 원 분석 기준: `4b506c16059e63b0fc706589e3fb2b8abc43132d`.
- PR 작성 기준: `83a2a1f1f94b65240851218ddf965cabebb5b82d`. 두 기준 사이 14개 커밋의 변경 파일 14개는 navigation 영역이며 protocol·schema·평가 원장·pilot·seed 관련 분석 근거는 동일하다.
- 상태: **1차 회신 수신·보완안 재검토 및 사람 결정 대기**. 이 문서의 존재, CI 성공, 검토 동의는 사람 승인·동결·L3 합격을 뜻하지 않는다.

### 1. 현재 v0 작업과 최종 B 판정을 구분해 달라

9/21 실행 계획은 빈월드 고정 경로 주행·시뮬 센서 인증으로 먼저 한 바퀴를 연결하는 순서를 명시한다. 이번 제안은 그 중간 구현을 중단하거나 Nav2/카메라부터 다시 만들라는 지시가 아니다.

- K 단계의 연결 성공은 해당 단계의 관측으로 계속 기록할 수 있다.
- 다만 시뮬 센서 인증 결과로 최종 B의 손 카메라 QR 판독을 검증했다고 쓰지 않자는 제안이다.
- 최종 B도 sim 인증으로 축소하기로 사람이 결정한다면, 변경 범위와 표시할 주장부터 별도 protocol에 기록해야 한다. 현재 제안의 PASS_B 의미를 암묵적으로 바꾸지 않는다.
- 본문의 F0-F3은 이 acceptance 설계의 **동결 선행 조건 표기**다. #239 기존 F0-F4 기능 통합 작업 ID·담당을 재배정하지 않는다.

### 2. 관측·해석·제안을 분리한 재현 근거

동일 소스의 `run_log.OrderLedger`를 직접 호출했다. 아래는 Isaac 실험이 아니라 기존 원장 판정의 순수 Python 재현이다.

| 입력 | 실제 반환 | 해석 | acceptance 제안 |
| --- | --- | --- | --- |
| claim=DELIVERED, cabinet=wrong/cabinet, present=true | SUCCESS, reason 빈 값 | 기대 목적지와 대조하지 않음 | 승인 요청 snapshot 대조 + 실제 위치 기반 evaluator |
| claim=DELIVERED, 동일 cabinet에 true 후 false | SUCCESS, reason 빈 값 | 한 번의 true가 유지됨 | 정착 창과 DOCKED 시 잔류 확인; 이탈·누락은 성공 금지 |
| claim=ABORT, present=true | SUCCESS, reason=claim_disagrees | 제어 종료와 관측이 달라도 SUCCESS | 불일치를 보존하고 이번 acceptance에서는 불합격 |

이 세 결과를 근거로 기존 frozen pilot 또는 과거 SUCCESS 기록을 재작성하지 않는다. 원장 의미를 전역 변경할지, acceptance 전용 판정을 분리할지는 구현 검토 사항이다. 요구하는 것은 최종 acceptance의 가짜 합격 차단이다.

### 3. 다음 일곱 항목에 채택·수정·반박으로 답해 달라

| 검토 항목 | 요청하는 답 | 후속 근거 |
| --- | --- | --- |
| B / B+ / C 경계 | 스테이션은 주행까지인가, 인증·하역까지인가? 최종 QR의 요구 경로는 무엇인가? | schedule·scenario 차이를 승인 이슈/PR/ADR에서 정리 |
| 12/12와 시간 제한 | 4침상×3seed, 600 sim / 900 wall을 수용하는가? 대안이면 근거·표본·분모까지 제시 | 관측에서 역산한 합격선이 아니라 사전 합의로 명시 |
| 독립 평가 | 기대 fixture, actual object/geometry, logger, offline 판정의 책임 경계가 맞는가? | INT-3 및 순간 관측/claim 충돌 검토, 운영 제어로 GT 유출 차단 |
| 관측의 시행 귀속 | epoch 없는 CabinetObservation을 session·object·sequence·source stamp에 어떻게 연결할 것인가? | wire 변경 또는 sidecar 방식 비교; stale replay 거부 증거 |
| 동결 전 수치 | 어떤 담당이 어떤 장면·주기로 포함/정착/신선도/도킹 공차와 spawn 범위를 측정할 것인가? | 수치·단위·근거·측정 자료. 미측정은 그대로 유지 |
| 증거·리뷰 | raw 두 위치·복구 확인·verify-artifacts·독립 reviewer를 누가 맡는가? | 실제 위치/권한과 run별 검토 계획; 기존 pilot 임시 예외와 분리 |
| 반증 5개 | X1-X5 각각 정상 control과 변형 거부를 확인할 최소 실행 순서가 타당한가? 더 쉽게 뚫리는 사례는 없는가? | 새 반증이면 예상 가짜 합격 경로와 최소 수정 조건 제시 |

독립 검토자의 결론에는 대조한 계약 절, 검증 명령/결과, L2 상태, 배선 변경 여부를 함께 적어 달라. 동의하지 않는 항목은 승인처럼 처리하지 말고 이유와 대안을 남겨 달라.

### 4. 검토 후 진행 순서

1. 위 일곱 항목을 검토하고 관련 확인 결과를 이 PR에 모은다. 이 문서는 담당 배정·착수 수락을 대신하지 않는다.
2. 합의된 부분을 proposed 문서/JSON에 반영하고, 사람 결정이 필요한 범위·합격선은 임재범에게 같은 PR에서 올린다.
3. 미측정 값·저장/리뷰 책임·범위 해석이 남으면 proposed를 유지한다. 문서 병합과 protocol freeze는 별개다.
4. 독립 평가·새 집계·seed/scene·증거 보존은 각각 좁은 후속 구현/검증 작업으로 분리한다. 이 PR에서 제품 코드 변경이나 현장 실행을 시작하지 않는다.
5. 기준 동결 뒤 실행 자격 Q를 검증하고, 그 다음 사전 등록 12개 슬롯을 실행한다. 실패·미실행·리뷰 없음은 그대로 보고한다.

### 5. 이 PR의 검증 범위

- 기존 저장소 `tools/evidence.py::validate_protocol`로 proposed JSON 검증: 통과. phase acceptance, 지표 10개, 예정 시행 12개.
- 세 판정 결함의 순수 Python 재현: 완료. Isaac/ROS 동작 확인으로 해석하지 않는다.
- Markdown 경로·이름·물결표 및 새 파일 NUL 검사: PR 게시 전 확인.
- 전체 저장소 검사·unittest·ruff·colcon L1/L2: GitHub CI에서 확인. 이 환경에서는 Git HTTPS 인증이 없어 전체 checkout 검증을 수행하지 못했다. 일부 파일 검사를 전체 저장소 검사로 보고하지 않는다.
- Isaac L3·원본 hash 복구·독립 리뷰: 미실행. X1-X8은 설계만 완료했다.
- 인터페이스·launch·스텁·운영 배선 변경: 없음. 기존 frozen protocol·run·review 수정: 없음.


### 6. 9/21 피드백 처리 현황

문장 검토 댓글의 제안 5건을 반영했다.
권고와 성공 조건을 나누고, 참값·별도 연결 기록을 설명하고, 표의 문장을 다듬었다.
통계 설명은 제안의 “서로 독립”만으로 줄이지 않고 **독립성과 동일한 성공확률**을 함께 명시했다.
12/12의 단측 95% 신뢰하한 77.9%는 이 가정 아래의 값이며 실측 신뢰성 보증이 아니다.

위의 문장 검토 댓글은 일곱 설계 질문에 대한 독립 검토 답변을 대신하지 않는다.
첫 문장 수정 시점에는 항목별 회신이 없었으나, 이후 1차 회신을 수신했다. 아래 7절에서 처리한다.
범위·합격선·공차·증거 보존 책임은 새로 확정하지 않았다. protocol은 proposed다.
추가 문장 제안 1건도 반영했다. 회신 수신과 미결정 해소는 구분한다.

### 7. 1차 회신의 독립 대조와 초안 보강

원문: 일곱 항목 1차 회신.
검토 PR head는 `9c15fd4396707cd4e71883a6b546a6bdef3f8afd`, 추가 코드 기준 main은 `3816edce12388d8af461ec5492ee895eb59eadf7`다.
추가로 읽은 PR과 기준 SHA는 다음과 같다.

- #452: `2fc211285d0fb870e738a110c9680a9a3b5b1275`
- #445: `ef69b81450555bb339ec4c017708431ac6d0292b`

대조 중 #452 head가 `769daff2c35ab50ce5be48a942cb646ee8e48196`로 바뀌었다. 두 SHA의 차이는 `bridge.py`의 CABINET QoS·스키마와 토픽 집합 시험 추가다.
parser·adapter 파일은 바뀌지 않았다. #445 판단은 명시한 SHA의 코드에 한정한다.
회신의 수신은 확인했다. 설계 동의와 사람 승인·구현 완료는 별개다.

| 항목 | 처리 | 근거·초안 반영 | 남은 일 |
| --- | --- | --- | --- |
| 1 범위·QR | 방향 동의, 사람 결정 대기 | schedule의 B는 침상·스테이션 주행과 환자 QR, C는 스테이션 하역이다. scenario에는 스테이션 인증도 있다. sim 인증은 기존 `INTEGRATION_ONLY`로 구분하고 `PASS_B_SIMAUTH`를 승인된 새 등급으로 만들지 않았다. | 최종 QR 경로·스테이션 요구를 임재범이 확정 |
| 2 표본·시간 | 분모 채택, 선행조건·시간식 보완 | 네 침상 요청마다 실제 목적지로 놓는지 Q1에 추가했다. wall 예산은 아래처럼 reset·준비·마지막 관측까지 포함한다. 12회·600/900은 미승인 후보다. | 첫 완주 feasibility 자료, RTF 하한과 각 구간 예산 승인 |
| 3 책임 경계 | 채택, 구현 자격 보류 | 기대 fixture / 실제 기하 evaluator / 기록 / 독립 판정을 구분한다. #445·#452 연결은 진전이나 acceptance 전체 조건 충족은 아니다. | 집계기·기하·최종 잔류 검증 |
| 4 시행 귀속 | sidecar 우선 설계 채택, 필드 보완 필요 | wire 유지 방향은 동의한다. 현재 JSON에 없는 객체 ID·producer session/seq를 수신자가 추정해 채우지 않도록 명시했다. | producer 원본과 typed message의 식별 가능한 연결, stale replay 거부 |
| 5 미측정 수치 | 보류 채택 | 새 배치의 실제 측정만 근거로 채운다. 기존 코드 상수·센서 주기를 물리 합격 공차로 승격하지 않는다. | 포함·회전·정착·잔류·도킹·신선도 값과 근거 |
| 6 보존·리뷰 | 미정 유지 | 두 위치·접근권한·복구·작성자 외 reviewer의 필요 조건을 유지한다. | 임재범 결정과 담당 수락 |
| 7 반례 | X6-X8 추가, 분모 정책 보완 | 단일 작성자·실제 신선한 수신·좌표값의 기준을 각각 검증한다. 이미 시작한 시행의 INVALID를 분모 제외로 쓰지 않는다. | 재생 control/변형 거부 뒤 실제 연결 검증 |

**직접 확인한 코드 사실**

- main [arm_node.py](../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py#L320)은
  `cabinet_frame`을 기동 때 읽고, 1142행에서 음수 target_slot의 목적지로 사용한다.
  기대 동작은 요청 침상별 실제 놓기다. 현재 고정 파라미터만으로 네 침상 캠페인을 입증하지 못한다.
  **acceptance 실행 차단 조건**으로 남긴다. 운영 코드 수정은 별도 담당 작업이다.
- #452 [isaac_json.py](../../src/rokey_p3_bringup/rokey_p3_bringup/isaac_json.py#L46)의
  `CABINET_FIELDS`는 v, stamp, epoch, cabinet_id, order_id, present다.
  [adapter 433행](../../src/rokey_p3_bringup/rokey_p3_bringup/isaac_adapter.py#L433)은
  epoch를 검사한 뒤 typed message에 stamp·cabinet·order·present만 옮긴다.
  기대하는 안정 객체 ID·source session·source seq는 아직 없다. **현재 JSON 보존만으로 시행 귀속이 완성된다는 해석은 채택하지 않는다.**
- #445 [pharmacy_stage.py 1214행](../../sim/standalone/pharmacy_stage.py#L1214)은
  실제 `get_world_pose()` 위치와 보관함 기하를 대조한다.
  다만 [truth_sensors.py 100행](../../sim/standalone/p3sim/truth_sensors.py#L100)은
  중심점의 축 정렬 부피 판정이다. 초안 8절의 전체 형상·회전·해제·정착·최종 잔류까지 확인하는 acceptance evaluator와 차이가 남는다.
  통합 관측의 개선과 acceptance 자격을 구분한다.
- main [judge_run.py](../../tools/judge_run.py)의
  `trips()`는 DOCKED가 없는 요청도 end_stamp=None 행으로 반환하고,
  `verdicts()`는 `laps=len(trips)`로 센다.
  `laps.min=1`만 있는 기준에서 미완료 1건이 laps 검사를 통과하는 경로를 아래의 순수 Python 재현으로 확인했다.
  이는 모든 criteria에서 항상 통과한다는 뜻이 아니다. acceptance 집계 검증의 차단 근거다.

**시간식 수정 제안**

`W_attempt = W_reset_budget + S_trip_limit / RTF_floor + W_tail_budget`.

| 기호 | 의미 |
| --- | --- |
| `W_attempt` | 시행 하나의 전체 실제 시간(wall) 예산 |
| `W_reset_budget` | 리셋·요청 준비의 실제 시간 예산 |
| `S_trip_limit` | 왕복의 시뮬레이션 시간 한도 |
| `RTF_floor` | 시뮬레이션 시간 / 실제 시간 비율의 사전 합의 하한 |
| `W_tail_budget` | 마지막 잔류·종료 관측의 실제 시간 예산 |

reset·요청 준비·최종 잔류/종료 관측 중 sim trip 밖 구간은 중복 없이 별도 예산에 넣는다.
600/0.756 = 793.65 s이므로 900 s 후보의 나머지는 106.35 s다.
리셋과 마지막 관측이 여기에 들어가는지는 미확인이다.
이 계산은 회신 수치의 산술 검산이며 새 RTF 측정이 아니다.
RTF 하한의 적용 구간·pause 처리·각 예산은 feasibility 뒤 사전에 승인해야 한다.
느린 acceptance 결과를 보고 예산을 늘리거나 표본을 제외하지 않는다.
미정값이 남아 JSON의 후보 숫자는 바꾸지 않았고 동결 보류를 유지했다.

**새 반례의 범위와 확인 한계**

X6은 단순 writer 수뿐 아니라 올바른 source인지 확인한다.
JSON 생산자와 typed 중계자는 서로 다른 토픽의 정상 경로이므로 둘을 합산해 중복이라고 하지 않는다.
X7은 옛 latched 표본의 수신과 현재 생성된 표본의 신선도를 구분한다.
X8은 이름이 아니라 실제 객체·보관함의 기하를 대조하고 공유 layout 오류도 별도로 검증한다.
이 세 반례는 회신이 보고한 현장 사례에서 온 설계 입력이다. 이 검토에서 현장 재현한 것은 아니다.

회신의 “여섯 번 전부 ④” 요약은 같은 회신이 연결한
lap6의 ① 전 기동 실패와 다르다.
따라서 그 요약을 새로운 관측 사실로 복제하지 않았다.
트레이 영향 분석 #451은 전달 완료한 읽기 전용 결과이며
본 protocol 수정으로 물리 칸·자리 용량 계약을 임의 변경하지 않는다.

**인계·미결정**

회신이 제안한 레인별 분담은 각 레인의 수락과 완료 근거가 필요하다.
이 검토의 완료 범위는 설계 대조와 proposed 문서·JSON 반영이다.
남은 차단은 범위 승인, 시간·공차 수치, 발행 출처 식별(source identity) 구현, 네 침상 실행 자격, 집계기, raw 보존, 독립 reviewer다.
회신의 “9/23 전 wire 변경 금지”는 이 검토에서 별도 승인 근거를 확인하지 못했으므로 저장소 전체 금지 규칙으로 추가하지 않았다.
제품 코드·운영 배선·기록된 run·frozen protocol은 변경하지 않았다.


**이번 보강의 실행 검증**

- 기준 main의 `tools/evidence.py::validate_protocol(root, path)`를 Python으로 직접 호출했다. 수정 JSON 검증은 오류 없이 끝났고 `proposed`, 지표 10개, 슬롯 12개, X1-X8 문구를 확인했다. 전체 evidence 검사를 대신하지 않는다.
- 기준 main의 `tools/judge_run.py --logs <빈 임시 로그 폴더> --stamp synthetic --run <임시 run> --criteria <임시 JSON>`를 실행했다. 임시 `events.jsonl`에는 `{"name":"REQUEST_ACCEPTED","request_id":"r1","stamp":1.0}` 한 줄만, criteria에는 `{"gates":{"laps":{"min":1}}}`만 넣었다. **DOCKED 없이 exit=0**을 재현했다. 이는 결함 경로 재현이며 acceptance 합격 결과가 아니다.
- Markdown·JSON NUL 검사와 시간식 산술 검산을 수행했다.
- `python3 tools/check_repository.py`, `python3 tools/evidence.py validate --base origin/main`, `python3 -m unittest discover -s tests`, `ruff check .`는 로컬 **미실행**이다. Git HTTPS 인증이 없어 전체 checkout을 확보하지 못했고, 기준 파일 일부만 GitHub 도구로 받아 검증했다. 새 head의 CI 확인이 필요하다.
- ROS/colcon·Isaac L3, X1-X8 현장 시험, raw 복구·독립 reviewer 검증은 미실행이다. 이 환경에서 현장 실행 환경과 원본을 확보하지 않았다.
