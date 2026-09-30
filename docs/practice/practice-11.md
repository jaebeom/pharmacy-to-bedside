# 실습11 — master01, v0.3.0 후보 `2c68b73` 슬롯(증거 실행, 확정 대본, L3-2)

| 항목 | 값 |
| --- | --- |
| 번호 | 실습11 |
| 날짜·시각 | 2026-09-20 03:10-05:30 슬롯(KST). ② 증거 실행 03:11:05-03:14:45, ③ 확정 대본 03:16:52-03:23:35, ④ L3-2 03:24:58-03:50(슬롯 반환) |
| 장소 | `master01`(IsaacSim14), 도메인 117 |
| 돌린 사람 | `master01` 원격 실행(03:15 에 다시 붙음) |
| 출처 | master01 보고와 #240 댓글(아래 목록). 수치가 다르면 #240 이 맞다 |
| 원본 | `master01` 로컬(저장소 밖) |
| 기록 | 이 기록은 `master01` 화면을 직접 보지 않고 썼다 |

#240 댓글: 보류 해제·슬롯 순서, 증거 실행, 확정 대본, L3-2 1회차, L3-2 2회차, L3-2 진단 회차.

## 목적

v0.3.0 후보 SHA `2c68b73` 한 트리로 슬롯 항목 넷을 돈다(#240 보류 해제 댓글의 순서).

1. `2c68b73` 빌드
2. 증거 실행(protocol `pharmacy-lap-pilot-v1`, frozen)
3. 확정 대본 실행(창 모드: 자동 긴급 → 웹 1인 `ord-0001` → 묶음 `ord-0003`+`ord-0004`)
4. L3-2(UR5 selfdemo 픽)

앞선 원격 연결은 03:08 무렵 끊겼고, 그때 L3-2 는 돌지 않았다(#240). 실습10 의 범위는 두 회차 그대로다.

## 구성

| 부분 | 값 |
| --- | --- |
| 트리 | ①-③·④ 1·2회차 `2c68b73`. ④ 진단 회차만 `13a2dfd`(#322). 두 커밋 모두 `main` 에 있다 |
| 절차 | ② [증거 실행 runbook](../runbooks/evidence-run-pharmacy-lap.md) 그대로. ③ [시연 runbook](../runbooks/demo-0921-v2.md) 3절. ④ [L3 팔·인식 runbook](../runbooks/l3-arm-perception.md) 분류표 |
| 웹 python | 실습10 때의 `release/20260920-419b20b/web/backend/.venv` |
| protocol | `pharmacy-lap-pilot-v1`, frozen(`frozen_at` 2026-09-19T17:44:12Z, #301 머지 2026-09-19T18:07Z), sha256 `7fcf25bd65adbfcea349a75767fd8316c9e731789e0b03e9010cdf9df7c4be05` |

## 관측

### ② 증거 실행 — headless (#240)

웹 요청은 넣지 않았다(자동 요청만). 리셋은 웹 `POST /api/reset`(202) 3번이고, 매번 `DOCKED`·`REFILL_DONE`·`DISPENSER_RESUMED` 뒤에 했다.

| 시행 | epoch | run ID | lap_s | load_s | dispense_to_end_s | return_s | refill_s | pick_attempts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 분모 제외(not_a_trial) | 1 | `20260919T181215Z-master01-1cefc5f8` | 12.533 | | | | 19.933 | |
| 1(seed 0) | 2 | `20260919T181249Z-master01-8d458d4e` | 12.867 | 11.333 | 9.117 | 1.017 | 23.050 | 1 |
| 2(seed 1) | 3 | `20260919T181328Z-master01-123c263d` | 12.917 | 11.450 | 9.667 | 1.017 | 21.333 | 1 |
| 3(seed 2) | 4 | `20260919T181358Z-master01-154727c1` | 12.683 | 11.100 | 9.317 | 1.017 | 22.517 | 1 |

- 시행 3개 모두 `status=trial`, `lap_success=1`.
- 빌드(①): `release/20260920-2c68b73`(`2c68b73cd0f1`, 커밋 안 한 변경 0), colcon build 12 s exit 0. 진단 회차 트리 `release/20260920-13a2dfd`(`13a2dfdad0c2`)도 colcon 12 s exit 0.
- 기동: `demo_v2 up` 03:11:05, PLAY 8 s, 계획 캐시 16/16(59.8 s, 새로 풂), stack 1 s, web 1 s.
- epoch 1: 자동 `ord-0002` → `DOCKED` 78.533 → `REFILL_DONE` 87.0 → `DISPENSER_RESUMED` 90.833 sim s. 시행마다 `RESET_DONE` → `REQUEST_ACCEPTED` 는 3.8-4.3 sim s.
- run `created_at`(18:12-18:13Z)은 `frozen_at` 17:44:12Z 보다 뒤다.
- down 03:14:36-45, web·stack·arm·stage 모두 `exit 0`. run 디렉토리 5개에 파일 5개씩. 남은 프로세스·tmux 없음.
- WARN/ERROR: arm 0/0, web 0/0, stack 1/0(SIGINT 종료 안내), stage 119/0(kit 경고). adapter·orchestrator 종료 로그에 dropped·wait 줄 없음.

runbook 과 다른 점(실행 중에 고치지 않았다):

- (a) 스테이지 로그의 scene 줄이 `scene base_usd=- base_usd_sha256=- meters_per_unit=- up_axis=-` 다. preset `demo-ros-refill-v2` 의 `base_usd` 가 null 이라 scene 해시가 없다. 이 줄은 둘째 줄이 아니라 넷째 줄이다.
- (b) `cabinet.jsonl` 이 다섯 run 모두 0 바이트다.
- (c) Isaac 쪽에 seed 파라미터가 없어 seed 는 시행 번호로만 썼다(시드 미적용). 팔은 `v2_seed=7` 고정이다.
- (d) aggregate 출력의 `trip_limit_s` 는 600.0 이다. runbook 1절은 protocol timeout 900 s wall 을 말한다.

### ③ 확정 대본 실행 — 창 모드 (#240)

[시연 runbook](../runbooks/demo-0921-v2.md) 3절 대본(결정 25)이다. 트립 4개 모두 `DOCKED`, 409 0건. 1인과 묶음 한 바퀴가 Isaac 에서 끝까지 돈 것은 이 트리에서 처음이다.

| 순서 | 요청 | `REQUEST_ACCEPTED` → `DOCKED`(sim s) | 비고 |
| --- | --- | --- | --- |
| 1 | 자동 긴급 `ord-0002`(`r001-0001`) | 70.000 → 82.450 = 12.45 | 웹 입력 없음 |
| 2 | 웹 1인 `ord-0001`(`mode` 0, dest `bed_a1`) | 128.333 → 140.833 = 12.50 | 200 OK |
| 3 | 웹 묶음 `ord-0003`+`ord-0004`(`mode` 2, dest `bed_b1`) | 156.700 → 179.700 = 23.00 | 200 OK. `/api/snapshot` 으로 PAUSED 가 비고 `refilling=false` 인 것을 본 뒤 보냄. 묶음 중 보충 없음(앞 보충으로 재고 있음) |
| 4 | 리셋(`POST /api/reset` 202) 뒤 자동 `ord-0002`(epoch 2) | `RESET_DONE` 344.4, 348.000 → 360.283 = 12.28 | |

- 모두 `HOLD_RETURN`/`pharmacy_only`, pick 1회씩. `orders.jsonl` 의 네 주문 모두 claim `HOLD_RETURN`.
- 보충(REQ → DONE, sim s): ibu 19.93, amox(원통) 18.70, ibu(epoch 2) 21.35.
- 기동 03:16:52, PLAY 11 s, 계획 캐시 16/16(64.0 s, 새로 풂). 스테이지 종료 줄 `stop reason=sigint wall_s=389.896 loop_hz=59.63 sim_s=387.467 rtf=0.994`.
- 자원(5 s 샘플 62개): Isaac python RSS 5.27 → 5.28 GiB(평탄), VRAM 최대 2600 MiB.
- WARN/ERROR: arm 6/0(`joint_states` 수신 공백 0.21-0.23 s wall 3쌍), stack 1/0(SIGINT 안내), web 0/0, stage 104/0(kit 경고), browser 0/0.
- down 03:23:27-35: browser exit 130(firefox C-c), web·stack·arm·stage `exit 0`. 남은 프로세스·tmux 없음.
- run: epoch 1 `20260919T181809Z-master01-6929bed5`(트립 3개라 protocol 집계 대상 아님), epoch 2 `20260919T182250Z-master01-47672df1`. 파일 5개씩.
- 비교: 실습9(`master02`, `10c8e83`)의 묶음은 23.4 s 였다.

이 실행의 제한(빠진 것):

- **웹 요청은 `curl` 로 `POST /api/requests` 를 보냈다.** 프론트와 같은 엔드포인트지만 화면 버튼을 누르지 않았다. 버튼 → 요청 경로는 **미실행**이다.
- firefox 가 또 x=116 에 떠서 Isaac 을 가렸고, 창 위치만 손으로 옮겼다(P25 재현).
- 녹화·캡처 없음. **왜 없는가**: ②·④ 는 headless 다. ③ 은 창 모드였지만 켜지 않았다. 시간이 모자라서가 아니다. 슬롯 요청에 녹화·캡처 항목이 없었고, `demo_v2.sh` 의 `P3_CAPTURE_EVERY` 기본값이 0(꺼짐)이라 자동 캡처도 없었다(master01 답, 9/20). 다음 창 모드 실행부터는 녹화·단계 캡처를 켜고 파일명·크기·sha256 을 같이 보낸다.
- 묶음 중에 보충이 끼는 경우는 나오지 않았다(미관측).

### ④ L3-2 UR5 selfdemo 픽 — 트리 `2c68b73`, 1·2회차 (#240)

`pharmacy_stage.py --mode selfdemo --ur5 --loop 3 --headless`. **두 번 모두 실패, 픽 0/3.** 실행 중에 고치지 않았다.

먼저 본 세 줄(1회차, 2회차와 diff 0):

```text
[pharmacy_stage] ur5 world_joints count=1 ["/World/P3Pharmacy/Loading/UR5/root_joint body1=['/World/P3Pharmacy/Loading/UR5/base_link'] local_pos0=[0.0000, 0.0000, 0.0000]->[3.2500, 0.5500, 0.4500] articulation_root=True"]
[pharmacy_stage] ur5 tcp_source fk_tool0=[0.8482, 0.2144, 0.0509] end_prim=[0.8482, 0.2144, 0.0509] difference_m=0.0000 base_link=[0.0000, 0.0000, 0.0000] articulation=[0.0000, 0.0000, 0.0000] pedestal=[3.2500, 0.5500, 0.4500] tool0_from_pedestal_m=2.458 (tcp uses fk)
[pharmacy_stage] ur5 base_frame_mismatch: the simulated UR5 is not on its pedestal; picks will fail IK
```

| 항목 | 1회차(03:24:58) | 2회차(03:34:41) |
| --- | --- | --- |
| 첫 실패 | `above_pouch ik_failed count=1 target=[0.6727, -0.0708, 0.5931]` | 같음 |
| `ik_failed` | 195줄 | 278줄(내린 시각이 달라 다름) |
| `TIMEOUT` | 21줄(above_pouch error_m 2.3967, touch 2.3132, lift 2.3441) | 21줄 |
| `suction miss` | 12줄(distance 2.3133-2.3244, limit 0.04) | 12줄 |
| `placed` | deck_slot 1·2·3 모두 `in_slot=False`. 봉투는 벨트 끝 `[2.81, 0.99, 0.755]` 그대로 | 같음 |
| 끝 | `--loop 3` 뒤에도 끝나지 않아 C-c. `wall_s=549.641 loop_hz=47.33 sim_s=433.583 rtf=0.789`, exit 0 | 세 번째 placed 뒤 C-c. `wall_s=539.325 loop_hz=46.49 rtf=0.775`, exit 0 |

- `--ur5` 가드(#244)에 걸리지 않고 기동했다. 자산은 원격 자산 서버(S3)의 `ur5.usd` 를 참조한다(`ur5 built usd=https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/Isaac/Robots/UniversalRobots/ur5/ur5.usd`).
- `ur5 ready … base_pose=[0.0000, 0.0000, 0.0000]`: Lula 베이스도 원점이다.
- 로그 행 순서는 build → `step=articulation_ready ok` → UR5 dof 6 → `ur5 ready` → `tcp_source` → `base_frame_mismatch` 다. "world.reset" step 줄은 없다.
- 곁가지: `log_dofs` 가 M0609 의 joint_1..6 을 `type=translation type_raw=1` 로 찍는다. UR5 는 `type=rotation` 이다. 판단: 표기(enum 매핑) 문제이고 동작과 무관하다. 그 매핑(`m0609_refill_stage.py` 93행 부근)은 `log_dofs` 에서만 쓰인다. 시연 뒤에 고친다.

### ④ L3-2 진단 회차 — 트리 `13a2dfd`(#322) (#240)

이 회차는 L3-2 진단 전용이다. 트리가 다르므로 ①-③ 과 섞지 않는다. v0.3.0 후보는 `2c68b73` 그대로다.

`--mode selfdemo --ur5 --loop 3 --headless --duration 300 --kit-log-file … --kit-log-verbose`, 기동 03:44:45:

```text
[pharmacy_stage] ur5 world_joints count=1 [… local_pos0=[0.0000, 0.0000, 0.0000]->[3.2500, 0.5500, 0.4500] set_ok=True articulation_root=True"]
[pharmacy_stage] ur5 pin_check ur5_prim=[0.0000, 0.0000, 0.0000] base_link=[0.0000, 0.0000, 0.0000] base_link_resets_xform_stack=False joints=['/World/P3Pharmacy/Loading/UR5/root_joint written=[3.2500, 0.5500, 0.4500] readback=[3.2500, 0.5500, 0.4500] strongest_layer=anon:0x1896ca90:World0.usd']
[pharmacy_stage] ur5 pin_failed base_link composed world [0.0000, 0.0000, 0.0000] is not the pedestal [3.2500, 0.5500, 0.4500]
[pharmacy_stage] stop reason=duration updates=14186 wall_s=300.021 loop_hz=47.28 sim_s=236.433 rtf=0.788 dispensed=1 render_products=1 ur5=on …
```

- 관측(#322 판정표에 맞춘 것):
  - 관절 쓰기는 반영됐다: `set_ok=True`, readback 이 쓴 값과 같다.
  - `base_link_resets_xform_stack=False`.
  - **USD 합성 월드에서 UR5 prim 이 원점이다.** 판정표로는 "`SingleArticulation(position=받침대)` 가 USD 의 prim 변환에 쓰이지 않은" 칸이다.
  - `pin_failed` 는 한 줄뿐이고, `--duration` 으로 스스로 끝났다(exit 0).
  - Kit 로그(186 MB) grep 23줄 가운데 "fixed base"·"resetXformStack"·관절 프레임 불일치에 해당하는 경고·오류는 0줄이다.
  - 자산 USD 직접 조회는 하지 않았다(슬롯 지시).
- 원본(`master01` 로컬, sha256 앞·뒤만): `rc2-1-032458.log` c961bbd7…bbad, `rc2-2-033441.log` fa04b9df…f355, `rc2-diag-034445.log` 27f52098…d4744, `kit-13a2dfd.log` 633f5e28…448a. 전체 값은 master01 보고 원문에 있다.
- 슬롯 반환 03:50. Isaac·rokey_p3 프로세스 0, tmux 없음, VRAM 316 MiB. `master01` 에 워크트리 `../release/20260920-2c68b73`·`20260920-13a2dfd`, 로그 `$HOME/markle_tmp/ev`·`demo`·`l3-2` 를 남겼다.

## 해석 (#240)

- 합격선은 protocol 에 없다. **`lap_success` 3/3 은 protocol 결과이지 일정표의 "3회 연속 성공" 의 정의가 아니다**(검토 지적). v0.3.0 판정에 쓸지는 재범이 정한다.
- ②·③ 을 합쳐 후보 SHA `2c68b73` 에서 긴급·1인·묶음과 리셋 뒤 재실행이 모두 끝까지 돌았다. 태그를 막는 관측은 지금 없다. 태그 여부는 재범이 정한다.
- **공식 기록은 manifests PR 이 `evidence.py validate` 를 통과하고 머지돼야 확정된다.** manifests 는 #321(Draft, 보호 경로라 재범 승인 대기)이다. 이 실습 기록은 evidence 가 아니다.
- (a)-(d) 에 대한 판단(#321):
  - (a) scene: `not_applicable` + 이유(재범 판단 요청).
  - (b) `cabinet.jsonl` 0 바이트는 `pharmacy_only` 에서 정상이다.
  - (c) 시드 미적용은 protocol purpose 8 이 허용한다(시행 번호를 seed 로 쓰고 notes 에 적음).
  - (d) 600 s 와 900 s 는 다른 값이라 runbook 이 맞다.
  - protocol 은 frozen 이라 고치지 않는다.
- `2c68b73` 의 기본 동작은 `419b20b`(실습10) 때와 같은 범위다(트립 12.5-12.9 s, 보충 19.9-23.1 s).

### ④ 해석 (#240)

- 9/17 의 실패와 같은 모양이다. `f796210`(월드 고정 관절의 `localPos0` 에 받침대 위치를 더함)은 관절 앵커만 받침대로 옮겼다. UR5 prim 자체가 USD 에서 원점이라, 고정 베이스 articulation 은 원점 자세로 만들어졌다. 그래서 `f796210` 이 효과가 없었던 것으로 본다. **9/17 수정이 Isaac 에서 효과가 없었다는 첫 관측이다.**
- 후보 A("참조 자산이라 쓰기가 조합에 안 들어간다")와 H2("base_link 가 부모 변환을 무시한다")는 진단 회차 줄로 아니다.
- 수정 방향(SIM-9 2단계, #324 Draft): UR5 prim 의 변환을 물리 파싱 전에 USD 에 직접 쓴다. 수정 뒤 구성 확인 기준은 로봇·Lula `base_pose` = 받침대, `tool0_from_pedestal_m` < 1.2, `pin_failed` 0줄이다(합격선 아님). 확인은 9/20 15-21시 통합 슬롯.
- **영향 범위**: 시연 preset 은 UR5 가 스텁이라 ②·③ 결과와 v0.3.0 후보 `2c68b73` 에는 영향이 없다. 다만 1차 시연 범위의 "벨트 끝 UR5 픽" 은 Isaac 에서 아직 한 번도 성공하지 않았다(9/17 에 이어 두 번째 실패 관측).

## 문제

| P | 내용 | 출처 | 고치는 쪽 | PR |
| --- | --- | --- | --- | --- |
| P26 | 증거 실행이 runbook 과 다른 점 넷((a)-(d), 본문 ②) | master01 실습11 ② | evidence manifests | #321(Draft) |
| P27 | L3-2 에서 UR5 가 받침대가 아니라 원점에 있다(`base_frame_mismatch`, `tool0_from_pedestal_m=2.458`, `pin_failed`). 픽 0/3 을 두 번 재현했다. 9/17 수정 `f796210` 은 효과가 없었다 | master01 실습11 ④ | `sim`(SIM-9 2단계) | 진단 #322(머지), 수정 #324(Draft) |

## 다음 실습에서 확인할 것

- P27: SIM-9 2단계 뒤 `base_pose` = 받침대, `tool0_from_pedestal_m` < 1.2, `pin_failed` 0줄, 그리고 픽(9/20 15-21시 통합 슬롯).
- 화면 버튼으로 같은 대본, 창 배치, 묶음 중 보충이 끼는 경우(9/21 리허설).
- manifests PR 의 `evidence.py validate` 결과와 머지.
