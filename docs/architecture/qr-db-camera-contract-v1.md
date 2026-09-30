# 계약: QR·약 DB·카메라 한 장·흡착 압력 v1

- 상태: proposed. **(제안·미확정)** 표시가 붙은 줄은 아직 정하지 않은 것이다.
- 기준: main `f316197`(v1.1.0). 이름·접두·서비스·토픽과 6절 현황을 이 커밋의 코드와 대조했다. 코드와 다른 곳은 문서를 코드에 맞췄다. 맞춘 곳은 [9절](#9-v110-대조-2026-09-30)에 모았다.
- 이력: 2026-09-23 처음 썼다(기준 main `09d349c`). 같은 날 2.3·5절·6절을 `ae8b0b9` 로 고쳤다. 2026-09-24 에 6절을 골든-4 `aca8840` 로 고쳤다(설계 갭 G3, #576 댓글 5806300285).
- QR 이 어디에 붙고 카메라가 어떻게 달렸는지는 [QR 배치와 카메라 구성](qr-camera-layout.md)에 있다.
- 담당 / 소비자 / 이슈: QR·DB·카메라 레인 / orchestration·manipulation·perception·simulation / 결정 #520
- 버전 / 대체 계약: v1 / 없음. [배송 계약 v1](delivery-contract-v1.md)에 **이름을 더한다**(그 문서 9절상 호환). 기존 이름·타입·QoS 는 바꾸지 않는다.
- 요구사항 / 완료 조건: #520 결정 1–5. 이 PR 은 문서만 바꾼다. 메시지·코드는 아래 "단계"의 PR 에서 생산자·소비자를 같이 바꾼다.

**이 문서가 정하는 것**: QR 접두와 ID 형식, 약 DB 의 표와 소유자, 카메라 한 장 찍기 요청, 흡착 압력 토픽.
**정하지 않는 것**: 판독률 합격선(6단계 PR 에서 결과 전에 고정), 압력 모사의 수치(시뮬 설정값).

접두 해석(9/23 확인): `cn-` 는 지금 코드의 캐니스터다. `md-` 는 사각 알약통이다.
재범은 "약통 및 모듈의 QR"을 따로 말했다. 모듈은 "사각형 알약통"이라고 답했다.
#520 의 "cn- 약통(= 모듈은 사각형 알약통)" 문구를 이렇게 읽는다. 재범 확인 여부는 미확인이다.

## 1. QR 접두와 ID

QR 에는 **ID 만** 담는다. 약 이름·유통기한 같은 정보는 DB 에서 찾는다(#520 결정 2). GS1 은 범위 밖이다.

| 접두 | 대상 | ID 형식 | `TagRead.kind` | `tag_id` |
| --- | --- | --- | --- | --- |
| `ord-` | 봉투 | `ord-[0-9]{4}` (기존) | `KIND_POUCH=2` (기존) | QR 내용 전체 (기존) |
| `pt-` | 환자 | `pt-<환자 ID>` (기존) | `KIND_PATIENT=0` (기존) | 접두 뗀 것 (기존) |
| `st-` | 스테이션 | `st-<zone id>` (기존) | `KIND_STATION=1` (기존) | 접두 뗀 것 (기존) |
| `cn-` | 약통(지금 코드의 캐니스터) | `cn-[0-9]{4}` | `KIND_CONTAINER=3` (신설) | QR 내용 전체 |
| `md-` | 모듈(사각 알약통) | `md-[0-9]{4}` | `KIND_MODULE=4` (신설) | QR 내용 전체 |

- 새 접두도 봉투처럼 **QR 내용 전체가 ID** 다. DB 의 기본 키와 같은 문자열이다.
- 형식 판정의 원본은 `rokey_p3_perception/qr_payload.py` 정규식이다(배송 계약 7절과 같다). 모르는 접두는 지금처럼 버린다.
  - `cn-`·`md-` 는 `parse_tag` 가 `[0-9]{4}` 형식까지 본다(`qr_payload.py` 13–14·32·58–60행).
  - `ord-` 는 `parse_tag` 가 공통 ID 형식(`^[a-z0-9][a-z0-9_-]{0,63}$`)만 본다. `ord-[0-9]{4}` 판정은 `is_order_id` 에만 있다(11–12·70–72행).
  - 봉투 집기는 판독 ID 가 goal 의 `order_id` 와 같을 때만 한다(`pick_permission.select_detection`). 그래서 형식이 다른 `ord-` 판독은 집기에 쓰이지 않는다.
- `TagRead` 에는 상수만 더한다. 필드는 바꾸지 않는다. 기존 소비자는 모르는 `kind` 를 무시해야 한다.
  - 상수와 소비자 처리는 3단계 PR 에서 같이 넣는다.

QR 이미지는 **DB 시드**의 ID 로 만든다. 봉투는 지금처럼 `order_pool.yaml` 에서, 약통·모듈은 새 시드에서 만든다.
생성 스크립트는 simulation 소유 그대로다(`sim/standalone/make_qr_textures.py`). 접두 확장 PR 은 이 레인이 내고 simulation 담당이 검토한다.

## 2. 약 DB

### 2.1 소유와 수명

| 항목 | 규칙 |
| --- | --- |
| 저장 | sqlite 파일 하나. 경로는 orchestrator 파라미터 `pharmacy_db_path`(비우면 메모리). 열 때 모든 표를 비우고 다시 채운다(run 마다 새로) |
| 쓰는 쪽 | **orchestrator 프로세스 하나.** 다른 노드는 파일을 열지 않는다. 필요한 값은 토픽·액션 결과로 받는다 |
| 시드 | 기존 `dispenser.yaml`·`order_pool.yaml` 은 그대로 시드로 남는다(#520 결정 5). 약 마스터·약통·모듈은 새 시드 yaml 에 둔다 |
| 기동 | orchestrator 파라미터 `pharmacy_db`(기본 false)가 켜졌을 때만 연다. 병원 기본은 `P3_CONTAINER_QR=1` 이라 `pharmacy_db:=true` 다(`demo_v2.sh` 473행). 시드 세 파일을 읽어 표를 채운다. `pharmacy_catalog_file` 을 비우면 share 의 `pharmacy_catalog.yaml` 이다. 시드 검증 실패면 기동을 거부한다. 예외는 `CatalogError` 다 |
| 현장 재고 파일 | 노드는 재고 파일과 카탈로그의 로트가 어긋나도 기동한다(현장 `dispenser_refill.yaml` 등). 재고 파일의 로트에 cn- ID 가 없으면 그 로트는 약통 표에 없다. 카탈로그가 재고 파일에 없는 로트를 **이름만** 가리키는 줄은 건너뛴다. 둘 다 경고 한 줄로 남는다. 선반 약통(제 값을 다 적은 줄)은 그대로 들어간다 |
| 리셋 | 약통·모듈·봉투 표는 시드로 되돌린다. **스캔 기록은 지우지 않는다**(epoch 열로 구분한다). 배송 계약 6절 3 의 "파일 값으로 되돌림"은 이 표들에 해당한다. 스캔 표는 그 되돌림 밖이다 |
| 오늘 날짜 | 만료 판정의 기준일은 run 설정값이다(orchestrator 파라미터 `pharmacy_today`, 비우면 카탈로그의 `today`). 벽시계를 쓰지 않는다. 같은 시드·같은 `today` 면 같은 판정이 나와야 한다 |
| 재고 모듈 | `dispenser_inventory.py`(2슬롯·FEFO·임계값)와 그 시험은 **바꾸지 않는다**(#520 결정 5). DB 는 조회·기록을 더하고 FEFO 판단은 기존 모듈이 한다 |

### 2.2 표

열 이름은 `rokey_p3_orchestrator/pharmacy_db.py` 의 `SCHEMA` 가 원본이다. 여기서는 무엇이 들어가는지와 키만 정한다.

| 표 | 키 | 담는 것 |
| --- | --- | --- |
| `drug` (약 마스터) | `item_id` (기존 `drug-amox` 형식) | 이름, 성분·함량, 제형, 보관 조건, 고위험 여부 |
| `container` (약통 `cn-`) | `container_id` | `item_id`, 유통기한, 로트, 잔량, 위치(선반·슬롯 a/b), 상태, 입고일 |
| `module` (모듈 `md-`) | `module_id` | 사각 알약통. 든 약(약·수량), 출처 약통(`source_container`, 로트는 그 약통에서 찾는다), 위치, 상태 **(제안·미확정: 모듈이 어느 흐름에서 쓰이는지는 아직 정하지 않았다)** |
| `pouch` (봉투 `ord-`) | `order_id` | 든 약(약·수량·약통·로트), 집는 로봇, 수령 확인, 목적지(환자·병상), 발행 시각, 처방 ID, 긴급, 복용 시점, 전달 기한 |
| `pouch_status` | (`order_id`, 순번) | 봉투 상태 이력. 시각은 sim time, epoch 포함 |
| `scan` (스캔 기록) | 순번 | 누가(로봇·노드), 어디서(zone, 약통 확인이면 선반 칸), 언제(stamp, epoch), 무엇(QR 내용), 결과(아래) |

약통 상태: `in_use`(슬롯 장착), `standby`(선반 대기), `expired`, `recalled`.

선반 약통은 스테이지 scene v2 의 16칸과 1:1 이다(`cn-0101..0116`, 위치 `shelf:<칸>`, 9/23 결정). 카탈로그 시험이 스테이지 칸과 대조한다.
병원 M0609 워크셀 18칸도 1:1 이다(`cn-0201..0218`, 위치 `shelf:<칸>`). 만료 칸은 빈월드 `floor_right/r0c1`(cn-0106), 병원 `shelf_72/r0c0`(cn-0211)이다.

스캔 결과 값: `ok`(DB 에 있음), `unknown_id`(형식은 맞지만 DB 에 없음), `bad_format`(접두·형식 틀림), `expired`(약통이 만료),
`recalled`(약통이 회수), `mismatch`(기대한 ID 와 다름), `stale_epoch`(약통 확인 요청이 다른 epoch). 기록은 판정을 바꾸지 않는다. 판정은 기존 규칙(배송 계약 2.3 `qr_mismatch` 등)이 한다.

v1.1.0 코드에서 `scan` 표에 들어가는 것은 약통 확인(`CheckContainer`) 한 가지다.
orchestrator 는 `/amr_1/hand_camera/tag_reads` 를 받지만 트립 FSM 에만 넘긴다(`orchestrator_node.py` 334–338행).
`PharmacyDb.record_scan` 은 있지만 orchestrator 가 부르지 않는다(`pharmacy_db.py` 363행). 그래서 봉투·인식표 판독은 DB 에 남지 않는다.

### 2.3 장착 거부

- 보충 때 장착할 약통이 **만료(`유통기한 < today`)거나 `recalled`** 면 장착하지 않는다.
- 판정은 DB 모듈의 순수 함수다. ROS 를 import 하지 않고 L1 로 시험한다.
- 부르는 자리(9/23 결정, 재범 전결): **M0609 가 잡기 직전에 약통 QR 을 읽고 orchestrator 에 묻는다.**

| 인터페이스 | 생산자 → 소비자 | 타입 | 시한 | 실패 |
| --- | --- | --- | --- | --- |
| `/orchestrator/check_container` | m0609/arm → orchestrator | srv `CheckContainer` (신설) | 2 s wall(팔 쪽) | 시한 초과·서버 없음 = 거부 |

```
string container_id      # QR 내용 cn-NNNN
string robot_id          # m0609
string cell_id           # 스테이지 선반 칸(기록용)
uint32 epoch             # 팔이 본 마지막 RESET_DONE 의 epoch. 0 = 아직 못 봄(현재 epoch 로 받는다)
---
bool allowed
string reason            # ok, expired, recalled, unknown_id, bad_format, stale_epoch
```

- orchestrator 는 `pharmacy_db` 파라미터가 켜졌을 때만 이 서비스를 낸다. 스캔 한 줄을 결과와 함께 남긴다.
- 서비스는 자기 콜백 그룹에서 돈다. orchestrator 는 Refill 결과를 콜백으로 받으므로 Refill 도중의 질문에 막히지 않는다(L2 로 고정).
- 거부면 팔은 **잡기 전에** Refill 을 `success=false` 로 닫고, 그 칸은 같은 epoch 에서 다시 고르지 않는다. orchestrator 의 보충 재시도(최대 3회)는 그대로이므로 다음 시도는 다른 칸이다.
- `Refill` 액션 필드와 `REFILL_*` 이벤트는 바꾸지 않는다. 결과의 `lot_id` 에 읽은 약통 ID 를 싣는다(기록용, 계약 2.1 끝과 같은 뜻).
- 팔 쪽(m0609/arm, 파라미터 `container_check`, 기본 false):
  - 판독은 `/m0609/hand_camera/tag_reads` 의 약통 판독 중 `grasp_pose` 도착 뒤 stamp 인 것만 쓴다. `container_read_timeout_s`(2 s sim) 동안 기다린다.
  - `tag_reads` 는 `pouch_detector` 인스턴스 `m0609_detector` 가 `/m0609/hand_camera/image_raw` 에서 읽어 낸다. 자리만 찾고 못 읽은 QR 은 네 점으로 펴서 한 번 더 읽는다([QR 배치와 카메라 구성](qr-camera-layout.md) 3절).
  - 약통 QR 은 몸통 앞(통로 쪽) 스티커이고, 높이는 `grasp_pose` 에서 손 카메라 축에 맞춘다(재범 9/23). 그래서 이 자세에서 스티커를 정면으로 본다.
  - 노드 파라미터 `container_check` 의 기본은 false 다(`m0609_arm_node.py` 239행).
  - `demo_v2.sh` 는 `P3_CONTAINER_QR=1` 일 때 `container_check:=true` 를 준다(407행). 병원 기본은 1, 그 밖은 0 이다(191행).
  - 확인은 잡기 직전 그리퍼를 닫는 단계 앞에서 한다(`m0609_arm_node.py` 1711–1715행). 장면 v2 계획은 레일 고르기(`first_feasible`·`preferred_first`)와 상관없이 이 단계 실행을 거친다(1678행).
  - 서비스 시한은 `container_check_timeout_s`(2 s wall)다.
  - DB 가 아닌 팔 쪽 거부 이유: `unreadable`(판독 없음, 서비스를 부르지 않는다), `check_timeout`(서비스 없음·무응답). 거부 detail 은 `container_refused <ID> cell=<칸> reason=<이유>` 다.
  - 가드 모듈 경로(`v2_guarded_module_path` 의 module 칸)는 아직 이 확인을 거치지 않는다.

## 3. 카메라 한 장 찍기

**구현 현황(v1.1.0 `f316197`)**: 이 절의 `capture`·`CaptureFrame`·`camera_mode` 는 **미구현**이다. `CaptureFrame.srv` 가 `rokey_p3_interfaces` 에 없다. 지금 손 카메라는 연속 발행(`--camera-max-hz`, 기본 10 Hz)이다.
지금 해상도 기본은 AMR 1280×800(`P3_CAMERA_RESOLUTION`), M0609 960×600(`--m0609-camera-resolution`)이다. 판독률 실측으로 정한 값은 아니다(6.3).
계약 밖 토픽이 하나 있다. 검출기가 `/<robot>/hand_camera/qr_view`(`sensor_msgs/Image` bgr8, 폭 ≤ 640, S depth 2)로 QR 추적 영상을 낸다(#787). 보는 구독자가 있을 때만 그린다(`pouch_detector_node.py` 125–127·239–247행).
카메라를 하나 켜면 빈월드 rtf 가 약 0.2 떨어졌다([실습41](../practice/emptyworld/practice-41.md)). 이 절을 구현하는 근거로 남긴다.

QR 을 읽어야 할 때 **로봇이 선 것을 확인한 뒤 한 장만** 찍는다(#520 결정 1). 카메라는 평소 끈다. 컬러만 쓰고 깊이는 끈다.

| 인터페이스 | 생산자 → 소비자 | 타입 | 시한 | 실패 |
| --- | --- | --- | --- | --- |
| `/<robot>/hand_camera/capture` | 요청자(arm, m0609/arm) → isaac(adapter 경유) | srv `CaptureFrame` (신설) | 2 s wall **(제안·미확정)** | 아래 `message` |
| `/<robot>/hand_camera/image_raw`, `camera_info` | isaac → pouch_detector | 기존 그대로 | 요청마다 **한 장** | — |

`<robot>` 은 `amr_1`, `m0609` 다. `amr_1` 은 배송 계약 2.1 의 손 카메라 이름 그대로이고, `/m0609/hand_camera/*` 는 새 이름이다(같은 타입·QoS).

시한 2 s 는 `Dispense` 에서 빌린 값이다. 꺼 둔 렌더 프로덕트를 켜면 첫 프레임이 늦을 수 있다(Isaac 에서 미측정). 6단계 판독률 실측에서 같이 재고 정한다.

새 프레임(배송 계약 3절 TF 표에 더한다):

| 항목 | 값 |
| --- | --- |
| 이름 | `m0609/hand_camera_optical` |
| 부모 | `link_6`(M0609) |
| 작성자 | isaac TF 발행기 (simulation). **지금은 내지 않는다**(9/23, #550): 부모 `link_6` 을 포함한 M0609 링크 TF 가 아직 없어서, 내면 트리에서 끊긴 프레임이 된다. 약통 QR 판독은 이미지만 쓰고 TF 를 조회하지 않는다. M0609 링크 TF 를 내는 PR 에서 같이 낸다. v1.1.0 에서도 내지 않는다(`canister_qr.py` 325행 `tf=none`) |
| 비고 | `/m0609/hand_camera/*` 의 `image_raw`·`camera_info`·`tag_reads` header 프레임. 장착값은 5절 자산 표(M0617 에서 추출, **M0609 미확인**). optical 축 규약은 `amr_1/hand_camera_optical` 과 같다 |

`CaptureFrame` (4단계 PR 에서 생산자·소비자와 같이 넣는다)

```
uint32 epoch          # 요청자가 본 마지막 RESET_DONE 의 epoch
string request_id     # 캡처 ID. 요청자가 만든다. 같은 ID 재요청은 같은 응답(재전송 멱등)
---
bool accepted
string message        # accepted=false: not_stopped, busy, stale_epoch, camera_unavailable
builtin_interfaces/Time stamp   # 찍은 이미지의 header.stamp(sim time). accepted=false 면 0
```

- `CaptureFrame.request_id` 는 배송 계약 7절의 `request_id`(`Deliver` 요청, 재수신 거부)와 **다른 ID** 다. 캡처 재전송을 멱등으로 만드는 용도이고 형식은 요청자가 정한다.
- **정지 확인은 두 번 한다.**
  - 요청자는 요청 전에 자기 쪽 정지를 확인한다. AMR 은 `base/stopped=true`, 팔은 관절 속도가 문턱 아래로 정착한 뒤다. 문턱은 파라미터다.
  - isaac 은 찍기 직전에 해당 로봇의 관절·베이스 속도를 다시 본다. 움직이면 `not_stopped` 로 거절하고 찍지 않는다.
- `accepted=true` 이면 isaac 은 그 한 장을 `image_raw`·`camera_info` 로 **정확히 한 번** 내고, 응답의 `stamp` 는 그 이미지의 stamp 다.
- 요청자는 `tag_reads` 중 `header.stamp == 응답 stamp` 인 판독만 쓴다. 배송 계약 2.4 의 "1.0 s 이상 오래된 판독은 버린다"는 그대로다.
- 판독이 없으면 빈 결과다. 재촬영은 요청자의 기존 재시도 한도 안에서 한다(`ScanTag` 1회 등). 새 재시도 횟수를 만들지 않는다.
- 리셋 barrier 동안은 `stale_epoch` 로 거절한다.
- 해상도는 **판독률 실측으로 정한다**(#520 결정 3). 640×480·20 cm·한 변 4 cm 는 어림이고 합격선이 아니다.

**이행**: 지금 `pouch_detector` 와 arm 은 연속 이미지에 기댄다.
isaac 쪽에 `camera_mode` 파라미터(`continuous` 기본, `on_request`)를 두고, 소비자가 `capture` 를 부르게 된 PR 에서 기본값을 바꾼다.
`continuous` 일 때 `capture` 는 다음 한 장의 stamp 를 돌려준다. 그래서 요청자 코드는 두 모드에서 같다.
기본값을 `on_request` 로 바꾸는 PR 은 배송 계약 2.1 손 카메라의 rate 규칙("10 Hz 이하")도 같이 고친다.

## 4. 흡착 압력

| 인터페이스 | 생산자 → 소비자 | 타입·단위 | QoS·rate | 실패 |
| --- | --- | --- | --- | --- |
| `/amr_1/gripper/pressure` | isaac(adapter 경유) → arm, GUI, event_logger | `std_msgs/Float32`, **kPa 게이지압**. 대기 = 0, 진공은 음수 | H, 10 Hz(`GripperState` 와 같다) | 모르면 NaN |

- 범위는 AMR 흡착 그리퍼 하나다. M0609 는 RG2 손가락 그리퍼(`m0609_refill_stage` 의 `finger_joint`)라 압력 토픽이 없다.
- **파지는 압력으로 안다.** 압력을 추적해 판정하는 것은 **생산자**(isaac, 실물이면 그리퍼 드라이버)다. 판정 결과를 싣는 곳은 기존 `GripperState` 하나다(#520 결정 4, 상태 표시를 둘로 나누지 않는다).
  - 실물 규칙: 압력이 문턱(파라미터, kPa) 아래로 내려가 정착 시간(파라미터) 동안 유지되면 `state=HELD`, 대기압 쪽으로 올라오면 `RELEASED` 다.
  - 소비자(arm 등)는 `GripperState` 만 본다. `/amr_1/gripper/pressure` 를 직접 판정에 쓰지 않는다. `Float32` 에는 stamp·epoch·seq 가 없어서다. 압력 토픽은 표시·기록용이다.
  - `GripperState` 필드는 바꾸지 않는다.
- 시뮬에서 압력은 **모사값**이다. isaac 은 SurfaceGripper 상태에서 둘(`GripperState`·압력)을 같은 step 에 만든다.
  - `GripperState.state`: 닫힘·붙음 → `HELD`, 열림 → `RELEASED`, 그 밖 → `UNKNOWN`. 이때 `mode=PHYSICAL` 이다.
  - 파지·해제 확인 조건은 배송 계약 11.6 그대로다. `HELD` 라도 `last_applied_command_seq` 가 닫기 명령의 `command_seq` 이상일 때만 파지다. `epoch`·`seq` 규칙도 11.6 공통 규칙을 따른다.
  - 압력: 상태별 설정값. 수치는 시뮬 설정 파일에 두고 "모사"라고 적는다. 현장 수치가 아니다.
- 가상 attach(`mode=VIRTUAL`)일 때 압력은 NaN 이다. 가상 흡착을 압력으로 꾸미지 않는다.

## 5. 단계와 PR

| 단계 | 바뀌는 것 | 검증 |
| --- | --- | --- |
| 1 (이 PR) | 이 문서, 배송 계약 2.4·7절의 가리킴, 계약 목록 | 문서 검사 |
| 2 | orchestrator DB 모듈·시드, 장착 거부 순수 함수 | L1 unittest. 재고 모듈 시험은 그대로 통과해야 한다 |
| 3 | `qr_payload` 정규식, `TagRead` 상수, QR 이미지 생성 | L1, 생성 이미지 되읽기 |
| 4 | D455 부착(AMR·M0609), `camera_mode`, `CaptureFrame` | 오프라인 기하 대조, 마스터 L3 |
| 5 | 압력 모사, `GripperState` PHYSICAL 경로 | 마스터 L3 |
| 6 | 판독률 실측 | 판정선을 PR 에 먼저 고정한 뒤 master02 슬롯 |

`sim/scenes/*.usda` 는 바꾸지 않는다. D455 는 런타임에 reference 로 붙인다.

4단계 자산:

| 로봇 | 자산 | 장착값 | 상태 |
| --- | --- | --- | --- |
| AMR | #506 `gripper-only.usd`(흡착 그리퍼+D455) → `sim/assets/amr_gripper/short_gripper.usd` 로 승격(#538) | 자산에 들어 있다. 흡착점 손목 +Z 0.1555 m, 컬러 카메라 (−0.0115, 0.07, 0.0355) m(오프라인 측정) | `--amr-hand-camera` 가 합본 손목에 reference 한다. 강체·조인트·흡착 프림·충돌은 끈다. `AssemblerFixedJoint` 는 다시 잇지 않고 끈다. D455 의 좌·우 IR·가짜 깊이 카메라와 렌더 프로덕트 틀도 끈다(컬러만) |
| M0609 | D455 컬러 내부값의 USD Camera 를 따로 두고 매 스텝 `link_6` 을 따라가게 한다(링크가 인스턴스 프림일 수 있어 자식으로 못 단다). 보이는 몸체로 AMR 자산의 D455 서브트리를 그 카메라 아래에 reference 하고, 그 안의 카메라 넷은 끈다. #550 | `link_6` 기준 t=(0, 0.0483, 0.0185) m, 컬러 q(wxyz)=(0, 0, 1, 0), HFOV 90.5° | **M0617 에서 추출, M0609 미확인**(#134 조립에서 뽑음) |

## 6. 구현 현황 (기준: main `f316197`, v1.1.0)

- 상태 표식은 `proposed` 그대로다. 아래 "구현"은 코드가 있다는 뜻이고, 계약이 확정됐다는 뜻이 아니다.
- 6.1 의 항목은 모두 v1.1.0 코드에 있다. 대조한 파일은 `qr_payload.py`, `TagRead.msg`, `CheckContainer.srv`, `pharmacy_db.py`, `orchestrator_node.py`, `m0609_arm_node.py`, `qr_rectify.py`, `read_snapshot.py`, `canister_qr.py`, `amr_base.py`, `tools/demo_v2.sh` 다.
- **골든-4** 열은 9/24 기록이다. 그 커밋(또는 같은 변경)이 `aca8840` 에 있으면 Y. main 에만 있었으면 "main".
- **회차 증거** 열: #240 댓글 ID 와 그 회차의 실행 SHA. 회차 증거가 없으면 "없음(코드만 됨)"이다. #240 에 게시되지 않은 원문은 그렇다고 적는다.
- v1.1.0 커밋 `f316197` 로 돌린 acceptance 회전은 없다(릴리스 v1.1.0 본문). 9/29 변경의 L3 상태는 #772 댓글 5891599172(대조 기준 `7860b4c`)를 따른다.

### 6.1 QR·DB·약통 확인

| 항목 | 구현 | 골든-4 | 회차 증거 |
| --- | --- | --- | --- |
| 1절 접두 `cn-`·`md-`, `TagRead` 상수 | #545 | Y | L1 |
| 2절 약 DB·시드. 선반 16칸(빈월드)·워크셀 18칸(병원 `cn-0201..0218`) | #522·#545·#546 | Y | L1 |
| 2.3 `CheckContainer`·orchestrator 서비스 | #546 | Y | L2(Refill 도중 거부 뒤 허용) |
| 2.3 M0609 잡기 직전 판독·거부·칸 제외 | #548 | Y | 원통: 5794528230(`35fb28a`) `약통 확인 'cn-0208' cell=shelf_70/r0c1 → 장착 허용`. 모듈: 아래 모듈 잡는 높이 |
| 2.3 `CheckContainer.epoch` 0 = 아직 못 봄(현재 epoch 로 받는다) | #636(`d4ca497`) | main | 실패 5800180626(회차33, `5a51804`): `container_refused cn-0204 … reason=stale_epoch … epoch 0`. 통과 5800360786(회차34, `d6b88b1` = `5a51804` + 이 커밋): stale_epoch 0줄, `cn-0204 … 장착 허용 (ok)` |
| 약통 QR 을 몸통 앞 스티커로(원통 곡면·모듈 앞면, 두께 0.5 mm) | `2276027`(#553) | Y | 5794528230(`35fb28a`) 원통 cn-0208 판독·허용 |
| 모듈 잡는 높이 중심 + 0.03 m(손 카메라가 선반 가로보 위로) | `f8eac1c`(#608) | Y | 실패 5795027810(`94f19fb`)·5795355277(`05339c9`): 모듈 `unreadable`. 통과 5795627672(`f8eac1c`, master02) `약통 확인: cn-0204 cell=shelf_68/r0c1 장착 허용` → REFILL_DONE 71.58. 재현 5795682106(`f8eac1c`, master01) 5/5 |
| 펴서 다시 읽기(`qr_rectify.reread`) | `429ac27`(#553) | Y | 5794528230(`35fb28a`) 원통 판독. `펴서 읽었다: cn-0208. 한 변 81 px` 줄 원문은 #240 에 없다(master02 직접 전달) |
| 2 배로 키워 다시 읽기(`qr_rectify.read_enlarged`) | `05339c9`(#608) | Y | 모듈에는 효과 없음 5795355277(`05339c9`, 원인은 가림). 봉투·약통 판독: 회차17(`4d01333`) `키워서 읽었다: ord-0001 49/65/64 px`, `cn-0204 59~74 px` — **#240 게시 없음**(master01 원문, 로그 master01 `~/markle_tmp/m1-hospital-cam-4d01333-17/`) |
| 거울상 뒤집어 다시 읽기 | `87394bb`(#553) | main | 없음(master colcon 거울상 시험 회귀 수정. 시뮬 영상은 거울상이 아니다) |
| 약통 QR 판독 순간 손 카메라 한 장(발표 PiP, `read_snapshot`) | `fa1be27`(#628). 발행 뒤 저장·실패는 경고 `5595180`(#628) | Y(발행 순서 수정은 main) | 없음(코드만 됨). `<기동시각>-qr-reads/` 폴더 확인 미실행 |
| M0609·합본 D455 컬러만(좌·우 IR·가짜 깊이 끔) | `2276027`(#553) | Y | 없음(카메라 목록 확인 미실행) |

### 6.2 봉투·인식표 카메라 QR — v1.1.0 병원 기본

이 절의 9/24 문장(결정 ④ 를 옮긴 것, 고치지 않는다): "집기는 참값 센서(`pouch_source: sim`)가 기본이다. 카메라 집기는 선택이고 영상 편성에 들지 않는다. 영상의 D455 는 약통 QR 확인 장면이다."

이 기본은 재범 9/29 결정으로 병원에서 카메라로 바뀌었다(#784 본문 인용: "QR 반드시 찍고 가져가야함", "병상 QR을 찍고 약을 찍어서 매칭을 한 다음에 그 다음에 약을 내려놔야함"). #797 이 v1.1.0 기본으로 넣었다.

v1.1.0 코드:

- `P3_CAMERA_POUCHES` 는 병원 기본 1 이다. `P3_CAMERA_TAGS` 는 그 값을 따른다(`tools/demo_v2.sh` 126·162–163행).
- 스택 인자는 `use_pouch_detector:=true pouch_source:=camera scan_tag_source:=camera` 다(`demo_v2.sh` 444·449행).
- 봉투는 판독 QR 이 goal 주문과 같을 때만 집는다(`pick_permission.select_detection`, 51–63행). 다른 QR 만 읽히면 `qr_mismatch`, 못 읽으면 `not_detected` 다.
- 병상·스테이션 인식표(`pt-`·`st-`)도 손 카메라 QR 로 읽는다. 팔은 `<zone>/tag` 를 `tag_standoff_m` 0.25 m 에서 본다(`ur5_arm.amr-combined.camera-receiver.yaml`).
- 참값으로 되돌아가는 길은 없다. 참값 집기는 `P3_CAMERA_POUCHES=0` 을 줄 때만이다(#784).
- 봉투는 A1 모듈 탁자(receiver prim `SM_SideTable_02a_74`)에 정착한다. 합본은 그 앞 적재 자리에서 집는다. 그 자리가 `dock_1` 이다(`zones.hospital-receiver.yaml`, #796·#797, `demo_v2.sh` 127–136행).
- 벨트 관측 오프셋은 병원 카메라 기본에서 0 이다(`demo_v2.sh` 135행).
- 탁자 집기는 손목 J6 를 고정하고 재관측을 건너뛴다. 파지 높이는 탁자 평면에서 0.05 m 더 내린다(`arm_node.py` 1395–1396·1424·1438–1453행, `belt_pick_contact_drop_m: 0.05`). 이 0.05 m 는 실측 보정이다. 높이 오차의 근본 수정이 아니다(params 파일 1행).

| 항목 | 구현 | 골든-4 | 회차 증거 |
| --- | --- | --- | --- |
| 재관측이 이 주문 QR 을 먼저 고른다, 관측·재관측 로그 | `289a384` | Y | 실패 회차17(`4d01333`): 재관측 자세로 가다 팔뚝↔컨베이어 touch 7, timeout ×2(#240 게시 없음, 위와 같은 원문) |
| 첫 관측에서 QR 을 읽었으면 재관측 생략 | `626cb3f`(exp) | N | 5798030004(회차20, `626cb3f`): touch 7 → 0, 판독 45–135 px. 집기 `grasp_failed` ×2, 흡착 nearest 0.100–0.104 m |
| QR 을 읽은 검출은 QR 중심을 봉투 자리로 | `8e63d37`(exp) | N | 5799937654(회차31, `8e63d37`): nearest 0.10 → **0.057 m**(한도 0.04), 판독 55·60·68 px. `grasp_failed` ×2 |
| 집기 잔차 계측(팔 목표↔도달 FK 흡착점, 스테이지 miss 줄의 tcp·봉투 좌표) | `4baab3d`(exp) | N | 없음(회차 미실행) |
| 병원 QR 필수: 봉투·인식표 카메라 기본 | #784 | — | #772 5891599172: bed_a1 1건만(#796) |
| 탁자 정착 + 도크 = 적재 자리 + 추가 하강 0.05 m | #796(`7860b4c`), #790, #797 | — | [실습45](../practice/simworld/practice-45.md): `05b8e28`(후보 작업 트리) bed_a1 1건 DELIVERED, 흡착거리 0.0052 m, 카메라 판독 환자 2001 → `AUTH_OK`. 탐색 실습이다. acceptance 가 아니다. `7860b4c` 통합본과 v1.1.0 은 미실행 |
| QR 추적 영상 `/<robot>/hand_camera/qr_view` | #787 | — | 미실행(#772 5891599172) |
| 웹 QR 판독 요약 `snapshot.qr_reads` | #786(`web/api.md` 1.12) | — | 미실행 |
| 웹 약 QR 매칭 칩·사유 | #785 | — | 미실행 |

- exp 커밋 `626cb3f`·`8e63d37`·`4baab3d` 는 main 의 조상이 아니다(`git merge-base`). QR 을 읽은 검출의 자리를 QR 중심으로 두는 규칙은 main 코드에 있다(`pouch_detector_node.py` 418행).
- 잔차 해석(오프라인, 회차31 `pouch_at_end` 참값 대조): QR 중심 검출은 참값에서 수평 약 2 cm·높이 1 cm 안이다. 남은 0.057 m 는 집기 목표 → 실제 흡착점 쪽이다(미확인, 위 계측으로 가른다).
- 롤러 끝 카메라 흡착 오차의 근본 원인은 고치지 않았다. #796 은 탁자 정착과 추가 하강 0.05 m 로 우회했다(#772 5891599172).
- 관측·재관측 자세에는 충돌 검증이 없다(설계 갭 G7 "관측 자세 충돌 검증").

### 6.3 미구현·미실행

| 항목 | 상태 |
| --- | --- |
| 3절 한 장 찍기(`CaptureFrame`·`camera_mode`) | 미구현. 두 손 카메라는 연속 발행(`--camera-max-hz` 10 Hz) |
| 4절 흡착 압력 | 미구현. `/amr_1/gripper/pressure` 발행·구독이 코드에 없다 |
| 6단계 판독률 실측 | 미실행. 판독 줄은 2 s 에 한 번으로 묶여 로그로는 비율을 못 센다 |
| 약 DB 의 봉투·인식표 스캔 기록 | 없음. `scan` 표에는 약통 확인만 들어간다(2.2 끝) |

### 6.4 병상 인식표 판(계약 밖 소품)

| 항목 | 구현 | 골든-4 | 회차 증거 |
| --- | --- | --- | --- |
| 병원 협탁 환자 인식표 판(`pt-<환자 ID>` QR). 9/24 기록은 "시각 전용, 인증은 참값 그대로"였다 | `77239a9`(#628) | Y | 없음(정지 캡처·`patient_plates plates=10` 로그 미확인) |
| 판을 로봇 가까운 가장자리로 옮기고 `<bed>/tag` TF 와 QR 면을 맞춤. 스테이션 테이블은 `st-<zone>` 판 | `7c59bc82`(#796) | — | [실습45](../practice/simworld/practice-45.md) bed_a1 카메라 판독 `AUTH_OK` 1건(`05b8e28`). 다른 병실은 미실행 |

- v1.1.0 병원 기본에서 카메라 인증은 이 판의 QR 을 읽는다(`scan_tag_source:=camera`, `sim/standalone/p3sim/patient_plates.py` 3행). 판 한 변은 0.10 m, QR 한 변은 0.08 m 다(9–11행).
- 스테이지는 병원에서 늘 `--patient-plates` 를 준다(`demo_v2.sh` 350행).

회차별 판독 원문·px 표는 [회차별 QR 판독](../presentation/qr-reading-rounds.md), 배치·카메라 구성은 [QR 배치와 카메라 구성](qr-camera-layout.md), 빈월드 L3 기록은 [실습41](../practice/emptyworld/practice-41.md)이다.

## 7. 검증

이 PR 시점의 검증: 문서 검사만 한다. **L1·L2·L3 는 전부 미실행**이다(코드 변경 없음).
2026-09-30 v1.1.0 대조도 문서만 고쳤다. 코드를 읽어 대조했다. 새로 돌린 시험·회차는 없다.

## 8. 변경·롤백

- 모든 항목이 이름 추가다. 되돌리면 이 문서와 가리킴만 지운다.
- `camera_mode=continuous` 가 기본인 동안은 기존 연속 이미지 경로가 그대로 돈다.

## 9. v1.1.0 대조 (2026-09-30)

main `f316197` 의 코드와 이 문서를 맞대 본 결과다. 문서가 코드와 다른 곳은 문서를 코드에 맞췄다. 계약의 결정 문구는 바꾸지 않았다.

| 곳 | 문서가 말하던 것 | 코드가 하는 것 | 근거 |
| --- | --- | --- | --- |
| 1절 `ord-` 형식 판정 | `qr_payload.py` 정규식이 `ord-[0-9]{4}` 를 본다 | `parse_tag` 는 `ord-` 뒤를 공통 ID 형식으로만 본다. 엄격 형식은 `is_order_id` 에만 있다 | `qr_payload.py` 11–14·23–32·70–72행 |
| 2.2 `scan` 표 | 로봇·zone·결과를 담는 스캔 기록 | 약통 확인만 기록한다. 봉투·인식표 판독은 기록하지 않는다 | `orchestrator_node.py` 334–338·593행, `pharmacy_db.py` 363행 |
| 3절 계약 밖 토픽 | 없음 | `/<robot>/hand_camera/qr_view`(Image bgr8, 폭 ≤ 640, best effort depth 2). 구독자가 있을 때만 낸다 | `pouch_detector_node.py` 47–49·125–127·239–247행 |
| 3절 해상도 | 640×480 어림, 실측으로 정한다 | AMR 1280×800(`P3_CAMERA_RESOLUTION`), M0609 960×600. 스테이지 인자 기본은 640×480 이다 | `demo_v2.sh` 193행, `pharmacy_stage.py` 527·593행 |
| 6.2 봉투 집기 기본 | 참값 센서가 기본, 카메라는 선택 | 병원 기본이 카메라 집기다. 인식표도 카메라다. 참값으로 되돌아가지 않는다 | `demo_v2.sh` 126·162–168·444·449행, `pick_permission.py` 51–63행 |
| 6.4 병상 인식표 판 | 시각 전용, 인증은 참값 | 병원 기본의 카메라 인증이 이 판을 읽는다. 스테이션 `st-` 판도 있다 | `patient_plates.py` 3·29–46행, `demo_v2.sh` 350·444행 |
| 2.3 확인 경로 | (레일 고르기와의 관계를 적지 않았다) | `preferred_first`(v1.1.0 기본) 도 같은 단계 실행에서 확인한다 | `m0609_arm_node.py` 1678·1711–1715행, `demo_v2.sh` 406행 |

이름이 코드와 같은 것(바꾸지 않음): 접두 `ord-`·`pt-`·`st-`·`cn-`·`md-`, `TagRead.KIND_*` 0–4, `CheckContainer` 필드와 `reason` 값, 서비스 `/orchestrator/check_container`, 토픽 `/m0609/hand_camera/image_raw`·`camera_info`·`tag_reads`, 프레임 `m0609/hand_camera_optical`(TF 없음), 파라미터 `pharmacy_db`·`pharmacy_catalog_file`·`pharmacy_db_path`·`pharmacy_today`·`container_check`·`container_read_timeout_s`·`container_check_timeout_s`.
근거: `TagRead.msg`, `CheckContainer.srv`, `orchestrator_node.py` 236–239·294–295행, `m0609_arm_node.py` 239–242·370행, `canister_qr.py` 284·309–317행.
