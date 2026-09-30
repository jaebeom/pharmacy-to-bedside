# 실습12 — master02, UR5 받침대 수정(#324) 뒤 RC-2 재실행

| 항목 | 값 |
| --- | --- |
| 번호 | 실습12(계획표). 아래 12c 는 같은 목적의 재실행이다 |
| 날짜·시각 | 2026-09-20. 3회차 09:05-09:11:06, 12c 09:27-09:32:21(KST) |
| 장소 | `master02`(IsaacSim07), **headless** |
| 돌린 사람 | `master02` 원격 실행(기동·중지)과 읽기 전용 관측 |
| 출처 | master02 관측 보고. 원문은 `master02` `$HOME/markle_tmp/m2-rc2/rc2_obs_20260920T0911.md`(저장소 밖) |
| 기록 | 이 기록은 `master02` 화면을 직접 보지 않고 썼다 |

## 목적

P27 을 수정 #324(SIM-9 2단계) 뒤에 다시 본다. UR5 가 받침대가 아니라 원점에 서는 문제이고, [실습11](practice-11.md) ④ 에서 드러났다.

절차는 [L3 팔·인식 runbook](../runbooks/l3-arm-perception.md) 의 RC-2 다. "먼저 볼 것" 네 줄은 #326 이 적었다.

## 구성

| 부분 | 값 |
| --- | --- |
| 트리 | HEAD `644ec0a`. 커밋 안 한 변경 0. #324 가 들어 있다 |
| 트리 확인 | 워크트리 `/home/rokey/Dev/cobot3_ws/release/20260920-644ec0a`, sha `644ec0aa1e4d1404da05b54e2b15bfd3bc45b73f`. #322(`13a2dfd`)·#326 도 포함. `644ec0a` 는 `main` 에 있다(#330 머지 커밋, 2026-09-19T23:48:34Z) |
| 빌드 | exit 0, 7 packages, 12.1 s |
| 자산 | M0609 `m0609_gripper.usd` sha256 `b4879c8319851a23828c562dc9dc4f5018ddfcbfde9b082c6ce5547eff19ebeb` |
| 원본 | `master02` `$HOME/markle_tmp/m2-rc2/`: `rc2.log`(1.2 MB), `rc2.typescript`+`rc2.timing`(`scriptreplay` 재생 가능), `build.log`, 관측 기록 `rc2_obs_20260920T0911.md` |
| 명령 | `pharmacy_stage.py --mode selfdemo --ur5 --loop 3 --duration 300 "${P3_ASSETS[@]}" --headless`. 런카드 원문에서 바꾼 인자는 없다(`--headless` 만 더했다) |
| 끝 | `exit=0`, `dispensed=1`, `rtf=0.983` |
| 종료 줄 | `stop reason=duration updates=17690 wall_s=300.007 loop_hz=58.97 sim_s=294.833 rtf=0.983 dispensed=1 render_products=1 ur5=on`. 종료 뒤 프로세스 0개, VRAM 183 MiB(실행 전 182) |

## 관측 (master02)

### P27 은 해소됐다 — runbook "먼저 볼 것" 네 줄 모두 통과

| 볼 것 | 값 |
| --- | --- |
| prim 위치 쓰기 | `prim_translate set_ok=True composed_world=[3.2500, 0.5500, 0.4500]` |
| `pin_check` | readback = written |
| `ur5 ready` | `base_pose=[3.2500, 0.5500, 0.4500]` |
| `tcp_source` | `difference_m=0.0000`, `tool0_from_pedestal_m=0.839`(기준 1.2 m 아래) |
| `base_frame_mismatch`·`pin_failed` | **0줄** |
| 준비 단계 | `step=… ok` 10개 모두 ok. `FAILED`·`ERROR`·`Traceback`·`physics_view` 0줄 |

9/20 1·2회차(실습11 ④)의 원점 결함과 `ik_failed` 195줄은 재현되지 않았다.

### 집기는 여전히 실패 — 실패 모양이 바뀌었다

| 항목 | 값 |
| --- | --- |
| `suction on` | 0 |
| `suction miss` | 22 |
| `TIMEOUT` | 29 |
| `ik_failed` | 1(실습11 ④ 는 195·278) |
| `placed` | 5회 모두 `in_slot=False` |
| `off_belt` | 0줄 |
| `placed` pouch 좌표 | 매회 벨트 위 그대로(z 0.7550 고정) |
| `off_belt` | 0줄. `belt note=` 는 `stop_belt` 1줄뿐, `dispensed=1`. 벨트 점유가 안 풀려 `ur5 deck full slots=5; parking carried pouches []` |
| 접촉 | `contact` 4133줄 가운데 UR5·Belt·Pouch 가 든 줄 **0개**. UR5 가 봉투에 닿은 적이 없다 |

첫 실패와 그 앞(`rc2.log` 줄 번호):

```text
651 ur5 pick order_id=ord-0001 pick=[2.8055, 0.9926, 0.7550] deck_slot=1
652 ur5 phase=above_pouch target=[2.8055, 0.9926, 0.8200] steps=447 tcp=[4.0672, 0.7415, 0.4439]
923 ur5 TIMEOUT phase=above_pouch error_m=0.0647
925 ur5 phase=touch target=[2.8055, 0.9926, 0.7600] steps=30 tcp=[2.8535, 1.0359, 0.8202]
973 ur5 TIMEOUT phase=touch error_m=0.0715
982 ur5 phase=suck  target=[2.8055, 0.9926, 0.7600] suction=on steps=60 tcp=[2.8602, 1.0379, 0.7678]
983 ur5 suction miss distance=0.0717 limit=0.04
```

- 축 분해(뺄셈): `above_pouch` Δ=[+0.0480, +0.0433, +0.0002], `touch` Δ=[+0.0547, +0.0453, +0.0078]. **z 는 사실상 0 이고 오차가 x·y 평면에만 있다.**
- 2바퀴째부터 `above_pouch` 는 시작 tcp 가 `ur5_ready=[3.05, 0.55, 1.0]` 와 같고 `steps=179`, `error_m` 0.2906·0.2923·0.2925·0.2941·0.2307 로 반복한다.
- `reached` 로 끝난 phase 는 suck·drop·ready 셋인데 suck·drop 은 `kind=hold` 라 제자리에서 시한을 채운 것이고, 진짜 도달은 `ready`(`error_m=0.0005`) 하나다.

캡처·녹화: 없다. **왜 없는가**: `--headless` 로 돌아 화면이 없다. 실행 쪽 Isaac 셸이 `env -i` 라 `DISPLAY` 가 없어 창을 띄울 수 없었다. 관측은 읽기 전용이라 별도 뷰포트를 띄우지 않았다. 대신 `rc2.typescript`+`rc2.timing` 이 있어 `scriptreplay` 로 터미널을 재생할 수 있다(`master02` 로컬).

## 12c — 진단 인자(#346)로 재실행

