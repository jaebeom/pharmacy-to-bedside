# QR 배치와 카메라 구성 (시뮬)

- 상태: 현황 기록. [QR·DB·카메라 계약 v1](qr-db-camera-contract-v1.md)을 바꾸지 않는다. 그 계약의 시뮬 쪽 구현이 어디에 무엇을 두는지 적는다.
- 기준: main `f316197`(v1.1.0). 1–5절의 값과 기본값을 이 커밋의 코드와 대조했다.
  - 대조한 파일: `sim/standalone/p3sim/canister_qr.py`·`amr_base.py`·`pouch.py`·`patient_plates.py`, `sim/standalone/make_qr_textures.py`, `pharmacy_stage.py`(인자·preset), `rokey_p3_perception`(검출기·`qr_overlay`), `arm_node.py`, `m0609_arm_node.py`, `stub_loop.launch.py`, `tools/demo_v2.sh`, UR5 팔 params 파일.
- 이력: 2026-09-23 처음 썼다(기준 `feat/hospital-full` `87394bb`, 팔 params 두 판은 `feat/hospital-full-2` `ae8b0b9`). 3절의 "관측" 줄은 그때 회차 기록이다.
- 값의 원본은 코드다. 이 문서와 코드가 다르면 코드가 맞고, 이 문서를 고친다.
- 판독 픽셀은 **계산값**이다. Isaac L3 에서 잰 값이 아니다. 관측값은 따로 표시한다.
- v1.1.0 의 병원 기본은 카메라 집기다. 봉투와 병상·스테이션 인식표를 AMR 손 카메라 QR 로 읽는다(#784, #797). 참값 센서 구성은 `P3_CAMERA_POUCHES=0` 을 줄 때만이다.

## 1. QR 배치

QR 에는 ID 만 담는다(계약 1절). 텍스처는 `sim/standalone/make_qr_textures.py` 가 만든다. 여백은 4 모듈이다. 오류 정정은 M 이다(65행). `ord-`·`cn-`·`md-` ID 는 모두 버전 1 이다. 21 모듈이다.
병원 기동은 주문 풀과 카탈로그로 봉투·환자·스테이션·약통 QR 을 한 번에 만든다(`demo_v2.sh` 317–321행, `make_qr_textures.py` 1행).

| 대상 | 붙는 곳 | 크기 | 두께(표면에서 띄운 거리) | 원본 |
| --- | --- | --- | --- | --- |
| 봉투 `ord-` | 윗면(+z). 봉투 자세를 매 스텝 따른다 | 정사각, 한 변 = 0.8 × 봉투 짧은 변(기본 봉투 0.10×0.07×0.01 m → 0.056 m) | 0.5 mm | `p3sim/pouch.py` `qr_face_size`(97·100–106행), `scene.add_top_texture` |
| 약통(원통) `cn-` | 몸통 옆면의 통로 쪽(-y). 옆면을 감싼 곡면 스티커 | 펼친 한 변 0.04 m(`CYLINDER_STICKER_SIDE`). 지름 70 mm 에서 감싼 각 약 65° | 0.5 mm(`FACE_LIFT`) | `p3sim/canister_qr.py` `sticker_mesh` |
| 모듈(사각) `cn-` | 앞면(통로 쪽 -y)의 평면 스티커 | 정사각, 한 변 = 0.72 × 앞면 폭(병원 모듈 0.06 m → 0.0432 m) | 0.5 mm | 같은 파일 |
| 약통 윗면 | 위가 열린 칸(`access: top`, 빈월드 윗단)에만 더 붙인다. 병원 워크셀 18칸은 모두 `front` 라 윗면 QR 이 없다 | 0.72 × 앞면 폭 | 0.5 mm | `cell_faces`, `top_mesh` |
| 병상 인식표 판 `pt-`, 스테이션 판 `st-` | 협탁 윗면에 눕힌 흰 판 위. 병실 판은 로봇에 가까운 가장자리에 두고 `<bed>/tag` TF 와 같은 좌표로 맞춘다(`7c59bc82`, #796). 스테이션 판은 먼 가장자리다 | 판 한 변 0.10 m, QR 한 변 0.08 m | 판 4 mm + QR 0.5 mm | `p3sim/patient_plates.py` 9–15·18–27·29–46행. 병원에서 늘 켠다(`--patient-plates`, `demo_v2.sh` 350행) |

- 병원 워크셀 18칸의 QR 은 약통 종류와 무관하게 칸의 `cn-` ID 다(카탈로그 `cn-0201..0218`, 위치 `shelf:<칸>`). 칸마다 원통·모듈은 시드로 섞인다(`workcell_layout.shuffled_stock`, 167행). 스티커 모양은 스테이지가 그 칸에 세운 종류를 따른다.
- v1.1.0 병원 preset 은 18칸을 모두 채운다. 쓴 약통은 선반으로 돌아오지 않고 빈 칸이 된다. 리셋하면 다시 찬다(preset `workcell_empty_cells: 0`·`workcell_consume: True`, `pharmacy_stage.py` 205·560–563행, #791).
- `md-` 는 카탈로그의 모듈 표(`md-0001` 등)에만 있다. 스테이지에 붙는 `md-` QR 은 없다.
- 스티커는 따로 된 판이 아니다. 물리가 없는 Mesh 이고 충돌체가 없다. 인식표 판도 물리·충돌이 없다(`patient_plates.py` 3행).
- **스티커 높이**: 잡기 직전(`grasp_pose`) M0609 손 카메라 축의 높이에 둔다(`sticker_center_z`).
  - 앞 접근에서 공구 +z 는 월드 +y, link_6 +y 는 월드 -z 다(`scene_v2.FRONT`). 그래서 카메라 축은 잡는 점보다 0.0483 m **아래**다. 이 부호는 `sim/tests/test_canister_qr.py` 가 고정한다.
  - 잡는 점: 원통은 윗면 − 0.02 m, 모듈은 중심 + 0.03 m 다(`canister_qr.py` 32·34행, `scene_v2.DEFAULT_PARAMS`). 병원 원통(높이 0.12 m)의 스티커 중심은 약통 중심 −0.0083 m 다.
  - 모듈의 축은 잡는 점(중심 + 0.03 m)보다 0.0483 m 아래라 중심 −0.0183 m 다. 스티커가 몸통을 벗어나면 가장자리 여유 3 mm 안으로 당긴다(`canister_qr.py` 58–70행).
  - 9/23 기록(모듈 높이 0.14 m, 잡는 점 = 중심)에서는 축이 중심 −0.0483 m 라 당겨서 −0.0454 m 에 두었다. 잡는 높이를 올린 것은 `f8eac1c`(#608)다. v1.1.0 병원 모듈의 실제 높이는 이 문서에서 다시 재지 않았다(미확인).
- 약통은 물리로 움직인다. 스티커는 스테이지가 따로 옮긴다. 잡힌 것과 되돌아가기를 기다리는 것은 매 스텝, 선 약통은 0.5 s(`CANISTER_FACE_SYNC_S`, `pharmacy_stage.py` 63행)마다 실제 약통 자세를 따른다.

## 2. 카메라 구성

두 로봇 모두 RealSense D455 의 **컬러 카메라 하나만** 쓴다. 깊이·IR 은 쓰지 않는다. Isaac 의 카메라 목록에는 컬러 둘(합본 AMR, M0609)과 스테이지 뷰 카메라만 남기는 것이 목표다. 목록 확인은 L3 미실행이다.

| 항목 | 합본 AMR (`--amr-hand-camera`) | M0609 (`--m0609-hand-camera`) |
| --- | --- | --- |
| 몸체 | 흡착 그리퍼+D455 자산 `sim/assets/amr_gripper/short_gripper.usd` 를 손목 `wrist_3` 에 reference. 강체·조인트·흡착 프림·충돌은 끈다 | 우리 USD Camera 아래에 같은 자산의 D455 서브트리를 reference(보이는 몸체만). 물리 없음 |
| 찍는 카메라 | 자산 안 `Camera_OmniVision_OV9782_Color` | 따로 둔 USD Camera(D455 컬러 내부값). `link_6` 월드 자세 × 장착값으로 매 스텝 옮긴다 |
| 끄는 프림 | 자산 안 `Camera_OmniVision_OV9782_Left`·`_Right`·`Camera_Pseudo_Depth`·`TemplateRenderProducts` (`amr_base.GRIPPER_PRIMS_OFF`) | 모델 안 카메라 넷(컬러 포함)과 `TemplateRenderProducts` (`canister_qr.attach_d455_model`) |
| 장착값 | 손목 기준 컬러 카메라 (−0.0115, 0.07, 0.0355) m, 시선 = 공구 +Z. 흡착점 손목 +Z 0.1555 m(자산에서 오프라인 측정) | `link_6` 기준 t=(0, 0.0483, 0.0185) m, q(wxyz)=(0, 0, 1, 0), 시선 = link_6 +Z. **M0617 조립에서 추출, M0609 에서는 미확인** |
| 내부값 | 초점 1.93 mm, 수평 조리개 3.896 mm(수평 화각 90.5°) | 같다 |
| 해상도 | `P3_CAMERA_RESOLUTION`, 기본 1280×800(`demo_v2.sh` 193행). 스테이지 인자 자체의 기본은 640×480 이다(`pharmacy_stage.py` 593행) | `--m0609-camera-resolution`, 기본 960×600(`pharmacy_stage.py` 527행) |
| 주기 | ≤ 10 Hz(`--camera-max-hz` 10). 병원 렌더 30 Hz 에서 2틱 건너뛴다. 미측정 | 같다 |
| 근접 클립 | 자산 값 | 0.03 m(몸체가 제 영상을 가리지 않게) |
| 토픽 | `/amr_1/hand_camera/image_raw`, `camera_info` | `/m0609/hand_camera/image_raw`, `camera_info` |
| 프레임·TF | `amr_1/hand_camera_optical`, TF 를 낸다 | `m0609/hand_camera_optical`. **TF 는 내지 않는다**(M0609 링크 TF 가 없다, 계약 3절. `canister_qr.py` 325행 `tf=none`) |
| 판독 노드 | `pouch_detector`(병원 기본 `use_pouch_detector:=true`, color + QR) | `pouch_detector` 인스턴스 `m0609_detector`(`use_m0609_detector:=true`, QR 만) → `/m0609/hand_camera/tag_reads` |
| QR 추적 영상 | `/amr_1/hand_camera/qr_view`(#787) | `/m0609/hand_camera/qr_view` |
| 켜는 조건 | 병원은 늘 켠다(`demo_v2.sh` 346행). 빈월드는 `P3_CAMERA_POUCHES=1` 이고 합본일 때 | `P3_CONTAINER_QR=1`(병원 기본 1, 그 밖 0. `demo_v2.sh` 191·368행) |

- 근거: `amr_base.py` 681–702·728–827행, `canister_qr.py` 38–44·150–183·255–334행.
- **QR 추적 영상**: 검출기가 찾은 QR 마다 네 꼭짓점 사각형을 그린다. 초록은 읽음(지금 집는 주문이면 `OK`), 빨강은 다른 주문 봉투(`NOT ORDER`), 노랑은 자리만 찾고 못 읽음(`QR ?`)이다(`qr_overlay.py` 1–29행).
  - 폭 640 px 로 줄여 bgr8 로 낸다. 보는 구독자가 있을 때만 그린다(`pouch_detector_node.py` 239–247행).
  - 보는 곳은 촬영 창(`P3_CAMERA_VIEW=1`, `/amr_1/hand_camera/qr_view` 만, `demo_v2.sh` 773–783행)과 웹 카메라 탭(`--live-sensors`)이다. demo_v2 는 웹에 `--live-sensors` 를 주지 않는다.
- **추론 상한**: 병원 기본은 검출기 추론 상한이 없다. 들어온 프레임을 모두 처리한다(`detector_max_rate_hz` 기본 0, `stub_loop.launch.py` 245–247행). 5 Hz 상한은 참값 분기(`P3_CAMERA_POUCHES=0 P3_SIM_SENSORS=1`)에서 `P3_DECK_VISION=1` 일 때만 준다(`demo_v2.sh` 453–457행).

**한 장 촬영**: 계약 3절(정지 확인 뒤 한 장, `CaptureFrame`)은 **미구현**이다. 지금 두 카메라는 연속 발행이고, 상한은 `--camera-max-hz`(기본 10 Hz)다. 카메라 하나를 켜면 빈월드 rtf 가 약 0.2 떨어졌다([실습41](../practice/emptyworld/practice-41.md), 관측).

## 3. 판독 절차와 픽셀 계산

`pouch_detector` 는 `cv2.QRCodeDetector.detectAndDecodeMulti` 로 읽는다(`pouch_detector_node.py` 279–317행).

- 하나도 못 읽었으면 영상을 2 배로 키워 한 번 더 읽는다(`qr_rectify.read_enlarged`, 291–297행).
- 자리(네 점)만 찾고 내용이 비면 `qr_rectify.reread` 로 한 번 더 읽는다(304–309행). 네 점을 모듈당 8 px 의 정사각형으로 편다. 여백 4 모듈을 두른다. Otsu 로 이진화한다. 그 다음 `detectAndDecode` 로 읽는다.
- 그래도 비면 편 영상을 좌우로 뒤집어 한 번 더 읽는다(거울상을 못 푸는 OpenCV 버전이 있다, #553 colcon).

- 오프라인 확인(OpenCV 5.0): 코드 한 변 70–120 px, 기울기 0–40° 에서 다시 읽기가 읽었다. 60 px 을 기울이면 못 읽었다. 여러 개 읽기만으로는 100 px 아래에서 대부분 못 읽었다. master 의 OpenCV 버전에서는 미확인이다.
- 그래도 못 읽으면 `QR 을 못 읽었다(펴서 다시 읽기 포함). 한 변 N px` 경고를 2 s 에 한 번 남긴다.
- QR 을 읽은 검출은 QR 중심을 봉투 자리로 쓴다. 못 읽으면 색 사각형 중심이다(`pouch_detector_node.py` 418행).

픽셀 계산식: 코드 한 변(여백 뺀 것) px = 스티커 한 변 × 21/29 × fx / 거리, fx = 폭 px × 1.93 / 3.896. 광축이 스티커에 수직일 때 값이다(`amr_base.qr_code_pixels`, 705–712행).

| 장면 | 거리 | 해상도 | 코드 한 변(계산) |
| --- | --- | --- | --- |
| AMR 적재 관측(`belt_view_standoff_m` 0.30). 카메라 기본에서는 A1 탁자 위 봉투다 | 봉투 윗면 위 0.30 m | 1280 | 약 86 px |
| AMR 재관측(`refine_view_standoff_m` 0.20). 상판 집기에서 쓴다. 탁자 집기(손목 고정)는 건너뛴다 | 봉투 윗면 위 0.20 m | 1280 | 약 129 px |
| AMR 인식표 판독(`tag_standoff_m` 0.25), 판 QR 0.08 m. 버전 1 가정 | 인식표 위 0.25 m | 1280 | 약 147 px |
| M0609 잡기 직전, 원통 | 0.19671 − 0.0185 − 0.035 = 0.143 m | 960 | 약 96 px |
| M0609 잡기 직전, 모듈 | 0.19671 − 0.0185 − (0.05 − 0.04) = 0.168 m | 960 | 약 88 px |

- 관측 거리 근거: `demo_v2.sh` 185·450–452행(`belt_view_standoff_m`), `ur5_arm.amr-combined.camera-receiver.yaml`(`refine_view_standoff_m` 0.2, `tag_standoff_m` 0.25), `arm_node.py` 1395–1396·1424·2035행.
- 카메라 기본에서 `pharmacy/belt_end` 는 A1 탁자 위 정착점이다(`zones.hospital-receiver.yaml`, `hospital_nav_files.py` 20·46행). 관측점 오프셋은 0 이다(`demo_v2.sh` 135행).
- M0609 의 거리 = link_6→TCP 0.19671 − 카메라 앞섬 0.0185 − (잡는 점 → 스티커 면). 원통의 잡는 점은 중심 축 위라 반지름, 모듈은 중심에서 0.04 m 앞이라 0.05 − 0.04 다.
- 원통 곡면 스티커는 정면에서 본 폭이 펼친 길이보다 좁다(약 0.95 배). 위 표는 세로 한 변이다.
- 관측(289a384, 병원, 1280×800, master01): `QR 을 못 읽었다. 한 변 83 px`. 이 줄이 첫 관측에서 났는지 재관측에서 났는지는 로그만으로 모른다. 이 회차는 다시 읽기(`429ac27`) 전이다.
- 관측(35fb28a master02, ae8b0b9 master01, 병원 M0609 960×600): 원통 `cn-0208`(shelf_70/r0c1)은 `펴서 읽었다: cn-0208. 한 변 81 px` 로 읽혀 장착 허용됐다. 같은 칸에서 `못 읽었다(펴서 다시 읽기 포함). 한 변 81–83 px` 줄도 섞여 나왔다. 계산 96 px 보다 작다(거리로 되짚으면 약 0.167 m, 계산 0.143 m).
- 관측(같은 두 회차): 모듈 칸 보충은 `container_refused … reason=unreadable` 로 3/3 거부됐다. 35fb28a 에서는 거부 앞에 m0609_detector 의 `QR 을…` 줄이 없다(QR 후보를 못 찾았다). 뒤에 모듈 잡는 높이를 중심 + 0.03 m 로 올려(`f8eac1c`, #608) 판독·허용됐다([QR·DB·카메라 계약](qr-db-camera-contract-v1.md) 6.1).

## 4. 판독이 쓰이는 곳

| 판독 | 쓰는 쪽 | 조건 |
| --- | --- | --- |
| 봉투 `ord-` | AMR 팔(`PickPouch`). 판독 ID 가 goal 주문과 같을 때만 집는다(`pick_permission.select_detection`) | 팔의 `pouch_source` 가 `camera` 일 때. 병원 기본이다 |
| 병상 `pt-`·스테이션 `st-` | AMR 팔(`ScanTag`) → orchestrator 인증(`AUTH_OK`·`AUTH_FAIL`) | `scan_tag_source` 가 `camera` 일 때. 병원 기본이다(`demo_v2.sh` 444행) |
| 약통 `cn-` | M0609 팔 `container_check` → orchestrator `CheckContainer` | 계약 2.3. `grasp_pose` 도착 뒤 stamp 의 판독만 쓴다 |
| 모든 판독 | 웹 `snapshot.qr_reads`(#786). ID 를 주문 풀·카탈로그·재고 파일로 풀어 보인다 | 표시만 한다. 판정에 쓰지 않는다([웹 API](../../web/api.md) 1.12) |

병원 AMR 팔 params(`tools/demo_v2.sh` 164–171행, v1.1.0):

| `P3_CAMERA_POUCHES` | 기본 params | `pouch_source` |
| --- | --- | --- |
| 1 (병원 기본, v1.1.0) | `ur5_arm.amr-combined.camera-receiver.yaml` | `camera`(launch 인자 `pouch_source:=camera`). 9/29 master02 성공 회차 설정이다. 탁자 집기에서 손목 J6 를 고정하고 0.05 m 더 내린다(`belt_pick_lock_wrist`, `belt_pick_contact_drop_m`). 0.05 m 는 실측 보정이고 근본 수정이 아니다(params 1행) |
| 0 | `ur5_arm.amr-combined.gripper.yaml` | `sim`(참값 센서). 흡착점 0.1555 m 는 camera 판과 같다. `P3_SIM_SENSORS=1` 이면 launch 인자 `pouch_source:=sim` 이 같은 값을 준다 |

- 카메라 판 params 에 `tool_frame`·`tcp_offset_m`·`refine_view_standoff_m` 이 없으면 기동 전에 막는다. 인식표 카메라면 `tag_standoff_m` 도 본다(`demo_v2.sh` 633–643행).
- `ur5_arm.amr-combined.camera.yaml`(손목 고정·추가 하강 없음)은 저장소에 있다. 병원 기본은 아니다.
- camera-receiver 파일 안의 `scan_tag_source: sim` 은 launch 인자 `scan_tag_source:=camera` 가 이긴다(`stub_loop.launch.py` 355–360행).
- `P3_UR5_ARM_PARAMS` 를 직접 주면 그 파일이 이긴다. launch 인자가 있으면 파일의 `pouch_source` 보다 launch 인자가 이긴다.
- 9/23(`ae8b0b9`) 에는 병원 기본이 `P3_CAMERA_POUCHES=0` 이었다. 재범 9/29 결정으로 1 이 됐다(#784).

## 5. 비전 파이프라인 — 영상에서 동작까지 (재범 9/25, 점수판 AI 비전)

이 절의 봉투 열은 9/25 의 **비전 교차 확인**이다. 참값으로 집으면서 카메라 검출을 대조한다(`P3_CAMERA_POUCHES=0 P3_SIM_SENSORS=1 P3_DECK_VISION=1`).
v1.1.0 병원 기본은 이 경로가 아니다. 카메라 검출로만 집고, 틀리거나 없으면 참값으로 돌아가지 않고 실패로 닫는다(4절, 계약 6.2).

교차 확인 구성에서는 두 곳에서 카메라가 **동작을 바꾼다**. 한 바퀴의 성공(참값 집기·참값 인증)은 깨지 않는다 — 비전이 틀리거나 늦으면
참값으로 돌아가고 그 사실을 로그에 남긴다. 약통 열은 병원 기본에서도 그대로다.

| 단계 | 봉투(AMR 손 카메라, 상판 집기, 교차 확인) | 약통(M0609 손 카메라, 보충 잡기 직전) |
| --- | --- | --- |
| 영상 | `/amr_1/hand_camera/image_raw` 1280×800, D455 컬러 | `/m0609/hand_camera/image_raw` 960×600, D455 컬러 |
| 검출 | `pouch_detector`: 색(HSV, 밝고 채도 낮은 덩어리) + QR(`detectAndDecodeMulti`, 못 읽으면 2 배 키워 읽기·펴서 다시 읽기, 3절). QR 을 읽은 검출은 **QR 중심**이 봉투 자리(색 덩어리 중심은 옆 흰 롤러와 합쳐져 9 cm 틀렸다, 회차20). 추론 5 Hz 상한(`max_rate_hz`, 이 구성에서만) | `m0609_detector`: QR 만(같은 판독 경로). 상한은 `detector_max_rate_hz` 를 따른다. 병원 기본은 상한 없음 |
| 판정 | 팔(`arm`, `vision_check`): 접근 자세(봉투 위 0.10 m)에서 1 s 안에 이 주문 QR 을 읽은 검출을 봉투 윗면에 투영, 참값과 0.05 m 안이면 **검출 좌표로 집는다**. 없거나 어긋나면 참값 + `vision_mismatch` | 팔(`m0609_arm`, `container_check`) → orchestrator `CheckContainer`(DB: 만료·회수·epoch). 거부면 **잡지 않는다** |
| 동작 | 파지 자세의 (x, y) 가 검출에서 온다(높이·방향은 참값) | 장착 허용/거부, 거부 칸은 그 epoch 에서 다시 안 고른다 |
| 로그(시도마다 한 줄) | `vision pouch ord-…: ok\|vision_mismatch 지연 N ms, 참값과 차 D m, 판독 R/F 프레임, 자리 검출\|참값` | `vision container cn-…: ok\|<거부 이유> 지연 N ms, 판독 R건(도착 뒤), cell=…`(`m0609_arm_node.py` 735–737행) |
| 켜는 법 | `P3_CAMERA_POUCHES=0 P3_SIM_SENSORS=1 P3_DECK_VISION=1`(기본 0). demo_v2 의 참값 분기에만 있다. 카메라 집기 구성에서는 `P3_DECK_VISION` 을 쓰지 않는다(`demo_v2.sh` 453–459행) | `P3_CONTAINER_QR=1`(병원 기본 1) |

계약: 새 메시지·이벤트는 없다. `vision_mismatch` 는 로그 문자열이다(이벤트 이름을 늘리지 않는다). 새 파라미터는
팔 `vision_check`·`vision_check_timeout_s`·`vision_check_tolerance_m`, 검출기 `max_rate_hz`, launch `vision_check`·
`detector_max_rate_hz` 다.

### 수치

| 항목 | 값 | 출처 |
| --- | --- | --- |
| 약통 QR 판독 한 변 | 59–82 px(성공) | 회차17 `4d01333`(#240 게시 없음, [회차별 QR 판독](../presentation/qr-reading-rounds.md)) |
| 봉투 QR 판독 한 변 | 45–135 px(성공), 41 px 실패 1 | 회차17·20 |
| 약통 확인 결과 | 모듈 cn-0204 허용 → REFILL_DONE 71.58 | #240 5795627672(`f8eac1c`) |
| 카메라 집기 한 건(탁자 정착) | 흡착거리 0.0052 m, 병상 판 카메라 판독 → `AUTH_OK`, bed_a1 1건 DELIVERED | [실습45](../practice/simworld/practice-45.md)(`05b8e28`, 탐색 실습, acceptance 아님). v1.1.0 `f316197` 에서는 미실행 |
| 판독 지연·판독률(봉투 `vision pouch`, 약통 `vision container`) | **미실행** — 이 줄을 찍는 첫 회차에서 채운다 | 두 마스터 L3 |
| 추론 처리 비용 | 2 배 키워 읽기 약 30 ms/프레임(오프라인 960×600) | 오프라인 |
| 교차 확인의 참값 대비 오차 | **미실행** | 두 마스터 L3 |
