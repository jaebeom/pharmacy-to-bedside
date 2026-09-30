# 실습41 — 빈월드 카메라 인식 L3와 약통 QR L3

| 항목 | 값 |
| --- | --- |
| 날짜 | 2026-09-23, master02 |
| 실행 | `master02` 원격 실행 |
| 환경 | 빈월드(`P3_WORLD=emptyworld`), AMR 합본 lap16 조합, 창 모드 |
| 회차 | A: 카메라 인식 `311b1fc`. B: 약통 QR `957347a` |
| 상태 | 회차 A 는 불통과다. ord-0004 거부는 동작했다. 회차 B 는 불통과다. 첫 거부까지는 동작했다 |
| 원본 | master02 외부 `~/markle_tmp/m2-camera-l3-311b1fc/{c0,c1}/`, `~/markle_tmp/m2-container-qr-957347a/` |
| 출처 | #240 5789183670(A 판정선)·5789606141(A 결과)·5790574350(B 판정선)·5790698806(B 결과) |

이 문서는 실습 관찰 기록이다. frozen protocol 의 합격 evidence 가 아니다. 판정선은 두 회차 모두 결과 전에 PR 본문(#532, #550)에 고정했고, 결과를 보고 바꾸지 않았다. 아래 "원문"은 #240 게시의 인용이고 "해석"은 #240 덧붙임과 이 기록의 풀이다.

## 회차 A — 카메라 인식 L3 (`311b1fc`)

발표 평가 'AI 비전'(#527 V행). 그때까지 한 바퀴의 봉투 입력은 모두 시뮬 참값 센서였다. 카메라가 동작을 바꾸는 장면을 보려는 회차다.

### 구성

- SHA `311b1fc` = `test/camera-l3` = main + #531(`pharmacy/belt_end`) + #532(카메라 배선·벨트 관측 자세) + #534(팔 params). colcon 7/7, porcelain 0.
- 공통: `P3_SIM_SENSORS=1`, `P3_STAGE_ARGS='--pouch-pool 3'`(봉투 라벨 ord-0001–0003), 재고 `~/markle_tmp/dispenser_refill.yaml`(첫 up 이 `P3_DISPENSER_FILE` 없음으로 멈춰서 넣었다).
- ① 기준: `P3_CAMERA_POUCHES=0`, ord-0001 한 바퀴. rtf 만 기록.
- ② 카메라: `P3_CAMERA_POUCHES=1`, ord-0001 → ord-0004.
- 카메라: 손목에 둔 USD Camera, 640×480, 초점 18 mm, 10 Hz, 오프셋 (0.06, 0, 0).

### 판정선 (5789183670)

ord-0001 의 `PickPouch=ok` 이고, 직전 `/amr_1/hand_camera/pouches` 에 `order_id=ord-0001` 이 있으며, 팔 기동 로그가 `pouches=/amr_1/hand_camera/pouches (camera)` 다. ord-0004 는 `qr_mismatch`(재시도 포함)이고 상판에 안 옮겨진다. 둘 다면 통과다.

### 결과 — 불통과

| 항목 | 관측(원문) |
| --- | --- |
| ① rtf | **0.952**. ①–⑩ 완주, ⑤ 0.0063, ⑧ 0.0055 |
| ② rtf | **0.745** |
| ② ord-0001 ⑤ 적재 픽 | 부착됐지만 **suction 0.0365(걸림)**. `amr suction on distance=0.0365 reason=gripper_command close=true t=136.000`. 앞서 POUCH_DETECTED 3회, `QR 을 못 읽었다. 한 변 58 px` |
| ② ord-0001 ⑧ 침상 픽 | `PickPouch ord-0001: not_detected (검출 1건, 맞는 QR 없음)` ×2. 이벤트는 PICK_ATTEMPT×2 → ORDER_DONE → RETURNED → DOCKED |
| ② ord-0004 | 스테이지 `qr_mismatch order_id=ord-0004 pouch_label=ord-0001 pool_slot=0`. 팔 `PickPouch ord-0004: qr_mismatch (검출 3건, 맞는 QR 없음)`. **잘못된 봉투를 싣지 않았다** |
| 판독 QR 한 변 | 실패 줄만 있다: 58 / 61 / 58 px. 성공 판독의 크기 줄은 로그에 없다 |
| 캡처 | 단계 캡처 10장. 관측 자세 캡처에서 QR 은 화면 좌상단 구석에 작고 기울어져 보인다. **녹화 미실행** |
| 기타 | IK 실패·TF 없음 줄 0, Traceback 0, 남은 프로세스 0 |

판정: **불통과.** ord-0001 은 카메라로 집기는 했다. 그러나 QR 판독에 실패했고(58–61 px), 흡착은 0.0365("붙었지만 걸림")였으며, ⑧ 침상 픽이 `not_detected` 로 전달하지 못했다. ord-0004 거부는 판정선대로 동작했다.

`ORDER_DONE` 은 결함이 아니다(계약 388행: 종료 상태 넷 모두에서 난다). 다음 회차부터 `/orders/status` 의 상태를 같이 적는다.

### 원인 (해석, 코드·기하 읽기)

1. 관측점이 **고정점**(벨트 끝 − 0.075 m)이라, 봉투가 실제로 선 자리가 다르면 QR 이 화면 구석에 찍힌다.
2. 봉투 자리를 검출기의 **고정 거리**로 놓았다. 광선이 비스듬하면 자리가 틀린다(흡착 0.0365 의 후보).
3. QR 면이 봉투 비율(0.08×0.056)로 늘어난 정사각 QR 이었다. 모듈이 직사각형이고 짧은 변이 작았다.
4. 해상도 640 폭이다. 58 px 는 모듈당 약 2.3 px 다.
5. 침상 상판 픽에는 관측 자세가 없었다. 홈 자세의 카메라는 상판을 보지 않는다.

### 다음 회차로 넘긴 것

- #538: 세준 흡착 그리퍼+D455 자산을 합본 손목에 붙인다. 흡착점은 손목 +Z 0.1555 m(오프라인 측정)로, 스테이지 가상 흡착과 팔 `tcp_offset_m` 이 같은 점을 쓴다.
- #539: 재관측(첫 검출 위에서 봉투 방향으로 다시 봄), 광선 ∩ 봉투 윗면 투영, 상판 관측 자세, 정사각 QR 면, 1280×800. 계산으로는 재관측 0.20 m 에서 QR 코드 한 변 129 px 다(640 폭이면 64 px).
- 두 PR 은 main 에 들어갔다. **카메라 인식의 재회차 L3 는 미실행**이다.

## 회차 B — 약통 QR L3 (`957347a`)

Q1(재범 결정 #527: 약통 QR 을 첫 바퀴부터). M0609 가 잡기 직전 약통 QR 을 읽고 orchestrator 에 장착 여부를 묻는다.

### 구성

- SHA `957347a` = main `885877e` + #545(cn- 정규식·카탈로그 16칸) + #546(`CheckContainer` 서비스) + #548(M0609 판독·거부) + #550(약통 QR 면·M0609 손 카메라·`P3_CONTAINER_QR`).
- 빈월드 lap16 조합 + `P3_CONTAINER_QR=1` + 동시 보충 재고(첫 amox 에서 보충), `P3_V2_GUARDED_MODULE_PATH=false`, 팔 `v2_seed` 7.
- 만료 칸: `floor_right/r0c1`(cn-0106). 시드 7 이 원통형에서 처음 고르는 칸이라(계산) 첫 보충에서 거부 장면이 나오도록 골랐다.

### 판정선 (5790574350)

스테이지 로그에 `canister_qr faces=32`·`m0609 hand_camera` 줄이 있다. 첫 보충이 `floor_right/r0c1`(cn-0106, 만료)에서 `container_refused … reason=expired` 로 끝나고, 그리퍼를 닫지 않으며, orchestrator 가 장착을 거부한다. 재시도가 다른 칸에서 장착 허용 → `REFILL_DONE`. 셋 다면 통과다. 판독 QR 한 변 px, 손가락 가림(캡처), rtf 는 기록만 한다.

### 결과 — 불통과

| 항목 | 관측(원문) |
| --- | --- |
| 스테이지 | `canister_qr faces=32`, `m0609 hand_camera` ok |
| 첫 보충 | **cn-0106 expired 거부까지 동작** |
| 재시도 | 재시도·`REFILL_DONE` 없이 STUCK. `orchestrator_node.py:551 _on_check_container … ValueError: Logger severity cannot be changed between calls.` 이벤트는 ARM_HOME 뒤 180 s 없다 |
| rtf | `P3_CONTAINER_QR=0` 0.968 / `=1` 0.744 |
| 판독 QR px·잡기 직전 캡처 | 미확보(트리거 미발동) |
| 원본 | `~/markle_tmp/m2-container-qr-957347a/`, SHA256SUMS `0bdb2b456f73…` |

판정: **불통과.** 판정선 셋 중 앞의 둘(스테이지 줄, 첫 거부)은 관측됐다. 셋째(다른 칸 허용 → `REFILL_DONE`)는 서비스가 죽어 나오지 않았다.

### 원인

`orchestrator_node._on_check_container` 가 `log = info if allowed else warning; log(...)` 한 호출 자리에서 등급을 바꿨다. rclpy 는 같은 자리에서 등급이 바뀌면 예외를 낸다. 두 번째 확인(허용)에서 서비스 콜백이 죽었다. L1 로거 대역은 등급 규칙을 흉내 내지 않아 이 결함을 잡지 못했다.

같은 날 #546 CI 의 L2 도 다른 결함으로 실패했다. 로트가 다른 현장 재고 파일로 기동하면 카탈로그의 `cn-0001..0008` 줄이 `CatalogError` 를 냈다. 이 회차는 먼저 거부 칸에 닿아 그 결함을 밟지 않았지만, 같은 재고 파일로는 기동이 막힐 수 있는 결함이다.

### 고친 것과 다음 회차

- `dd78624`(#546): 로그 호출 자리를 등급별로 나눴다. L1 에 rclpy 처럼 자리별 등급을 지키는 로거 대역을 넣었다(옛 코드에서 실패, 고친 코드에서 통과 확인). L2 는 거부 뒤 허용을 연달아 묻는다.
- `383aadc`(#546): 로트가 다른 재고 파일이면 카탈로그의 이름만 적은 약통 줄을 건너뛴다.
- 재회차 SHA `46ab1a3`(#550 head)로 슬롯을 다시 요청했다. **재회차 L3 는 미실행**이다(이 기록 시점).

## 두 회차에서 본 비용

| 구성 | rtf |
| --- | --- |
| 카메라 끔(A①) | 0.952 |
| AMR 손 카메라 640×480 켬(A②) | 0.745 |
| 약통 QR 끔(B) | 0.968 |
| 약통 QR 켬(B, M0609 손 카메라 960×600) | 0.744 |

카메라 하나를 켜면 rtf 가 약 0.2 떨어졌다. 요청이 올 때만 찍는 방식(QR·DB·카메라 계약 3절, `CaptureFrame`)의 근거로 남긴다. 그 방식은 **미구현**이다.
