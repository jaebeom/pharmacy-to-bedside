# ADR 0007 — 병원 기본: 카메라 QR 로 집고 인증한다, 도크 = 적재 자리, M0609 레일 후보는 preferred_first

- 상태: proposed
- 날짜: 2026-09-30
- 결정자: 재범. 승인 전이다. 아래 재범 발언은 PR 본문이 인용한 원문이다.
- 승인 PR: 없음(이 ADR 의 PR 에서 검토)
- 관련 issue / RFC / evidence review: PR #784(`54075f9`), #790(`b3f3ba6`), #795(`0914d6d`), #796(`7860b4c`), #797(`f316197` = `v1.1.0`), #391(`914d23d`). #240 5754620387(실습21). #772 5891599172. [실습 45](../practice/simworld/practice-45.md). [스테이지 인자·기본값](../architecture/stage-arguments.md) 1.1절. [시스템 그림](../architecture/system-overview.md)
- 대체 관계: [ADR 0004](0004-auth-pick-v0-truth-sensors.md) 의 "카메라는 v1 옵션" 판단을 대신한다. 0004 의 본문은 고치지 않는다

## 맥락

### 카메라 QR

- v1.0.0(`a5d1107`)까지 병원 기본은 참값 센서 집기였다. `P3_CAMERA_POUCHES` 기본은 0 이었다(`a5d1107` 의 `tools/demo_v2.sh` 155행). 회전 7 도 이 구성이다.
- 재범 9/29(#784 본문 인용): "QR 반드시 찍고 가져가야함."
- 재범 9/29(#784 본문 인용): "병상에 있는건 환자 확인을 위해 병상 QR을 찍고 약을 찍어서 매칭을 한 다음에 그 다음에 약을 내려놔야함."
- #784(`54075f9`)가 병원 기본을 카메라로 바꿨다. 봉투와 인식표를 모두 손 카메라 QR 로 읽는다.
- 롤러 끝에서 카메라로 집어 끝까지 간 기록은 없다. 9/23 리하는 3/3 `grasp_failed` 였다. 흡착 오차는 0.057 m 로 한도 0.04 m 를 넘었다(#797 본문).
- 탁자 정착 프로필(#796)로 코드 `05b8e28` 에서 `bed_a1` 1건이 DELIVERED 됐다. 도크 복귀까지 갔다([실습 45](../practice/simworld/practice-45.md)).
- 그 프로필의 흡착 추가 하강 0.05 m 는 실측 보정이다. TF 높이 불일치의 근본 수정이 아니다(#796 본문).

### 도크 = 적재 자리

- 재범 9/29(#790 본문 인용): "도크 스테이션에서 파지를 할때 가능하다면 AMR이 이동하지 않고 그 자리에서 바로 파지를 함."
- 재범 9/29 22:4x(#797 본문 인용): "왼쪽으로 다 옮겼는데 왜 또 움직여서 파지를 하냐? 그 자리에서 바로 해야지".
- 옛 dock_1(−7.272, 4.784)에서 봉투 정착 자리까지 팔 밑동 수평 거리는 1.028 m 다. UR5 설계 한도 0.70 m 를 넘는다(#790 본문, `hospital_nav` 계산).
- 탁자 정착 프로필에서 load(−8.266, 4.102)와 옛 dock_1(−8.995, 4.686)은 약 0.9 m 떨어져 있었다(#797 본문).
- dock_1 에서 탁자 정착점을 바로 집으면 팔 밑동 수평이 0.741 m 다. 적재 한도 0.70 m 를 넘는다(#797 본문, 안 (b)).
- dock_1 을 적재 자리로 옮기면 팔 밑동에서 봉투까지 0.45 m 다. 성공 회차와 같은 기하다(#797 본문, 안 (a)).

### M0609 레일 후보 순서

- #391(`914d23d`, 9/21)이 `v2_rail_select` 를 opt-in 으로 열었다. 팔 노드 기본은 `first_feasible` 이다(`m0609_arm_node.py` 230행).
- 실습21(9/21 빈월드 master01, `preferred_first`)에서 보충 79회 중 ok 78 이었다. module 40, cylinder 39 다. 낙하는 2/78 이다(#240 5754620387).
- 실패 1건은 Isaac 창이 닫힌 뒤 0.942 s 에 났다. 창이 닫히기 전까지는 78/78 ok 다(같은 댓글).
- v1.0.0(`a5d1107`)과 #797 직전 main(`7860b4c`)의 `tools/demo_v2.sh` 에는 `v2_rail_select` 를 넘기는 줄이 없다. 그 기동은 노드 기본 `first_feasible` 로 돌았다.
- 9/29 영상에서 M0609 가 약통을 집다 몸에 부딪혔다는 지적이 있었다(#772 5891599172). 그 회차의 레일 설정은 원본 기동 로그로 확인하지 않았다(미확인).
- 재범 9/29 "디폴트로 켜서"(#797 본문, `tools/demo_v2.sh` 86행).

## 대안

| 안 | 내용 | 판단 |
| --- | --- | --- |
| 참값 집기 기본 유지 | ADR 0004 그대로. QR 을 읽지 않는다 | 재범 9/29 지시("QR 반드시 찍고")와 맞지 않는다 |
| 롤러 끝에서 카메라 집기 | 봉투가 끝 롤러에 선다 | 끝까지 간 기록이 없다(3/3 `grasp_failed`) |
| 탁자 정착 + dock_1 에서 탁자 집기 | 도크는 그대로 둔다 | 0.741 m 로 적재 한도 0.70 m 를 넘는다. 기각(#797 안 (b)) |
| **탁자 정착 + dock_1 = 적재 자리** | 도크를 성공 회차 적재 자리로 옮긴다 | 채택(#797 안 (a)) |
| 레일 `first_feasible` 유지 | 노드 기본 | 몸에 부딪힌다는 지적이 있었다. 원인 대조는 미확인 |
| **레일 `preferred_first` 기본** | `demo_v2.sh` 가 넘긴다 | 채택. 실습21 78/79, 실패 1건은 창 닫힌 뒤 |

## 결정과 이유

`v1.1.0`(`f316197`) 병원(`P3_WORLD=hospital`) 기동의 기본은 아래다.

1. 봉투와 병상·스테이션 인식표를 손 카메라 QR 로 읽는다(`P3_CAMERA_POUCHES=1`, `P3_CAMERA_TAGS=1`). 봉투 QR 이 goal 주문과 맞을 때만 집는다. 참값으로 되돌아가는 길은 없다(#784 본문).
2. 봉투는 A1 모듈 탁자에 정착한다(`P3_HOSPITAL_RECEIVER_PRIM`, #796·#797).
3. dock_1 = load = (−8.266, 4.102)다(`zones.hospital-receiver.yaml`). orchestrator 는 `load_at_dock` 으로 보고 이동 없이 적재한다(#790). dock_2–4 는 모듈 왼쪽이다(#795).
4. M0609 레일 후보 순서는 `tools/demo_v2.sh` 가 `preferred_first` 를 넘긴다(`P3_V2_RAIL_SELECT`). 팔 노드 자체 기본은 `first_feasible` 그대로다.
5. 약통 QR 확인(`P3_CONTAINER_QR=1`)은 9/23(`72d0e2e`)부터 병원 기본이었다. 이 ADR 이 바꾸지 않는다.

- 적용 위치: `tools/demo_v2.sh` 124–183·191·207·406행, `src/rokey_p3_description/config/zones.hospital-receiver.yaml`·`routes.hospital-receiver.yaml`, `src/rokey_p3_manipulation/config/ur5_arm.amr-combined.camera-receiver.yaml`.
- 이유: 재범 지시를 따르면서, QR 필수로 끝까지 간 기록이 있는 유일한 구성(#796)을 기본으로 둔다.

## 결과

- acceptance protocol v4 는 카메라 구성(`P3_CAMERA_POUCHES=1`)을 범위 밖에 둔다(`experiments/protocols/hospital-full-acceptance-v4.json` purpose 1). 이 기본으로 판정하려면 새 protocol 이 필요하다(#784 본문).
- `v1.1.0` 커밋으로 돌린 acceptance 회전은 없다(v1.1.0 릴리스).
- 근거는 두 건뿐이다. 실습 45(`05b8e28`, 통합 전 SHA, `bed_a1` 1건)와 실습21(빈월드, 레일)이다. 다른 병실·다른 도크·반복 신뢰성은 미실행이다.
- 감수할 부채:
  - 흡착 추가 하강 0.05 m 는 실측 보정이다.
  - M0609 플래너에는 팔 링크끼리의 충돌 검사가 없다(`scene_v2.py` 57·131행).
  - `P3_SIM_SENSORS` 기본 0 이면 `/evaluator/cabinet` 작성자가 없다. 런카드와 `config/hospital-camera-delivery.sh` 는 1 을 준다.
- 재검토 조건:
  - 카메라 구성 protocol 회전이 판정선에 못 미친다. 성공률 90% 는 v4 protocol 문장 그대로다(승인 아님).
  - 다른 병실·다른 도크의 반복에서 `grasp_failed`·`not_detected`·`auth_mismatch` 가 난다.
  - `preferred_first` 에서 M0609 자기 충돌이 재현된다.

## 롤백

코드를 바꾸지 않고 기동 환경 변수로 돌아간다.

| 되돌릴 것 | 방법 | 영향 |
| --- | --- | --- |
| 참값 집기·인증 전부 | `P3_CAMERA_POUCHES=0` | 구역 파일이 `zones.hospital.yaml`, 출발 자리가 (−8.995, 4.686)로 돌아간다(`tools/demo_v2.sh` 138–143행). 그 파일도 dock_1 = load 다(#790) |
| 인식표만 참값 | `P3_CAMERA_TAGS=0` | 봉투는 카메라 그대로다 |
| 탁자 정착 | `P3_HOSPITAL_RECEIVER_PRIM=`(빈 값). `P3_ZONES`·`P3_ROUTES` 는 `zones/routes.hospital.yaml`, `P3_AMR_START` 는 그 파일의 dock_1 로 준다 | 봉투가 끝 롤러에 선다. 카메라 집기는 켜진 채다 |
| 레일 후보 순서 | `P3_V2_RAIL_SELECT=first_feasible` | v1.0.0 기동과 같다 |
