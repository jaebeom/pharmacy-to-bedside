# 튜터 평가표 1:1 대응 — 발표 원본

> 재범 요청(9/25): 튜터 평가 문서의 요구를 1:1 로 말하고 어떻게 대응했는지 보이는 발표. 평가 항목 7개 = 7쪽이다.
> 기준: 2026-09-28, main 66eeee8 · v1.0.0 → a5d1107. 수치는 evidence 의 v0.5.0 · v1.0.0 배포 기록에서 옮겼다. 요구 원문은 [최종 발표 평가](../reference/tutor/final-presentation-evaluation.md) 2·3절 전사 그대로다. 4–8절은 우리 작성 가이드다. 요구로 세지 않는다. 2절(영상 발표)은 3.6 쪽에 넣었다.
> 발표 파일: [tutor-response.html](tutor-response.html). 이 md 와 html 은 [tutor-deck/](tutor-deck/) 의 같은 데이터에서 만든다. 쪽에는 한 일을 요구마다 앞 세 줄만 싣는다.

## 2 최종 영상 발표 — 문서

> 튜터 요구: 최종 영상으로 발표!! 기능을 직관적으로 확인할 수 있는 영상 및 편집 필요!

**대응**: 등록 run 녹화를 이어 붙이고, 자막으로 단계 · 로봇 · 결과 · 배속 · run ID 를 표시한다

- 편집 계획: 안전판 = v0.5.0(a4b1a4e) 등록 PASS run 녹화 6개(한 바퀴 · seed 11/23 · 10건 · Play/Stop · AMR 2대)
- 시간표 300 s: 영상 158 s(M0609 보충은 1× 50 s) · 슬라이드 142 s(본 발표 7쪽 + 제어 · 구조 · 스택 3쪽)
- 첫 화면 "서로 다른 run 6개를 이어 붙였다", 끝 화면 run_id · sha256 표. 배속 구간은 ×N 계속 표시
- 촬영 계획 v5(여섯 뷰)는 본촬영 기록이 없어 기록(동결)으로 남겼다

증거: docs/presentation/edit-plan-5min.md · docs/presentation/tech-3.html · docs/presentation/hospital-demo-shotlist.md(기록)

남은 것: 편집본 제작 · 리허설 시간 기록 — 미실행. 안전판은 기본 뷰 한 앵글이다

## 3.1 문제 정의 — 문서

> 튜터 요구: 해결하려는 현실 문제와 디지털 트윈으로 검증해야 하는 이유가 명확히 서술되어 있다.

**대응**: 병원 약제의 보충 → 조제 → 병동 전달 → 복귀를 한 흐름으로 정의했다

