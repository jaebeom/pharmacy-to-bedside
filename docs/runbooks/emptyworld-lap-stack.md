# 빈월드 한 바퀴 — 현재 기동 조합

> **상태: 지난 기록 (2026-09-24 기준).** 지금은 [병원 한 바퀴 런카드](hospital-full.md)를 따른다.

기준: `main` `fab74be7a4385ca6191121042b922572fb9eedb4`(#469 병합).
관측 원문과 회차별 변경은 [실습30](../practice/practice-30.md)에 있다.

> **한계 — 통합만 본다(`INTEGRATION_ONLY`).** 봉투·인식표 입력은 스테이지 참값 기반 시뮬 센서이고,
> 흡착은 그리퍼 형상 없이 거리로 판정해 부착한다. 주문은 1인 1건, 침상은 `bed_a1` 하나,
> 주행은 고정 경로 추종이다. 실물 Ridgeback+UR5의 장착 자리와 심월드 문 통과 높이는 **미확인**이다.

## 1. lap14에서 돈 조합

| 항목 | 값 |
| --- | --- |
| 장면 | 빈월드 + AMR 합본 `ridgeback_ur5.usd` |
| 배치 | 팔 = 상판 한쪽 끝 + 받침 0.15 m, 반대쪽 트레이 3자리, 보관함 높이 0.70 m |
| 주행 | 현재 상한의 80%: 0.4 m/s, 0.8 rad/s, 0.8 m/s², 1.6 rad/s², `follower_slow_radius=0.667` |
| 시뮬 스텁 | `use_stub_sim:=false` |
| 센서·보관함 | `P3_SIM_SENSORS=1`; K5b `isaac_adapter`가 봉투·인식표·보관함 참값을 옮김 |
| 팔 | 합본용 params v4, #469의 흡착 대기·홈 복귀 경유 |
| 주문 | 자동 주문 끔, 1인 1건 → `bed_a1`; 완주 뒤 리셋 |
| 실행 | `master02`, 창 모드, `ROS_DOMAIN_ID=121` |
| lap14 트리 | `cf95cab = main 3fd21ab + 559a926`(#469 머지 전 head) |

lap14는 위 트리에서 ①–⑩ 연속 3바퀴·실패 0으로 관측됐다. #469는 현재 main에 병합됐고, main 단독 재확인은 진행 중이다. 결과는 #240에 남긴다.

## 2. 환경과 기동

`<repo>`는 저장소 절대 경로다. 기계마다 다른 두 파일 경로를 먼저 정한다.

```bash
export P3_WORLD=emptyworld
export P3_SIM_SENSORS=1
export P3_AMR_COMBINED=<ridgeback_ur5.usd-절대경로>
export P3_UR5_ARM_PARAMS=<합본용-arm-params.yaml-절대경로>
export P3_AUTO_ORDER=0
export ROS_DOMAIN_ID=<그날-예약한-도메인>

cd <repo>
tools/demo_v2.sh cmds
tools/demo_v2.sh up
```

`tools/demo_v2.sh cmds`의 출력을 먼저 보며 실제 실행 대상과 경로를 확인한다.
이 프로필은 다음 묶음을 만든다.

| 프로세스 | 현재 조합 |
| --- | --- |
| Isaac 스테이지 | `emptyworld-loop`, `--amr-combined`, 시뮬 센서, M0609 자산 |
| 주행 | `motion_backend:=waypoints`, 빈월드 zones/routes, 실물 fleet |
| 스택 | `pharmacy_only:=false`, `use_isaac_adapter:=true`, `use_stub_sim:=false`, `use_stub_fleet:=false`, `use_stub_arm:=false`, `use_ur5_arm:=true` |
| 시뮬 센서 묶음 | `sim_pouches:=true sim_tag_reads:=true pouch_source:=sim scan_tag_source:=sim sim_cabinet:=true` |
| 보충 팔 | `m0609_arm`, sim time, scene v2 |
| 관제 웹 | 명령 허용, 같은 order pool·zones 파일 |

`<zones>`는 `src/rokey_p3_description/config/zones.emptyworld.yaml`,
`<routes>`는 `src/rokey_p3_description/config/routes.emptyworld.yaml`이다.
주행과 웹이 같은 zones 절대 경로를 쓰는지 기동 요약에서 확인한다.

## 3. 합본용 팔 params

lap14를 재현하려면 합본용 params에 다음 키를 명시하거나, 표에 적은 기본값이 실제 코드와 같은지
확인한다. 현장 파일의 전체 값은 저장소에 없으므로 표 밖의 값을 추측해 채우지 않는다.

| 키 | 값·확인 방법 | 이유 |
| --- | --- | --- |
| `joint_names` | `ur_arm_shoulder_pan_joint`, `ur_arm_shoulder_lift_joint`, `ur_arm_elbow_joint`, `ur_arm_wrist_1_joint`, `ur_arm_wrist_2_joint`, `ur_arm_wrist_3_joint` | 합본 USD 이름을 그대로 사용 |
| `arm_base_frame_convention` | `base_link` | 합본 TF에 180° 보정을 두 번 적용하지 않음 |
| `home_joint_positions` | 기동 로그 `amr arm_home steps=90 joints={…}`의 6개 값을 그대로 옮김 | 자산 스폰값. 문서에 값이 없어 **미측정값을 만들지 않음** |
| `via_joint_positions` | `[0.0, -1.6, 0.3, -0.2708, 1.5708, 0.0]` | v4 경유 자세 |
| `approach_height_m` | `0.08` | lap14 사용값 |
| `arrival_check_enabled` | `true` | 이동 실패를 흡착 실패로 보고하지 않음 |
| `arrival_tolerance_rad` | `0.05` | lap14 코드 기본값 |
| `grasp_hold_timeout_s` | `2.0` | 첫 `holding=false`로 닫지 않고 부착을 기다림(#469) |

`P3_SIM_SENSORS=1`일 때 `pouch_source`와 `scan_tag_source`는 launch 인자가 `sim`으로
덮는다. 이 둘을 params 파일과 launch에 서로 다른 값으로 두지 않는다.

## 4. 기동 확인

주문을 넣기 전에 다음을 원문으로 남긴다.

1. 스테이지에 `ur5 pedestal disabled reason=--amr-combined`가 있다.
   없으면 받침대 팔과 합본 팔이 함께 떠 있다.
2. `amr arm_base_frame … origin=`이 대략 `(0, 0, 0.28)`, yaw 180°다.
3. `/amr_1/joint_states`가 베이스 3 + UR5 6의 9관절 한 메시지다.
4. 팔의 기준 프레임 관례 자가 확인이 통과한다.
5. `/amr_1/gripper/holding` 발행자는 스테이지 하나다.
6. `/evaluator/cabinet` 발행자는 K5b 어댑터 하나다. `stub_sim`과 함께 켜지 않는다.
7. zones/routes와 웹이 같은 빈월드 파일을 읽는다.
8. `/clock`과 명령 발행자가 하나씩인지 확인한다.

하나라도 다르면 회차를 시작하지 않고 실제 출력과 사용한 파일 SHA를 남긴다.

## 5. 한 바퀴와 K6

1. 1인 요청 하나를 `bed_a1`로 넣는다.
2. ① 요청 수락 → ② 적재 도킹 → ③④ 조제·벨트 끝 → ⑤ 적재 픽 →
   ⑥ 침상 도착 → ⑦ 인증 → ⑧ 전달 → ⑨ 복귀 → ⑩ 도킹·리셋 순서로 본다.
3. 참값은 ⑤ 스테이지 `suction on distance`(≤ 0.01 m), ⑥ 스테이지 `d_xy`(≤ 0.05 m),
   ⑧ `/evaluator/cabinet present=true`다.
4. 리셋 뒤 다음 1인 요청을 넣어 연속 3바퀴까지 반복한다.
5. Python 예외·`[ERROR]`, AMR/UR5 링크 `touch`, 낙하, 같은 자리 3분 무이벤트가 나오면
   그 원문과 각 노드의 마지막 줄을 남기고 내린다.

## 6. ⑤ 픽 최종 실패 뒤에는 운영자가 리셋한다

재범 결정 50이다. 자동 리셋이나 임계값 완화로 바꾸지 않는다.

픽이 재시도까지 최종 실패하면 봉투가 벨트 끝에 남아 다음 조제가 `belt_occupied`로 막힌다.
`pick_notice:=false`인 실물 UR5 조합에서 어댑터가 먼저 치우게 해서는 안 된다.
배출 대기 줄이 쌓이기 시작하면 기다리지 말고 운영자가 다음을 실행한다.

```text
POST /api/reset
```

리셋은 실려 있던 다른 주문도 지우므로 자동화하지 않는다. 벨트 끝 reject 경로는 v0.4.1의
계약·시뮬·어댑터·orchestrator 후속 범위다.

## 7. 기록과 미실행

- run ID, 실행 트리 SHA, params 파일 경로·SHA, 기동 시각, 캐시 여부를 첫 줄에 적는다.
- 영상·캡처는 `master02` 로컬 원본 경로와 전체 sha256을 남기고 둘째 저장 위치를 정한다.
  실습30 작성 시점에는 **둘째 저장 위치 미정**이다.
- `tools/judge_run.py --logs <P3_LOG_DIR> --stamp <기동 시각> --run <run>` 출력을 붙인다. `--logs`·`--stamp` 는 필수다. lap14 원문에는 이 출력이 없다. 미실행으로 남았다.
- main `fab74be` 단독 K6 재확인은 진행 중이며 결과는 #240에 남긴다. 실물 장착 자리와 문 통과 높이는 아직 미확인이다.
