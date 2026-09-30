# AMR 흡착 그리퍼 + D455

`short_gripper.usd` 는 #506 에서 그대로 옮긴 것이다.
옮긴 날은 2026-09-23 이다. 재범 전결이다.

| 항목 | 값 |
| --- | --- |
| 원본 | master01 `/home/rokey/hospital_custome/Collected_gripper/gripper.usd` (세준 작성, #506) |
| sha256 | `10b0508bb244c0ea4a189c0de92e4facd433ff2110ffb06249dd181d189a560a` (2026-09-30 D455 재질 수정 뒤). 옮길 때(#506) 값은 `4ad69ced306231d3a1ca75923bbbdd3b6daf90b0574c05aedef5b703bd29dea2` 다 |
| 형식 | USD crate 한 레이어, 1 m 단위, Z-up, defaultPrim `/World`, 외부 참조 없음. 재질은 Isaac 내장 `OmniPBR.mdl`·`OmniGlass.mdl` 만 쓴다 |
| 쓰는 곳 | `--amr-hand-camera` 일 때 붙인다. 부모는 합본 `ur_arm_wrist_3_link` 다. 프림 이름은 `/World/short_gripper_01` 이다. 코드는 `p3sim/amr_base.py` 다 |

## D455 재질 수정 (2026-09-30)

D455 몸체가 Isaac 에서 빨갛게 보였다.
원인은 재질 셋(`Aluminum_Anodized`·`Aluminum_Cast`·`Plastic_ABS`)의 MDL 경로다.
경로가 `./omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/…` 였다.
인터넷 주소의 `https:/` 가 빠진 상대 경로라 MDL 을 찾지 못했다.
세 재질을 `OmniPBR.mdl` 로 바꿨다.
색은 D455 겉모습에 맞췄다: 짙은 회색 몸체(0.12), 밝은 회색 주물(0.55), 검정 플라스틱(0.02).
인터넷 없이도 같은 화면이 나온다.
`sim/tests/test_canister_qr.py` 의 `test_gripper_materials_use_only_builtin_mdl` 이 다시 깨지는 것을 막는다.
Isaac 화면 확인(L3)은 미실행이다.

## 오프라인으로 잰 값 (usd-core, Isaac 없이)

기준 프레임은 손목이다. 자산에서는 그 자리가 `attach_frame` 이다. `AssemblerFixedJoint` 가 `ur_arm_wrist_3_link` 와 `attach_frame` 을 로컬 항등으로 묶는다. 그래서 두 프레임이 같다. 합본에서 `wrist_3` 와 `tool0` 도 항등이다(`amr_base.py` 탐침).

| 무엇 | 손목 기준 값 | 코드 |
| --- | --- | --- |
| 흡착점(`suction_cup`, SurfaceGripper 부착점) | (0, 0, **0.1555**) m, 회전 없음 | `amr_base.GRIPPER_TCP_OFFSET` |
| 흡착컵 면(`gripper_tip` 메시 끝) | z = 0.158 m | 참고 |
| 컬러 카메라(자산 프림 `RSD455/Camera_OmniVision_OV9782_Color`) | (−0.0115, 0.07, 0.0355) m, 시선 = 공구 +Z. 계약 2.1 토픽·frame 이름(`/amr_1/hand_camera/image_raw`·`camera_info`, `amr_1/hand_camera_optical`)은 그대로다. 흡착 판정(계약 11.6)은 이 카메라나 자산 `SurfaceGripper` 가 아니라 기존 가상 흡착·`GripperState` 다 | `amr_base.GRIPPER_COLOR_CAMERA` |
| 컬러 카메라 내부값 | 초점 1.93 mm, 수평 조리개 3.896 mm → 수평 화각 90.5° | 자산 그대로 |
| 전체 외형 | 0.164 × 0.124 × 0.134 m | 참고 |

## 붙일 때 끄는 것

v1.1.0 에서도 **겉모양·카메라·TCP 만** 쓴다. 진짜 흡착(SurfaceGripper)은 쓰지 않는다(`amr_base.GRIPPER_PRIMS_OFF`).

- `short_gripper_01` 의 강체(`physics:rigidBodyEnabled=false`): 팔 링크 아래 강체가 중첩되지 않게 한다.
- `AssemblerFixedJoint`·`Suction_Joint`(`physics:jointEnabled=false`): body0 이 이 장면에 없는 경로를 가리킨다.
- `SurfaceGripper` 프림(비활성): 흡착은 기존 가상 흡착(거리 판정)이 한다. 그 거리는 흡착점(위 0.1555 m)에서 잰다.
- 충돌(`physics:collisionEnabled=false`): 그리퍼 끝이 봉투를 밀지 않게 한다.

병원 한 바퀴는 `tools/demo_v2.sh` 가 늘 `--amr-hand-camera` 를 준다. v1.0.0 회전 7(`9760d9d`)의 `demo_v2.sh` 도 이 인자를 준다. 그래서 `demo_v2.sh` 로 돈 병원 회차는 이 그리퍼를 붙인 구성이다.
