# rokey_p3_perception

v1.1.0 병원 한 바퀴에서 `pouch_detector` 실행 파일이 두 이름으로 뜬다(`stub_loop.launch.py`).
`pouch_detector`(amr_1, `detector=color` + QR)는 UR5 손 카메라로 봉투 QR·병상 인식표 QR 을 읽는다. 팔은 봉투 QR 이 주문과 맞아야 집는다(#784).
`m0609_detector`(m0609, `detector=none`)는 M0609 손 카메라로 약통 QR(`cn-`)만 읽는다. 보충 전 약통 확인에 쓴다(QR·DB·카메라 계약 2.3).

봉투 검출과 QR 판독. 사람 인식 노드는 v1.1.0 에 없다. **manipulation 담당이 소유**한다.
검출에서 파지 포즈까지 한 사람이 끝까지 가져가기 위해서다 — [Git 가이드 담당 표](../../docs/process/git-start-guide.md#담당-다섯-자리--내-폴더만-고친다).

- 노드: `ros2 run rokey_p3_perception pouch_detector`
  - 받는 것: `/<robot>/hand_camera/image_raw`, `/<robot>/hand_camera/camera_info`, `/events`
  - 내는 것: `/<robot>/hand_camera/tag_reads` (`TagRead`), `/<robot>/hand_camera/pouches`
    (`PouchDetectionArray`, 검출 0건이어도 빈 배열), `/events` 의 `POUCH_DETECTED`,
    `/<robot>/hand_camera/qr_view`(`Image`, QR 추적 영상. 구독자가 있을 때만 그린다. 판정에는 안 쓴다, #787)
  - 파라미터(기본값): `robot_id`(`amr_1`), `detector`(`color`. `yolo` 또는 `color` 폴백. `none` 이면 봉투 상자를 내지 않고 QR 만 읽는다),
    `yolo_weights`(빈 값), `yolo_confidence`(`0.25`), `yolo_allowed_classes`(`['']`), `yolo_fallback_to_color`(`true`),
    `qr_min_size_px`(`0`), `pouch_width_m`(`0.0`), `pouch_distance_m`(`0.0`), `color_saturation_max`(`60`), `color_value_min`(`120`),
    `min_area_px`(`400`), `pouch_from_qr`(`true`), `save_reads_dir`(빈 값. 약통·모듈 QR 을 읽은 순간 한 장),
    `max_rate_hz`(`0.0` = 상한 없음), `deck_watch_s`(`10.0`. 상판 집기 뒤 프레임 기록 시간, sim s)
  - launch 가 주는 값: `pouch_detector` 는 `robot_id=amr_1`·`detector=color`, `m0609_detector` 는 `robot_id=m0609`·`detector=none`·`pouch_from_qr=false`
    ([bringup README](../rokey_p3_bringup/README.md))
- 순수 로직: `qr_payload.py` — QR 내용 → (종류, ID). 접두는 `pt-` 환자, `st-` 스테이션, `ord-` 봉투, `cn-` 약통, `md-` 모듈(사각 알약통). 약통·모듈은 `cn-0000`·`md-0000` 형식만 받는다.
  봉투는 QR 내용 전체가 주문 ID 이고 환자·스테이션은 접두 뒤가 ID 다 (계약 7절).
- 순수 로직: `pouch_geometry.py` — 픽셀·깊이 → optical 프레임 위치와 z 축 회전. REP 103.
- 순수 로직: `plane_projection.py`(#271) — 픽셀 광선과 지지 평면(벨트 상판·상판 칸 바닥·보관함 바닥)의 교차.
  입력(내부 파라미터·평면 자세 quaternion xyzw·허용 영역·최소 입사각)은 전부 호출자가 넘기고 기본값이 없다. 거부 이유를 코드로 돌려준다.
  **노드에 아직 연결하지 않았다.** 지금 검출기의 깊이는 여전히 `pouch_width_m`·`pouch_distance_m` 이다.
- 순수 로직: `qr_rectify.py` — 자리는 찾았는데 못 읽은 작은 QR(한 변 100 px 아래)을 네 점으로 펴서 다시 읽는다.
- 순수 로직: `qr_overlay.py` — QR 추적 영상의 사각형·색(초록 읽음, `OK` 는 지금 집는 주문, 빨강 `NOT ORDER`, 노랑 못 읽음). 판정(`mark_for`)은 cv2 없이 시험한다.
- 순수 로직: `read_snapshot.py` — QR 을 읽은 순간 영상 한 장(`save_reads_dir`, epoch 마다 ID 당 한 장)과 상판 집기 뒤 프레임 기록(`DeckWatch`). 기록용이다.
- 내는 메시지: `rokey_p3_interfaces/msg/PouchDetectionArray`, `TagRead`, `sensor_msgs/Image`(`qr_view`)

## 마스터에서 확인할 것

> 9/17 에 적은 목록이다. v1.1.0 병원 카메라 값은 `tools/demo_v2.sh` 가 준다: 벨트 관측 거리 0.30 m, 검출 고정 거리 0.290 m(`detector_pouch_distance_m`), 손 카메라 해상도 1280×800(`P3_CAMERA_RESOLUTION`).
> 9/23 L3 에서 640 폭은 QR 한 변 58 px 로 판독에 실패했다(`demo_v2.sh` 주석).

- 봉투까지의 거리: `pouch_width_m`(봉투 실제 폭) 또는 `pouch_distance_m`(고정 거리) 중 하나는
  있어야 `pose` 가 나온다. 둘 다 0 이면 `pose` 를 0 으로 내고 팔이 그 검출을 쓰지 않는다.
- 손 카메라 해상도와 QR 판독 거리, `qr_min_size_px` 의 실제 값.
- `color` 폴백의 HSV 시작값은 "밝고 채도 낮은 면"이다. 봉투 자산 색에 맞춘다.

`ultralytics` 는 `detector: yolo` 일 때만 import 한다. 없으면 경고를 내고 `color` 로 돈다.
`yolo_allowed_classes` 는 봉투로 받을 class **이름** 목록이다. ID 는 모델 `names` 에서 찾는다.
목록이 비었거나 모델에 없는 이름이 하나라도 있으면 그 모델을 쓰지 않는다(fail-closed, 오류 로그 후 `color` 폴백).
허용 class 밖의 상자는 버린다. 순수 로직은 `yolo_classes.py` 에 있다.
기동 시 실제로 쓴 검출기를 한 줄로 남긴다: `effective_detector=color (requested=yolo, reason=…, pouch_from_qr=…)`.
`yolo_fallback_to_color: false` 면 YOLO 를 못 쓸 때 color 로 넘어가지 않고 봉투 상자를 내지 않는다(오류 로그 1회).
YOLO 단독 성능을 재는 run 은 이 값과 `pouch_from_qr` 를 false 로 띄운다. 그래야 color·QR 폴백 검출이 섞이지 않는다.
학습 데이터(Replicator 합성) 생성 스크립트는 `sim/` 에 두고 simulation 담당이 맡는다.
