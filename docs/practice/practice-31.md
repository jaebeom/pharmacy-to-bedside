# 실습31 — 최신 main AMR 합본 회귀 확인

| 항목 | 값 |
| --- | --- |
| 상태 | 첫 배송 중 관측 기준에 따라 중단, 연속 3회 미실행 |
| 날짜 | 2026-09-22 (KST) |
| 돌린 사람 | 임재범 요청, `master02` 원격 실행 |
| 장비 | master02 (`IsaacSim07`) |
| 대상 SHA | `321c069e6eb7d842c0d8dee031e62e95297c378e` |
| 실행 디렉토리 | `/home/rokey/Dev/cobot3_ws/release/20260922-practice31-321c069` |
| 원본 수집 위치 | `/home/rokey/markle_tmp/m2-practice31-321c069` |
| 도메인 | 118, master02 도메인 규칙. 기존 lap14의 121과 다름 |

## 목적

최신 main에서 빈월드 AMR 합본 1인 1건, bed_a1 배송과 리셋 포함 연속 3바퀴를 확인한다.
한계는 `INTEGRATION_ONLY`: 참값 기반 시뮬 센서, 거리 기반 흡착, 고정 경로 주행이다.
실물 검증·Nav2 성능·병원 문 통과 검증으로 확대 해석하지 않는다.

## 구성

[기동 절차](../runbooks/emptyworld-lap-stack.md)를 기준으로 별도 release에서 새 build/install을 만든다.
실행 명령 원문은 원본 수집 위치의 `commands.txt`, 환경은 `env.sh`, 입력 해시는 `inputs.json`에 보존한다.
기동 시각·실행 캐시 상태는 기동 후 기록한다. 기존 install은 재사용하지 않는다.

## 관측

### 사람이 본 것

임재범 화면 관측 보고 대기.

### 로그로 본 것

- 준비 단계에서 tmux 서버 없음, NVIDIA compute-apps 목록 비어 있음.
- 도메인 118의 `ros2 node list --no-daemon` 출력 비어 있음. `/clock`은 `Unknown topic`.
- 원본: `preflight-nodes.txt`, `preflight-clock.txt`.
- 새 release 빌드: `Summary: 7 packages finished [15.5s]`, exit 0 (`build.log`).
- ROS 테스트: 1,387 tests, 0 errors, 0 failures, 2 skipped (`test-result.log`).

## 문제

| 번호 | 무엇 | 처리 |
| --- | --- | --- |
| P1 | 실행 절차는 팔 프레임 관례를 base_link로 쓰지만 lap14 실제 params는 base | 성공 회차 원본 그대로 사용. 기동 시 FK/TF 자가 확인 결과 확인 예정 |
| P2 | GitHub CLI 미인증으로 #240의 최신 결과 조회 불가 | 문서에 남은 항목을 현재 미해결로 단정하지 않음 |

## 캡처·녹화와 보존

아직 기동 전이라 영상·캡처 미생성. 기동 전 녹화 시작, 실제 프레임 검증 예정.
둘째 독립 저장 위치 미정. 이번 실습을 정식 acceptance evidence로 선언하지 않는다.

## 다음 실습에서 확인할 것

이번 회차 종료 후 결과와 미실행 항목을 기록한다.

## 실행 결과 (13:52:27–13:56:07 KST)

- 기동 SHA `321c069`, 신규 install. M0609 경로 캐시는 이번 기동에서 16/16칸 계산(70.6 s). 프론트 브라우저 미기동, API 요청 경로 사용.
- run `20260922T045359Z-master02-37cf59a1`. 요청 `practice31-lap1`은 13:54:38 수락.
- 팔 관례 자가 확인 `base=0.000m base_link=1.200m`, 실제 설정 `base` 통과.
- 원점 로그 `(-0.35, 0.000024, 0.43)`, yaw 180°. lap14 원문과 일치하며 런북의 `(0,0,0.28)`과 다르다.
- 봉투 흡착 거리 0.0045 m, 트레이 `in_slot=True`, offset_xy 0.0032 m. 보충 REFILL_DONE 1건.
- 병동 이동 중 13:55:58부터 종료. 최초 손목–봉투 접촉은 sim 136.650, 검출·중단 판단은 이동 중에 이뤄졌다. 실시간 자동 중단 감시가 아니었다.
- `wrist_3_link/collisions`–`Pouches/Pouch_00` touch 4줄(sim 136.650–142.650). 최대 impulse 0.0010, sep -0.0011 m. 줄 수는 충돌 횟수가 아니다.
- 계획한 링크 touch 중단 기준을 적용했다. 원인 미확정. 연속 3바퀴·인증·전달·복귀·리셋은 미실행.
- orders.jsonl: ABORT, reason=run_ended_before_terminal. cabinet present=true 0건(집계 도구 출력), 파일 5/5.
- 종료 중 navigation action callback에서 `feedback publisher is invalid` ERROR 1·Traceback 1. 실행 프로세스 종료 코드는 모두 0이지만 오류 없는 실행으로 보고하지 않는다.
- 자체 API 관측기는 웹 종료 뒤 Connection refused로 종료됐다. 제품 Traceback과 별개다.
- stage 종료 `reason=sigint rtf=0.943`. 종료 후 tmux 없음, NVIDIA compute-apps 비어 있음, 도메인118 node list 출력 없음.

### 기존 성공 회차와 대조

lap14 원본 stage 로그에도 같은 손목–봉투 touch가 27줄 있다. 이번 현상을 새 회귀로 단정할 수 없다.
기존 실습30의 touch 0과 집계 범위가 다르며 원문 `wrist-contact-comparison.txt`를 남겼다.
이 문서는 기존 run·실습30을 수정하지 않는다. 무접촉의 대상·예외를 담당자가 명시한 뒤 새 회차로 재검증해야 한다.

### 집계와 보존

`python3 tools/judge_run.py --logs /home/rokey/markle_tmp/m2-practice31-321c069/logs --stamp 20260922-135227 --run /home/rokey/.ros/rokey_p3/runs/20260922T045359Z-master02-37cf59a1 --json /home/rokey/markle_tmp/m2-practice31-321c069/judge.json`

출력은 `judge.txt`. criteria 미지정이므로 도구 exit 0은 합격이 아니다. 도구의 run 구간은 이벤트 구간 112.7–149.6 sim s라 종료까지 전체 물리 구간을 뜻하지 않는다.
녹화 `clips/practice31.mkv`: 5,956 frames, 10 fps, 595.6 s. 기동 준비부터 데스크톱을 녹화했다.
기본 카메라가 M0609 쪽이라 AMR 배송 동작 전체의 시각 검증은 미실행이다. 캡처 frame-495.png, frame-525.png를 원본 디렉토리에 보존했다.
사람 화면 관측은 아직 보고되지 않았다. 독립 둘째 보존 위치는 미정이다.
저장소 검사 PASS, evidence 구조 검사 OK, unittest 188 OK. ruff는 실행 파일이 없어 미실행.

## 후속

- touch 집계 범위와 중단 기준을 명확히 한 뒤 연속 3바퀴 재실행.
- 런북의 팔 기준 프레임·원점 표 정정 검토.
- 종료 중 action callback 오류 진단.
- 임재범 요청으로 #483 병원 월드 대응 정보수집을 후속 작업으로 진행한다.
