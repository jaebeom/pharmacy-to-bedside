# 실습44 — 병원 S3·S4 회차, 기동 멈춤, 봉투 QR 카메라 회차(9/23)

| 항목 | 값 |
| --- | --- |
| 날짜 | 2026-09-23, master02 |
| 실행 | `master02` 원격 실행 |
| 환경 | 병원 씬. 조제실은 회차마다 다르다(아래 표) |
| 실행 코드 | `feat/hospital-full` 의 `bb3ac33`, `248b80b`, `603dfc1`, `d448530`, `f85dd70`, `c136757` |
| 원문 | `master02` 보고. 이 기록에 그대로 옮겼다. **#240 게시 전**이다(게시 권한 대기) |
| 원본 | master02 `/home/rokey/markle_tmp/m2-hf-{s34-bb3ac33,s34-bb3ac33-r2,s34-603dfc1,full-d448530,full-f85dd70,cam-c136757}/`, 각 `SHA256SUMS` |

이 문서는 실습 관찰 기록이다. frozen protocol 의 합격 evidence 가 아니다. "원문" 칸은 `master02` 보고를 고치지 않고 옮긴 것이고, "해석"은 이 기록의 풀이다.

## 한눈에

| # | 회차 | 구성 | 결과 |
| --- | --- | --- | --- |
| 1 | S3·S4 1회차 `bb3ac33` | `hospital-full` + `P3_POUCH_AT_END=1`, 레이아웃 없음 | **불통과**(집기 전) |
| 2 | S3·S4 2회차 `248b80b` | — | **미실행** |
| 3 | S3·S4 3회차 `603dfc1` | hospital + integrated-09 `workcell.json` | **미완**(기동 대기에서 멈춤, 지시로 down) |
| 4 | 전체 한 방 `d448530` | hospital + 실습37 workcell(`7fb6c613…`) | **기동 멈춤** 2회 |
| 5 | 전체 한 바퀴 `f85dd70` | `P3_HOSPITAL_SCENE=base-523.usda` + integrated-09 `workcell.json` | **불통과**(기동 15 s) |
| 6 | 봉투 QR 카메라 `c136757` | `hospital-full` + `P3_CAMERA_POUCHES=1`, `P3_POUCH_AT_END=1` | **불통과**. 재범 지시를 어기고 잘못 돌린 회차다 |

S3·S4 는 병원 시나리오의 3·4단계(A1 끝 봉투를 집어 AMR 에 싣기)다. 여섯 회차 중 집기까지 간 것은 6번 하나였고, 그 회차도 봉투를 고르지 못했다.

## 회차별 원문

### 1. S3·S4 1회차 `bb3ac33` — 불통과(집기 전)

> `spawn … xyz=[-8.1937, 5.0644, 0.4097]` 뒤 POUCH_AT_END 없음 → DISPENSED 54.62 후 60 s 에 ORDER_DONE·RETURNED
> m2-hf-s34-bb3ac33/ SHA256SUMS e587c7478502

해석: 봉투는 A1 끝 근처(`belt_end` y 4.9644 보다 0.1 m 상류)에 스폰됐다. 그러나 벨트 끝 도착 신호가 나오지 않았고, 60 s 뒤 주문이 닫혔다. 도착 신호가 왜 없었는지는 원문에 없다(**미확인**).

### 2. S3·S4 2회차 `248b80b` — 미실행

> 미실행. 사유: 직전 bb3ac33+integrated-09 레이아웃 재기동이 stage 대기에서 10분 넘게 멈춰 down, 그 사이 3회차 SHA 가 와서 건너뜀
> m2-hf-s34-bb3ac33-r2/ SHA256SUMS ede8446a088e

폴더 `-r2` 는 `bb3ac33` 에 integrated-09 레이아웃을 붙여 다시 띄운 기동 기록이다. `248b80b` 로 돈 회차는 없다.

### 3. S3·S4 3회차 `603dfc1` — 미완

> hospital + integrated-09 workcell.json — 미완(기동 대기 멈춤, stage ready 뒤 up 이 진행 안 됨, 지시로 down)
> m2-hf-s34-603dfc1/ SHA256SUMS 7555f5dd5d80

### 4. 전체 한 방 `d448530` — 기동 멈춤 2회