| 항목 | 값 |
| --- | --- |
| 트리 | `release/20260920-eba5351`(sha `eba53519faad997e36cb0c54ea3a725e5a42ea29`, #346 머지). 위 3회차의 `644ec0a` 와 **다른 트리**다. porcelain 0줄, 재빌드 exit 0, 7 packages 11.8 s |
| 명령 | `--mode selfdemo --ur5 --loop 3 --duration 300 --ur5-contact-log --headless` |
| 런카드에서 바꾼 것 | 둘. `--ur5-contact-log`(#346 진단 인자, 기본 꺼짐, 이 회차에서 켬. 로그만 늘고 동작은 그대로), `--headless` |
| 시각·도메인 | 09:27:12-09:32:23, `ROS_DOMAIN_ID=117` |
| 끝 | `exit 0`. `stop reason=duration updates=17695 wall_s=300.007 loop_hz=58.98 sim_s=294.917 rtf=0.983 dispensed=1 render_products=1 ur5=on contact_watch=on` |

관측:

- 핀 검사 네 줄은 3회차와 같다(`pin_failed`·`base_frame_mismatch` 0줄, `tcp_source difference_m=0.0000`).
- **결과가 3회차와 똑같이 재현된다.** `suction on` 0, `suction miss` 22, `TIMEOUT` 29, `ik_failed` 1, `placed` 5(모두 `in_slot=False`)로 개수가 같고, `placed` 의 `sim_time` 도 70.783·124.833·179.500·235.117·277.683 으로 소수점까지 같다. pouch 좌표도 같다. #346 은 진단만 더했고 동작은 바꾸지 않았다.
- **`ur5 ik_check` 29줄이 모두 `solved=True`** 다. IK 는 매번 해를 찾는다.
- 남는 것은 명령 관절각과 실제 관절각의 차이(`max_joint_diff_rad`)다. worst 관절은 shoulder_lift 23건, shoulder_pan 6건이고 손목 3축은 한 번도 worst 가 아니다.
- TCP 잔차가 관절 부족분과 맞는다(계산, 받침대에서 목표까지 반지름 0.627 m): `above_pouch` 0.1032 rad × 0.627 = 0.0647 m(보고된 `error_m` 0.0647), `touch` 0.1143 × 0.627 = 0.0717(보고 0.0715), `lift` 0.1034 × 0.627 = 0.0649(보고 0.0648).
- 부족분은 두 크기로 갈린다. 작은 것 0.085-0.114 rad(5 s 를 다 써도 줄지 않는 정상상태 오차), 큰 것 0.92-1.57 rad(`shoulder_pan want 4.0240 have 2.4580` 처럼 90° 넘게 요구. 관절 한계는 넘지 않는다).

- **UR5 링크 접촉이 처음 관측됐다**(`--ur5-contact-log`). touch 183건이다: forearm↔`Belt/Surface` 54(최대 impulse 40.52), upper_arm↔`DeckSlot3WallYPlus` 21, upper_arm↔`DeckSlot4WallYPlus` 18(19.32), upper_arm↔`Room/Wall_belt_before` 15(34.37), forearm↔`Wall_belt_above` 8, upper_arm↔`Pedestal` 3(17.95, sim 11.383 부터 `sep=-0.0000`). UR5↔UR5 는 0건이다.

- **`TIMEOUT` 29개는 전부 접촉이 있다. `reached` 8개는 전부 접촉이 없다.** `kind=tcp` phase 37개, 예외는 없다(master02 로그 대조).
  - 셈: TIMEOUT 쪽은 phase 당 touch 3-13건, reached 8개는 ready 6 + 5바퀴 deck 3 이고 전부 0건이다.
- **`forearm_link` 가 벨트 끝 모서리에 걸린다.** 2-5바퀴 touch phase 의 첫 접촉이 매번 같은 점이다: `at=[2.950, 0.875, 0.714]`, 상대는 `Belt/Surface`.
  - 근거: impulse 39.65·39.47·39.46·40.52. 벨트 기하(`belt_start=(1.35, 1.0, 0.75) length=1.6 width=0.25 thickness=0.1`)로 보면 x 2.95 는 벨트 먼 끝, y 0.875 는 UR5 쪽 가장자리, z 는 슬래브 안이다.
- 1바퀴 deck 쪽은 `Wall_belt_before`(upper_arm·wrist_2·wrist_3, 최대 34.37), 2-4바퀴 deck 쪽은 상판 칸 벽(`DeckSlot2-4 Wall*`), 6바퀴 벨트 쪽은 `Wall_belt_above` 다.
- 접촉 건수는 2 s 스로틀 때문에 하한이다.

해석(미검증): IK 는 풀리는데 관절이 그 해에 못 간다. 같은 회차에 환경 접촉이 관측됐다. 구동력이 모자란 것인지 기하로 막힌 것인지는 아직 갈리지 않았다. 위 phase×접촉 대조는 물리적 막힘 쪽 그림과 맞는다. 실습12d(`--ur5-base 3.25 0.55 0.80` 한 개만 바꾼다)로 가른다. `--phase-timeout-s`·`--ur5-tcp-speed` 변경은 뒤로 미뤘다. 정상상태 오차와 큰 이동의 시한 초과도 원인이 다를 수 있다.

캡처·녹화: 없다. **왜 없는가**: `--headless` 로 돌아 화면이 없다. `master02` 에 계정 `rokey` 가 쓸 수 있는 X 디스플레이가 없기 때문이다(`:0` 은 gdm 소유 로그인 화면, 03:00 부팅 뒤 데스크톱 로그인 이력 없음, GDM 자동 로그인 미설정(12c 시점. `master02` 는 10:23 에 적용됐다), Xvfb·VNC 계열 미설치. `master02` 에서 확인). 대체 증거로 `rc2c.log` 와 터미널 녹화 `rc2c.typescript`+`rc2c.timing` 을 남겼다(`scriptreplay -t rc2c.timing rc2c.typescript` 로 재생). 재범이 로그인하면 같은 명령을 창 모드로 한 번 더 돌려 영상을 채우기로 했다.

## 12d·12e — 받침대를 옮기고, ready 까지 올려 본 재실행

`master02` 관측. 기준 로그 `$HOME/markle_tmp/m2-rc2e/rc2e.log`, 자원 표본 60 s 주기.

| 회차 | 바꾼 인자 | 화면 | 시각 |
| --- | --- | --- | --- |
| 12c | (없음, 진단 인자 #346 만) | 헤드리스 | 09:27-09:32 |
| 12d | `--ur5-base 3.25 0.55 0.80` | 헤드리스 | 10:26-10:30 |
| 12d-v | 12d 와 같은 인자 | 창 모드 | 10:34-10:36 |
| 12e | 12d + `--ur5-ready 3.05 0.55 1.35` | 헤드리스 | 11:06:57-11:12, `--duration 300` |

### 12d 단독 기록 — 받침대만 올렸다

- 트리 `$HOME/Dev/cobot3_ws/release/20260920-eba5351`, sha `eba53519faad997e36cb0c54ea3a725e5a42ea29`(#346). 12c 와 같은 트리, 재빌드 없음. `ROS_DOMAIN_ID=118`, M0609 `$HOME/cobot3_ws/isaacpjt/M0609`.
- 명령: `--mode selfdemo --ur5 --loop 3 --duration 300 --ur5-contact-log --ur5-base "3.25 0.55 0.80" --headless`
- **런카드 RC-2 원문에서 바꾼 것 3개**: `--ur5-contact-log`(#346 진단), `--ur5-base "3.25 0.55 0.80"`(**동작 인자 1개 변경**. z 0.45 → 0.80), `--headless`. 스크립트 주석에도 같은 문장이 적혀 있다.
- 10:25:31 시작 - 10:30:42 종료. 종료 줄 `stop reason=duration updates=17930 wall_s=300.012 loop_hz=59.76 sim_s=298.833 rtf=0.996 dispensed=1 render_products=1 ur5=on pick_notices_ignored_ur5=0 gripper_bool_ignored=0 contact_watch=on`
- 핀 1-4 통과: `prim_translate set_ok=True composed_world=[3.2500, 0.5500, 0.8000]`, `tcp_source difference_m=0.0000 tool0_from_pedestal_m=0.839`, `base_frame_mismatch` 0줄.
- 개수: `suction on` **0**, `suction miss` 16, `TIMEOUT` 29, `ik_failed` **0**, `placed` 4(`in_slot=True` 0), `off_belt` 0. `ik_check` 29줄 전부 `solved=True`.

**실패 모양이 12c 와 다르다.**

| | 12c | 12d |
| --- | --- | --- |
| `ready` phase | 5회 전부 도달 | **4회 전부 TIMEOUT**(0.0676·0.0677·0.1100·0.1006) |
| `upper_arm`↔`Deck/DeckSlot*` | 80건 | **0건** |
| `upper_arm`↔`Pedestal` | 3건(최대 17.95) | **65건(최대 161.94)** |
| `upper_arm`↔`Wall_belt_before` | 15건(34.37) | **65건(150.45)** |
| touch 합계 / 최대 impulse | 183 / 40.52 | 197 / **161.94**(9배) |
| elbow 부호 뒤집힘 | 0건 | **4건**(deck 쪽 `lower` 3, `above_slot` 1) |
| `max_joint_diff_rad` | 0.0848-1.5666 | 0.3327-3.2772 |
| worst 1위 빈도 | shoulder_lift 23, pan 6 | shoulder_lift 20, pan 6, **elbow 3** |

- `ready` 가 전부 실패한 것은 **인자 교란이다**: `--ur5-ready` 가 월드 절대 좌표라 base 를 올리자 base→ready 거리가 0.585 → 0.283 m 로 같이 줄었다. 12e 가 ready 를 함께 올려 이 교란을 가린다.
- phase × touch: `kind=tcp` 29개가 전부 TIMEOUT 이고 전부 touch>0 이다. **도달한 tcp phase 가 0개라 상관의 한쪽만 확인된다.**

캡처·녹화: 12d 본 회차는 **없다**(`--headless`). 직후 **12d-v**(10:34-10:36)가 **실화면 창 모드**로 같은 인자를 돌았다.

**그 회차는 영상 녹화에 실패했다.** `rc2dv.mp4` 가 **0 바이트**이고 `gst.log` 에 `MIT-SHM X_ShmGetImage BadMatch` 가 남아 있다. 한 프레임도 기록되지 않았다.

**시각 증거는 캡처 PNG 2장뿐이다**: `$HOME/markle_tmp/m2-rc2dv/shots/p12dv-live-103604.png`(262,068 B, `2d076171…`)·`p12dv-live-103608.png`(265,353 B, `003f3a61…`), 둘 다 1440×900. 스크립트 캡처 4장도 처음에는 0 바이트였고 셸 전개 오류(`${XID:+…} ${XID:-…}`)를 고친 뒤 이 2장이 **수동으로** 확보됐다.

원인은 **`remote=true` 누락**이다(`ximagesrc` 의 MIT-SHM 경로를 끄는 옵션).

`use-damage=0` 은 원래 스크립트에 있었고 그것만으로는 안 됐다. 10:36 에 같은 Isaac 창에 `remote=true` 로 5초 시험 녹화를 해 **925,227 B mp4 정상 생성**을 확인했고 11:09 에 스크립트를 고쳤다.

0 바이트 `rc2dv.mp4` 는 **실패 증거로 보존한다**(삭제하지 않는다).

그 파일의 sha256 `e3b0c442…b855` 는 **빈 파일의 해시**라 **해시 자체가 0 바이트임을 증명한다.** 그 PNG 의 UR5 영역을 4배 확대해 본 묘사: 상완이 받침대 윗면에 얹힌 것이 아니라, **어깨가 받침대 위에서 뒤로 꺾여 팔꿈치가 뒤편 벽에 거의 닿은 Z 자 자세**이고 상완-어깨 이음부가 받침대 모서리와 벽 사이 틈에 낀 모양이다. **다만 이 뷰로는 "윗면에 닿음" 과 "모서리에 끼임" 을 가르지 못한다**(뷰가 멀고 위에서 비스듬하다). 받침대 옆·수평 근접 캡처를 다음 창 모드 회차에 지시해 뒀다.

**정정: 문서가 관측 원문과 어긋나 있었다. 같은 사실에 원문과 2차 정리가 둘 다 있으면 원문이 기준이다.**

#240 의 12d-v 보고(9/20 12:33 게시)에는 처음부터 이렇게 적혀 있었다: "gst 녹화 **실패**(`rc2dv.mp4` 0 바이트, `ximagesrc` MIT-SHM `BadMatch`). 스크립트 캡처 4장도 실패, 수동 2장 확보".

문서는 그 원문이 아니라 **나중의 파일 목록 정리**에서 쓰였다. **파일 목록만 보고** 크기를 확인하지 않았고(20:2x 정정), **재료를 넘길 때** #240 의 그 줄을 함께 가리키지 않았으며, 문서를 쓸 때도 원문과 대조하지 않았다.

위의 캡처 2장은 스크립트가 아니라 **수동으로 확보한 것**이다. `master02` 에서 `ximagesrc` 로 녹화하려면 `remote=true` 가 필요하다(실행 중 확인, #240 원문).

**9/20 `master02` 회차의 영상 증거는 없다** — 12d-v 가 유일한 시도였고 실패했다. 다만 **위 4배 확대 묘사의 근거는 처음부터 PNG 이지 영상이 아니므로** 그 단서("이 뷰로는 윗면 접촉과 모서리 끼임을 못 가른다")는 그대로 유효하다.

산출물(`$HOME/markle_tmp/m2-rc2d/`, sha256 앞 16자): `rc2d.log` 1,477,788 B `dc2c3b509d8b0fa5`, `rc2d.timing` 69,776 B `c52c4bbdb0620eed`, `rc2d.typescript` 1,484,622 B `0a93c04e3c766c35`, `run_rc2d.sh` 1,189 B `79c8f1444bedae75`. 저장소에는 넣지 않는다(크기). 전체 sha256 의 정본은 `master02` 의 `$HOME/markle_tmp/inventory-20260920.txt` 다. **2026-09-20 21:22:57 시점 7,761 B, sha256 `9b5e23bd…3a51e` 다. 회차가 붙으면 또 갱신된다.** 12:46:24 시점 값이던 7,627 B `621bca0d…b886` 은 12d-v 녹화 실패 표시가 들어가며 바뀐 것이다. 12d 네 파일을 따로 계산해 인벤토리 값과 일치함을 확인했다. `master02` 의 `$HOME` 은 `/home/rokey` 이고 심볼릭 링크가 아니다(같은 확인).

**ready 를 같이 올려도 elbow 부호 뒤집힘은 그대로다.** `ik_check` 에서 `want` 와 `have` 의 부호가 반대인 항목이 12d·12e 모두 4건이고, **바퀴·phase 까지 같은 자리**에서 난다.

| 바퀴·phase | 12d want → have (diff) | 12e want → have (diff) |
| --- | --- | --- |
| 1바퀴 `lower` | +0.9177 → -1.7806 (+2.6984) | +0.9177 → -1.7806 (+2.6984) |
| 2바퀴 `lower` | +1.1675 → -1.6408 (+2.8083) | +1.1676 → -1.6138 (+2.7814) |
| 3바퀴 `above_slot` | +1.5468 → -1.7303 (+3.2772) | +1.5467 → -1.7478 (+3.2945) |
| 3바퀴 `lower` | +1.2048 → -1.0119 (+2.2167) | +1.2046 → -1.0155 (+2.2201) |

- `want` 가 소수점 3자리까지 같다. 4건 모두 `want` 양수 · `have` 음수이고 **전부 deck 쪽 phase** 다. **ready 자세 교란을 걷어내도 남는다.**
- 12c 는 elbow 항목 16건 전부 `want` 와 `have` 가 같고(`diff ±0.0000`) 뒤집힘이 0건이다. 받침대를 옮긴 뒤에만 나온다.
- **elbow `have` 가 양수인 경우는 12c·12d·12e 통틀어 0건**이다(12e 범위 -1.9388 에서 -1.0155).
- 셈의 한계: `worst[...]` 는 상위 3개 관절만 찍으므로 elbow 가 4위 이하였던 줄은 빠진다(elbow 등장 12c 16회, 12d 20회, 12e 13회).

### `ready` phase 는 부분 회복했고, 걸리는 관절이 바뀌었다

| 회차 | 바퀴 | `ready` 도달 |
| --- | --- | --- |
| 12c | 5바퀴 완주 + 6바퀴 중단 | 5/5 |
| 12d | 4바퀴 | 0/4 |
| 12e | 3바퀴 완주 + 4바퀴 중단 | 1/3 |

12e 의 시도가 3회인 것은 **바퀴 수 때문**이다. `ur5 pick` 은 4회 있었고 4바퀴째가 `lift` 까지 가다가 `--duration 300` 으로 끊겼다. 중간에 죽거나 건너뛴 것이 아니다.

```
1바퀴 ready TIMEOUT 0.3881  maxΔ=1.4011
  worst[wrist_3_joint: want 0.9937 have 2.3948 diff -1.4011, wrist_1_joint: want 0.7484 have -0.5078 diff +1.2562, shoulder_lift_joint: want -0.6450 have 0.2872 diff -0.9322]
2바퀴 ready TIMEOUT 0.3938  maxΔ=1.5377
  worst[wrist_3_joint: want 0.9933 have 2.5310 diff -1.5377, wrist_1_joint: want 0.7477 have -0.3854 diff +1.1331, shoulder_lift_joint: want -0.6450 have 0.2878 diff -0.9328]
3바퀴 ready reached 0.0005   (도달했으므로 ik_check 줄 없음)
```

실패한 두 번은 1위가 `wrist_3_joint` 다. 12c·12d 에서 worst 1위로 거의 안 나오던 관절이다(12c 빈도 shoulder_lift 23·pan 6, 12d shoulder_lift 20·pan 6·elbow 3). **ready 를 올리자 어깨 대신 손목이 걸린다.**

### phase × 접촉 대조는 세 회차 모두 예외가 없다

| 회차 | 전체 phase | `kind=tcp` (TIMEOUT / reached) | `kind=hold` | 예외 |
| --- | --- | --- | --- | --- |
| 12c | 48 | 37 (29 / 8) | 11 | 0건 |
| 12d | 37 | 29 (29 / 0) | 8 | 0건 |
| 12e | 30 | 23 (22 / 1) | 7 | 0건 |

`kind=tcp` phase 에서 TIMEOUT 이면 touch>0, 도달했으면 touch=0 이다. 다만 **12d 는 도달한 tcp phase 가 0개라 한쪽만 확인됐다.** 12e 의 도달 1건은 3바퀴 `ready`(touch 0건)다. 접촉 건수는 쌍마다 2 s 스로틀이 걸려 있어 하한이다.

### 12e 만 느리다 — 사람이 띄운 GUI 때문은 아니다

| 회차 | 시각 | GPU util | VRAM | Isaac RSS | load1 | rtf / loop_hz |
| --- | --- | --- | --- | --- | --- | --- |
| 12c | 09:27-09:32 | 14-45 % | 2329 MiB | 4.8 GB | 2.5-5.4 | 0.983 / 58.98 |
| 12d | 10:26-10:30 | 45-54 % | 2400 MiB | 4.8 GB | 2.8-5.4 | 0.996 / 59.76 |
| 12e | 11:07-11:11 | 100 %(표본 5개 전부) | 2855 MiB | 4.8 GB | 3.5-4.5 | 0.788 / 47.27 |

- 이 표의 `rtf`(12c·12d·12e)는 **`master02` 로그 기준**이다.
  - `master01` 회차(12f-12m)의 값은 `stop reason=` 줄로 **전수 대조**했고 문서 값과 전부 일치한다. 12c·12d 의 로그는 `master01` 에 없어 그쪽에서는 확인되지 않았다 — **기계가 다르기 때문이고, 틀렸다는 뜻이 아니다**("미확인" 이 아니라 "관측 범위 밖"이다).
- **사람이 띄운 Isaac GUI 와는 겹치지 않는다(확정).** 12e 는 11:06:57-11:12 다(`rc2e.typescript` 첫 줄, `rc2e.log` mtime). 사람의 Isaac 은 12:33:34 다. 사이는 1시간 21분이다.
  - 근거: 자원 표본에서 `isaac_rss` 가 그때 0.01 → 5.30 GB 로 튄다. 그 사이 구간은 `isaac_rss 0.01` 로 Isaac 이 하나도 떠 있지 않았다.
- 남는 관측: **12e 구간에만 GPU 가 100 % 로 포화**됐다. 또 10:23:43 에 자동 로그인으로 `rokey` 데스크톱 로그인이 올라온 뒤(적용 경위는 [실습15](practice-15.md)) 유휴 GPU 부하가 0 %(09:26, 183 MiB)에서 25-30 %(11:06, 194 MiB)로 상시 올라갔다. 다만 12d 도 그 뒤에 돌았는데 rtf 0.996 이므로 데스크톱만으로는 설명되지 않는다. **원인은 조사 중이다.**

캡처·녹화: **12e 는 없다.** **왜 없는가**: `--headless` 로 돌았고(`"headless": true`, `"view": "none"`, `"livestream": false`) Xvfb 도 걸지 않았다(`run_rc2e.sh` 에 `DISPLAY`·Xvfb 줄 0건). 이 시점에는 실화면 창 모드가 이미 가능했으므로 **기술적 제약이 아니다** — 바로 앞 12d-v(10:34-10:36)가 창 모드로 돌았다. **그 회차는 녹화에 실패했고 캡처 2장만 남았다**(위 12d 절). 12c·12d 와 `render_products`·`loop_hz`·`rtf` 를 나란히 놓으려고 헤드리스를 유지한 것으로 보이나, 회차 의도는 확인이 필요하다. 대체 증거는 `rc2e.log` 와 터미널 녹화 `rc2e.typescript`+`rc2e.timing` 이다(`scriptreplay -t rc2e.timing rc2e.typescript`).

## 12f — 받침대 단면을 줄여 본 A/B (master01)

**12 계열이 `master01` 로 옮겨 간 첫 회차다.** `master02` 를 팀원이 콘솔에서 쓰고 있어 기계를 바꿨다. 기계가 다르므로 아래 `rtf`·`loop_hz` 는 12c-12e 표와 나란히 놓지 않는다.

master01 로그 추출(12c-12e 와 같은 스크립트, 로그 sha256 대조 일치) + master01 보고.

| 항목 | 값 |
| --- | --- |
| 기계·도메인 | `master01`, 117 |
| 트리 | 워크트리 `../release/20260920-1585a91`(tree `1585a91`). `selfdemo` 라 colcon 빌드 없이 `sim/` 직접 실행. `release 45d7fe3` 워크트리는 porcelain 0 유지 |
| 화면 | 실화면 창 모드 `DISPLAY=:1`, `--headless` 없음. 기동 전 남의 Isaac·GPU 프로세스 0 |
| A | 12:56:54-13:02:17. `--mode selfdemo --ur5 --loop 3 --duration 300 --ur5-contact-log --ur5-base "3.25 0.55 0.80" --ur5-ready "3.05 0.55 1.35" --view ur5` = **`master02` 12e 의 재현** |
| B | 13:02:59-13:08:14. A + **`--ur5-pedestal-size "0.10 0.10"`**. B 로그에만 `ur5 pedestal_size=[0.1000, 0.1000] default=[0.3, 0.3] (diagnostic)` |
| 종료 줄 | A `updates=17832 wall_s=300.006 sim_s=297.200 rtf=0.991`(`loop_hz` 59.44) / B `updates=17781 wall_s=300.017 sim_s=296.350 rtf=0.988`(59.27) |

**관문 줄은 A·B 가 같다. #324 이후 `master01` 첫 통과다.** `pin_failed`·`base_frame_mismatch` 0건이다.

원문: `prim_translate set_ok=True composed_world=[3.2500, 0.5500, 0.8000] pedestal=[…같음]`, `pin_check … base_link_resets_xform_stack=False … written=readback`, `tcp_source fk_tool0=[4.0672, 0.7415, 0.7939] difference_m=0.0000 tool0_from_pedestal_m=0.839 (tcp uses fk)`, `world_joints count=1 articulation_root=True`, deck_slots `[2.980|3.140|3.300|3.460|3.620, 0.050, 0.470]`.

### 기둥은 원인이었다 — 접촉이 사라지고 도달이 는다

| touch 쌍 | A (건수/최대 impulse) | B |
| --- | --- | --- |
| upper_arm↔`Pedestal` | **74 / 160.38** | **0** |
| upper_arm↔`Wall_belt_before` | 38 / 146.90 | 8 / 52.66 |
| forearm↔`Belt/Surface` | 41 / 19.93 | 20 / 12.40 |
| upper_arm↔`Belt/Surface` | 25 / 11.85 | 48 / 14.73 |
| forearm↔`Pedestal` | 0 | 16 / 8.42 |
| forearm↔`Wall_belt_above` | 0 | 13 / 10.24 |
| forearm↔`Wall_belt_before` | 0 | 2 / 10.04 |
| wrist_3↔`Wall_belt_above` | 17 / 6.78 | 0 |
| wrist_3↔`Wall_belt_before` | 12 / 8.13 | 0 |
| wrist_2↔`Wall_belt_before` | 5 / 1.54 | 0 |
| wrist_2↔`Wall_belt_above` | 4 / 4.32 | 0 |
| wrist_1↔`Wall_belt_before` | 4 / 0.44 | 0 |
| **합계** | **220 / 160.38** | **107 / 52.66** |

- **도달이 느는 것은 deck 쪽이다. `touch` 는 A 0/5, B 0/6 이다.** 합계 **A 11/28 → B 33/21**.
  - phase 별 reached/TIMEOUT(분모는 그 phase 가 시작된 횟수. 300 s 로 끊겨 바퀴 수가 phase 마다 다르다) A → B: `above_pouch` 0/5 → 1/5, **`touch` 0/5 → 0/6**, `lift` 0/4 → 1/5, `above_slot` 0/4 → **5/1**, `lower` 0/4 → 2/4, `retreat` 0/4 → **6/0**, `ready` 2/2 → **6/0**. `suck`·`drop` 은 `kind=hold` 라 제자리에서 시한을 채운 것이고 도달로 세지 않는다.
- 집계 A → B: pick 5 → 7, `ik_failed` **로그 0줄 → 2줄**, `suction on` **0 → 0**, `suction miss` 18 → 24, `placed` 4 → 6, `in_slot=True` **0 → 0**.
- **벨트 쪽은 그대로 막혀 있다.** `touch` phase 는 A 0/5, B 0/6 으로 둘 다 한 번도 도달하지 못했다. 좋아진 것은 deck 쪽(`above_slot`·`retreat`·`ready`)이다.
- phase×touch 상관: A 는 예외 0건. **B 에는 예외 2건**이 있다(2·6바퀴 `above_slot` 이 `reached` 0.0004·0.0006 인데 touch 1건씩). 12c-12e 의 "예외 없음" 이 B 에서 깨진다.
- B 의 `ready` 6회는 **전부 deck 쪽 출발**([2.98-3.62, 0.0500, 0.820], reached 0.0000-0.0003)이다. A 는 벨트 쪽 출발 2회가 TIMEOUT(0.3881·0.3938), deck 쪽 출발 2회가 reached 였다. **"벨트 쪽이 고쳐졌다" 로 읽으면 안 된다** — 출발 자리가 달랐다.

### elbow 부호 뒤집힘은 원인이 아니라 결과였다

- A 4건(1바퀴 `lower` +0.9177/-1.7806, 2바퀴 `lower` +1.1676/-1.6138, 3바퀴 `above_slot` +1.5467/-1.7478, 3바퀴 `lower` +1.2046/-1.0155) → **B 0건**(elbow 항목 21개 전부 `want ≈ have`).
- elbow `have` 가 양수인 경우는 A·B 모두 0건이다(A 범위 -2.0165 에서 -1.0155, B 는 -2.1329 에서 -1.4509).
- `max_joint_diff_rad` A 0.5052-3.2945(n=28) → B 0.0477-2.1346(n=21). worst 1위 빈도 A shoulder_lift 18·pan 5·elbow 3·wrist_3 2 → B shoulder_lift 20·pan 1.
- B 의 벨트 쪽 `ik_check` 는 전부 `solved=True` 인데 **`shoulder_lift` 가 0.18 rad 근처에 붙박인다**: 2바퀴 `above_pouch` 0.8045 → 0.1903, `touch` 0.9163 → 0.1863, `lift` 0.8045 → 0.1831, 3-5바퀴 `touch` 0.917-0.920 → 0.186. 1바퀴만 0.9154 → 0.8098 로 따라간다. elbow·pan 의 차이는 0.03 이하다.
- **붙박이는 구간에 벨트 접촉이 끊기지 않는다.** upper_arm↔`Belt/Surface` 48건은 벨트 쪽 네 phase 에만 있다. `above_slot` 이후는 0건이다(`12f-b.log` 를 phase·`sim_time` 으로 쪼갠 결과).
  - 셈: `above_pouch` 12 · `touch` 16 · `suck` 4 · `lift` 16, 2-5바퀴 각 3·4·1·4. 4바퀴 예: `above_pouch` TIMEOUT 0.3763(sim 157.5-161.6) `count=`3259 → `touch` TIMEOUT 0.4512(163.5-169.6) 3723 → `suck` 3843 → `lift` TIMEOUT 0.3813(173.6-179.6) 4301. impulse 는 11.6-14.7 로 일정하다.
- **1바퀴에는 upper_arm↔`Belt/Surface` 가 0건**이다(forearm↔`Belt/Surface` 3건만, `touch` 구간, 최대 12.40). 그 바퀴만 `shoulder_lift` 가 0.8098 까지 따라갔고 `touch` 오차도 0.0723 이었다.
- 나머지 배치: forearm↔`Belt/Surface` 20건은 `above_pouch` 12 · `touch` 8. upper_arm↔`Wall_belt_before` 8건은 `above_slot` 5 · `lower` 2 · 그 외 1(3바퀴 `above_slot` TIMEOUT 0.8523 구간에 4건, 최대 26.99. `lower` 에서 52.66). forearm↔`Pedestal` 16건은 `lower` 12 · `drop` 4 로 벨트 쪽에는 0건. 6바퀴는 forearm↔`Wall_belt_above` 11건.
- **읽기: 상관이지 인과가 아니다.** 판정 틀(정체 중에 접촉이 있으면 기하, 이동 구간에만 있으면 드라이브)로는 기하 쪽으로 읽힌다. 1바퀴는 출발 TCP 가 낮아 접촉도 없고 도달도 한 것일 수 있다 — **12g 가 가른다**(가른 결과는 아래 12g-12j 절).
  - 단서: 건수는 2 s 스로틀의 하한이고 지속의 근거는 `count=` 다. 캡처의 "B 는 공중에 서 있다" 는 한 프레임(13:05:42)이다. 다른 읽기는 "벨트 쪽 실패는 전부 `solved=True` 라 IK 가지가 아니라 관절이 그 값으로 안 가는 것" 이다.
- `suction miss` 는 `distance=<값> limit=0.04` 형식이다(`target=` 필드 없음). A 18건 0.3473-1.1160, B 24건 중 1바퀴 세 건만 0.0771·0.0771·0.0669 이고 나머지 21건은 0.34-1.24 다. **0.04-0.07 사이는 A 에 0건**이다.
- `ik_failed` **2줄**은 B 의 deck 쪽이다: `phase=above_slot target=[3.1493, 0.5822, 1.0473] count=1`, `… target=[3.2608, 0.4561, 0.9934] count=60`.
  - **`count=60` 은 그 phase 에서 IK 가 60회 이상 잇따라 실패한 것이다.** 로그는 첫 번째와 60의 배수마다 찍힌다. 줄 수와 횟수는 다르다.
  - 근거: `sim/standalone/pharmacy_stage.py:1680-1684`(tree `07b9771`(#371 머지) 이후. 그 뒤로 이 파일은 안 바뀌어 지금 main 에서도 같다). 회차가 돈 `1585a91` 에서는 1675-1679 였다. #371 이 5줄을 밀었다.
  - 1680 은 `target` 이 직선 보간 중간점이라는 근거다. 1682-1683 이 ThrottledLog 호출이다. throttle 동작 자체는 `sim/standalone/p3sim/common.py:71-80`(코드 확인)에 있다.
  - 12c 의 `ik_failed` 1 도 같은 읽기(로그 1줄)다.
  - `target=` 은 phase 의 목표가 아니라 **phase 시작 TCP 에서 목표까지 직선 보간의 중간점**이다. `ready`(y 0.55)에서 deck 칸(y 0.05)으로 가는 직선이 받침대 위를 지나 base 바로 위 좌표가 찍혔다. **코드 결함이 아니다.** 보간도 Lula 도 환경을 모른다는 것이 증상의 배경이다.

### `deck full` 계수 결함

`placed` 가 B 6건(칸 1·2·3·4·5·1)인데 **봉투는 벨트 끝 자리 그대로**다(A 마지막 `[2.8131, 0.9952, 0.7550]` sim 273.833, B 마지막 `[2.8136, 0.9954, 0.7550]`). `in_slot=False` 인데도 칸이 찬 것으로 세고 있다. **계수 결함으로 확정한다**.

### A 는 `master02` 12e 와 값이 같다 — 기계 간 결정론 1회 관측

- elbow 뒤집힘 4건의 `want`·`have` 가 소수 **넷째 자리까지** 같다.
- `ready` 실패 `error_m` 0.3881·0.3938 이 같다. `max_joint_diff_rad` 범위 0.5052-3.2945 가 같다.
- touch 쌍별 최대 impulse 160.38·146.90·19.93·6.78·8.13·1.54·4.32·0.44 가 같다(upper_arm↔`Belt/Surface` 만 11.85 대 11.75).
- 건수는 다르다(12e 는 `rtf` 0.788 로 느렸다). **1회 관측이라 결정론은 미확인이다.**

### 캡처 판독 — 12d-v 의 "가르지 못한다" 를 닫는다

`--view ur5` 로 같은 카메라·화각에서 찍은 `shots/a-loop-125944.png` 와 `shots/b-loop-130542.png` 를 나란히 놓고 읽었다.

- **A 는 굵은 회색 기둥 윗면 모서리에 상완이 걸쳐 있다**(팔꿈치가 기둥 윗면 바로 위). B 는 기둥이 가늘고 팔 전체가 기둥 옆·위 공중에 서 있어 상완이 어디에도 얹히지 않는다.
- A 는 어깨·상완이 왼쪽 흰 벽면보다 앞(카메라 쪽)이고 팔꿈치가 벽 모서리 근처다. B 는 팔이 벽면보다 오른쪽·뒤라 겹치지 않는다. "앞/뒤" 는 **이 한 각도에서의 상대 위치**다.
- 두 장 다 deck 의 파란 칸 다섯이 비어 있고 봉투를 들고 있지 않다. A 하단에만 배너 `getSimulationTimeMonotonicAtTime: no data found for time 9048/30, returning current sim time` 가 있다(그 순간 화면 이야기다. 로그로는 **A·B 각 12건**이고 stage·kit 수가 같다. 오늘 `ur5=off` 회차 7개는 0건이라 **UR5 회차에만 난다** 까지가 관측이고, 시연 경로와는 무관해 보인다).
- 영상 관측(master01): 팔이 내려앉는 것이 아니라 **버티다 못 가는** 쪽이다.
- **따라서 위 12d·12e 절의 "이 뷰로는 윗면에 닿음과 모서리에 끼임을 가르지 못한다" 는 닫힌다: A 는 윗면 모서리에 걸쳐 있다.**

캡처·녹화: **있다.** `master01` `$HOME/markle_tmp/p12f/`(저장소 밖): `rec-a.mp4` 4,532,817 B(`a7c70e3f…`), `rec-b.mp4` 4,416,847 B(`b07f75f6…`), 캡처 45장(`SHA256SUMS` 의 sha256 `63b811b1…`), 로그 `12f-a.log` 1,518,591 B(`3455133b…`)·`12f-b.log` 1,599,538 B(`ce807ed0…`)·`kit-a.log`(`a77e26af…`)·`kit-b.log`(`387d5d5a…`). 경로는 그 디렉토리 기준 상대경로다. 정리 뒤 프로세스 0, tmux 는 이름으로 `kill-session`, VRAM 309 MiB.

### 판정과 남는 것

확정된 것: **기둥은 원인이었다**(upper_arm↔`Pedestal` 74/160.38 → 0, 전체 최대 impulse 160 → 52.7). **elbow 가지 뒤집힘은 원인이 아니라 결과다**(A 4 → B 0, 시드 다중화 후보는 보류). **`deck full` 계수 결함**. **기계 간 결정론은 1회 관측이라 미확인.**

남는 것(해석, 미검증): **`ready` 에서 출발하면 벨트 쪽 접근이 안 풀린다. 기둥을 치워도 `touch` 는 0 이다**(A 0/5·B 0/6, `suction on` 0).

근거와 제외: 실습12(base 0.45·ready 1.0)에서도 1바퀴만 벨트 쪽 잔차 0.065-0.072 였고 2바퀴부터 0.23-0.38 이었다. 받침대는 Lula 모델에 없는데 B 에서만 `ik_failed`·`max_joint_diff` 가 달라진 것은 "막히지 않아 다른 관절 상태에 도달해 시드가 바뀌었다" 는 자료로 본다(미검증). `--end-zone` 은 계산으로 후보에서 뺐다(줄이면 벨트 끝면 통과 높이 +0.050 → +0.024).

다음 회차 **12g**: `--ur5-ready "4.0672 0.7415 0.7939"`(기동 자세의 TCP, base 에서 0.839 m), 나머지는 12f B 그대로, C 한 회차(대조군 = 12f B). **풀리면 TCP 위치 문제, 안 풀리면 관절 자세(시드) 문제다.**

**뒤에 밝혀진 것**: 위 "상관이지 인과가 아니다" 는 **기하가 원인이었다**로 닫혔다. 12g 에서 경로를 없애니 붙박임과 접촉이 같이 사라졌고, 12i·12j 에서 기둥을 줄이고 낮추니 접촉이 0건이 되며 놓기가 3/3 이 됐다(아래 절).

## 12g-12j — 한 회차에 자유 변수 하나씩, 그리고 첫 온전한 한 바퀴

`master01`, 도메인 117, 실화면 창 모드 `DISPLAY=:1`, `--view ur5`, `selfdemo`(빌드 없음). 회차마다 ffmpeg 녹화 1개 + 캡처가 있고 **headless 회차는 없다.** `release 45d7fe3` 워크트리는 porcelain 0 을 유지했다. **한 회차에 자유 변수 하나, 대조군은 직전 회차**다.

| 회차 | 시각 | 트리 | 더한 인자 | 결과 한 줄 |
| --- | --- | --- | --- | --- |
| 12g(C) | 13:19:49-13:25:20 | `1585a91` | `--ur5-ready "4.0672 0.7415 0.7939"` | 집기 **1회 성공**(P29 이후 처음) |
| 12h(D) | 13:36:07-13:41:29 | `1585a91` | `--ur5-base "3.25 0.55 0.90"` | 집기 **3/3**, 놓기 **0/3** |
| 12i(E) | 13:49:59-13:55:18 | `1585a91` | `--ur5-pedestal-size "0.02 0.02"` | **기둥 확정**, 안착 1/3 |
| 12j(F) | 14:02:54-14:08:14 | **`07b9771`** | `--ur5-pedestal-height 0.45` | **집기 3/3 + 안착 3/3** |

12j 만 트리가 다르다(`07b9771` = #371 머지 커밋, 워크트리 `../release/20260920-07b9771`). `1585a91..07b9771` 의 차이는 `sim/` 의 `ur5_cell.py`·`pharmacy_stage.py`(+5줄)·시험 세 파일뿐이고 **`src/`·`tools/` 는 0** 이다(`git diff --stat` 을 세 번 따로 확인). 관문 줄은 네 회차 모두 통과했다(`prim_translate set_ok=True`, `pin_check` readback 일치, `pin_failed`·`base_frame_mismatch` 0건, `tool0_from_pedestal_m=0.839`).

**전부 진단 인자이고 기본값은 하나도 바뀌지 않았다.** 기본 배치와 흡착 툴 모델링은 재범 결정이다.

### 12g — `ready` 를 기동 자세로 되돌렸더니 한 번 집었다

- **`touch` 는 5바퀴에서 처음 도달했다.** P29 이후 첫 집기이고 1회다.
  - 5바퀴는 reached 0.0006 → `ur5 suction on distance=0.0050` → `ur5 placed deck_slot=5 in_slot=True pouch=[3.6198, 0.0504, 0.4630] sim_time=235.517` 이다.
  - 1-4바퀴는 TIMEOUT 이다. 6바퀴는 TIMEOUT 0.4176 이다.
- **막히는 자리가 7 cm 로 좁혀졌다.** 1-4바퀴 정체 TCP 는 `touch` 목표 `[2.8055, 0.9926, 0.7600]` 기준 dz +0.0712·+0.0764·+0.0717·+0.0663 이고 dx·dy 는 0.012 이하다. **목표보다 7 cm 위, `above_pouch` 높이(0.820)에서 못 내려간다.** 12f B 는 `[2.840, 0.92, 1.19]` 에서 dz +0.43-0.45 였다.
- **`shoulder_lift` 붙박임이 사라졌다**: have 0.808-0.820(12f B 는 0.182-0.192). `suction miss` 18건 중 12건이 0.0661-0.0816 으로 문턱 근처까지 왔다(1-4바퀴 앞 세 번씩).
- **접촉은 합계가 아니라 바퀴별로 본다.** upper_arm↔`Belt/Surface` 30건 중 **29건이 6바퀴**다(1-5바퀴는 1건).
  - UR5 touch 바퀴별은 9/11/8/19/8/**43** 이다. **성공한 5바퀴만 `touch`·`suck`·`lift` 접촉이 0건**이다.
  - 대조: 실패한 1-4바퀴는 `touch` 구간에 forearm↔`Belt/Surface` 가 3건씩 있다(impulse 12.15-12.60). 5바퀴의 wrist_3↔`Pouch_00` 6건(`above_slot` 4·`lower` 1·`above_pouch` 1)은 impulse 0.00 으로 **봉투를 물고 가는 접촉**이라 막는 접촉이 아니다.
- **합계로 읽어 한 번 틀렸다**: 12f B 107 → 12g 105 만 보고 "접촉은 원인이 아니었다" 고 읽었다가 철회했다. 바퀴별로 보면 1-5바퀴가 8-19 건이고 6바퀴만 43건이다.
- **6바퀴는 별개로 본다.** 시작 tcp 가 기둥 밑동이다(`[3.0526, 0.6400, 0.0727]`).
  - `ready` 는 0/5 다. deck 에서 기동 자세로 가려면 **`shoulder_pan` 227°** 가 필요해 시한 안에 못 돈다(출처: `ik_check phase=ready solved=True max_joint_diff_rad=3.9729 worst[shoulder_pan: want 0.0998 have 4.0727 …]`. TIMEOUT 1.5358·1.5357·1.5357·1.4721·1.2490).
  - 5바퀴 `ready` 실패 뒤 `ur5 deck full slots=5; parking carried pouches [0]` 이 찍히고도 6바퀴가 `deck_slot=1` 로 또 집으러 간다(P32 ③ 의 증거 줄이다).
  - **`ready` 실패가 만든 것인지 `deck full` 뒤에 계속 도는 것인지는 같이 일어나 못 가른다.** 6바퀴의 접촉은 forearm·wrist_1·wrist_2↔`Pedestal` at.z 0.06-0.15 이고, `ik_check` 는 elbow want +0.90 / have -0.65--0.83(뒤집힘 3건)·`shoulder_lift` -3.64--3.71 로 다른 해다.
- `ur5 placed` 는 **시도 줄**이다. 앞 네 건은 `in_slot=False pouch=[2.80xx, 0.993x, 0.7550]` 로 집으러 간 자리 그대로다. `ik_failed` 로그 2줄은 둘 다 성공한 5바퀴의 `above_slot`(count 1·60)이다.
- 종료 줄: `updates 17812 sim 296.867 rtf 0.990`, 6바퀴.

### 12h — 받침대를 10 cm 올리니 집기는 3/3, 놓기가 0/3

`--ur5-base` z 를 0.80 → 0.90 으로 올렸다(접근각 11.6° → 20.1°, 계산값). `--clearance` 는 M0609 보충 계획과 공유하는 인자라 후보에서 뺐다.

- **집기 3/3.** `touch` reached 0.0089·0.0080 · TIMEOUT 0.0117(정체 dz +0.0087·+0.0078·+0.0115), **`suction on` distance 0.0138·0.0129·0.0166, `miss` 0**.
- **흡착이 진짜인지 판정선을 결과 전에 고정했다**: "distance 가 0.01 근처가 아니면 문턱에 걸린 흡착으로 본다". 계산으로 **distance = `touch` dz + 0.005(봉투 중심↔윗면)** 가 세 건 다 0.1 mm 안에 맞아 **진짜 흡착**으로 수락됐다.
- **놓기 0/3 이다. 봉투 둘은 바닥이다.**
  - 칸1 은 상판 위·칸 밖이다: `placed deck_slot=1 in_slot=False pouch=[2.9576, 0.0207, 0.4950] sim 50.350`.
  - 칸2·칸3 은 바닥이다: `deck_slot=2 … [3.1066, -0.0993, 0.0050] sim 90.233`, `deck_slot=3 … [3.3023, -0.2034, 0.0050] sim 134.067`.
- `above_slot` 은 3/3 도달(0.3 mm 이하)인데 **`lower` 가 하강 도중 -y 로 밀린다**(TIMEOUT 0.0524·0.1416·0.1723). 놓은 자리는 `[2.9582, 0.0235, 0.5126]`·`[3.1016, -0.0332, 0.5810]`·`[3.2868, -0.0589, 0.6058]` 로 칸 윗면 0.470 보다 **5-14 cm 위**다. **칸이 기둥(x 3.25)에 가까울수록 단조롭게 나빠진다.**
- 미는 것은 자기 받침대다: forearm↔`Loading/Pedestal` 26건 중 `lower` 가 10건(바퀴별 3·4·3, impulse 8.00·8.44·7.79, `count` 240·360·240 틱 연속, at.z 0.584-0.631). `lower` 의 `ik_check` 는 `solved=True` 이고 elbow·pan 차이는 0.0005 이하인데 **`shoulder_lift` 가 1.3335·1.3418·1.3195 에 붙박인다**(want 1.40·1.54·1.56).
- **시연 경로와는 무관하다.** 시연은 `ur5=off`(`--preset demo-ros-refill-v2`, 트리 v0.3.0)이고 이것은 `selfdemo` 의 UR5 놓기 구간이다. 시연 회차(13b·13c·14p 등)에 같은 현상은 없다.
- 철회·정정 둘: "y 는 `above_slot` 이 남긴 것이고 바퀴마다 누적된다" 는 읽기는 위 표로 철회됐다. 첫 추출("`pedestal_size` 줄 없음, UR5 touch 0건")은 오류였고 전수 재확인으로 정정됐다 — master01 보고 값이 맞다(UR5 touch 37 = `Pedestal` 26 + `Wall_belt_before` 6 + `Belt/Surface` 5. 전부 3바퀴이고 1·2바퀴는 0건인데 그 둘만 `touch` reached).
- `ready` 0/3, 쓰러진 바퀴 없음, `ik_failed` 0. rtf 0.993, 3바퀴. 관문은 전부 z 0.9000, `fk_tool0` z 0.8939, 받침대도 0.9000.

### 12i — 고치는 회차가 아니라 가르는 회차

받침대 단면을 `0.02 0.02` 로 줄였다. **0.05 는 음성일 때 해석이 갈리지 않아 0.02 를 골랐다.** 판정 틀을 결과 전에 고정했다: `Pedestal` 접촉이 줄고 새 쌍이 안 생기고 붙박임이 풀리면 **기둥 확정**, 다른 쌍이 대신 나오면 단면으로는 못 품, 그대로면 기둥 아님.

**틀 ① 기둥 확정.**

- `lower` 의 `Loading/Pedestal` 3·4·3 → **0**·3·3(impulse 10.23·10.31), 전체 26 → 14, UR5 touch 37 → 25.
- **자리바꿈이 없다**: `base_link`·`shoulder_link`·`upper_arm`·wrist 계열·UR5 끼리 전부 `count=0`.
- `shoulder_lift` have 1.33 → 1.4522·1.4477 로 붙박임이 풀리고, `lower` 오차가 **reached 0.0007**·0.0623·0.0812 로, 놓은 자리가 목표 쪽으로 4.4-7.4 cm 돌아왔다(dy/dz +0.0001/-0.0002 · -0.0390/+0.0452 · -0.0553/+0.0592).
- **1바퀴는 한 바퀴 안에 집기 + 안착을 했다**: `placed deck_slot=1 in_slot=True pouch=[2.9804, 0.0484, 0.4630] sim 45.550`. 칸2 는 `[3.1215, 0.0077, 0.4950]`(상판 위), 칸3 은 `[3.3777, -0.1200, 0.0050]`(바닥)이다.
- 집기는 12h 와 소수 **넷째 자리까지** 같다(`suction on` 0.0138·0.0130·0.0165, distance - dz = +0.0051 ×3). 접촉대 at.z 는 0.6060-0.6150 이다.
- **단면만으로는 끝까지 못 간다**: 팔 스윙 평면이 베이스 축을 지나기 때문이다(`UR5_DH` 의 j2·j3 은 d=0). 그래서 다음 변수는 **높이**다.
- `Pedestal` 이라는 이름이 둘(레일 캐리지에도 있다)이라 **경로를 붙여 셌고** 섞이지 않은 것을 확인했다.

### 12j — 집기 3/3 + 안착 3/3, Isaac 에서 첫 온전한 한 바퀴

받침대 높이를 0.45 로 낮췄다(#371, 재범 14:01 머지). **판정선 8개를 결과 전에 고정했고 전부 충족됐다.**

1. `lower` 의 `Loading/Pedestal` 0·0·0 이고 **회차 전체가 0건**이다(UR5 touch 11 = forearm↔`Belt/Surface` 5 + forearm↔`Wall_belt_before` 6).
2. `lower` reached 0.0007·0.0007·0.0006, `drop` 0.0002·0.0009·0.0008, **`in_slot=True` 3/3**: `deck_slot=1 pouch=[2.9804, 0.0484, 0.4630] sim 45.550`, `deck_slot=2 [3.1403, 0.0486, 0.4630] sim 80.933`, `deck_slot=3 [3.3011, 0.0483, 0.4630] sim 120.350`. 놓은 자리 오차가 세 바퀴 다 **0.2 mm 안**이고 `ik_check phase=lower` 는 0줄이다.
3. `touch` reached 0.0089·0.0081 · TIMEOUT 0.0119, `suction on` 0.0138·0.0130·0.0169, `miss` 0, distance - dz = +0.0051·+0.0051·+0.0050.
4. 새 접촉 쌍은 전부 `count=0`.
5. 관문은 그대로(z 0.9000).
6. `ur5 pedestal_height=0.4500 base_z=0.9000 gap=0.4500 (diagnostic: the stand no longer reaches the robot, which is fixed to the world)`.
7. `pedestal_size [0.0200, 0.0200]`.
8. `Deck/DeckPlate`·`DeckSlot` 접촉 0건(전례는 12g 의 wrist↔`DeckPlate` 9건뿐).

rtf 0.994, 3바퀴, `ik_failed` 0.

**단서 셋. 이것을 "풀렸다" 로 읽으면 안 된다.**
- **`ready` 0/3**(1.5361·1.5361·1.5362)이다. **연속 운전이 아니다.**
- 칸 1-3 까지만 봤다.
- 이 구성의 UR5 는 **기둥 위 0.45 m 에 떠 보인다**(캡처 `12j-00-pedestal-low`). 보기에 맞는 배치가 아니라 원인을 가르려고 만든 구성이다.

### 상충과 남는 것

**집기와 놓기가 서로 반대 방향을 요구한다**. 집기(목표 z 0.760)는 어깨가 높을수록 좋고, 놓기(z 0.473)는 더 깊이 내려가야 하는데 그 길에 **자기 받침대**가 있다. 실측으로도 base z 0.80 은 집기 1/5·놓기 1/1 이고 0.90 은 집기 3/3·놓기 0/3 이다. 12i·12j 는 **"base z 는 높게 두고, 받침대가 그 부피를 차지하지 않게"** 로 그 상충을 풀었다.

남는 것은 [P31](#문제)로 따로 뗀다: `ready` 실패(`shoulder_pan` 227°. 12h 에서는 forearm↔`Wall_belt_before` 6건이 전부 `ready` 구간 at.z 0.853-0.873), "팔이 쓰러진다", `deck full` 계수 결함.

### 산출물

`master01` `$HOME/markle_tmp/p12f/`(저장소 밖). 경로는 그 디렉토리 기준 상대경로다.

| 회차 | 로그 | kit 로그 | 녹화 | 캡처 `SHA256SUMS` |
| --- | --- | --- | --- | --- |
| 12g | `12g-c.log` 1,610,669 B `6401676f…` | `kit-12g-c.log` 3,506,265 B `80d58203…` | `rec-12g-c.mp4` 4,812,692 B `9d6e098d…` | `d591f745…`(2바퀴 지정 캡처는 `12g-loop` 이름으로만 남음) |
| 12h | `12h-d.log` 1,385,639 B `d3fdbdd4…` | `kit-12h-d.log` 3,206,127 B `51ef6e50…` | `rec-12h-d.mp4` 4,168,222 B `2fd4c1f8…` | `60c83fa1…`(`12h-lap1/2` 의 `above_pouch`·`touch`) |
| 12i | `12i-e.log` 1,441,972 B `0a6c1281…` | `kit-12i-e.log` 3,280,178 B `81877199…` | `rec-12i-e.mp4` 4,203,686 B `67a0f6de…` | `b8480556…`(`12i-00-pedestal`, `12i-lap1/2/3`) |
| 12j | `12j-f.log` 1,382,157 B `abf1eb38…` | `kit-12j-f.log` 3,201,207 B `c13a462e…` | `rec-12j-f.mp4` 4,062,248 B `cc8a6833…` | `a0be9839…` |

12i 부터는 추출이 `extract_all.sh` 고정 묶음이고, 합계 한 줄을 master01 보고 값과 먼저 대조한 뒤 적었다.

### 이 회차들에서 굳은 읽는 법 넷

1. **`ur5 placed` 는 시도 줄이다.** 성사는 `in_slot=` 과 `pouch=` 좌표로 본다.
2. **접촉은 합계가 아니라 바퀴별·phase 별로 본다.** 12g 에서 합계만 보고 한 번 틀렸다.
3. **`ik_failed` 는 줄 수다.** 횟수는 `count=`(누적)로 읽는다.
4. **흡착이 진짜인지는 `distance` = `touch` dz + 0.005 로 가린다.**

## 12k-12m — 연속 운전, 도달 한계, 그리고 성사 확인이 없다는 것

`master01`, 도메인 117, 트리 **`07b9771`**(`../release/20260920-07b9771`, `selfdemo` 라 빌드 없음), 실화면 창 모드 `DISPLAY=:1`, `--view ur5`, 회차마다 ffmpeg 녹화 1개 + 캡처. 공통 인자는 `--mode selfdemo --ur5 --ur5-contact-log --ur5-base "3.25 0.55 0.90" --ur5-pedestal-size "0.02 0.02" --ur5-pedestal-height 0.45` 다. 관문·진단 줄은 세 회차 모두 12j 와 같다(`pin_failed`·`base_frame_mismatch` 0). **자유 변수는 한 회차에 하나, 대조군은 직전 회차**다.

**거리 기준이 바뀌었다**(앞선 기준을 정정했고, 독립 계산으로 재현했다). 도달은 base 가 아니라 **어깨 `(3.25, 0.55, 0.989)`** 에서 place 목표 **`(칸 x, 상판 y, 0.473)`** 까지의 직선 거리이고, 한계는 **상완+전완 0.425 + 0.392 = 0.817 m** 다. 앞서 쓰던 "base 에서 0.85" 는 틀린 기준이다. 슬롯 prim 의 z 는 0.470 이고 drop 목표 z 는 0.473 이다.

| 회차 | 시각 | 더한 인자 | 결과 한 줄 |
| --- | --- | --- | --- |
| 12k(G) | 14:13:23-14:23:44 | `--ur5-ready "3.30 0.05 0.85"`, `--loop 6 --duration 600` | `ready` **6/6**, 칸1-4 연속 안착, 칸5 붕괴 |
| 12l(H) | 14:29:11-14:39:44 | `--deck-center "3.25 0.05 0.45"` | **다섯 칸 전부 안착 5/5** |
| 12m(I) | 14:44:32-14:49:59 | `--deck-center "3.25 0.20 0.45"`(딸린 값 `--ur5-ready "3.25 0.20 0.85"`), `--loop 5 --duration 300` | 놓기가 더 정확(76.3 % 에서 오차 0), 5바퀴부터 집기 실패 |

### 12k — `ready` 가 풀렸다. 연속 운전의 첫 관측이다

- **1바퀴는 내장 대조군이다.** 기동 자세에서 출발하므로 `ready` 변경과 무관해야 한다. `above_pouch` 출발 tcp `[4.0672, 0.7415, 0.8939]`, `touch` 0.0089, `suction` 0.0138, `lower` 0.0007, `drop` dy/dz +0.0001/-0.0002, `placed pouch=[2.9804, 0.0484, 0.4630]` — **여섯 값 전부 12j 1바퀴와 소수 넷째 자리까지 같다.**
- **P31 ① 이 인자로 풀렸다**: `ready` **6/6 reached**, error_m 0.0004·0.0004·0.0006·0.0004·0.0004·0.0004(12j 는 TIMEOUT 1.5361·1.5361·1.5362). 새 `ready` 자리 `(칸 x, 0.05, 0.85)` 는 `retreat` 가 팔을 놓고 가는 자리 옆이라 pan 을 거의 안 돌린다. 12g-12j 의 실패 원인이던 `ik_check phase=ready … max_joint_diff_rad=3.9729 worst[shoulder_pan: want 0.0998 have 4.0727]`(227°)가 12k 에는 아예 안 찍힌다 — **도달했으므로 `ik_check` 가 없고, 근거는 reached 0.0004 다.**
- 2바퀴부터 `above_pouch` 출발 tcp 가 `[2.8399, -0.1822, 0.7934]`(12j) → **`[3.3000, 0.0500, 0.8500]`** 으로 바뀌었는데 집기·안착은 그대로다. 걱정했던 **"12j 의 성공이 `ready` 실패 자세에 기대고 있었을 수 있다" 는 아니었다.**
- **칸1-4 연속 집기·안착**: `touch` reached 0.0089·0.0083, TIMEOUT 0.0126·0.0120 / `suction on` 0.0138·0.0132·0.0177·0.0169 / `lower` reached 0.0006-0.0007 / `in_slot=True` `[2.9804, 0.0484, 0.4630]`·`[3.1403, 0.0486, 0.4630]`·`[3.3013, 0.0481, 0.4630]`·`[3.4606, 0.0483, 0.4630]`. distance - dz 는 여섯 건 +0.0048-0.0051 로 흡착 판정선 안이다. 종료 줄 `updates 35758 sim 595.967 rtf 0.993 dispensed=6`.
- **칸5 는 도달 한계 근처에서 무너진다(98.9 %).** 어깨에서 목표까지 0.8082 m / 0.817 이다.
  - `above_slot` 은 reached 0.0004 다. `lower` 는 TIMEOUT 0.7404 다. `placed` 는 `in_slot=False pouch=[3.2362, 0.7321, 0.0050]` 다.
  - 셈: 분자는 어깨→`(3.62, 0.05, 0.473)`, 분모는 0.817 이다. 칸1-4 는 93.9·89.0·88.2·91.6 % 다.
  - 이상한 점: `above_slot` 의 `ik_failed` 2줄(`target=[3.1589, 0.6022, 0.8199] count=1`·`target=[3.2723, 0.4665, 0.8199] count=60`)은 **60회 넘게 실패하고도 도달했다**는 뜻이다. `lower` 에는 `ik_check` 가 없고, `drop` 은 reached 0.7404 다.
- **덜 내려간 것이 아니다. 팔이 base 옆 아래로 접혀 내려갔다.** 놓은 자리는 목표에서 dy +0.6135 / dz -0.2815 다.
  - `Loading/Pedestal` 접촉 at.z 0.332 는 기둥 윗끝(0.45)보다 0.118 m 아래다. 무너진 팔이 닿은 결과로 읽는다(미검증).
  - 원문: `persist touch forearm↔Loading/Pedestal impulse=3.80 at=[3.248, 0.646, 0.332] count=2891`(sim 144.65) → 3011 → 3131, 이어 `impulse=5.1172 at=[3.244, 0.654, 0.450] count=3243`(sim 150.65). **5.9초 지속됐다** — 스치듯 닿은 것이 아니다.
- 접촉 전체는 forearm↔`Belt/Surface` 14건(최대 10.22)과 위 `Loading/Pedestal` 4건뿐이다. `Wall_belt`·`Deck/DeckPlate`·`DeckSlot`·`base_link`·UR5 끼리는 0건이다.
- **안착한 봉투가 나중에 밀렸는지는 확인할 수 없다.** 로그로도(`count=0`) 캡처로도 안 된다 — 두께 1 cm 봉투가 파란 칸 바닥과 분간되지 않는다.
- 정정: 첫 보고 "`Pedestal` 0건" 은 12j 출력을 붙인 실수였고 전수 재확인으로 정정됐다. **대책으로 수치 옆에 회차 파일명을 적기로 했다.**

### 12l — 상판 중심을 base 에 맞추니 다섯 칸 전부 들어갔다

`--deck-center` 를 `[3.3, 0.05, 0.45]` → **`[3.25, 0.05, 0.45]`** 로 x 만 옮겼다. **튜닝이 아니라 대칭 맞추기**다(base x 가 3.25다). 슬롯 x 는 2.930·3.090·3.250·3.410·3.570 이 된다. **결과 전에 고정한 것**: 0/5 나 악화가 나와도 실패가 아니라 한계선 관측으로 본다, 대조군은 집기 쪽이다.

- 집기 대조군 통과: 1바퀴 `touch` 0.0089·`suction` 0.0138, 2-5바퀴 `suction` 0.0133·0.0177·0.0168·0.0162(12k 는 0.0132·0.0177·0.0169·0.0163), 1-5바퀴 `miss` 0.
- **5/5 안착**: `[2.9304, 0.0484, 0.4630]`·`[3.0904, 0.0486, 0.4630]`·`[3.2513, 0.0481, 0.4630]`·`[3.4106, 0.0483, 0.4630]`·**`[3.5703, 0.0486, 0.4630]`** 전부 `in_slot=True`. 놓은 자리 dx/dy/dz 는 다섯 칸 전부 0.3 mm 안이다.
- **96.3 % 의 계산**: 칸1·5 는 어깨→`(2.930|3.570, 0.05, 0.473)` = 0.7865 m / 0.817 이다(칸2·4 는 0.7361 = 90.1 %, 칸3 은 0.7185 = 87.9 %).
- **`lower` error_m 0.0008(칸1)·0.0007·0.0006·0.0007·0.0017(칸5)** — 96.3 % 인 두 칸만 다른 칸의 약 1.3-2.8배다. **경계는 96.3 % 와 98.9 % 사이에 있고, 좌우 비대칭은 없다.**
- `ready` 는 1-5바퀴 reached. `ik_failed` 는 5바퀴 `above_slot` count 1·60 으로 12k 와 같은데 **그 바퀴가 성공했다.** 1-5바퀴 접촉은 forearm↔`Belt/Surface` 뿐이다(`Pedestal`·`Deck`·`Wall_belt_before`·UR5 끼리 0).

### 12m — 상판을 앞으로 당기면 놓기가 더 정확해진다

`--deck-center "3.25 0.20 0.45"`(자유 변수는 "상판 위치")와 **딸린 값** `--ur5-ready "3.25 0.20 0.85"`, `--loop 5 --duration 300`. 예상 도달률은 85.8 %(칸1·5, 0.7008 m)·78.8 %(칸2·4, 0.6437)·76.3 %(칸3, 0.6235)다.

| 도달률 | `lower` error_m |
| --- | --- |
| 96.3 %(12l 칸1·5) | 0.0008 · 0.0017 |
| 85.8 %(12m 칸1·5) | 0.0006 · 0.0009 |
| 78.8 %(12m 칸2·4) | 0.0005 · 0.0008 |
| **76.3 %(12m 칸3)** | **0.0004. 놓은 자리 dx/dy/dz 0.0000/0.0000/0.0000** |

칸3 의 tcp 는 `[3.2500, 0.2000, 0.4730]` 으로 목표 그대로다. 칸1-4 는 `in_slot=True`(`[2.9303, 0.1984, 0.4630]`·`[3.0903, 0.1986, 0.4630]`·`[3.2512, 0.1981, 0.4630]`·`[3.4104, 0.1983, 0.4630]`), `ready` 는 1-7바퀴 reached, 1-4바퀴에 새로 닿는 것은 0 이다. 종료 줄 `updates 14698 sim 244.967 rtf 0.817 dispensed=5`.

**5바퀴부터 집기가 실패한다. 봉투 위치 탓이 아니다.**
- pick 좌표가 1-5바퀴 모두 12l 과 넷째 자리까지 같다(5바퀴 `ord-0001 [2.8035, 1.0279, 0.7550]`). **12l 은 같은 좌표에서 `touch` 0.0114 로 성공했고, 12m 은 TIMEOUT 0.0338 에 `miss` 0.0705·0.0705·0.0707·1.0996 이다.** 벨트 정지 프레임도 같다.
- **`Wall_belt` 접촉 41건이 5-8바퀴에만 있다**: 5바퀴 `above_pouch` TIMEOUT 0.0861 구간에 3건(sim 117.1-121.1, at.z 1.02), `touch` 3건(123.1-127.1), `suck` 1건, `lift` TIMEOUT 0.0781 구간에 3건(impulse 8.00).
- **벽에 걸려 못 내려간 것이다.** 첫 벽 접촉이 `touch` TIMEOUT 보다 10.7초 앞선다(sim 117.1 대 약 127.8).
  - 정체 TCP 는 목표에서 수평으로 이탈했다. `ik_check` worst 는 `wrist_1` 이다.
  - 값: 정체 TCP `[2.8303, 1.0076, 0.7564]` 대 목표 `[2.8035, 1.0279, 0.7600]` = dx +0.0268 / dy -0.0203 / **dz -0.0036**(z 는 거의 안 모자란다 — 그래서 수평 이탈이다). `wrist_1` want -4.1030 / have -4.2314.
- **왜 5바퀴부터인지는 미확인이다.** TCP 출발점은 2-5바퀴가 같다. 관절 자세(시드)가 바퀴마다 다를 수 있다는 읽기는 미검증이다.
- 정정: master01 보고의 "5바퀴 봉투 `[2.8262, 1.0072]`" 는 6바퀴 pick 좌표의 오기였다.

### P32 — UR5 집기·놓기가 성사 여부를 확인하지 않는다

네 가지가 한 문제다.

1. **흡착에 실패해도 놓기를 계속한다.** 12l 6바퀴: `above_pouch` TIMEOUT 0.0929, `touch` TIMEOUT 0.0482, `ur5 suction miss distance=` 0.1399·0.1399·0.1567·1.0345(limit 0.04) → 그런데 `lower` reached 0.0017 · `drop` reached → **`placed deck_slot=1 in_slot=False pouch=[2.7374, 1.0644, 0.7550]`**(봉투는 벨트 위 그대로). 원인은 `sim/standalone/p3sim/ur5_cell.py` 의 `suck()`(371-383)이 **거리를 넘으면 로그만 남기고 순서를 멈추지 않는** 것이다(코드 확인).
2. **`ur5 placed` 가 시도를 센다.** 12m 은 `placed` 7줄에 `in_slot=True` 4 다.
3. **`deck full` 뒤에도 멈추지 않는다. 12k 6바퀴는 이미 찬 칸1 에 겹쳐 놓았다.** `slots=5` 인데 실제로 찬 칸은 4개다. 12m 도 칸5 가 빈 채 `deck full` 이 찍힌다.
   - 겹쳐 놓았다는 근거: `placed deck_slot=1 in_slot=True pouch=[2.9810, 0.0481, 0.4630] sim_time=186.983` 이 1바퀴 봉투 `[2.9804, 0.0484, 0.4630]` 과 **0.6 mm** 차이다.
   - 원문 차례: `ur5 deck full slots=5; parking carried pouches [0, 1, 2, 3, 4]` → 바로 다음 줄 `ur5 pick order_id=ord-0002 pick=[2.8039, 1.0009, 0.7550] deck_slot=1`. 그 뒤 sim 187-596 에는 새 pick 이 없고 종료 직전 `ready reached … holding=False` 다. 12m 의 줄은 `deck full slots=5; parking carried pouches [0, 1, 2, 3]` 이다.
4. **집기에 실패한 봉투를 계속 다시 집으러 간다.** `--loop` 는 **배출 횟수만 센다**(`sim/standalone/pharmacy_stage.py:1710`). 실패한 봉투가 벨트에 남으면 새 배출 없이 그것을 또 집으러 가서 바퀴가 안 끊긴다 — 12m 은 `dispensed=5` 인데 pick 8회이고 6-8바퀴가 전부 같은 `ord-0001` 이다(pick `[2.8262, 1.0072]`·`[2.8280, 0.9861]`·`[2.7916, 1.0425]`). **설계대로이고 인자 결함이 아니다.** "5 를 주면 6·7바퀴가 안 생긴다" 던 앞선 예측은 정정됐다.
- 12l 7바퀴는 여기서 더 간다: `above_slot` 1.1552·`lower` 1.2069·`ready` 1.2614 TIMEOUT, `miss` 4건 1.8659, `placed deck_slot=2 in_slot=False pouch=[2.2000, -0.5500, 0.0050]`(**주차 자리 좌표**). 12l·12m 의 6바퀴 이후는 `deck full` 뒤라 1-5바퀴와 나눠 적는다.

### `rtf` 0.808·0.817 은 접촉 탓이 아니라 GPU 포화다

12l 종료 줄은 `updates 29091 wall 600.006 sim 484.850 rtf 0.808 loop_hz 48.48` 이다. 1분 간격 표본이 원인을 가른다.

| | GPU util | Isaac VRAM | GPU 총 | rtf |
| --- | --- | --- | --- | --- |
| 12f A·B-12k(일곱 회차) | 39-47 % | 2085-2092 MiB | 2464-2471 | 0.988-0.994 |
| **12l** | **94-97 %** | **2587-2594 MiB** | 2966-2973 | 0.808 |
| **12m** | **95 %** | **2587 MiB** | 2966 | 0.817 |

- **이 표는 "6·7바퀴 접촉 폭주 탓" 을 반증한다.** 12l 은 첫 표본부터 GPU 값이 고정이다. 무너진 6바퀴의 초당 접촉 줄도 평범하다.
  - 근거: 고정은 첫 표본 **14:30:04** 부터 끝까지다. 초당 접촉 줄은 바퀴별 19·22·25·19·19(12k) 대 19·21·25·19·18·20(12l)이다. load1(3.4-7.3 대 4.0-7.5)과 kit RSS 는 같아 다른 원인도 배제된다.
  - 그 추측은 이 표로 철회됐다.
- 다른 GPU 프로세스 0, 타 사용자 로그인 0, 렌더 인자 동일이다. **"기동 때 정해지는 무거운 렌더 상태" 를 확인하는 방법은 회차 첫 표본부터 끝까지 VRAM 이 한 값으로 고정되는 것**이다. 조제실 경로의 2055/2310 두 무리, `master02` 의 12d(52 %·2400 M·0.996) 대 12e(100 %·2855 M·0.788)와 같은 구조다.
- **물리 결과는 같다**(집기 값이 12k 와 넷째 자리까지). 시연 경로(`ur5=off`)는 무거운 쪽에서도 rtf 0.99 다.
- **결론을 붙이지 않는다.** 무리는 `deck_center` x 와 1:1 로 **맞는다**(대응은 관측된 사실이다). 기동 간격은 가르지 못한다.
  - 인과는 못 읽는다. 표본 9, 조건 칸 7 대 2 다. **x 와 시간 순서가 겹친다**(x 3.25 인 두 회차가 맨 끝의 연속 두 회차다). 기전이 없다.
  - 값: x 3.30 인 일곱 회차는 Isaac 몫 VRAM 2085-2092 MiB·util 39-47 %·rtf 0.988-0.994, x 3.25 인 12l·12m 은 2587-2594 MiB·93-97 %·0.808/0.817 이다(9회차 전수).
  - **기동 간격은 맞지 않는다**: 직전 Isaac 종료→기동 간격이 00:51-11:38 로 흩어져 있다(짧은 간격 5건 중 3건이 가벼운 쪽, 긴 간격 4건은 전부 가벼운 쪽). 지워진 것은 **간격**이고, "그 무렵 무언가 바뀌었다"(시간 흐름)는 지워지지 않았다.
  - **x 와 시간이 겹친다**: x 3.25 인 두 회차는 시간상으로도 맨 끝의 연속 두 회차(14:29 이후)다. 이 표로는 "x 가 조건" 과 "그 무렵 바뀌었다" 가 갈리지 않는다.
  - **기전이 없다**. 상판을 5 cm 옮기는 것으로 VRAM 이 500 MiB 늘 이유가 없다 — **형상 수·카메라·렌더 인자가 같다**(근거는 로그가 아니라 장면 구성이다).
    - **허수일 가능성이 높다**는 판단이 있다. 다른 해석("x 3.25 가 상판을 벽·벨트 쪽으로 당겨 생기는 부하")은 **미검증 가설**이고 이 판단과 나란히 둔다.
  - 추가 관측(확정 아님): 12l·12m 의 무거움은 **첫 표본부터** 2587 MiB·94 % 이고 상승 구간이 없다. 14:29 무렵 Isaac 밖의 변화(다른 GPU 프로세스, stack·web RSS)는 샘플러에 없고 회차 사이 GPU 는 매번 307 MiB 로 돌아왔다.
  - **가르는 회차의 첫째는 12k 인자를 한 번 더 도는 것이다.** 시간과 x 를 가른다. 시연 뒤, 미실행.
    - 인자는 `x 3.30, y 0.05` 그대로다(`_ops/72`, `_ops/32b`). 먼저 쓰던 구성을 나중 시각에 다시 돌리는 것이 요점이다.
    - **가벼우면 시간 흐름이 지워지고 x 가 남는다. 무거우면 x 가 아니다.** 그다음 순서는 x 3.25 반복 → x 3.30 + y 0.20 → `--no-hand-camera` 다.
  - 출처: 기동 `kit-*.log` 1행(UTC+9), 종료는 같은 파일 mtime, VRAM·util 은 1분 샘플러의 `gpu_procs`(compute-apps), rtf 은 각 회차 로그의 `stop reason=` 줄.
  - **철회**: 앞선 실수는 **조제실 경로 표**에서 났다. 그 표는 이 문단의 UR5 회차 표와 다른 자료다.
    - 이 문단의 첫 판에는 **"'기동 때 우연' 쪽은 지워졌다"** 라고 적혀 있었다. 표가 지운 것은 **간격**뿐이고 **시간 흐름은 남아 있으며 기전도 없다**(검토에서 지적됨). 1:1 만 보고 결론을 올린 것이라 위 세기로 고쳤다.
    - 조제실 경로 표에서는 **반례 둘만 보고 간격을 지웠고, 쪽수만 보고 "강한 경향" 으로 올렸다.**
    - **방향은 반대였지만 같은 잘못이다: 자료의 세기를 재지 않고 결론부터 붙였다.**
- 정정: "12f-12j 는 값이 비어 있다" 는 첫 보고는 회차 사이 표본을 본 실수였다.

### 산출물

`master01` `$HOME/markle_tmp/p12f/`(저장소 밖). 경로는 그 디렉토리 기준 상대경로다.

| 회차 | 로그 | kit 로그 | 녹화 | 캡처 `SHA256SUMS` |
| --- | --- | --- | --- | --- |
| 12k | `12k-g.log` 2,715,034 B `952e0d17…` | `kit-12k-g.log` 4,940,506 B `83c29c49…` | `rec-12k-g.mp4` 7,493,054 B `c873191f…` | `54a57257…` |
| 12l | `12l-h.log` 2,357,779 B `e4300803…` | `kit-12l-h.log` 4,481,396 B `97de9efa…` | `rec-12l-h.mp4` 6,401,043 B `b5746d2b…` | `46e3a193…`(종료 캡처는 `down` 전) |
| 12m | `12m-i.log` 1,415,823 B `67181433…` | `kit-12m-i.log` 3,256,189 B `82c1974d…` | `rec-12m-i.mp4` 4,035,496 B `93cd4847…` | `d09d2799…` |

12m 에는 `gpu-12m.csv` 208 B(`0f125b79…`)가 더 있다. **12k 의 `12k-99-end` 캡처는 무효다** — Isaac 이 닫힌 뒤라 파일 관리자 창이 찍혔다. 끝난 뒤 VRAM 307 MiB 기준선을 확인했다.

### 오늘 UR5 회차는 12m 으로 끊었다

12:57-14:50 에 아홉 회차(12f A/B-12m)를 돌았고 **한 번에 자유 변수 하나, 전부 진단 인자, 기본값 변경 0** 이다. 남는 것은 둘이다.

- **코드**: [P31](#문제)(한계 근처의 붕괴, 시드), [P32](#문제)(성사 여부를 확인하지 않는다).
- **재범 결정**: 기본 배치 넷 — base z, 받침대 모양, 상판 위치, 흡착 툴 모델링. 결정이 나면 #239에 번호로 남고, 기본값이 실제로 바뀌면 코드 PR 과 런카드에 적힌다. 이 문서에는 그때 "결정 N 에 따라 …" 한 줄을 더한다.

## 해석과 그 철회

- 받침대 고정(핀) 문제는 해소됐고, 실패 모드가 IK 도달 범위 문제에서 **TCP 수렴 실패**로 바뀌었다. [L3 팔·인식 runbook](../runbooks/l3-arm-perception.md) RC-2 표의 "#324 뒤 재실행 대기" 칸이 채워졌다.
- 처음 올린 가설 둘(flange 와 tool0 사이 상수 오프셋 누락, `steps > 300` 이면 보간이 시한을 못 넘김)은 **철회됐다.** 반례가 나왔다: 5바퀴째에 deck 쪽 phase 4개가 `error_m` 0.0001-0.0014 로 모두 도달했고(상수 오프셋이면 그럴 수 없다), `steps=359` 성공과 `steps=30` 실패가 함께 있다.
- 철회 뒤 남는 사실: 벨트 쪽 phase 4개는 6바퀴 모두 실패, deck 쪽은 바퀴마다 좋아져 5바퀴째에 모두 성공, `ready` 는 6바퀴 모두 성공이다. 바퀴별 표는 따로 보냈다(저장소 밖).

## 확인하지 않은 것

- `ros json topics pub=` 목록: selfdemo 라 해당 없음.
- `error_m` 허용치 기준: runbook 도 미확정이다.
- UR5 중간 궤적: 스테이지에 주기적 tcp 로그가 없어 못 봤다. UR5 는 phase 시작·종료 줄에서만 tcp 를 찍는다. `sim` 개선 요청으로 올렸다.

## 문제

| P | 내용 | 출처 | 고치는 쪽 | PR |
| --- | --- | --- | --- | --- |
| P27 | UR5 가 받침대가 아니라 원점에 선다 | 실습11 ④ | `sim` | 진단 #322(머지), 수정 #324(머지). **실습12 에서 해소 확인** |
| P29 | UR5 가 받침대에 선 뒤에도 벨트 끝 집기가 0/5 다. IK 는 풀리고(`ik_check` 29줄 모두 `solved=True`) 관절이 명령값에 도달하지 못한다(worst 는 shoulder_lift·shoulder_pan). TCP 잔차 0.065-0.072 m 가 관절 부족분과 맞고, 같은 회차에 팔↔환경 접촉 183건이 찍혔다 | master02 실습12·12c | `sim` | 진단 #346(머지). **원인은 기하로 확정**(12g·12i·12j). 12j 에서 집기 3/3 + 안착 3/3. 기본 배치는 재범 결정 대기 |
| P31 | 도달 한계 근처에서 팔이 무너진다. ① `ready` 미복귀는 **12k 에서 인자로 풀렸다**(`--ur5-ready` 를 `retreat` 자리 옆으로. 6/6 reached, error_m 0.0004) ② 남은 것은 **한계 근처의 붕괴**다 — 어깨 기준 98.9 % 인 칸5 에서 `lower` TIMEOUT 0.7404 뒤 팔이 base 옆 아래로 접히고(`placed … pouch=[3.2362, 0.7321, 0.0050]`), 12m 5바퀴부터는 `Wall_belt` 에 걸려 집기가 안 된다(첫 벽 접촉이 TIMEOUT 보다 10.7 s 앞섬). 같은 출발점인데 바퀴마다 갈리는 이유는 미확인(시드 가설, 미검증) | master01 12g-12m | `sim` | 아직 없음 |
| P32 | **UR5 집기·놓기가 성사 여부를 확인하지 않는다.** ① 흡착에 실패해도 놓기를 계속한다(`ur5_cell.suck()` `sim/standalone/p3sim/ur5_cell.py:371-383` 이 거리를 넘으면 로그만 남기고 순서를 안 멈춘다) ② `ur5 placed` 가 시도를 센다(12m `placed` 7줄에 `in_slot=True` 4) ③ `deck full` 뒤에도 멈추지 않아 **이미 찬 칸에 겹쳐 놓는다**(12k 6바퀴, `slots=5` 인데 실제로 찬 칸은 4개) ④ 집기에 실패한 봉투를 계속 다시 집는다(`--loop` 는 배출 횟수만 센다. `sim/standalone/pharmacy_stage.py:1710`. 설계대로이고 인자 결함은 아니다) | master01 12k-12m | `sim` | 아직 없음 |

## 다음 실습에서 확인할 것

- P29 는 닫혔다(기하). 남는 것은 **기본 배치와 흡착 툴 모델링을 어떻게 둘지**이고 재범 결정이다. 12g-12j 는 전부 진단 인자이고 기본값은 바뀌지 않았다.
- P31 의 남은 것(한계 근처의 붕괴, 바퀴마다 갈리는 이유)과 P32 네 가지.
- `rtf` 두 무리: **12k 인자 그대로 한 번 더 돌려 시간과 x 를 가른다**(첫째 회차). 기동 간격은 아니다(위). 시연 뒤다.
- 재범 로그인 뒤 창 모드 재실행으로 영상 채우기.