- 확정 시나리오(9/16, 4인 합의 PR #21): 웹 주문 → M0609 보충 → 조제기 → 컨베이어 → AMR 합본 집기 → 병상 보관함 → 도크
- 종료 상태 넷(SUCCESS · HOLD_RETURN · ABORT · TIMEOUT)과 실패 처리를 결과 전에 정했다
- 왜 디지털 트윈(초안): 실제 병동에서 로봇 팔·AMR 을 반복 실험하면 환자 동선과 약 안전을 건드린다. 같은 조건을 몇십 번 다시 만들고 실패를 안전하게 일으킬 수 있는 시뮬레이션에서 흐름 · 인터락 · 실패 처리를 먼저 검증한다

증거: docs/planning/scenario.md 10–27행(흐름) · 183–196행(종료 상태) · PR #21

남은 것: "왜 디지털 트윈" 문장은 초안이다 — 재범 확정 대기

## 3.1 현실 반영도 — 계약 합격

> 튜터 요구: 다중 로봇 작업 흐름이 실제 현장을 반영하고, 검증 목표(성공률, 한계)가 정의되어 있다.

**대응**: 병원 씬에서 로봇 셋(M0609 · UR5 · AMR)이 한 주문을 끝까지 넘겨받는다. 판정선은 결과 전에 고정했다

- 골든 다섯 장면: ① 조제실 준비 ② M0609 보충 둘 ③ 봉투 A1 끝 ④ UR5 집기 · 적재 ⑤ 목적지 · 복귀
- 판정선(5/5 · DELIVERED · AMR touch 0 · 녹화)을 회차 전에 적었다(#240 5755830894)
- 병원 acceptance protocol v4(frozen): 16 attempt · 판정선 ≥15/16 · 실패마다 failure_class 필수. 15/16 의 95 % 하한 0.736 을 적었다(신뢰도 주장 아님)
- v0.5.0 회전 1–5: 63 run · PASS 53 · FAIL 10(robot 1 · infra 6 · operator 3). v1.0 회전 7: master01 14/14
- 주장 범위 고정: Nav2 는 접근점까지, 마지막 0.5 m 는 직접 추종기 · 위치는 시뮬 도크 TF(odom)

증거: experiments/protocols/hospital-full-acceptance-v4.json · evidence/deployments/2026-09-27-jaebeom-v0-5-0.md · evidence/deployments/2026-09-28-jaebeom-v1-0-0.md

남은 것: v1.0 에서 attempt 12 · 13(다중 PC)은 미실행이다. 다중 PC 판정 run 은 회전 1–3 에만 있다

## 3.1 저장소 완결성 — 문서

> 튜터 요구: 실행에 필요한 모든 파일과 버전·패키지·환경 변수가 저장소에 문서화되어 있다.

**대응**: 코드 · 씬 · preset · 인자 · 자산 해시를 저장소에 둔다. 커스텀 자산은 Release 첨부 + 해시 검증

- 스테이지 인자 · 기본값 표(값 + 근거 회차): stage-arguments.md
- 골든 런카드 한 장(명령 · 값 · 씬 · 판정선): runbooks/hospital-full.md
- 커스텀 자산 ZIP 은 GitHub Release 비공개 첨부, 해시 검증 절차(#651)
- 녹화 원본 전체 SHA-256 표: master01 70행 · master02 100행

증거: docs/architecture/stage-arguments.md · docs/runbooks/hospital-full.md · docs/reha/recordings-master01.md · recordings-master02.md

남은 것: 환경 변수가 90종이다(설계 갭 P1-5). 한 표로 모으는 일이 남았다

## 3.1 실행 재현성 — 계약 합격

> 튜터 요구: README 순서만 따라 하면 어느 PC에서도 절대 경로 의존 없이 실행이 재현된다.

**대응**: 새 clone 에서 문서만 보고 돌려 막힌 곳을 문서로 되돌렸다

- 회차32: 새 clone · 문서만으로 → 주문 전에 멈춤, 막힌 줄 13개를 기록
- 문서 보강(#635) 뒤 회차33: 새 clone 4/5 까지
- Isaac 셸은 env -i 로 시스템 ROS 를 섞지 않는다(절대 경로 대신 P3_REPO)
- protocol phase F(attempt 16): 새 clone → 주문 완료 PASS. 회전 1 503.087 s · 회전 4 503.786 s, 자산 해시 일치

증거: #240 5800028169(회차32) · 5800180626(회차33) · evidence/deployments/2026-09-27-jaebeom-v0-5-0.md 새 clone 절 · docs/runbooks/hospital-demo.md

남은 것: v1.0 회전 7 attempt 16 은 PASS 이나 fresh_clone 두 값이 비었다(null). 회전 4 값은 STEPS.md 를 회차 뒤 옮겨 쓴 입력이다

## 3.2 씬 구성 — 계약 합격

> 튜터 요구: 환경·로봇·물체·센서 배치가 작업 목적에 적합하게 구성되어 있다.

**대응**: 병원 USD 위에 조제실 · 로봇 셋 · 센서를 목적대로 올렸다

- 조제실: 3축 레일 M0609 · 약통 선반 18칸 · 조제기 · 씬 컨베이어 A1
- AMR 합본(Ridgeback + UR5 흡착) · RTX 2D 라이다 · D455 손 카메라 · 병상 D1–D10 보관함
- 촬영용 카메라 여섯 · 바닥 데코(채택) · 도크 충전 스테이션 표시(#688)

증거: docs/architecture/system-overview.md · #240 5807102321(회차46)

남은 것: 바닥 데코는 main 에 들어갔다(p3sim/hospital_decor.py)

## 3.2 물리 속성 — L3 관측

> 튜터 요구: RigidBody·Collider·Mass·마찰력 등이 올바르게 설정되어 있다.

**대응**: 물리 값을 코드에 적고, 물리가 문제를 일으킨 곳을 고쳤다

- 질량 · 충돌체를 코드에 명시: 레일 받침 50 kg · 캐리지 10 kg · 약통 0.1 kg · 봉투 0.02 kg · dt 1/60 s
- 선반 삼각 메시 → 잰 판 두께 상자: PhysX 경고 419,292줄 → 0(232931c)
- 레일 드라이브 강성 1e5 · 1e4 · 5e4: 물리 멈춤 5 → 0

증거: sim/standalone/p3sim/scene.py · #240 5795175482(레일 드라이브) · docs/analysis/2026-09-23-hospital-sim-load.md

남은 것: 마찰 계수는 재지 않았다. UR5 흡착은 물리 대신 거리 판정 attach 다. 발표에서 밝힌다

## 3.2 ROS2 연동 — L3 관측

> 튜터 요구: clock, 이미지, tf 등 시뮬레이션 데이터가 ROS2로 정상적으로 연동된다.

**대응**: /clock · tf · 라이다 · 카메라 · 관절이 ROS2 로 온다. 나머지는 JSON 토픽 → 어댑터

- /clock 발행자는 스테이지 하나 — boot_check 가 발행자 1 을 확인해야 주문
- /amr_1/scan 16 Hz → Nav2 코스트맵 · 감속기(scan 토픽 고침 138cbac)
- map → odom 은 dock_origin_tf, 정차 자리는 zones_tf
- Isaac Python 3.11 ↔ Jazzy 3.12: JSON 토픽 + isaac_adapter(ADR 0002)

증거: #240 5787139396(scan 16.0 Hz) · docs/adr/0002 · docs/architecture/system-overview.md

남은 것: 손 카메라 이미지 Hz 를 판정선에 넣는 안(v0.5.0 제안)

## 3.2 재현성(Play/Stop) — 계약 합격

> 튜터 요구: Play/Stop 반복 실행 시 매번 동일한 초기 상태에서 동일한 동작 결과가 재현된다.

**대응**: Stop → 자동 Play → 리셋 → 같은 주문이 다시 DELIVERED

- 단계형 리셋(epoch): 타임라인을 멈추지 않고 초기 상태로
- 툴바 Stop → 자동 PLAY · physics_view recovered → POST /api/reset → 주문 → DELIVERED
- 적재 중에 Stop 해도 복구(회차63)
- 회차39 · 56 · 62(master01), f610fa3(master02) 통과

증거: #240 5802419185 · 5810138800 · 5815786839 · 5814610703 · 5816054551

남은 것: protocol phase C(attempt 7 · 8)로 들어가 v0.5.0 · v1.0 에서 PASS 했다. "같은 초기 상태" 를 자세로 대조하는 줄은 없다. master02 737fee9 는 트레이 drift 0.0342 > 0.03 이다

## 3.3 개별 로봇 동작 — 계약 합격

> 튜터 요구: Pick & Place 또는 자율주행이 안정적으로 완수되고, 파라미터 튜닝 근거를 설명할 수 있다.

**대응**: 로봇 셋이 각자 일을 반복해서 끝낸다. 설정마다 바꾼 이유와 전후 값이 있다

- M0609: 원통 · 모듈 보충, 약통 QR 확인 뒤 장착. 속도는 두산 사양 80 %
- UR5: A1 끝 봉투 흡착 → 트레이 in_slot. 접근점 회전으로 ArmRiser 접촉 57 → 0
- AMR: Nav2 접근점 + 추종기. 감속기는 LETHAL 100 만 벽으로(4d01333), 복도 113 → 72 s
- 병상 D1–D10 전부 10/10(beds-all) 여러 회차

증거: beds-all #240 5810523930 · 5811299608 · 5814924837 · 5816206952 · 10건 #240 5808852884 · docs/reha/ 골든 계보

남은 것: 속도 90 %(#695) 판정 여부는 미확인. 감속기 정지 규칙(긴급정지 감지)은 v1.0.1 로 미룸(#752)

## 3.3 설계-구현 일치 — 문서

> 튜터 요구: 문서화된 설계가 코드에서 동일하게 동작하고, 센서·토픽 등 외부 데이터가 동작 결정에 반영된다.

**대응**: 설계와 코드가 다른 곳을 숨기지 않고 표로 맞췄다. 센서가 결정을 바꾼다

- 시스템 그림은 main 코드에서 옮겼다(노드 · 토픽 · 액션)
- 확정 시나리오 ↔ as-built 13건 표(값 · 결정 출처 · 회차)
- 센서 → 결정: joint_states 도착 · holding 파지 · at_home 출발 거부 · scan 감속 · 약통 QR 장착 허용

증거: docs/architecture/system-overview.md · docs/planning/scenario.md 10.1(#684)

남은 것: 결정 기록 없음 4건(레일 3축 · 도크 4 · 묶음(병동) · 간호사 화면) — 재범 결정 + ADR 0003–0006

## 3.4 인식 안정성 — L3 관측

> 튜터 요구: 감지 모델(YOLO, HSV 등)이 대상을 안정적으로 인식하고, 인식률 개선 과정을 설명할 수 있다.

**대응**: QR 판독을 한 단계씩 고쳐 못 읽던 약통을 읽게 했다

- 약통 QR 을 윗면 → 옆면 스티커로(2276027)
- 네 점으로 펴서 다시 읽기 · 2배로 키워 다시 읽기(429ac27 · 05339c9)
- 모듈 잡는 높이 +0.03 m → 가림 해소 → cn-0204 장착 허용(f8eac1c)
- 카메라 집기 exp: 흡착 잔차 0.10 → 0.057 m(한도 0.04, 불통과)

증거: docs/presentation/qr-reading-rounds.md · #240 5799937654(회차31)

남은 것: 판독률(시도 대비 성공)은 로그 throttle 로 셀 수 없다 — 미실행. YOLO 가중치 없음

## 3.4 인식 결과 활용 — L3 관측

> 튜터 요구: 인식 결과가 로봇 동작에 실제로 반영된다.

**대응**: M0609 손 카메라의 약통 QR 이 장착 허용 · 거부를 가른다

- D455 → 약통 QR → /orchestrator/check_container → 장착 허용이면 놓고, 못 읽음 · 거부면 닫지 않는다
- 유효기간 지난 약통은 expired 로 거부(실습41 B)
- 봉투 집기 · 인식표 인증은 v1.0 판정 구성에서 참값 센서(P3_CAMERA_POUCHES=0)
- 9/29 main(#784): 병원 기본 = 봉투 QR 이 주문과 맞을 때만 집고(qr_mismatch · not_detected 면 안 집음), 병상 QR → AUTH_OK → 약 QR → 내려놓기. 웹에 판독 요약 · 추적 영상(#786 · #787). L3 미실행

증거: docs/presentation/qr-reading-rounds.md 2절 · docs/architecture/k5-delivery-interface.md 5행

남은 것: 봉투 · 병상 QR 카메라 판독(#784)은 코드만 — 판독률 · tag_standoff 0.25 도달을 마스터에서 재지 않았다. 발표에서 v1.0 증거와 나눠 말한다

## 3.4 처리 효율 — L3 관측

> 튜터 요구: 추론 주기 제한 등 실시간 대응과 시스템 부하를 고려한 설계가 있다.

**대응**: 카메라 주기 · 해상도 · 렌더 주기를 줄여 부하를 관리했다

- 카메라 ≤ 10 Hz · 1 s 넘은 검출 폐기 · 정지 뒤 한 장(계약)
- 손 카메라 끄면 rtf 0.925 → 0.992, GPU 99 → 74 %
- render_every 2: rtf 0.418 → 0.690(같은 SHA · master01)
- 키워 읽기 비용 프레임당 약 30 ms(오프라인)

증거: #240 5755273685 · 5796069792 · docs/presentation/challenge-rtf-levers.md

남은 것: 프레임당 지연(ms) 실측 없음

## 3.5 시스템 통합 — 부분

> 튜터 요구: 다중 PC 간 ROS2 통신이 정상이고, 시작부터 완료까지 전체 파이프라인이 끊김 없이 연결된다.

**대응**: 두 PC 로 나눠 한 주문을 끝까지 돌린 기록이 있다. v1.0 판정은 한 PC 다

- P3_ROLES: master01 = stage(Isaac), master02 = arm · nav · stack · web(도메인 131)
- 회차19 다중 PC 계약 합격: rtf 0.711(한 PC 0.686)
- fcec7a8 N=4 다중 PC PASS: ORDER_DONE · DOCKED, /clock 발행자 1
- 이득 +0.025 → 촬영은 한 PC(결정 ⑤)
- protocol phase E(attempt 12 · 13): 회전 2 · 3 에서 돌았고 판정은 FAIL(#726 · #747 · #745 — protocol 문구 · operator)

증거: #240 5797973069 · 5797973429(회차19) · #240 5816379015 · 5816418529(fcec7a8) · evidence/deployments/2026-09-28-jaebeom-v1-0-0.md

남은 것: v1.0(a5d1107)에서 다중 PC attempt 12 · 13 은 미실행이다. "다중 PC 로 v1.0 검증" 이라고 말하지 않는다

## 3.5 다중 로봇 조율 — 계약 합격

> 튜터 요구: 2대 이상 로봇의 작업 순서·역할이 충돌 없이 조율되고, 작업 완료 후 재실행이 가능하다.

**대응**: M0609 보충과 AMR 배송이 한 바퀴에서 이어지고, 10건을 끊김 없이 다시 돈다

- UR5 ↔ AMR 인터락(arm/at_home · base/stopped). M0609 보충은 트립과 병렬
- 합본 2대(배송 + 도크 대기) 충돌 없음(N=2)
- 주문 10건 연속 10/10 · AMR touch 0 · 배출 실패 0(af78350)
- 10건 계보 5 → 7 → 10(touch 1) → 9 → 4 → 8 → 10(touch 0)

증거: #240 5808852884(10건 I) · #240 5796814149 · 5801263234(N=2) · docs/reha/reha-07.md A–I

남은 것: 10건 attempt 6 은 v0.5.0 · v1.0 판정 회전에서 여러 번 PASS 했다(v1.0 rtf 0.505)

## 3.5 동적 대응 — 계약 합격

> 튜터 요구: 물체 위치가 매번 달라져도(랜덤 스폰) 정상 동작하고, 외부 이벤트에 따라 동작이 결정된다.

**대응**: 진열 · 스폰이 seed 로 바뀌어도, 긴급 주문이 끼어들어도 배송한다

- 진열 seed 0 → 7(빈 칸 배치가 다름): 5/5(회차40)
- 팔이 집는 칸 seed 11 · 23: 5/5 · 봉투 스폰은 (seed, epoch, index)
- 긴급 주문이 10건 안에서 끼어들어 먼저 배송 · 재고 임계 → 자동 보충
- 목적지 추가: 간호스테이션 B 테이블(station_b)

증거: #240 5802558111(회차40) · docs/reha/reha-06.md · #240 5808852884

남은 것: seed 11 · 23 은 protocol attempt 14 · 15 로 들어가 v1.0 에서 PASS 했다. 더미 · 보행자 ON 회차(v0.5.0 10건 조우 28)가 있다. 긴급 주문은 요청 대기열에서 앞서는 것이고 진행 중 배송을 선점하지 않는다

## 3.5 검증 및 분석 — 계약 합격

> 튜터 요구: 성공률·소요 시간 등 사전 정의 기준으로 정량 측정하고, 실패 원인과 한계를 분석했다.

**대응**: 판정선을 먼저 적고, 실패를 SHA · 회차별로 남기고, 원인을 고쳐 다시 쟀다

- 회차 목록: #240 원문 기준 전체 SHA · 호스트 · 결과 · 녹화 해시
- 실패 원인 → 고침: 제자리 회전 접촉 → 접근점 회전 / 배출 응답 10 s → 30 s
- 관측과 해석을 칸으로 나눴다. rc2 10/10 · touch 1 과 rc3 9/10 · touch 0 을 합치지 않는다
- 소요 시간: 복도 DEPARTED → ARRIVED(sim) 113 → 99 → 72 → 78 s

증거: docs/reha/rounds-240.md · docs/reha/reha-07.md · docs/analysis/2026-09-25-v050-scorecard-evidence-map.md

남은 것: 성공률 표: v0.5.0 회전 1–5 63 run · PASS 53 · FAIL 10(robot 1 · infra 6 · operator 3), 회전 6 중단(operator 3), v1.0 회전 7 14/14. 무실패 16/16 회전은 없다

## 3.6 문서 구성 · 시간 — 문서

> 튜터 요구: PPT 및 발표가 제시한 문서 구성과 시간을 준수 여부를 평가 — flowchart, 시스템 아키텍쳐, 기술 스택 등

**대응**: flowchart · 아키텍처 · 기술 스택을 실제 코드와 같게 그렸다. 5분에 맞췄다

- 로봇별 제어 flowchart · 시스템 아키텍처(PC · 역할 · 노드 · 도메인) · 기술 스택 3장, 값은 main 파일:줄에서
- 쓰지 않는 말 8개를 근거와 함께 적었다(참값 센서 집기 · 봉투 스폰 · AMCL 없음 · MoveIt 아님 등)
- 5분 시간표: 영상 158 s + 슬라이드 142 s

증거: docs/presentation/tech-3.html · docs/presentation/tech-3-sources.md · docs/presentation/edit-plan-5min.md

남은 것: 리허설 시간 기록은 9/29 — 미실행

## 3.7 기술 리포트 — 문서

> 튜터 요구: 공학적 탐구, 알고리즘 개선 · 센싱 데이터 분석 및 머신러닝 · 성능 개선을 위한 다양한 시도 기술 리포트

**대응**: 문제 → 가설 → 한 번에 한 변수 → 결과 → 한계로 두 편을 쓴다

- ① 병원 Nav2 0/6 → 6/6: 한 층씩 원인을 잘랐다
- ② rtf 0.34 → 0.69: 충돌체 · 레일 드라이브 · render_every · 계획 캐시(장비별 표)
- 곁가지: 감속기 세 층(QoS · 팽창 띠 99 · scan 토픽)

증거: docs/presentation/challenge-hospital-nav2.md · docs/presentation/challenge-report-0925.md · challenge-rtf-levers.md · challenge-multipc-bench.md

남은 것: 리포트 ② 는 9/28 에 자리표시를 채웠고 6절에 비는 곳을 적었다. rtf 0.34 → 0.69 는 장비가 섞인 값이다