> hospital + 실습37 workcell(7fb6c613…) — 기동 멈춤 2회
> `stage 준비 줄('stage ready')이 180 s 안에 없다` / 420 s 재시도도 같음(PhysX getMaterialFromInternalFaceIndex 경고 약 20만 줄)
> m2-hf-full-d448530/ SHA256SUMS 4ea2324d9b5f

해석: 경고가 약 20만 줄 쌓인 것과 준비 줄이 안 나온 것은 같은 회차의 관측이다. 둘의 인과는 확인하지 않았다(**미확인**).

### 5. 전체 한 바퀴 `f85dd70` — 불통과(기동 15 s)

> P3_HOSPITAL_SCENE=base-523.usda + integrated-09 workcell.json — 불통과(기동 15 s)
> `p3sim.common.StepError: add_base_scene: ValueError: Inlets/PillSupport geometry/anchor transform override`
> m2-hf-full-f85dd70/ SHA256SUMS 6a4153b8ccdc

씬을 붙이는 단계에서 조제기 `Inlets/PillSupport` 의 기하·앵커 변환 덮어쓰기 검사에 걸려 멈췄다. `3cf412c`(병원 조제실은 기준 조제기 그대로, base·workcell 을 저장소 준비기로 다시 만든다)로 고치는 중이다. **재회차는 미실행**이다.

### 6. 봉투 QR 카메라 `c136757` — 불통과, 잘못 돌린 회차

> c136757 hospital-full 카메라 회차(P3_CAMERA_POUCHES=1, POUCH_AT_END=1) — 불통과, 재범 지시 위반으로 잘못 돌린 회차
> `PickPouch ord-0001: not_detected (검출 12건, 맞는 QR 없음)` ×2 → ORDER_DONE 65.10, 배송 없이 복귀
> m2-hf-cam-c136757/ SHA256SUMS 3db372081773

**구성이 틀렸다.** 재범 지시는 "병원 실습에서 `hospital-full`(빈월드 조제실)은 쓰지 않는다. 카메라 회차도 `base-523.usda` + `workcell.json` 구성으로만 돌린다"였다. 이 회차는 그 지시 전에 요청됐다. 지시 뒤 보류 메시지가 갔지만, 회차가 그 메시지보다 먼저 돌았는지는 확인하지 않았다. 그래서 결과를 병원 카메라 판정에 쓰지 않는다.

관측으로 남기는 것:

- 봉투 상자는 검출됐다(12건). 그러나 QR 을 읽은 검출(`order_id` 가 있는 것)이 없어 `not_detected` 가 두 번 나왔다(재시도 포함).
- 팔은 봉투를 집지 않았고, 주문은 65.10 s 에 닫혔다. AMR 은 배송 없이 돌아갔다.

해석(**미확인**, 후보만): QR 판독 실패의 원인은 확인하지 않았다. 후보는 다음과 같다.
(가) `P3_POUCH_AT_END=1` 로 A1 끝에 바로 놓은 봉투가 QR 텍스처가 붙은 봉투 풀을 쓰지 않았다.
(나) 관측·재관측 자세의 판독 픽셀이 모자랐다. 오프라인 계산은 재관측에서 약 129 px 였다.
(다) 조명·화각.
구분하려면 원본 폴더의 스테이지 로그(`qr_textures`·봉투 스폰 줄)와 팔 피드백(`view`→`refine`)을 봐야 한다(**미실행**). rtf 는 `logs/*-stage.log` 의 stop reason 줄에 있다(이 기록에는 옮기지 않았다).

## rtf

| 회차 | rtf |
| --- | --- |
| `bb3ac33`·`603dfc1`·`d448530`·`f85dd70` | 미측정(ready 전에 멈췄거나 stop 줄 없음) |
| `c136757` | 원본 `logs/*-stage.log` 의 stop reason 줄(이 기록에 옮기지 않음) |

## 다음 회차

- 기동: 수정 SHA 로 `base-523.usda` + `workcell.json` 구성을 다시 띄운다. `P3_WORKCELL_LAYOUT` 은 이제 필수다(`3cf412c`).
- 봉투 QR 카메라: 그 SHA 가 나온 뒤 같은 구성으로만 다시 요청한다. 판정선은 결과 전에 고정한다. 6번의 원인 후보 (가)–(다)를 가를 로그 항목을 요청에 넣는다.
