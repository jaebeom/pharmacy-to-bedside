# L3 런카드 — UR5 팔·인식

> **상태: 지난 기록 (2026-09-20 기준).** 지금은 [병원 한 바퀴 런카드](hospital-full.md)를 따른다.

런카드는 Isaac 에서 한 장씩 돌리는 확인 절차다. 아래는 VA-1 부터 VA-7 이다.

- 대상: 마스터에서 Isaac 으로 UR5(벨트 끝 받침대 셀)와 손 카메라 인식을 확인하는 카드 7장과, UR5 selfdemo 픽 결과 분류표.
- 기준 코드는 `main` `e271081`. **Isaac 을 돌리지 않았다.**
- 상태: 카드마다 **미실행 / 관측됨** 을 적는다. 합격선이 정해지지 않은 항목은 "기록만(pilot)"이다. 결과를 보고 기준을 완화하지 않는다.
- 공통 규칙은 [배포 runbook](deployment.md)과 [0921 시연 runbook](demo-0921-v2.md)을 따른다. 슬롯 예약과 관측 게시는 이슈 #240 이다.

## 0. 공통

| 규칙 | 내용 |
| --- | --- |
| 기록 | 모든 카드에 SHA, 스테이지 인자 전체(`--camera-*`·`--suck-distance`·`--ur5-*`), headless/창 모드, 물리 dt 를 남긴다. 원본 로그는 저장소 밖, 기록은 `evidence/runs/` 다. 실패 run 도 분모에 넣는다 |
| 시연 스택의 M0609 경로 | [`tools/demo_v2.sh`](../../tools/demo_v2.sh) 는 `v2_guarded_module_path` 를 **명시로 끈다**(#230). 노드 기본값(v2 에서 true)과 다르다. `P3_V2_GUARDED_MODULE_PATH` 기본 false 가 `-p v2_guarded_module_path:=false` 로 넘어간다 |
| guarded 경로를 볼 때 | `P3_V2_GUARDED_MODULE_PATH=true` 를 주고 그 값을 run 에 남긴다 |
| 실물 `arm` 노드 | 카드 VA-4·5·6·7 은 스텁 팔 대신 실물 `arm` 노드를 띄운다. launch 에 `use_stub_arm:=false pick_notice:=false` 를 준다(스텁 팔·스텁 회수와 섞지 않는다). 시연 스택은 UR5 가 스텁이라 `arm` 파라미터가 의미가 없다 |
| 녹화·캡처 | 창 모드면 녹화와 단계 캡처를 켠다(재범 지시 9/20). headless 면 이유와 대체 증거(로그 구간·수치)를 적는다. "없음"만 적고 닫지 않는다 |
| 증거 파일 | 파일마다 이름·크기·sha256 을 기재한다. 원본은 저장소 밖에 둔다 |
| 새 동작 | 아래 opt-in 은 전부 기본 꺼짐이다. 켜는 법·짝·기본값은 [manipulation README](../../src/rokey_p3_manipulation/README.md)·[perception README](../../src/rokey_p3_perception/README.md) 에 있다 |

## 1. 카드

### L3-VA-1 벨트 끝 UR5 픽(selfdemo) — 관측됨: 받침대 고정은 통과, 픽 0/5

- 상태: **관측됨**(9/20 03:25–03:50, master01 headless, tree `2c68b73` 2회 + `13a2dfd` 진단 1회).
  - `ur5 base_frame_mismatch` 가 재현됐다. 픽은 0/3 이다(L3-2 결과).
  - 1·2회차의 첫 세 줄과 첫 실패 줄이 같다. `placed` 3건은 `in_slot=False` 다.
  - 원인 칸: **UR5 prim 이 USD 합성 월드에서 원점**이다. 관절 `localPos0` 쓰기는 됐다(`set_ok`, readback 일치). `SingleArticulation(position=…)` 이 prim 변환에 쓰이지 않았다(진단 회차, #322).
  - 이 회차의 `ik_failed` 는 배치 결함이 아니다. Lula `base_pose` 도 `[0,0,0]` 이라 벨트 끝으로 가는 첫 점부터 도달 범위 밖이다.
  - 수정: SIM-9 2단계(#324, prim 변환을 물리 파싱 전에 USD 에 직접 쓰기)가 main 에 들어갔다.
- **받침대 고정은 통과했다**(9/20 09:05 master02 headless, tree `644ec0a`, 실습12).
  - `ur5 pin_failed`·`base_frame_mismatch` 0줄. prim·`base_link`·Lula `base_pose` 가 모두 받침대 `[3.25, 0.55, 0.45]`, `tool0_from_pedestal_m=0.839`.
  - 그래도 **픽은 0/5** 다. `placed` 5회 모두 `in_slot=False`, `suction on` 0.
- **왜 실패했는지**(실습12·12c, tree `eba5351` 재현. 개수·좌표·sim_time 까지 같다):
  - `ur5 ik_check` 29/29 `solved=True` 인데 **명령 관절값과 측정 관절값이 다르다**(`want ≠ have`). 어긋난 관절은 shoulder_lift 23건·shoulder_pan 6건이고 손목은 0건이다.
  - 1바퀴 벨트 쪽은 pan 이 0.103–0.114 rad 모자라고, 그 값에 반지름 0.627 m 를 곱하면 `error_m` 과 맞는다.
  - **UR5 링크가 환경에 닿는다**: `forearm`↔벨트 표면 54건(최대 impulse 40.52), `upper_arm`↔칸 벽 39건, `upper_arm`↔방 벽 15건, `upper_arm`↔받침대 3건. UR5 끼리의 접촉은 0건이다.
  - 관절 한계는 넉넉하다(±2π, elbow ±π). 드라이브는 stiffness 5.778e4(손목 2.176e4)·max_effort 150(손목 28)·damping 229(손목 87)이고 스테이지가 UR5 이득을 설정하는 코드는 없다(M0609 는 `--rail-drive` 로 설정한다).
  - 바퀴마다 다르다: 1바퀴(기동 자세 출발) 잔차 0.065–0.072, 2바퀴 이후(대기 자세 출발) 0.23–0.38. 5바퀴째 상판 칸 4단계는 모두 도달(0.1–1.4 mm)했고 대기 자세 복귀는 6/6 도달이다.
  - **철회된 가설 둘**: flange↔tool0 상수 오프셋(`error_m` 은 Lula 모델 안의 값이라 설명이 안 된다), 보간 스텝 > 시한(스텝 30 짜리 단계도 같은 잔차로 TIMEOUT 이다).
- 목적: `f796210` 수정이 Isaac 에서 픽을 여는지 본다. `2c68b73` 에서 돌렸다. 픽은 열리지 않았다.
- 9/17 에는 집기에서 `ik_failed` 62줄이 났다. 수정 내용은 받침대 월드 고정 관절이다.
- 구성: [`pharmacy_stage.py`](../../sim/standalone/pharmacy_stage.py) `--mode selfdemo --ur5 --loop 3`. headless 1회, 창 모드 1회.
- **selfdemo 에서는 `arm` 노드가 UR5 를 움직이지 않는다.** 스테이지가 Lula IK(`tool0`)로 직접 움직인다. `ur5 ik_failed` 는 Lula 실패이고 `ur5_kinematics.UR5_DH` 와는 무관하다.
- 관측: `ur5 world_joints`, `ur5 tcp_source`, `ur5 base_frame_mismatch`, 단계별 `ur5 reached|TIMEOUT` 과 `ur5 ik_failed`, `ur5 suction on|miss`, `ur5 placed … in_slot=`, 손 카메라 Hz. 결과 분류는 [2절](#2-ur5-selfdemo-픽-결과-분류표)이다.
- 판정:
  - 필수(구성 확인): `base_frame_mismatch` 0건.
  - 기록만: 봉투별 `ik_failed` 수, suction 거리, `in_slot` 비율, 첫 시도 성공, 사이클 시간.
- 흡착은 거리 판정 + 텔레포트(가상 attach)다. **물리 파지 성공으로 집계하지 않는다.**

### L3-VA-2 손 카메라 QR 판독 거리 — 미실행

- 목적: 계약 v1 이 "해상도는 QR 판독 거리에서 정한다"고 남긴 실측.
- 구성: `--ur5 --mode ros` + `pouch_detector`(기본 color). 봉투·환자·스테이션 QR 을 여러 거리에 둔다(벨트 픽·상판 재관측·인식표 스캔 자세 포함).
- 관측: 거리별 `TagRead` 성공률, detector 경고 `QR 을 못 읽었다. 한 변 N px`, 성공 판독의 QR 한 변 px, `camera_info`(K, D), 해상도·Hz.
- 판정:
  - 기록만: 거리 ↔ 한 변 px ↔ 성공률 표. `qr_min_size_px`·`tag_standoff_m` 제안은 이 표를 보고 PR 로 낸다.
  - 필수: `camera_info` 의 D 가 0 인지 기록한다. `plane_projection`(노드 미연결)의 전제다.
- **캡처·녹화(이 카드는 영상이 증거의 본체다):**
  - 거리마다 손 카메라 원본 프레임 1장. 보이는 그대로 저장한다(자르거나 키우지 않는다).
  - 마지막 성공·첫 실패 거리에는 프레임과 `TagRead`·detector 경고 줄을 같이 남긴다.
  - 창 모드면 거리 이동을 이어서 녹화한다. headless 면 프레임만 남기고 이유를 적는다.

### L3-VA-3 손 카메라로 상판 칸 재관측 — 미실행

- 목적: "해제 뒤 손 카메라로 칸을 다시 보고 안착을 확인한다"(계약 11.4 제안)가 가능한지 본다.
- 구성: 봉투를 칸에 두고 팔을 칸 위 촬영 자세(높이 여러 개)로 둔다.
- 관측: 한 화면에 보이는 칸 수, 칸 벽 가림, QR 판독, 촬영 자세 IK, 충돌.
- 판정: 기록만. 칸마다 QR 이 읽히는 촬영 자세가 하나라도 있으면 "가능"이다. 없으면 안착 확인 방식을 다시 정한다.

### L3-VA-4 FK ↔ USD TCP 대조 — 미실행

- 목적: `ur5_kinematics.UR5_DH`(UR 공개 표준 DH)가 시뮬 UR5 자산과 맞는지 본다. `arm_clear_of_belt` 의 CLEAR 와 `arm` 노드 IK 는 이 대조 전에는 믿지 않는다(계약 11.6).
- 구성: `--ur5 --mode ros` + `arm` 노드. 관절 자세 여러 개(홈, 벨트 픽 접근, 상판 칸 위, 특이점 밖 임의 자세)에서 정지 뒤 잰다.
- 관측: 같은 시각의 `joint_states` 와 TF `amr_1/base_link → <공구 링크>`, 같은 관절값의 `forward_kinematics`, 위치·자세 오차. 공구 링크 이름은 미확인이다(`ur5 end_link=…` 로 확인).
- 판정: 기록만. 허용 오차는 미정이다.
- **캡처·녹화:**
  - 자세마다 정지 화면 1장. 그 시각의 관절값·TF 는 표로 같이 남긴다(파일명에는 자세 번호만).
  - 자세 사이 이동은 이어서 녹화한다. 팔이 예상 밖으로 움직이면 그 구간이 증거다.
  - headless 면 자세마다 수치(관절값·TF·FK 결과)를 남기고 그 이유를 적는다.

### L3-VA-5 GripperState / command_seq 연동 — 미실행

- 구성(**셋 다** 켠다):
  - 스테이지 `--ur5 --mode ros --gripper-command-seq`(#278)
  - launch `gripper_command_seq:=true`(#286)
  - `arm` 노드 `gripper_observation:=state`(#291)
- 셋이 안 맞으면 픽 실패로 보인다. 구성 오류다. 제품 결함이 아니다.
- 스테이지만 켜면 Bool 흡착 명령이 무시된다. 스테이지를 끄면 `GripperState` 가 없어 팔이 파지를 확인하지 못한다.
- 관측: `GripperCommand`(epoch, command_seq 1·2·3…), 스테이지 `applied`/`ignored reason=…`, `GripperState`(seq, last_applied, state, mode), PickPouch 결과·detail, 리셋 뒤 command_seq.
- 판정:
  - 필수: 명령 전 HELD 가 파지로 집계되지 않는다. 리셋 뒤 command_seq 가 1 부터다. 이전 epoch 명령은 무시된다. mode=VIRTUAL 이면 물리 피킹 집계 0건이다.
  - 기록만: 명령 → 적용 지연, 해제 확인까지 시간.

### L3-VA-6 ArmClearance 가 토픽으로 나오는지 — 미실행

- 구성: `arm` 노드 `arm_clearance_enabled:=true`(#282). 통로 기하 파라미터(`arm_clearance_lane_*`·`_link_radii`·`_tool_*`·`_payload_*`)는 값이 없어(미측정) 비운 채 돈다. launch `observation_guard:=true` 는 켜지 않는다(기하가 비어 첫 피킹에서 트립이 멈춘다).
- 관측: `/amr_1/arm/clear_of_belt` 주기, epoch(리셋 전 1, 리셋 뒤 RESET_DONE 값), 리셋 중 UNKNOWN, seq 가 `joint_states` stamp 와 함께 느는지, `detail` 의 미설정 이유.
- 판정: 필수 — **CLEAR 가 한 번도 나오지 않는다**(값이 없으므로 UNKNOWN 또는 INTRUDING 만). CLEAR 가 나오면 결함이다.

### L3-VA-7 칸 안착 확인 — 미실행

- 구성: L3-VA-5 의 셋 + `arm` 노드 `placement_check_enabled:=true`(#296).
  - `gripper_observation:=state` 없이 켜면 `arm` 이 기동을 거부한다(해제 확인이 먼저다).
  - `pouch_detector` 는 `pouch_width_m` 모드로 띄운다. 고정 거리만 주면 재관측 거리에서 위치가 틀린다.
- 설정(`placement_view_standoff_m`, `placement_slot_box_m`, `placement_cabinet_box_m`, `placement_timeout_s`, 기존 `tool_frame`)은 **기본값이 없다.** 하나라도 비면 기동 로그에 오류가 남고, 모든 픽이 안착 미확인으로 닫힌다.
  - 안착 미확인의 outcome 은 `dropped`(detail `placement_unconfirmed: …`)다. trip_fsm 에서 재시도를 부르지 않는 유일한 기존 값이라 임시로 쓴다(결정 16번 대기). 이 경로를 켠 run 의 "낙하" 집계에는 안착 미확인이 섞인다. detail 로 나눠 센다.
- **관측 자세 이동은 충돌 검증이 없다.** L3-VA-3 뒤에 켠다.
- 관측: 픽 결과 detail(`old=`·`other_order=`·`no_pose=`·`outside=` 개수), 관측 자세의 `hand_camera/pouches`, 평가 전용 관측과 arm 결과의 불일치(그대로 기록하고 arm 쪽에서 맞추지 않는다).
- 기본값 제안에 필요한 측정: 칸·보관함 안쪽 치수와 봉투 중심 높이 범위(원점 = 물체가 놓이는 윗면의 중심, 결정 23번), QR 이 읽히는 standoff 범위(L3-VA-2), 해제 확인부터 첫 유효 검출까지의 sim 시간 분포.
- 판정: 필수 — 설정이 빈 상태에서 `ok`·`POUCH_LOADED` 가 0건이다. 그 밖은 기록만.

### 순서 제안

VA-1 → VA-4 → VA-2 → VA-3 → VA-6 → VA-5 → VA-7. VA-1 은 다른 카드의 전제(UR5 가 받침대 위에 있는지)다.

## 2. UR5 selfdemo 픽 결과 분류표

원인 칸은 **추정**이다. 이 표는 고치지 않고 관측만 한다. 로그 문구는 [`pharmacy_stage.py`](../../sim/standalone/pharmacy_stage.py)·[`p3sim/ur5_cell.py`](../../sim/standalone/p3sim/ur5_cell.py) 에서 옮겼다.

**비교 기준(9/17):**
- `7ae2879`: 집기에서 `ik_failed` 62줄이 나왔다.
- `3b114c4`: `tool0` FK 와 끝 prim 이 모두 (0.80, 0.21, 0.27) 이었다. 받침대는 (3.25, 0.55, 0.45)였고 `suction miss distance=2.1791` 이 나왔다.
- 판단: 자산의 월드 고정 관절(body0 비어 있음)이 `localPos0` 에 월드 앵커를 가져서 UR5 가 원점에서 시뮬레이션됐다.
- `f796210` 의 수정: 그 관절의 `localPos0` 에 받침대 위치를 더하고, `ur5 world_joints` 로그와 `base_frame_mismatch` 검사를 넣었다.
- **정정(9/20 진단 회차, #322):** `localPos0` 쓰기는 됐는데도 UR5 가 원점이었다. UR5 prim 자체가 USD 에서 원점이었기 때문이다. 위 9/17 판단(월드 앵커)만으로는 원인이 설명되지 않는다. 표의 `ur5 pin_failed` 줄이 이 사례다.

한 봉투의 단계: `above_pouch` → `touch` → `suck` → `lift` → `above_slot` → `lower` → `drop` → `retreat`.
- tcp 단계는 보간 뒤 오차가 `--tcp-tolerance`(0.01 m)보다 크면 `--phase-timeout-s`(5 s sim) 동안 더 시도한다.
- 그래도 못 가면 `TIMEOUT` 을 찍고 **다음 단계로 넘어간다.** 그래서 TIMEOUT 뒤의 줄은 앞 단계를 못 끝낸 상태에서 나온 것이다.

| 보이는 줄 | 가장 그럴듯한 원인(추정) | 추가로 뽑을 줄 | 볼 코드 |
| --- | --- | --- | --- |
| `ur5 disabled reason=…; continuing without --ur5` | 자산 서버에서 `ur5.usd` 를 못 받음, 또는 참조에 `base_link`·끝 링크가 없음 | `reason=` 전문, 자산 루트 경로. 재시도는 `--ur5-usd <로컬 파일>` | 스테이지(`sim/`) |
| `ur5 world_joints count=0 none (…)` | 자산에 월드 고정 관절이 없어 받침대 보정이 적용되지 않음 | 이어지는 `tcp_source`·`base_frame_mismatch` | 스테이지(`sim/`) |
| `ur5 world_joints … (instance proxy, not moved …)` | 고정 관절이 instance proxy 라 옮기지 못함(9/17 재발 가능) | 같은 줄의 `local_pos0`, `tcp_source` | 스테이지(`sim/`) |
| `ur5 pin_failed` · `ur5_prim=[0,0,0]` | UR5 prim 이 USD 에서 원점이다. `localPos0` 쓰기는 됐다(9/20 L3-2 의 사례) | `ur5 pin_check` 전문, `ready … base_pose=` | 스테이지(`sim/`) |
| `ur5 prim_translate set_ok=False` 또는 `composed_world` 가 받침대가 아님(#324) | prim 변환 쓰기가 실패했거나 부모 변환에 눌렸다 | 같은 줄의 `composed_world=`·`pedestal=`, 이어지는 `pin_check` | 스테이지(`sim/`) |
| `pin_check` 는 받침대인데 `base_frame_mismatch` 가 남음 | USD 는 맞는데 물리가 다른 자세다 | `tcp_source` 전문, `base_pose=` | 스테이지(`sim/`) |
| `ur5 base_frame_mismatch` | 판정 조건: `tool0_from_pedestal_m > 1.2` 또는 `base_link` 가 받침대에서 5 cm 넘게 벗어남. 9/17 원인의 재발. **있으면 뒤의 ik_failed·miss 는 결과일 뿐이다** | `ur5 tcp_source` 전문(`base_link=`·`articulation=`·`pedestal=`), `ur5 world_joints` | 스테이지(`sim/`) |
| `ur5 tcp_source … difference_m=` 가 수 cm 이상 | Lula FK 의 `tool0` 과 끝 prim 이 다른 링크(`end_to_tool=identity (unconfirmed)`) | `ur5 end_link=… end_to_tool=…`, `ur5 ready …` | 스테이지, 인식(L3-VA-4 와 같이 봄) |
| `ur5 ik_failed phase=above_pouch\|touch\|lift` | 벨트 끝 봉투가 도달 범위 밖이거나 아래를 보는 자세 제약으로 안 풀림(배치 기하) | `ur5 pick … pick=`, 같은 단계의 `ur5 phase=… target=… tcp=… base=…`, `count=` 증가 모양 | 스테이지(`sim/`) |
| `ur5 ik_failed phase=above_slot\|lower\|retreat` | 상판 칸이 도달 범위 끝이거나 자세 전환이 커서 가지가 튐 | `deck_slot=`, 특정 칸에서만 반복되는지 | 스테이지(`sim/`) |
| `ur5 TIMEOUT phase=… error_m=…` | IK 는 풀렸지만 드라이브가 5 s 안에 1 cm 안으로 못 감(드라이브·속도 `--ur5-tcp-speed` 0.003·충돌) | 같은 단계의 `ik_failed` 동반 여부, `error_m` 크기(수 mm = 드라이브, 수십 cm = 막힘·IK) | 스테이지(`sim/`) |
| `ur5 suction miss distance=… limit=0.04` | `touch` 에서 봉투 윗면에 못 닿음(앞 단계 실패의 결과), 또는 TCP 오프셋(`--ur5-tcp-offset` 기본 0)이 흡착면과 다름 | 직전 `ur5 reached\|TIMEOUT phase=touch error_m=`, `distance=` 크기(0.04 바로 위 = 오프셋, 수십 cm = 도달 실패) | 스테이지, 인식(흡착면 정의) |
| `ur5 suction miss target=none …` | 흡착할 봉투 객체가 없음(이미 치웠거나 pool 에서 빠짐) | `candidates=… nearest=…`, 같은 시각 `pouch picked_by=ur5`·`ros pick_stand_in` | 스테이지(`sim/`) |
| `ur5 placed deck_slot=N in_slot=False` | 놓기 위치가 칸 밖(벽 위에 걸침, 떨어지며 튐) 또는 운반 중 낙하 | `pouch=` 좌표와 칸 중심, 직전 `lower`·`drop` 의 `error_m`, `holding=` | 스테이지, 인식(놓기 높이) |
| `suction on` 뒤 `in_slot=False` 이고 봉투가 벨트 근처 | 운반 중 놓쳤다 | `lift`·`above_slot` 의 `TIMEOUT`, `holding=` | 스테이지(`sim/`) |
| `ur5 deck full slots=…` | 상판 칸을 다 썼다. `--loop` 보다 칸이 적거나 앞 봉투가 칸을 차지했다 | `placed` 줄의 `deck_slot=` 목록, `--deck-count` | 스테이지(`sim/`) |
| `--loop N` 을 채웠는데 안 끝남 | 종료는 배출 횟수다. 픽 실패여도 루프가 돈다 | `stop reason=` | 스테이지(`sim/`) |
| 끝이 `app_stopped`·Kit 종료 | 창 모드 `app_stopped`(원인 미확인) 또는 GPU | `a1_probe {…}`, `kit_log tail …` 경로의 마지막 50줄 | 스테이지(`sim/`) |

### ROS 경로(`--ur5 --mode ros` + 실물 `arm`·`pouch_detector`)에서 처음 볼 것

selfdemo 가 통과해도 이 경로는 따로 본다. 팔 노드가 자체 DH IK 로 관절 명령을 내고 목표를 TF 로 받기 때문이다.
계약 3절은 `deck_slot_N` 의 N 이 0 부터인지 1 부터인지 적지 않았다. 결정 전에는 첫 픽이 팔을 움직이기 전에 닫힌다.

| 보이는 줄 | 가장 그럴듯한 원인(추정) | 추가로 뽑을 줄 | 볼 코드 |
| --- | --- | --- | --- |
| `not_detected` + `놓을 곳 TF 없음: amr_1/deck_slot_0` | 칸 TF 번호가 어긋난다. Isaac 은 1부터, `target_slot` 은 0부터다 | `tf2_echo …/deck_slot_1`, goal `target_slot` | 계약 결정 |
| `not_detected` 인데 TF 는 있고 `pose` 가 0 | `pouch_width_m`·`pouch_distance_m` 가 둘 다 0 이다 | detector 기동 경고, pouches `pose` | 인식·팔 노드 |
| 접근·파지 자세에서 `grasp_failed`(IK 실패) | 팔 노드 DH 가 자산과 다르거나(`L3-VA-4` 미확인), 흡착면 오프셋(`grasp_z_offset_m`)이 0 이다 | arm 로그의 IK 실패 줄(위치·회전 오차), `L3-VA-4` 의 FK↔TCP 값 | 인식·팔 노드 |
| 파지는 됐는데 `POUCH_LOADED` 뒤 봉투가 칸 밖 | 놓기 높이(`place_z_offset_m`)가 0 이거나 칸 프레임 원점 해석이 다르다(윗면 중심, 결정 23번) | `deck_slot_N` TF 와 봉투 월드 위치, `place_z_offset_m` | 인식·팔 노드, 스테이지(프레임) |

### 받침대 고정 뒤: 막힘인가 추종인가 (실습12·12c 기준)

| 보이는 줄 | 뜻 | 다음에 볼 것 |
| --- | --- | --- |
| `ur5 ik_check … solved=True` 인데 `want ≠ have` | IK 는 풀렸고 명령도 갔는데 관절이 그 값에 못 간다. `error_m` 은 여기서 생긴다 | 어긋난 관절 이름과 부족한 각도, 같은 시각의 contact 줄 |
| UR5 링크가 나오는 contact 줄(`forearm`↔벨트, `upper_arm`↔칸 벽·방 벽) | 기하에 막혔다. 막힌 자세에서는 토크를 더 줘도 안 간다 | 그 phase 의 목표·시작 tcp, 어느 링크가 어디에 닿는지 |
| contact 는 없는데 `want ≠ have` | 드라이브 추종·포화 쪽이다 | `log_dofs` 의 stiffness·damping·max_effort, 같은 목표를 더 느리게 갈 때 잔차가 주는지 |
| `ik_check` 가 `solved=False` | IK 자체가 안 풀린다(자세 제약·도달) | `ik_failed` 줄, 목표 자세 |

**슬롯 안에서 볼 순서:**
1. `ur5 disabled` 가 있는지 본다.
2. `ur5 world_joints` → `ur5 tcp_source` → `ur5 base_frame_mismatch` 를 본다. mismatch 가 있으면 뒤 줄은 보지 말고 이 세 줄 전문을 보고한다.
3. 첫 봉투에서 가장 앞선 `TIMEOUT`·`ik_failed` 단계를 본다. 가장 앞선 실패만 원인 후보다.
4. 봉투마다 `placed … in_slot` 을 모은다.

재실행은 **같은 인자로 한 번**만 한다. 허용치(`--phase-timeout-s`·`--tcp-tolerance`·`--suck-distance`)를 바꿔 보지 않는다.

## 3. 9/20 L3-1 보충 시간 — 관측과 해석

**관측**(이슈 #240, master01 관측):
- 1회차 issuecomment-5743927668, 2회차 issuecomment-5744000805. tree `419b20b`.
- M0609 보충(`REFILL_REQUESTED` → `REFILL_DONE`)은 ibu 19.95·21.27 s, amox 18.69 s 였다. 실습8(`a94f06e`)은 46.4–52.4 s 였다.
- 팔 로그의 단계 시간 합은 23.68·21.47·25.02 s 였다. 잡기·넣기·재생성 줄과 이벤트 셋은 보충마다 모두 있었다.
- `guarded module: motion=…` 줄은 0건이었다.

**해석**(코드와 PR 본문을 읽은 판단이고 원본 로그로 구간을 나누지 않았다):
- 단축의 원인은 #228 로 본다. 실습8 은 #228 머지 전의 tree 에서 돌았다.
  - #228 전에는 궤적 점마다 고정 대기를 했는데, Isaac 시계가 1/60 s 계단이라 점마다 두 틱이 들었다. 그래서 모든 궤적이 설계의 1.67배였다.
  - #228 은 이것을 흐른 sim 시간 기준으로 바꾸고, 이어지는 이동 사이의 중간 도착 대기를 없앴다.
  - #228 이 적은 계획 기준 이론값(원통 16–18 s, 모듈 19–22 s)에 L3-1 값이 들어온다.
- "기동 때 계획 캐시를 미리 풀어서"는 원인이 아니다. 실습8 도 기동 때 캐시를 16/16 풀었다.
- guarded 모듈 경로(#229·#230)는 이 실행에 관여하지 않았다. 시연 스택이 명시로 끈다([0절](#0-공통)).
- 단계 시간 합이 `REQUESTED → DONE` 보다 약 3.7 s 긴 이유: `REFILL_DONE` 은 마지막 단계(`fold_back`) 이동이 끝나면 나가고, 팔은 그 뒤 결과를 내기 전에 홈까지 간다. 단계 시간의 마지막 값에 그 복귀가 들어 있다.
- 그 복귀 중 다음 보충 요청이 오면 겹쳐 돌지 않고 기다린다(orchestrator 는 보충을 하나씩 보내고, 팔은 진행 중 goal 을 거부한다). 2회차 amox 29.70 s 가 그 대기다. `REFILL_DONE` 을 홈 도착 뒤로 옮길지는 시연 뒤 과제다(#239).
