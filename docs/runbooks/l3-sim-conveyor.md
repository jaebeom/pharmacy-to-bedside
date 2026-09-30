# L3 런카드 — 조제실 벨트·UR5·관측 opt-in·병원 씬

> **상태: 지난 기록 (2026-09-23 기준).** 지금은 [병원 한 바퀴 런카드](hospital-full.md)를 따른다.

런카드는 Isaac 에서 한 장씩 돌리는 확인 절차다. RC-1 부터 RC-4 까지다.

- 성격: **실행 계획이다.** 이 문서는 명령과 볼 줄, 판정 기준을 적는다. 관측 결과는 이슈 #240(슬롯·관측) 댓글과 `evidence/runs/` 기록에 남기고, 여기에는 링크만 둔다.
- 대상: 마스터에서 Isaac 을 돌리는 사람. 9/19–20 에 들어간 시뮬 변경을 Isaac 에서 확인한다.

| 카드 | 무엇 | 상태 |
| --- | --- | --- |
| RC-1 | 시연 경로 회귀(`demo-ros-refill-v2`) | 9/20 tree `419b20b` 에서 2회 관측(1회차, 2회차). 아래 확인 줄 두 개는 미확인 |
| RC-2 | 벨트 끝 UR5 픽(`--ur5`, selfdemo) | 1–4 통과. 집기 0/5 |
| RC-3 | 새 관측 opt-in(`--belt-observation`·`--belt-fail-closed`·`--gripper-command-seq`) | 미실행 |
| RC-4 | 병원 씬 이식 smoke(`hospital-v2`) | 미실행 |

## 0. 공통

- 셸: [sim README](../../sim/README.md) 「0.5단계 절차 0」의 `P3_REPO`·`P3_DOMAIN`·`M0609` 와 `P3_ISAAC_ENV`·`P3_ASSETS` 배열이 정본이다.
- 기록할 것:
  - `git -C "$P3_REPO" rev-parse HEAD`
  - 로그 첫 두 줄: `[pharmacy_stage] preset=… resolved_args={…}` 와 `[pharmacy_stage] scene base_usd=… base_usd_sha256=… meters_per_unit=… up_axis=…`
  - 종료 줄: `stop reason=… dispensed=… ur5=… pick_notices_ignored_ur5=… gripper_bool_ignored=…`
- 준비 판단: 단계마다 `step=<이름> ok` 가 찍힌다. `FAILED` 가 하나라도 있으면 그 줄이 결과다.
- **좌표 인자는 따옴표 친 문자열 하나다**: `--ur5-base "3.25 0.55 0.80"`. 토큰 셋으로 주면 `need three numbers 'x y z'` 로 즉시 종료한다(9/20 에 한 번 걸렸다). 같은 형식인 것은 `--belt-start` `--shelf-origin` `--dispenser-origin` `--rail-origin` `--tcp-offset` `--ur5-base` `--deck-center` `--ur5-ready` `--ur5-tcp-offset` `--camera-offset` 열 개다. 반대로 `--pick-cell ROW COL`·`--reach-offset DX DY`·`--screen-size W H` 는 따옴표 없이 띄어 쓴다.
- **인자 하나를 바꿀 때, 그 인자에 딸려 오는 값을 먼저 적는다.** 예: `--ur5-ready` 는 월드 절대 좌표라 `--ur5-base` 를 올리면 base→ready 거리가 같이 바뀐다. 적어 두지 않으면 자유 변수가 둘인 회차가 되고 결과를 못 읽는다(실습12d).
- **회차 간 비교는 건수가 아니라 비율·좌표·impulse 로 한다.** 창 모드는 같은 벽시계에 sim 이 덜 간다(12d headless rtf 0.996 ↔ 12d-v 창 모드 0.812, master02 는 3968x1152 듀얼 폭). 겹치는 `placed` 의 좌표·`sim_time` 은 소수 넷째 자리까지 같다. **창 모드냐 headless 냐는 물리 변수가 아니다** — 같은 인자면 같은 것이 같은 `sim_time` 에 일어나고, 벽시계 안에 도는 양만 줄어 건수가 작게 나온다. 그래서 진단 회차를 창 모드로 돌려도 된다.
- 중지는 `C-c`(SIGINT)만. 한 슬롯에서 여러 카드를 돌려도 Isaac 은 한 번에 하나만 띄운다.
  - 래퍼 셸에 보낸 SIGINT 가 안 먹으면 Kit 파이썬 프로세스에 직접 보낸다(9/20 실습15).
- **녹화·캡처**(재범 지시 9/20): 창 모드로 돌리면 녹화를 켜고 단계마다 캡처를 남긴다. 파일 이름·크기·sha256 을 기록에 적는다.
  - headless 라 못 하면 그 이유를 한 줄 적고 대체 증거(로그 줄·수치)를 남긴다. "없음"만 적고 닫지 않는다.
  - 도구: master01 은 ffmpeg x11grab, master02 는 gst-launch(ximagesrc). master02 는 rokey 로그인 세션이 있어야 한다.
  - master02 값: `DISPLAY=:0`, `XAUTHORITY=/run/user/1000/gdm/Xauthority`(master01 의 `:1` 과 다르고 `~/.Xauthority` 는 안 생긴다). 화면이 3968x1152 듀얼 폭이라 Isaac 창 xid 만 잡는다.
  - **gst 는 `ximagesrc … remote=true` 가 필요하다.** 없으면 `X_ShmGetImage BadMatch(MIT-SHM)` 로 0 바이트 파일이 나온다(12d-v 에서 mp4 와 캡처 4장이 그렇게 실패했다).

## RC-1 시연 경로 회귀 (`demo-ros-refill-v2`)

목적: 9/19–20 변경이 시연 기본 경로를 바꾸지 않았는지 본다. 기본 경로에 닿는 것은 #244(`--ur5` 가드)·#264(Dispense 재전송)다. 나머지 새 인자는 모두 기본 꺼짐이다.

띄우는 법은 [9/21 시연 runbook](demo-0921-v2.md) 이 정본이다. 스테이지만 따로 띄울 때는 다음과 같다.

```bash
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset demo-ros-refill-v2 \
  --order-pool "$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml" "${P3_ASSETS[@]}" \
  2>&1 | tee -i /tmp/p3-rc1.log
```

볼 줄:
- `scene base_usd=- base_usd_sha256=- meters_per_unit=- up_axis=-`(병원 씬 없음)
- `ros json topics pub=[…]` 에 네 개만: `/isaac/events`, `/isaac/pharmacy/belt`, `/isaac/pharmacy/dispense_response`, `/isaac/sim/reset_response`. 다른 토픽이 있으면 opt-in 이 새어 나간 것이다.
- 배출마다 `dispense … accepted=True`, `event … DISPENSED`, `belt note=stop_belt`, `event … POUCH_AT_END`
- `belt note=pouch_lost` 가 없어야 한다(`--belt-fail-closed` 기본 꺼짐).
- `dispense … resend=True` 는 같은 요청을 다시 보냈을 때만 나와야 한다.

판정: 준비 단계가 모두 `ok` 이고, 시연 runbook 의 트립·보충·리셋이 전과 같게 돌고, `ERROR`·`Traceback` 이 0 이면 통과다.

9/20 관측(tree `419b20b`, 요지. 전문은 링크):

| 회차 | 모드 | 트립(REQUEST_ACCEPTED→DOCKED, sim s) | 보충(REQ→DONE, s) | 종료 줄 | WARN/ERROR |
| --- | --- | --- | --- | --- | --- |
| 1 | headless | 12.43 / 12.53 / 12.35 → 리셋 → 12.52 | 19.95 / 18.69 / 21.27 | `rtf=0.990 loop_hz=59.42`, exit 0 | stage 0/0, arm WARN 2(joint_states 공백 0.22 s) |
| 2 | 창 + 녹화 | 12.72 / 12.47 / 12.83 → 리셋 → 12.52 / 13.15 | 19.92 / 18.60 / 21.27 / 29.70 | `rtf=0.993 loop_hz=59.57`, exit 0 | stage 0/0, arm WARN 8(공백 0.20–0.23 s) |

- 벨트 `speed_measured 0.1500 / requested 0.15, mismatch False`(1회차 4회 모두).
- Isaac RSS 는 1회차 10분 동안 10.06 GiB 로 평탄했다(1분 간격 10개 샘플). 누수 근거는 없다.
- **미확인**: 위 "볼 줄"의 `scene …` 줄과 `ros json topics pub=` 목록은 관측 기록에 없다. 다음 회차에서 두 줄을 같이 적는다.
- 관측자가 찾은 runbook 과의 차이(자동 요청 `order_generator` 가 epoch 마다 `ord-0002` 를 먼저 쓴다)는 시연 runbook 쪽 사항이다.

## RC-2 벨트 끝 UR5 픽 (`--ur5`, selfdemo)

목적: ROS 없이 UR5 가 스스로 집는지 본다. 대상은 #251·#255·#287·#322·#324 다.

**#324 가 든 커밋**에서 1–4 단계는 통과했다. 집기는 0/5 다(실습12, 9/20 09:05 master02, tree `644ec0a`).
그 전 두 회차(`2c68b73`·`13a2dfd`)는 로봇이 원점에서 돌아 실패다(진단 회차).

1–4 단계: 로봇이 받침대에 섰고 `pin_failed`·`base_frame_mismatch` 는 0줄이다.
**5 단계(집기)는 0/5 다.** 흡착이 한 번도 켜지지 않았다. 봉투는 움직이지 않았다.
`suction on` 0줄, `suction miss` 22줄(첫 값 0.0716 > 0.04), `placed … in_slot=False` 5줄이다.

`error_m` 은 **바퀴마다 다르다.** 1바퀴는 0.065–0.072, 2–6바퀴는 0.23–0.38 이다(실습12 로그를 바퀴별로 셈).

| 바퀴 | 시작 자세 | 벨트 쪽 phase 의 `error_m` |
| --- | --- | --- |
| 1 | 기동 자세 `[4.07, 0.74, 0.44]` | 0.065–0.072 |
| 2–6 | `ready [3.05, 0.55, 1.00]` | 0.23–0.38 |

- 벨트 쪽 phase 4개는 6바퀴 모두 실패다. y 가 0.18 모자라고 z 가 내려가지 않는다.
- 2–5바퀴의 `touch` 는 `[2.86, 0.81, 1.04]` 근처에서 멈춘다. 그 **TCP 위치**일 뿐 막는 물체가 거기 있다는 뜻은 아니다(아래 12c).
- 상판 쪽은 바퀴마다 나아져 5바퀴째(칸 5)는 네 phase 모두 `reached`(0.0001–0.0014)다. `ready` 는 6/6 이다.
- `steps` 와 성공은 무관하다(359 성공, 30 실패).
- UR5 관절: stiffness 5.778e+04(0–2)·2.176e+04(3–5), damping 229/231/87, max_effort 150(손목 28), 한계 ±2π(elbow ±π). Kit 의 drive·limit 경고는 0건이다.
  - **M0609 의 stiffness·max_effort 와 크기를 비교하지 않는다.** 축 종류·스케일·자산 출처가 달라 뜻이 없다.
  - **stiffness 는 이 증상과 무관하다.** PD 라 오차 0.1 rad 이면 이미 `max_effort` 에서 잘린다. 남는 물음은 그 자세의 중력 토크뿐이다.
- **UR5 의 `d1`(base_link → 어깨 축)은 0.0892 m 다.** UR5e 의 0.1625, UR10 의 0.1273 을 쓰지 않는다. base z 0.80 이면 어깨는 0.889 이고 벨트 상판 위로 **0.139 m** 뿐이다.

실습12c(tree `eba5351`, `--ur5-contact-log`)에서 원인이 갈렸다. 개수·좌표·`sim_time` 이 실습12 와 같아 **결정론적으로 재현**된다.

- `ik_check` 는 **29/29 `solved=True`** 다. IK 는 풀린다. 관절이 해를 못 따라간다(worst 는 shoulder_lift 23건·shoulder_pan 6건, 손목 0건).
- 같은 회차에 **UR5 링크가 환경에 실제로 닿는다**: forearm↔`Belt/Surface` 54건(max impulse 40.5), upper_arm↔`Wall_belt_before` 15(34.4), upper_arm↔`DeckSlot3/4WallYPlus` 39, upper_arm↔`Pedestal` 3. UR5↔UR5 와 봉투는 0건이다.
- 기하가 이 접촉과 맞는다(코드 계산, 실측 아님). 벨트는 y 1.00, 윗면 0.75, 끝 x 2.95 다. 봉투는 `(2.806, 0.993, 0.755)` 로 **벨트 끝이 아니라 벨트 위**다. 받침대는 `(3.25, 0.55, 0.45)` 라 팔이 벨트 윗면을 가로질러야 한다. 벽 구멍은 y 0.845–1.155·z 0.67–0.95 뿐이고, 받침대 정면(y 0.55)은 `Wall_belt_before` 통판이다.
- **막는 물체는 벽이 아니라 벨트다.** 2–5바퀴 `touch` 의 첫 접촉은 매번 `at=[2.950, 0.875, 0.714]`·상대 `Belt/Surface`·impulse 39.5–40.5 다. 그 점은 벨트 슬래브(x 1.35–2.95 · y 0.875–1.125 · z 0.65–0.75)의 **먼 끝 × UR5 쪽 모서리**이고 z 는 슬래브 안이다. forearm 이 거기 박혀 있다.
  - `Wall_belt_before` 는 **1바퀴 deck 쪽**(`above_slot`·`lower`·`retreat`)이다. 2–4바퀴 deck 쪽은 DeckSlot 벽, 6바퀴 벨트 쪽은 `Wall_belt_above` 다. 접촉 상대는 phase 마다 다르니 **한 좌표로 뭉뚱그리지 않는다.**
  - (초기 판독 정정) 처음에는 `[2.86, 0.81, 1.04]` 이 벽 통판 모서리(y 0.845)에서 0.035 모자란 점이라고 적었으나, 그건 TCP 위치이고 우연이다.
- **phase × touch 에 예외가 없다**: tcp phase 37개 중 `TIMEOUT` 29개는 **전부** touch>0, `reached` 8개는 **전부** touch=0 이다.
- 왜 슬래브를 뚫는지도 계산으로 나온다(직선 근사, 실측 아님). 어깨(base z + 0.089)에서 봉투로 직선을 그어 벨트 끝면 x 2.95 를 지나는 높이:

  | base z | x 2.95 에서 z | 벨트 윗면 0.75 대비 |
  | --- | --- | --- |
  | **0.45(기본)** | 0.685 | **슬래브 안 −0.065** |
  | 0.70 | 0.766 | +0.016 |
  | 0.80 | 0.798 | +0.048 |
  | 0.90 | 0.831 | +0.081 |

  관측 접촉 z 0.714 와 근사 0.685 의 차 0.029 는 팔이 굽어 직선보다 높이 지나기 때문으로 본다(해석, 미검증).
- (해석, 미검증) 드라이브가 약한 것만이 아니라 **팔이 기하에 막혀 서 있는** 그림이다. Lula IK 는 환경을 모른다.

### 실습12d–12f — 어깨를 올려 본 회차들

한 번에 **하나만** 바꾸는 줄기다. 값은 아래 "인자에 딸려 오는 값" 규칙을 따른다.

| 회차 | 바꾼 것 | 받침대↔상완 | 벽 통판↔상완 | 벨트↔전완 | 상판 칸벽 | `ready` |
| --- | --- | --- | --- | --- | --- | --- |
| 12c | (기준) base z 0.45 | 3건 / 17.9 | 15 / 34.4 | 54 / 40.5 | 88 | 6/6 |
| 12d | base z 0.80 | **65 / 162** | **65 / 150** | 35 / 22.8 | **0** | 0/4 |
| 12e | + `ready` 1.35 | 61 / 160 | 38 / 147 | 37 / 19.9 | 0 | 1/3 |
| 12f-A | (12e 재현, master01) | 74 / 160.4 | 38 / 146.9 | 41 / 19.9 | 0 | 2/4 |
| 12f-B | + 받침대 단면 0.10 | **0** | 8 / 52.7 | 20 / 12.4 | 0 | 6/6(전부 deck 쪽 출발) |
| 12g | + `ready` 를 기동 자세로 | 0 | 0 | 19 / 12.6 | 0 | **0/5(도달 불가)** |

**6바퀴는 따로 본다. 앞 바퀴들과 섞어 세지 않는다.** 5바퀴 `ready` 실패 뒤 팔이 받침대 밑동에 엎어진 자세에서 시작한다(`tcp` z **0.0727**, 상판보다 0.40 m 아래).
그 바퀴만 elbow 부호 뒤집힘 3건이고 `shoulder_lift` 부호가 반대다. UR5 touch 43건이 거기 몰린다.

**접촉은 합계로 보지 않는다. 바퀴별로 쪼갠다.** 12g 에서 upper_arm↔`Belt/Surface` 30건 중 **29건이 6바퀴 하나**다.
합계로만 보면 107 → 105 라 "그대로" 로 보이고, **정반대로 읽게 된다**(실제로 한 번 그렇게 읽었다).
건수보다 **최대 impulse 를 먼저 본다.** 회차마다 rtf 가 달라 건수는 비교가 안 된다.

### 실습12g — 처음으로 집어서 칸에 넣었다

`--ur5-ready "4.0672 0.7415 0.7939"`(기동 자세), 나머지는 12f-B 와 같다.

- **5바퀴에서 `ur5 suction on distance=0.0050` → `placed deck_slot=5 in_slot=True`.** 6바퀴 중 1회다.
- `touch` 오차가 12f-B 의 0.34–0.45 에서 **1–4바퀴 0.067–0.077** 로 모였다. 5바퀴는 `reached` 0.0006, 6바퀴만 0.4176 이다.
- `shoulder_lift` 붙박임이 풀렸다(12f-B 0.182–0.192 → 0.808–0.820, want 과 일치).
- **`ready` 0/5 는 통제되지 않은 변수다.** 12g 개선의 일부는 팔이 z 1.35 로 안 올라간 부작용이다.
  - `shoulder_pan` 을 227° 돌리라는 해가 나와 시한 안에 못 돈다(관절 한계 안이다).
  - 6바퀴가 깨진 것도 그 실패 자세가 다음 바퀴 시드가 된 탓으로 보인다(미확인).

### 남은 문제는 마지막 6–7 cm 다

정체 TCP 를 보면 한 줄로 좁혀진다. `touch` 목표는 `[2.8055, 0.9926, 0.7600]` 이다.

| 바퀴 | 정체 tcp | dx | dy | **dz** |
| --- | --- | --- | --- | --- |
| 1 | [2.8087, 1.0041, 0.8312] | +0.003 | +0.012 | **+0.0712** |
| 2 | [2.8077, 0.9987, 0.8364] | +0.002 | +0.006 | **+0.0764** |
| 3 | [2.8084, 1.0002, 0.8317] | +0.003 | +0.008 | **+0.0717** |
| 4 | [2.8098, 1.0024, 0.8263] | +0.004 | +0.010 | **+0.0663** |

- **오차의 98 % 가 z 이고 부호가 +다.** 정체 z 0.826–0.836 은 `carry_z`(0.820)와 거의 같다. 즉 **`above_pouch` 까지는 가고 거기서 봉투 윗면까지 수직 6–7 cm 를 못 내려간다.**
- 그 구간에 남는 접촉이 **forearm↔`Belt/Surface` 바퀴마다 3건**(impulse 12.15–12.60)이다.
- **성공한 5바퀴만 `touch`·`suck`·`lift` 접촉이 0건**이다.
- `suction miss` 거리(0.066–0.082)가 `touch` 잔차와 같다. `suck` 은 제자리 hold 라 잔차가 그대로 흡착 거리가 된다.

왜 그 자세가 되는지는 접근각으로 읽힌다(계산, 실측 아님). 어깨에서 `touch` 목표까지 수평은 0.627 m 로 고정이고, base 높이만 수직을 바꾼다.

| base z | 어깨 z | 내려오는 각 | `touch` 거리 | 칸5 `place` 거리 |
| --- | --- | --- | --- | --- |
| **0.80(지금)** | 0.889 | **11.6°** | 0.629 | 0.703 |
| 0.90 | 0.989 | 20.1° | 0.643 | 0.754 |
| 1.00 | 1.089 | 27.7° | 0.672 | 0.815 |
| 1.10 | 1.189 | 34.4° | 0.713 | **0.883 — 도달 밖** |

11.6° 는 거의 수평이라 전완이 상판을 따라 눕는다. **1.10 은 상판 칸 쪽이 도달 범위를 넘어 못 쓴다**(`place` 목표가 칸 중심보다 낮은 0.473 이라 칸 중심으로 재면 안 된다).

### 실습12h — 집기가 붙고, 문제가 놓기로 옮겨 갔다

12g + `--ur5-base "3.25 0.55 0.90"`(접근각 11.6° → 20.1°). 3바퀴를 돌았다.

- **집기 3/3.** `touch` 잔차가 0.067–0.077 → **0.0087 / 0.0078 / 0.0115** 로 약 1/7 이다. `suction on` 3회, `miss` 0.
- **놓기 0/3.** `lower` 가 세 번 다 TIMEOUT(0.0524 / 0.1416 / 0.1723)이고 봉투 둘은 바닥에 떨어졌다.

| 칸 | 칸 x | 기둥(x 3.25)과 \|dx\| | 놓은 z(목표 0.473) | 놓은 y(목표 0.05) |
| --- | --- | --- | --- | --- |
| 1 | 2.98 | 0.27 | 0.513 (+0.040) | +0.024 |
| 2 | 3.14 | 0.11 | 0.581 (+0.108) | −0.033 |
| 3 | 3.30 | **0.05** | 0.606 (+0.133) | **−0.059** |

- **칸이 기둥에 가까울수록 나쁘다.** 도달 거리는 오히려 줄어드는데(0.711 → 0.659) 오차는 커진다. **도달 문제가 아니다.**
- **y 는 수직 하강 도중에 밀린다.** `above_slot` 은 세 번 다 0.3 mm 안에 도착한다. `lower` 는 y 0.0500 에서 출발한다.
- 그때 `forearm`↔`Loading/Pedestal` 이 `lower` 에서 **끊기지 않는다**(240–360 틱).
  건수는 3·4·3 이고 접촉점 z 는 0.584–0.631 이다(그 phase 가 가장 낮다).
- `shoulder_lift` 의 `have` 가 **1.32–1.34 에 붙박이고 `want` 만 커진다**(1.40 → 1.54 → 1.56). 12f-B 의 벨트 쪽(0.18 붙박이)과 **값만 다르고 구조가 같다.**

### 실습12i — 기둥이 원인으로 확정됐다

12h + `--ur5-pedestal-size "0.02 0.02"`. **고치는 회차가 아니라 가르는 회차**다(기둥 모서리가 4 cm 물러난다).

| 판정선 | 12h | 12i |
| --- | --- | --- |
| `lower` 의 `forearm`↔`Loading/Pedestal` | 10건 | **6건**(1바퀴 **0**) |
| 놓은 자리가 목표 쪽으로 | — | **4.4–7.4 cm** |
| `in_slot=True` | 0 | **1**(칸1, 집기와 안착이 한 바퀴 안에) |
| 새 접촉 쌍(자리바꿈) | — | **없음** |
| 집기 | 3/3 | **3/3, 소수 넷째 자리까지 같음** |

- **자리바꿈이 없다는 것이 깨끗한 확정이다.** 6바퀴 때처럼 다른 데 걸린 것이 아니다.
- **받침대 단면은 집기에 영향이 없다.** 벨트 쪽 값이 그대로다.
- **단면에는 바닥이 있다.** 칸2·3 은 접촉이 남는다. impulse 는 8.4 → **10.3 으로 올랐다**(닿는 면이 줄어 국소 힘이 커진 것으로 본다, 미검증).
- 다음은 단면이 아니라 **기둥 높이**다(`--ur5-pedestal-height`, #371).
- 접촉 없는 바퀴만 `reached` 인 것이 **놓기에서도 재현**됐다. 벨트 쪽과 같은 모양이다.

### 흡착이 진짜인지 가리는 법

`suction distance` 는 TCP↔봉투 **중심** 거리이고 `touch` 목표는 봉투 **윗면**이다. 봉투 두께가 0.01 이니 **둘은 0.005 차이여야 한다.**

실습12h·12i 여섯 건은 모두 `distance − touch dz = +0.0051` 이다. **문턱 0.04 와 무관하게 붙었다.**
흡착면은 봉투 윗면에서 **8–12 mm** 위에 있었다.
**차가 0.005 보다 훨씬 크면 "문턱에 걸린 흡착" 이니 따로 센다.**
`--suck-distance` 0.04 는 두께 1 cm 봉투에 **4배**다. 언젠가 "닿지도 않았는데 붙는다" 로 돌아올 값이다(미확정).

### 실습12j — 한 바퀴가 온전히 돌았다

12i + `--ur5-pedestal-height 0.45`(단면 0.02 유지). 기둥 윗면이 칸 윗면(0.490)보다 낮아져 팔의 작업 공간 밖으로 나간다.
**결과 전에 정한 판정선 여덟을 모두 충족했다.**

| # | 판정선 | 12i | **12j** |
| --- | --- | --- | --- |
| ① | `lower` 의 `forearm`↔`Loading/Pedestal` **0건** | 0·3·3 | **회차 전체 0건**(12h 26 → 12i 14 → 0) |
| ② | `lower` 3/3 `reached`·`in_slot=True` 3/3 | 1·1 | **0.0007·0.0007·0.0006 / 3•3** |
| ③ | 집기 3/3 유지 | 3/3 | **3/3**(`suction on` 0.0138·0.0130·0.0169, `miss` 0) |
| ④ | 새 접촉 쌍 없음 | 없음 | **없음**(UR5 쌍 전부 count=0) |
| ⑤ | 관문 그대로 | — | `pin_failed`·`base_frame_mismatch` 0 |
| ⑥ | `pedestal_height` 진단 줄 | — | `gap=0.4500` |
| ⑦ | 단면 0.02 | 있음 | 있음 |
| ⑧ | 상판 새 접촉 없음 | 0 | **0**(`Deck/DeckPlate`·`DeckSlot*` 모두) |

- **놓은 자리 오차는 0.1 mm 대다.** 칸이 멀어져도 안 나빠진다(dy/dz 가 세 바퀴 모두 ±0.0002 안).
  12h 는 −0.027 → −0.109 로 벌어졌다.
- **`ik_check phase=lower` 가 0줄이다.** `shoulder_lift` 붙박임을 볼 대상 자체가 없어졌다.
- **남은 UR5 touch 11건은 전부 벨트 쪽이다.** 합은 37 → 25 → 11 이다.
  `forearm`↔`Belt/Surface` 5 + `forearm`↔`Wall_belt_before` 6. 3바퀴 `touch` 만 TIMEOUT(0.0119)인 것도 그쪽이다.
- `placed` 세 건 모두 `pouch` z **0.4630** 이다.
  rtf 는 0.994 이고 `ik_failed` 는 0줄이다.

**단서 — 이 결과를 과장하지 않는다.**
- **`ready` 는 0/3 이다**(오차 1.536, `shoulder_pan` 227°). **연속 운전이 아니다.** 바퀴마다 앞 바퀴가 끝난 자리에서 시작한다.
- **3바퀴(칸1–3)까지만 봤다.** 칸4·5 와 `deck full` 이후는 이 회차에 없다.
- **전부 진단 인자다. 기본값은 하나도 바뀌지 않았다.**
- 이 구성의 UR5 는 기둥 위 **0.45 m 에 떠 보인다.** 받침대가 하중을 받지 않아서다. 캡처를 보는 사람이 결함으로 읽지 않도록 같이 적는다.

### 실습12k — `ready` 가 풀리고 네 칸을 연속으로

12j + `--ur5-ready "3.30 0.05 0.85"`. 값은 **`retreat` 가 팔을 놓고 가는 자리(칸 x, y 0.05, `carry_z` 0.820) 옆**이라 `shoulder_pan` 을 거의 안 돌린다. 그전 실패는 전부 pan 227° 였다.

- **`ready` 6/6 `reached`**(0.0004–0.0006). 12j 는 0/3(오차 1.536)이었다.
- **칸1–4 연속 안착.** 연속 운전의 첫 관측이다.
- **1바퀴가 대조군으로 성립했다**: 여섯 값이 12j 와 넷째 자리까지 같다(`sim_time` 만 짧아졌다 — `ready` 가 빨라져서다).
- **출발 자세가 완전히 바뀌었는데 결과가 같다.** 2·3바퀴 `above_pouch` 출발 tcp 가 `[2.8399, −0.1822, 0.7934]`(12j 의 `ready` 실패 자리) → `[3.3000, 0.0500, 0.8500]` 인데 집기·안착이 같다. **12j 의 성공은 `ready` 실패 자세에 기대고 있지 않았다.**
- **칸5 실패**: `above_slot` 은 0.0004 로 도달하는데 `lower` 가 TIMEOUT 0.7404 다. 팔이 칸이 아니라 **받침대 밑동 쪽으로 접혀 내려가** 봉투를 `[3.2362, 0.7321, 0.0050]`(벨트 쪽 바닥)에 떨어뜨렸다. `Loading/Pedestal` 접촉 4건이 **전부 그 바퀴**이고 `at.z` 0.332 로 기둥 아랫부분이다 — **무너진 팔이 닿은 결과이지 원인이 아니다.**

### 도달 한계로 읽는다 — 어깨에서 재고, 한계는 0.817 m

**거리는 base 가 아니라 어깨(base z + 0.0892)에서 잰다. 2R 로 편 길이는 상완 0.425 + 전완 0.392 = 0.817 m 다.** 0.85 는 손목까지 더한 어림이라 이 판정에 쓰지 않는다.

| 칸 | 12h–12k 배치에서 어깨까지 | 편 길이 대비 | 결과 |
| --- | --- | --- | --- |
| 3 | 0.720 | 88.2 % | 성공 |
| 2 | 0.727 | 89.0 % | 성공 |
| 4 | 0.749 | 91.6 % | 성공 |
| 1 | 0.768 | 94.0 % | 성공 |
| **5** | **0.808** | **98.9 %** | **붕괴** |

**98.9 % 는 팔이 거의 일직선이라 IK 가 특이점 근처에서 조건수가 나빠진다.** 작은 목표 변화에 해가 크게 튄다.

### 실습12l — 상판을 로봇 중심에 맞추자 다섯 칸 전부

`--deck-center` x 가 3.30 인데 로봇 base x 는 **3.25** 였다. 상판이 로봇 기준으로 5 cm 치우쳐 있어 칸5 만 멀었다. **3.25 로 맞추면 다섯 칸이 모두 같은 거리(96.3 %)가 된다.**

- **집기·안착 5/5.** `ready` 5/5. 집기 값은 12k 와 넷째 자리까지 같다(대조군 통과).
- **경계가 좁혀졌다**: 87.9–96.3 % 성공 / 98.9 % 붕괴. **좌우 비대칭은 없다**(96.3 % 두 칸 모두 성공).
- `Wall_belt_before` 0 — 판과 벽이 0.080 m 까지 가까워져도 안 닿았다.
- **다만 96.3 % 두 칸의 `lower` 오차가 다른 칸의 2–3배다**(0.0008·0.0017 대 0.0006–0.0007). **되는 것과 여유 있게 되는 것은 다르다.**

### 실습12m — "여유 있게 되는 구간" 이 수치로 나왔다

12l + `--deck-center "3.25 0.20 0.45"`(상판을 로봇 쪽으로 0.15 m) + **딸린 값 `--ur5-ready "3.25 0.20 0.85"`**.
`ready` 는 `retreat` 자리 옆이어야 하므로 **상판을 옮기면 같이 옮긴다. 독립 변수가 아니다.**

**`lower` 오차가 편 길이 대비 %에 단조로 붙는다**:

| 편 길이 대비 | `lower` 오차 | 놓은 자리 |
| --- | --- | --- |
| 96.3 %(12l) | 0.0008 · 0.0017 | — |
| 85.8 % | 0.0006 · 0.0009 | — |
| 78.8 % | 0.0005 · 0.0008 | 0.0000–0.0001 |
| **76.3 %** | **0.0004** | 0.0000–0.0001 |

- 상판이 기둥 쪽으로 0.15 m 와도 **새로 닿는 것이 없다**(`Loading/Pedestal`·`Deck`·UR5 쌍 모두 0).
- 1–4바퀴 집기는 12l 과 넷째 자리까지 같다(대조군 통과). 칸1–4 `in_slot=True`.
- **5바퀴부터 집기가 무너졌다.** 5–8바퀴에만 `forearm`↔`Wall_belt_above` 7–10건/바퀴가 나온다.

### 12m 5바퀴 — 시드가 가지를 고른다는 통제된 쌍

12l 5바퀴와 12m 5바퀴는 **pick 목표가 같고**(넷째 자리까지) **`ready` 출발 TCP 도 같은데** 결과만 다르다(12l 성공, 12m 은 벽 접촉 뒤 실패, worst 가 `wrist_1` −4.23 rad).

**다른 것은 앞선 바퀴들이 남긴 관절 자세뿐이다.** 12m 은 상판이 옮겨져 1–4바퀴를 다른 자리에 놓았고, 그래서 5바퀴에 들어갈 때 관절 상태가 다르다. **같은 TCP 에서 출발해도 관절 조합은 다를 수 있다.**
- (초기 판독 정정) 처음에는 "봉투가 벨트 바깥쪽 절반에 서면 못 집는다" 로 읽었으나 **틀렸다.** 근거로 쓴 좌표가 5바퀴가 아니라 6바퀴 것이었고, 같은 y 에서 성공한 바퀴가 여럿이다.
- **오늘 로그로는 더 못 간다.** phase 시작 시점의 관절값이 로그에 없고, 12l 5바퀴는 성공해서 `ik_check` 자체가 없어 비교할 짝이 없다. 시드를 찍는 코드가 필요하고 그건 시연 뒤다.

### `--loop` 는 배출만 막는다

`--loop 5` 를 줘도 **바퀴가 5로 안 끊긴다.** 배출 횟수만 센다(`pharmacy_stage.py`). **집기에 실패한 봉투가 벨트에 남으면 새 배출 없이 팔이 그걸 또 집으러 간다** — 12m 은 `dispensed=5` 인데 `pick` 8회·`placed` 7줄이었다.

### 여기까지 온 길 (한 줄씩)

| 회차 | 바꾼 것 | 무엇이 풀렸나 |
| --- | --- | --- |
| 12c | (기준) | 원인이 기하라는 것 |
| 12f | 받침대 단면 0.10 | 상완↔기둥 74/160 → **0** |
| 12g | `ready` 를 기동 자세로 | `touch` 0.34–0.45 → 0.067–0.077, **첫 집기 1회** |
| 12h | base z 0.90(접근각 11.6° → 20.1°) | `touch` → 0.008–0.012, **집기 3/3**. 문제가 놓기로 |
| 12i | 단면 0.02 | **기둥 확정**, 안착 1회 |
| 12j | 기둥 높이 0.45 | **안착 3/3** |
| 12k | `ready` 를 상판 옆으로 | **`ready` 6/6**, 칸1–4 연속 |
| 12l | 상판을 로봇 중심(x 3.25)으로 | **5/5** |
| 12m | 상판을 로봇 쪽(y 0.20)으로 | **여유 있게 되는 구간**(76–79 %) |

**남은 것**: 한계 근처(98.9 %)에서 팔이 무너지는 것(P31), 성사 여부를 확인하지 않는 것(P32 — 흡착 실패해도 놓기를 계속 / `placed` 가 시도를 셈 / `deck full` 뒤에 안 멈춤 / `--loop` 로도 안 끊김), 기본 배치 결정(base z·받침대·상판 위치·흡착 툴).

- 12d 는 **단일 변수 회차가 아니었다.** `--ur5-ready` 가 월드 절대 좌표라 base 만 올리자 base→ready 가 0.585 → **0.283 m** 로 같이 줄었다. 0.283 은 2R 안쪽 경계(0.033)에 가까워 팔을 극단으로 접으라는 해가 나온다. 12d 의 elbow 폭증·`ready` 실패는 그 교란이 섞인 값이다.
- 12e 에서 오프셋을 되돌려도 `ready` 는 1/4 에 그쳤고, **받침대·벽 접촉은 12d 와 사실상 같다**(162→160, 150→147). 어깨 높이·대기 자세로는 안 풀린다는 뜻이다.
- 받침대는 `0.30 × 0.30 × (base z)` 라 **base 를 올리면 어깨 밑 기둥이 같이 자란다.** 상완·전완은 베이스 축을 지나는 평면에서 움직이므로(`UR5_DH` 의 j2·j3 은 d=0, 0.1091 은 **손목** 오프셋이다) 기둥은 팔이 지나는 자리 바로 아래에 선다. 그래서 12f 는 `--ur5-pedestal-size`(#360)로 단면만 좁힌다. 받침대는 하중을 받지 않는다(UR5 는 월드 고정).
- **벽은 목표를 막지 않는다.** 2R 로 팔꿈치 위치를 풀면 올바른 해는 어느 목표에서도 벽면(x 2.75)에서 0.16 m 이상 떨어진다(봉투 +0.226/+0.301, 칸1 +0.298/+0.416). 그런데 벽 접촉이 찍힌다 → 팔이 **유효한 해 근처에 없다.** 그래서 base 를 +x 로 빼는 안은 권하지 않는다. 봉투만 0.70 → 0.78 m 로 멀어진다.
- elbow 는 한계가 **±π** 다(다른 관절 ±2π). `have ≈ −1.75` 인데 `want ≈ +1.5` 인 가지 뒤집힘이 12d 에 4건 있었는데, 짧은 길(±π 를 넘는 2.98 rad)은 한계에 막혀 **0 을 지나는 3.30 rad 의 긴 길**만 남는다. 그 궤적은 벨트·상판이 있는 공간을 크게 훑는다. **한계 밖 해가 나온 것은 아니다**(`want` 가 한계를 넘은 건 0건).

```bash
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --mode selfdemo --ur5 --loop 3 \
  --duration 300 "${P3_ASSETS[@]}" 2>&1 | tee -i /tmp/p3-rc2.log
```

- `--mode selfdemo` 라 `--ros-pick-stand-in-s` 기본 0 이다. `--ur5` 가드에 걸리지 않는다.
- `--loop 3` 은 배출 횟수만 제한한다. 앱은 SIGINT 나 `--duration` 까지 돈다. 그래서 `--duration 300` 을 준다.
- UR5 자산은 자산 서버의 `ur5.usd` 다. 서버에 못 닿으면 `--ur5-usd <로컬 경로>`(경로 미확인).
- 집기 원인을 가리는 회차(실습12c 이후)에는 `--ur5-contact-log` 를 같이 준다. 동작은 바뀌지 않고 UR5 접촉 줄만 늘어난다.
- 진단용 opt-in(기본값은 지금 동작 그대로, 시연 경로와 무관):
  - `--ur5-pedestal-size "0.10 0.10"`(#360) — 받침대 단면만 좁힌다. 높이는 `--ur5-base` 의 z 에서 온다.
  - `--view ur5`(#363) — 받침대 옆·윗면 높이에서 적재 셀을 본다. 창 모드 회차에서 준다. `overview` 로는 셀이 프레임 밖이다.

### 먼저 볼 것 — 로봇이 받침대에 있는가

9/17 결함이 풀렸는지 보는 구성 확인이다. 합격선이 아니다. 1–4 가 맞은 뒤에야 5(집기)를 본다.

| # | 줄 | 기대 |
| --- | --- | --- |
| 1 | `ur5 prim_translate` | `set_ok=True composed_world=[3.2500, 0.5500, 0.4500]` |
| 2 | `ur5 pin_check` | prim·base_link 가 받침대. `pin_failed` 0줄 |
| 3 | `ur5 ready … base_pose=` | `[3.2500, 0.5500, 0.4500]`(로봇 루트이자 Lula 베이스) |
| 4 | `ur5 tcp_source …` | `tool0_from_pedestal_m` < 1.2, `ur5 base_frame_mismatch` 없음 |
| 5 | 집기 | 아래 "볼 줄"과 판정 |

1–4 중 하나라도 어긋나면 그 줄과 `ur5 world_joints`(`set_ok=` 포함), `step=world_reset` 앞뒤 순서를 기록하고 멈춘다. 5 는 의미가 없다.

볼 줄([sim README 「벨트 끝 UR5」](../../sim/README.md)):
- 준비: `ur5 end_link=…`, `ur5 world_joints count=…`, `ur5 tcp_source fk_tool0=… end_prim=… difference_m=…`. `ur5 base_frame_mismatch` 는 없어야 한다.
- 바퀴마다: `ur5 pick order_id=…`, `ur5 phase=…`, `ur5 reached phase=… error_m=…`, `ur5 suction on distance=…`
- #251: `pouch picked_by=ur5 … off_belt frame=(…)` 는 흡착 뒤 봉투가 벨트 부피 밖으로 나간 **뒤에** 나와야 한다. 그 전에는 다음 `dispense` 가 없어야 한다.
- `ur5 placed deck_slot=N in_slot=True`

판정:
- 통과: 위 1–4 가 모두 맞는다. 세 바퀴 모두 `in_slot=True` 이고 `ik_failed`·`suction miss`·`TIMEOUT` 이 0 이다.
- 참고(계산, 실측 아님): 벨트 끝 pick 점은 받침대에서 약 0.70 m 라 UR5 도달 범위 안이다. 9/20 실패 때는 원점 기준이라 0.90 m 로 범위 밖이었다.
- 실패: 첫 실패 줄과 그 앞의 `ur5 phase=`·`tcp=` 를 기록한다. 고치지 않는다.
- 미확인: `error_m` 허용치. `--tcp-tolerance` 기본값을 기준으로 삼지만 합격선은 아니다.

ROS 가 붙는 경우만(미확인): Isaac 이 selfdemo 에서도 TF 를 내는지 모른다. 낸다면 `ros2 run tf2_ros tf2_echo amr_1/base_link amr_1/deck_slot_1` 로 z 가 칸 바닥 **윗면**인지 본다. #287 뒤 기대값은 판 윗면 + 0.008 m 이고, 이전보다 0.004 m 높다.

### 1–4 단계가 어긋나면 — 무엇을 더 뽑나

고치지 않는다. 아래를 기록하고 멈춘다.

| 보이는 줄 | 뜻 | 더 뽑을 것 |
| --- | --- | --- |
| `ur5 prim_translate set_ok=False` | USD 에 translate 를 못 썼다 | 같은 줄의 `composed_world=`. Kit 로그(`--kit-log-file … --kit-log-verbose`)에서 `incompatible xformable` 와 `/Loading/UR5` 를 grep |
| `set_ok=True` 인데 `composed_world` 가 받침대가 아님 | 부모나 자산 루트의 다른 op 가 끼어들었다 | `pin_check` 의 `ur5_prim=`·`base_link=`. 둘이 다르면 자산 안쪽이 원인 |
| `pin_check` 의 `readback` 이 쓴 값과 다름 | 관절 쓰기가 되돌아갔다 | `strongest_layer=` 와 `ur5 world_joints … set_ok=` |
| `pin_failed` 는 없는데 `ready … base_pose=[0,0,0]` | USD 는 맞는데 PhysX 가 다른 기준을 썼다 | `step=world_reset` 과 `ur5 ready` 의 순서. Kit 로그의 `articulation`·`fixed base`·관절 프레임 경고 |

### 1–4 를 넘긴 뒤 처음 보게 될 실패 (스테이지 쪽)

팔·IK 쪽 분류는 [팔·인식 런카드](l3-arm-perception.md)에 있다. 아래는 스테이지가 찍는 줄이다.

| 보이는 줄 | 뜻 | 더 뽑을 것 |
| --- | --- | --- |
| `ur5 ik_failed phase=<이름>` 이 특정 단계에서만 | 그 단계의 보간점이 도달 범위·자세 제약 밖이다 | 실패한 `phase=` 과 바로 앞 `ur5 phase=… target=… steps=…`·`tcp=`, `count=` |
| `ur5 TIMEOUT phase=… error_m=…` | 시한(`--phase-timeout-s` 5 s) 안에 공차(`--tcp-tolerance` 0.01 m)에 못 들어왔다 | 같은 단계에서 `error_m` 이 줄고 있었는지 |
| `ur5 suction miss distance=… limit=0.04` | 흡착 시점에 TCP–봉투가 4 cm 밖이다 | `distance` 값. 0.04–0.10 이면 접근 깊이(`--clearance` 0.06), 1 m 이상이면 아직 위치 문제 |
| `suction on` 인데 `off_belt` 없음 | 쥔 봉투가 아직 벨트 안이다(#251). 다음 배출이 없다 | `belt note=`, 종료 줄 `dispensed=`, lift 단계 `target=` z |
| `ur5 placed deck_slot=N in_slot=False` | 칸 안에 안 들어갔다 | `pouch=` 좌표와 칸 번호. 칸 크기는 0.14×0.11×0.04 |
| `dispense … message=pool_exhausted` | 봉투가 상판에 남아 풀이 비었다 | `pool=… in_use=[…]`, `ur5 deck full …` |
| `dispensed=1` 로 끝남 | 벨트 점유가 안 풀려 배출이 멈췄다 | 위 `off_belt` 줄과 같이 본다 |
| `physics_view lost by timeline STOP` | Kit 내부 STOP. 복구 로직이 돈다 | `count=`, `physics_view recovered updates=…`, 그 앞 tick 의 trace 덤프 |

`TIMEOUT` 바로 다음 줄의 `ur5 ik_check …`(#346)로 두 경우를 가른다.

줄 모양은 `tcp_target=… solved=… max_joint_diff_rad=… joints=… worst[이름: want A have B diff C, …]` 다(상위 3관절).
**`want` 는 IK 가 요구한 값, `have` 는 그때 실제 관절값, `diff` 는 둘의 차다.** 셋을 섞어 읽지 않는다 — 9/20 에 `diff` 3.28 을 `want` 로 읽어 "관절 한계를 넘었다" 는 잘못된 갈래가 한 번 섰다.
`have` 는 **`TIMEOUT` 시점**의 값이다. phase 시작 관절값은 로그에 없다.

| `ik_check` | 뜻 |
| --- | --- |
| `max_joint_diff_rad` 가 크다 | 관절이 IK 해를 못 따라간다(드라이브·중력·충돌·한계) |
| `max_joint_diff_rad` 가 작은데 `error_m` 이 크다 | 해 자체가 목표에서 떨어져 있다(고정 자세 아래 근사해) |
| `solved=False` 가 이어진다 | 그 구간은 IK 가 아예 안 풀린다 |
| **`want` 와 `have` 의 부호가 반대** | IK 가 **반대 가지**를 냈다. 관절이 그 가지로 못 넘어간다 |
| 같은 목표인데 바퀴마다 `want` 가 다르다 | 가지를 고르는 것은 **출발 관절값(시드)** 이다. 자세 제약은 목표마다 상수라 바퀴 간 차이를 못 만든다 |

- **`contact` 줄이 없다고 안 닿은 것이 아니다.** 접촉 감시 대상은 M0609 와 약통뿐이라 UR5 는 보지 않는다. UR5 접촉을 보려면 `--ur5-contact-log`(기본 꺼짐, #346)를 준다.
- **접촉 로그의 `Pedestal` 은 둘이다.** `…/Loading/Pedestal` 은 UR5 받침대이고, 레일 캐리지에도 같은 이름의 `Pedestal` 이 있다(M0609 쪽, `p3sim/layout.py`). **이름만으로 grep 하면 섞인다. 경로를 붙여 센다.**
- **`--clearance` 는 UR5 전용이 아니다.** `pharmacy_stage.py` 에서 M0609 레일 팔의 보충 계획에도 쓰인다. selfdemo 는 레일 팔도 같이 도니 **두 로봇을 동시에 바꾸는 회차**가 된다. UR5 진단의 단일 변수로 쓰지 않는다.
- **`ur5 placed` 는 시도 줄이다. 성사 여부는 `in_slot=` 과 `pouch=` 좌표로 본다.** 흡착이 안 돼 봉투가 제자리에 있어도 이 줄은 찍힌다.
  - 12g 의 `placed` 5건 중 넷은 `in_slot=False` 다. 좌표는 집으러 간 자리 그대로다(`pouch=[2.80xx, 0.993x, 0.7550]`).
  - 다섯째만 `in_slot=True` 다(`pouch=[3.6198, 0.0504, 0.4630]`).
  - 그래서 **"placed 5" 는 "다섯 번 담았다" 가 아니다.** 12f-A·B 의 `placed` 4·6 은 **한 번도 못 옮긴 것**이다. `ik_failed` 의 `count` 와 같은 종류의 함정이다.
- **`deck full` 은 계수 결함이다(12g 로 확정).** `in_slot=False` 여도 칸이 찬 것으로 센다. 12g 는 `in_slot=False` 넷 뒤에 `deck full slots=5` 를 찍고도 **또 `deck_slot=1` 로 집으러 갔다.**

거리(**계산, 실측 아님**). UR5 도달 범위는 약 0.85 m 다.
받침대에서 대기 TCP 0.585 m, 벨트 끝 0.697 m, 접근점 0.728 m, 상판 칸 0.569–0.622 m. 9/20 원점 기준이면 같은 점이 0.90 m 였다.

**동작을 바꾸는 인자는 슬롯에서 임의로 쓰지 않는다**(`--tcp-tolerance`, `--phase-timeout-s`, `--suck-distance`, `--clearance`, `--ur5-tcp-speed`). 원인을 좁히려고 바꾸려면 #240 에 먼저 알리고, 바꾼 값을 run 기록에 남긴다.

## RC-3 새 관측 opt-in

목적: #276·#252·#278 의 발행과 동작을 본다. adapter 변환은 이 카드 밖이다. 여기서는 Isaac JSON 토픽만 본다.

3a. 벨트 관측과 fail-closed(UR5 없음, 스텁 경로):

```bash
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset demo-ros-refill-v2 \
  --belt-observation --belt-fail-closed \
  --order-pool "$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml" "${P3_ASSETS[@]}" \
  2>&1 | tee -i /tmp/p3-rc3a.log
# 같은 도메인의 다른 셸
ros2 topic echo /isaac/pharmacy/belt_observation std_msgs/msg/String --once
ros2 topic hz /isaac/pharmacy/belt_observation
```

볼 것:
- `ros json topics pub=` 에 `/isaac/pharmacy/belt_observation` 이 더해진다. hz 는 약 5 다.
- JSON `seq` 가 메시지마다 증가한다. 같거나 줄면 실패다.
- 종단에 정착하면 `pouch_zone=2`(종단 구역)·`pouch_motion=2`(멈춤)·`belt_command_applied=2`(정지 명령). 이송 중에는 1(벨트 위)·1(움직임)·1(구동 명령).
- `mode` 기본은 2(SIM_SENSOR)다. 스텁 회수(`pick_notice`·stand-in) 뒤에만 잠깐 1(STUB)이다.
- 배출이 한 번도 없었으면 유휴는 `mode=2`·`occupancy=1` 이다(9/20 실습15 관측과 같다).
- 스택 없이 스테이지만 띄우면 `dispensed=0` 이라 전이(배출 → 이송 → 정착)는 볼 수 없다. 전이까지 보려면 스택을 붙인다. launch 짝은 [스택 조합 문서](l3-stack-combos.md)를 따른다(`tools/demo_v2.sh` 로는 이 짝을 켤 수 없다).
- `belt_command_applied` 가 계속 0 이면 구동 속성을 읽지 못하는 것이다. 결과로 기록한다.

3b. 그리퍼 command_seq(UR5, ros 모드). 팔 노드가 command_seq 를 내야 한다:

```bash
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset demo-ros-refill-v2 \
  --ur5 --ros-pick-stand-in-s 0 --gripper-command-seq \
  --order-pool "$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml" "${P3_ASSETS[@]}" \
  2>&1 | tee -i /tmp/p3-rc3b.log
ros2 topic echo /isaac/amr_1/gripper/state std_msgs/msg/String --once
```

볼 것:
- `gripper command_seq applied seq=1 close=True` 다음에 `ur5 suction on …`. 같은 seq 를 다시 보내면 `gripper command_seq ignored … is not above …`.
- `/isaac/amr_1/gripper/state` 는 약 10 Hz. `last_applied_command_seq` 가 적용한 seq 와 같고, 흡착 중 `state=2`, `mode=1`.
- 종료 줄 `gripper_bool_ignored=N`. 팔이 Bool 도 같이 내면 N>0 이 정상이다.
- 선행 조건(미확인): 팔 노드의 command_seq 발행과 adapter 의 command_seq 변환이 main 에 있는지.

## RC-4 병원 씬 이식 smoke (`hospital-v2`)

목적: 병원 씬 위에서 조제실이 그대로 도는지 본다. 대상은 #259·#274·결정 22(`ridgeback_ur5` 는 살리고 WARN)다.
아래 준비·오프라인 점검·팔 단발 2회는 9/17 병원 씬 작업에서 받은 문장이다.

### 1. 자산 준비 (한 번만)

```bash
# 이미 있으면 내려받지 않는다
find "$HOME" -maxdepth 4 \( -name 'hospital-custom-assets-*.zip' -o -name 'm0617.usd' \) 2>/dev/null | head
# 없으면 릴리스 자산을 받는다(저장소가 private 이라 토큰이 필요하다. master02 에는 gh 가 없다)
curl -fL -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/octet-stream" \
  https://api.github.com/repos/jaebeom/ROKEY_P3_A3/releases/assets/571649529 \
  -o ~/markle_tmp/hospital-custom-assets-20260918.zip
# 해시를 대조한다. 다르면 멈춘다
sha256sum ~/markle_tmp/hospital-custom-assets-20260918.zip
cat "$P3_REPO/sim/scenes/hospital_assets.sha256"
# 푼다(약 20 MB). <custom-assets> 는 푼 폴더다
mkdir -p ~/markle_tmp/custom-assets
unzip -q -o ~/markle_tmp/hospital-custom-assets-20260918.zip -d ~/markle_tmp/custom-assets
find ~/markle_tmp/custom-assets -maxdepth 4 | head
```

- 토큰이 없으면 재범님이 dev01·master01 사본을 넣어 준다. 관측자가 할 일이 아니다.
- **지금 필요한 자작 파일은 `material/etc/Automatic+Blister+Packing+Machine+(DPB-80)/model.usd` 하나다.** M0617 은 `b9ba0d6` 에서 씬에서 빠져 `prepare_hospital_scene.py` 가 요구하지 않는다(9/20 확인).
- 그 파일과 Isaac 5.1 자산이 장비에 있으면 ZIP 을 받지 않는다. **쓴 경로와 파일의 sha256 을 적는다**(ZIP sha256 대조는 해당 없다).
- master02 는 `/home/rokey/Downloads/Collected_hopital_custome` 에 넷 다 있다(9/20 확인). 자산은 `hospital.usd`·`ConveyorBelt_A24.usd`·`ridgeback_ur5.usd` 다.
- **아래 절들이 쓰는 두 경로를 여기서 셸 변수로 잡는다**: `C=<자작 자산 폴더>`, `I=<Assets/Isaac/5.1>`.
- Isaac 자산 루트는 `Isaac/`·`NVIDIA/` 를 가진 `Assets/Isaac/5.1` 이다. 로컬 사본이 있으면 그 경로를 쓴다. 없으면 공개 서버 URL 을 `--isaac-assets-root` 에 준다. URL 이면 기동 때 내려받느라 느릴 수 있다(미확인).

### 2. 오프라인 선행 점검 (앱 없이, USD 파이썬(`pxr`)만)

```bash
python3 sim/standalone/prepare_hospital_scene.py --custom-assets "$C" \
  --isaac-assets-root "$I" --output /tmp/p3-hospital.usda
# pxr 이 있는 파이썬에서만 된다. 어느 쪽도 없으면 2절은 미실행이다(아래)
python3 sim/standalone/hospital_scene_check.py /tmp/p3-hospital.usda --hospital-v2 > /tmp/p3-rc4-check.json
[ -s /tmp/p3-rc4-check.json ] && python3 -c "import json; r=json.load(open('/tmp/p3-rc4-check.json'))['composed']; \
print({k: r[k] for k in ('deactivated','deactivate_missing','rigid_off','rigid_off_missing','rigid_bodies_enabled')}); \
print('footprint', r['footprint']); print('views', {k: v['hits'] for k, v in r['views'].items()})"
```

**어긋나면 Isaac 을 띄우지 않는다.** 값을 그대로 보고하고 멈춘다.

기준값(dev01 에서 main `86afb7d`·지금 씬·같은 자작 자산으로 돌린 값. **Isaac 아님**):

| 어디 | 값 |
| --- | --- |
| 레이어 | `/clock`·ROS 노드 0, `PhysicsScene` **0**, 벨트 그래프 22, 로봇 참조는 `ridgeback_ur5` 하나(M0617 은 빠진 뒤라 없다) |
| 합성 | `deactivated 50`, `deactivate_missing []`, `rigid_off 22`, `rigid_off_missing []`, `rigid_bodies_enabled 0`, `active_graphs 0`, `footprint []`, 세 시점 `hits []` |
| 합성 | `articulation_roots []` — dev01 에 `ridgeback_ur5` 자산이 없어 빈 것이다. **master02 에서는 3절의 WARN 에 나와야 한다**(결정 22) |

- **조건**: 이 값은 NVIDIA 공개 서버에서 받은 Isaac 자산 사본 기준이다. master02 는 `Collected_hopital_custome` 안의 사본을 쓴다. 병원 형상이 같으면 결과도 같겠지만 **두 사본이 같다는 것은 확인되지 않았다.**
- **같은 이름인데 모양이 다르다**: 점검 출력의 `deactivated` 는 **개수**, 3절 스테이지 로그의 `"deactivated"` 는 **경로 목록**이다. 둘 다 50 이면 같은 뜻이다. 목록을 개수와 나란히 놓고 "다르다" 로 읽지 않는다.
- `prepare_hospital_scene.py` 산출물의 **크기는 기계마다 다르다**(자산 절대 경로가 39곳 박힌다). 크기로 대조하지 않는다.
- 씬이나 `base_scene.py` 의 목록이 바뀌면 이 표는 무효다. 다시 돌린다.
- **`~/isaacsim/python.sh` 는 대체가 안 된다.** master02 에서 `python.sh -c "import pxr"` 가 `ModuleNotFoundError` 다(Isaac Sim 5.1.0-rc.19, 9/20 관측). Kit 앱 없이는 `pxr` 을 안 내놓는 것으로 본다(해석, 미검증). 앞서 런카드에 적어 두었던 대체 줄은 그래서 **지웠다.**
- **`pxr` 이 어디에도 없으면 2절은 "미실행" 이다.** master02 가 그렇다(시스템 python3 에도 없고 `python3 -m pip` 자체가 없어 `pip install usd-core` 도 안 된다. apt 는 sudo 다). 억지로 넘기지 말고 이렇게 한다.
  - 2절을 **미실행**으로 적는다. 점검은 종료 코드 1, stdout 34 B, stderr `usd-core (pxr) is needed…` 다. `prepare_hospital_scene.py` 는 `pxr` 을 안 써서 **exit 0 으로 씬은 만들어진다**(9/20: 355,225 B).
  - 3절 로그로 **대체 확인되는 것**: `base_scene usd=… {"deactivated", "missing", "rigid_off"}` 줄의 세 항목과, `WARN base_scene articulations …` 줄(결정 22 의 ridgeback). `/clock` 작성자는 런타임 `ros2 topic info /clock -v` 로 본다. 어긋나면 팔 단발 전에 내린다.
  - **대체 확인되지 않는 것은 전부 "미확인" 으로 남긴다**(9/20 확인):
    - `footprint`(우리 상자·로봇 범위·벨트가 씬 prim 과 겹치나), 세 시점 `hits`(시선 가림).
    - 씬에 **`PhysicsScene` 이 있는지**. 있으면 중력·솔버가 둘이 된다. 지금 씬엔 없지만 씬이 바뀌면 이걸 보는 것은 이 점검뿐이다.
    - **우리 목록 밖의 벨트 그래프·강체가 남아 도는지.** `rigid_off 22` 는 "우리가 끈 수" 이지 "남은 게 없다" 가 아니다. 그건 `rigid_bodies_enabled`·`active_graphs` 가 0 인지로 본다.
    - 컨베이어 몸체의 합성 scale·kinematic·surface velocity, 로봇 참조 목록, 최상위 배치.
  - 가르는 말로: **"우리가 아는 50·22 를 껐다" 는 로그로 되고, "씬에 우리가 모르는 것이 있나·우리 것과 겹치나" 는 안 된다.**
  - 그 회차에는 5절의 "통과" 를 쓰지 않는다.
- 값만 본다. 자산 참조가 일부 안 풀리면 stderr 에 `Could not open asset …` 경고가 여러 줄 나오지만 점검값과 무관하다.

### 3. 본 실행

```bash
"${P3_ISAAC_ENV[@]}" ~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset hospital-v2 --base-usd /tmp/p3-hospital.usda \
  --order-pool "$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml" "${P3_ASSETS[@]}" \
  2>&1 | tee -i /tmp/p3-rc4.log
```

팔 노드는 실습7-a5·7-b 와 같은 팔 명령으로 띄우고, 첫 L3 이므로 `-p v2_guarded_module_path:=false` 를 명시한다. **팔 v2 단발 2회**(원통 1회, 모듈 1회)를 돌린다. 병원 유무로 팔 경로가 달라지지 않는지가 이 smoke 의 핵심이다.

볼 줄:
- `scene base_usd=/tmp/p3-hospital.usda base_usd_sha256=<64 hex> meters_per_unit=1 up_axis=Z`
- `base_scene usd=… {"deactivated": [50개], "missing": [], "rigid_off": 22, "articulations": [...], …}`
- `WARN base_scene articulations this stage does not drive: […]` 에 **ridgeback 경로가 나와야 한다**(결정 22). 비어 있으면 그 자산이 안 풀린 것으로 본다
- `WARN base_scene deactivate paths not found` 가 **없어야** 한다
- 팔 기동 로그의 `v2 계획 캐시`가 **16/16 그대로**여야 한다(`16/16칸 풀림 …`). 숫자가 달라지면 좌표가 흔들린 것이다
- `refill_ros released cell=… type=… target=round` 와 `… target=module` 각 1회(`target=none` 0)
- `rail_overlap part=` 0줄, 팔 로그의 "레일이 밀려" 0줄
- `contact … /World/P3Base/…` — 우리 로봇·약통이 병원 물체에 닿았는지. 있으면 그 prim 경로를 기록한다
- 다른 셸에서 `ros2 topic info /clock -v` → 발행자 1(우리 스테이지). 2 면 씬 쪽 시계가 살아난 것이다(씬의 `Graph/ROS_Clock` 은 `b9ba0d6` 에서 빠졌다)

`base_usd_sha256` 은 기록용이다. 준비된 씬에는 절대 경로가 박혀 기계·경로마다 값이 다르다. 기계 간 비교는 ZIP 해시와 `hospital_layout.usda` 의 git 판으로 한다.

### 4. 화면·캡처

캡처는 Isaac 창만 3 s 간격으로 찍고 원본은 `~/markle_tmp/shots/p16_*` 에 둔다. 문서에는 대표 2–4장만 줄여 올린다. 웹을 같이 띄우면 창이 겹치지 않게 먼저 배치한다.

볼 것:
1. 조제실(선반 넷·레일·M0609·조제기·수납통)이 병원 방 동쪽 끝에서 바닥에 붙어 서는가. 떠 있거나 파묻히지 않는가
2. 끈 물건이 안 보이는가 — 의약품 캐비닛 2, 약병 24, 동쪽 벽 두 조각
3. 우리 벨트가 그 벽 자리를 지나 홀로 나가고, 끝과 적재 자리가 바닥 위에 있는가
4. 병원 컨베이어가 움직이지 않는가(모양은 남는다)
5. 기본 카메라(overview)가 병원 벽·천장에 가리지 않는가

### 5. 판정

- 통과: 2절 기대값이 맞고, 3절 볼 줄이 모두 나오고, 병원 씬 위에서도 준비 단계가 전부 `ok` 이며 팔 단발 2회가 `target=round`·`target=module` 로 끝난다.
- 기록: `articulations` 전체, `missing` 경로(고치지 않는다), `contact` 로 잡힌 병원 prim, `/clock` 발행자 수.
- 비교 기준: 같은 날 같은 코드의 `demo-ros-refill-v2` 로그로 갈음한다. 없으면 병원 없이 한 번 더 돌린다.
- 미확인: 병원 씬 위 RTF·물리 비용의 기준값, 참조 자산 단위가 겉보기 크기에 맞는지(`machine` 의 `unitsResolve` 등, 눈으로).

## RC-5 빈월드 전 구간 (`emptyworld-loop`)

재범 9/21 "구현부터. 전체 시나리오가 다 돌아가게 한 다음에 상세로 집중한다." 조제실 밖으로 복도·병실·도크를
상자로 얹고, 이동 베이스와 참값 센서를 붙인 구성이다. **치수는 전부 임시값이다**(실측은 `AMR_BBOX` 하나).

```bash
~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset emptyworld-loop --duration 120        # K1 장면만
~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset emptyworld-loop --amr --duration 300  # K2 베이스
~/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset emptyworld-loop --amr \
    --sim-sensors --order-pool /abs/order_pool.yaml --duration 300                                   # K4·K5 센서
```

`--zones-tf` 는 **주지 않는다** — 구역 TF 의 계약 단일 작성자는 주행 launch 의 `zones_tf` 다. 한 바퀴 조합에서
스테이지가 같이 내면 한 변환의 작성자가 둘이 된다(계약 3절). ROS 스택 없이 프레임을 눈으로 볼 때만 준다.

### 기동 직후 읽을 네 줄 — 회차가 끝나기 전에 판정한다

```
observers contact_watch=on watch_bodies=N roots=[…] ur5=on amr=on m0609=off zones_tf=off hand_camera=on
full_loop corridor_boxes=3 ward_boxes=12 dock_boxes=1 beds=[bed_a1,bed_a2,bed_b1,bed_b2] total_boxes=N
amr built root=/World/P3Pharmacy/Amr start_xy=(4.6, 0.55) joints=[…]
ur5 base_frame_tf parent=map child=amr_1/ur_arm_base_link topic=tf_static
```

`--ur5-spawn-ready` 가 켜진 구성은 **본 루프 전에 물리 스텝 91 회를 돈다**(정착 90 + 직후 1, 60 Hz 에서 약 1.5 s).
"PLAY 뒤 N 초" 로 구간을 끊으면 그만큼 밀린다 — `ur5 spawn_settled` 줄 **뒤**를 0 점으로 잡는 편이 깨끗하다.

### 스폰 자세 세 줄 — `at_home` 이 여기에 걸려 있다

```
ur5 spawn_ready     solved=True tcp=[…] written={…}
ur5 spawn_immediate joints={…} vs_written_rad=…
ur5 spawn_settled   steps=90 sim_s=1.500 joints={…} sag_rad=… at_home_tol=0.05 ok|WARN
ur5 home_positions=[…] spawn_ready=on
```

팔 노드의 `arm/at_home` 은 **관절값과 `home_joint_positions` 의 차**(관절마다 0.05 rad)로 정해지고, 주행은
`at_home=true` 없이 `GoToZone` 을 **전부 거부한다**(계약 5절). 그래서 `sag_rad` 이 공차를 넘으면(`WARN`)
그 자체가 결함 신호다 — 스폰 자세가 중력을 못 버틴다는 뜻이고, 한 바퀴가 ②에서 선다.
팔 params 의 `home_joint_positions` 에는 **`spawn_settled` 의 값**을 넣는다(직후 값이 아니다).

## RC-5 읽기 함정

실습23·24 와 그 준비에서 값을 잘못 읽었거나 시험이 거짓으로 통과한 자리들이다. 전부 **관측이 아니라 해석**에서
틀렸다.

### `near` 는 닿은 것이 아니다

접촉 줄에는 `touch` 와 `near` 가 있다. **판정선은 `touch` 로 적는다.** 실습24 에서 `/Amr/` 가 든 줄 138개가
전부 `near sep=0.0200`·impulse 0 이었는데, 이는 닿은 것이 아니라 **`GROUND_CLEARANCE` 가 PhysX 접촉 보고
문턱(기본 `contactOffset` 0.02)에 정확히 걸쳐** 매 스텝 근접이 보고된 것이다. 0.03 으로 올려 없앴다.
→ `351228b` 이후에 `/Amr/` 가 든 `near` 가 나오면 **문턱 밖인데 찍혔다**는 뜻이다. `b=` 원문을 남긴다.

### `contact_watch=off` 는 "안 닿았다" 가 아니라 "안 봤다" 다

실습23a 에서 꺼져 있었다. 감시가 `--robot-usd`(M0609)에 묶여 있어 팔 자산이 없는 빈월드에서는 안 켜졌다.
지금은 팔과 무관하게 켜지고, 볼 몸체가 하나도 없으면 그 사실을 로그로 남긴다. **`observers …` 줄로 먼저 가른다.**

### 같은 epoch 의 리셋은 무시되지 않는다

`reset note=epoch N is not greater than current N` 을 찍고도 **실행한다.** 의도된 동작이다
(`reset.epoch_note` docstring: epoch 의 주인은 orchestrator, 스테이지는 받아들인다). 스테이지가 거절하면
"리셋했는데 안 됐다" 가 생기고 그쪽이 더 나쁘다. 막을 자리는 보내는 쪽이다.
→ 그 줄의 **수를 관측으로 센다.** 0 이 아니면 누가 중복을 보냈는지 찾는다.

### 프레임 이름이 같으면 트리가 우연히 이어진다 — 실패가 아니라 조용히 틀린 값

스테이지가 UR5 밑동을 `amr_1/base_link` 로 내고 있었다. 그 이름의 작성자는 base_driver 다. 밑동은 TF
발행기에서 `parentPrim` 이라 **child 로 나간 적이 없었고**, 이름이 같아서 base_driver 의 `odom → base_link` 가
**우연히** 부모를 붙여 주고 있었다 — 그 변환은 AMR 자세라 **값은 틀린 채로** 트리만 이어져 있었다.
팔이 `<zone>/cabinet` 을 조회했다면 조회 실패가 아니라 **AMR 위치만큼 어긋난 값**을 받았을 것이다.
→ 결정 47 로 `amr_1/ur_arm_base_link` 로 갈랐고, `map → 밑동` 을 스테이지가 낸다(계약 #423).
**판정선에 `view_frames` 로 "뿌리가 `map` 하나" 를 넣는다** — 갈라 놓으면 끊긴 트리가 새 위험이다.

### 프레임 이름은 프림 이름이 아니라 `isaac:nameOverride` 가 정한다

9/21 에 "Isaac 은 프림 이름으로 프레임 이름을 짓고 프림 이름에 `/` 를 못 쓰니 슬래시 이름을 못 만든다" 고
보고했는데 **틀렸다.** `ur5_cell.add_camera_and_tf` 가 `amr_1/base_link` 를 이미 그 속성으로 내고 있었다.
`ROS2PublishTransformTree` 의 입력만 보고 판단했고 프림 속성을 안 봤다.
→ 계약 표기(`bed_a1/cabinet`)를 그대로 낼 수 있다. 안 내는 이유는 **못 해서가 아니라 계약이 단일 작성자를
`zones_tf` 로 정했기 때문**이다.

### 여유 시험은 **보는 상자 목록**만큼만 본다

하루에 세 번 같은 종류로 걸렸다. 전부 "시험이 거짓으로 통과" 였다.

| 빠져 있던 것 | 드러난 결함 |
| --- | --- |
| 조제실 상자 전부 | 적재 자리가 조제실 벽에서 **0.55 m** — AMR 이 설 수 없는 자리 |
| 모형 없는 병상 세 자리 | 그 자리의 통로가 빈 것으로 계산됨 |
| UR5 받침대·상판(`ur5_cell` 이 따로 만들어 `room()` 에 없다) | 적재 자리가 받침대에서 **0.074 m** |

→ 여유를 계산할 때는 **장면이 실제로 얹는 상자 전부**를 모은다. 목록을 좁혀야 할 이유가 있으면
(적재 자리처럼 가까이 서야 하는 곳) **예외가 아니라 다른 규칙**을 적고 그 이유를 시험 본문에 남긴다.

### 여유는 반폭이 아니라 회전 외접 반경으로 본다

침상 접근 자리는 두 줄이 통로 하나를 공유해 **같은 자리에서 yaw 만 ±π/2 로 돈다.** 반폭(0.40)으로 보면
회전에서 벽을 친다. 외접 반경은 **0.7106**(계획 footprint 1.10 × 0.90 기준)이다.
그리고 **실측 bbox 와 계획 footprint 는 다르다** — 장면 상자는 실측(`AMR_BBOX`), 여유 계산은 계획값
(`AMR_FOOTPRINT`, 큰 쪽)을 쓴다. 둘이 왜 다른지는 확인하지 못했으므로 **값을 맞추지 않고 관계만** 잡는다.

### 정지 기하는 추종 오차를 모른다

여유 수치는 전부 선분과 상자 사이의 **정지 거리**다. 추종 오차(모서리 자르기 + 한 주기 이동량)는 주행이 준
0.065 를 상수로 더했을 뿐이고, 위치 추정 오차는 빈월드라 0 으로 뒀다. **실제 최소 이격은 L3 에서 잰다.**

### 스테이지가 "늦게 붙인" 것이 아니라 팔이 아직 덜 온 것이다

`amr suction on distance=…` 이 팔의 `gripper on` 보다 늦게 뜨면 스테이지 부착이 느린 것처럼 보인다.
lap14 의 여섯 픽이 갈라 줬다(9/21): **벨트 픽 0.350 / 0.016 / 0.166 s, 트레이 픽 0.017 ×3.**
트레이는 발행 주기 한 번으로 일정하고 **벨트에서만 흔들린다.**

팔의 도달 판정은 **관절 공차**(0.05 rad)인데 그것이 만드는 **TCP 오차는 자세마다 다르다** —
벨트 파지(뻗은 비율 78 %)에서 최악 0.073 m, 트레이(49 %)에서 0.056 m 다. 흡착 한계는 0.04 m 라
**벨트에서는 "도착" 뒤에도 공구가 흡착 거리 밖일 수 있다.** 스테이지는 매 스텝 제대로 재고 있다.

> 관절 공차 하나가 자세에 따라 서로 다른 TCP 오차가 된다. **"도착했다" 는 관절 말이고 "닿았다" 는
> 공구 말이다.** 두 말이 다른 자리에서 지연이 생긴다.

공차를 조이면 **같은 기다림이 도달 확인 쪽으로 옮겨갈 뿐**이고 거짓 "미도달" 위험만 는다.
`grasp_hold_timeout` 으로 기다리는 것이 맞다.

### 봉투가 트레이에 있는데도 검출이 0 건일 수 있다

lap12 ⑧: 팔이 `POUCH_LOADED amr_1/deck_slot_1` 까지 갔는데 `/amr_1/sim/pouches` 1268 건이 전부
빈 배열이었다. **봉투는 트레이에 있었다 — 장부에만 없었다.**

팔이 봉투를 들어 벨트를 벗어나면 `pouch_left_belt → remove_pouch` 가 주차장으로 보내고
`pool.in_use` 에서 지운다. 그것을 막는 분기가 `cell`(받침대 셀)만 보고 있어 합본에서 안 돌았다.
**흡착이 매 스텝 TCP 로 다시 끌어와서 화면은 멀쩡했다.**

> 물리와 장부가 갈리면 **화면으로는 못 잡는다.** ⑤ 는 성공으로 보이고 ⑧ 만 죽는다.

지금은 `WARN pouch_parked SKIPPED` 가 뜬다. 그 줄이 보이면 분기가 또 뚫린 것이다.

### `wrist_3 ↔ TrayFloor` 0.007–0.009 는 정상이다

턱을 0.03 으로 낮춘 뒤 남은 `near` 는 전부 이것이다. **공구가 봉투를 집으러 바닥까지 내려간 것**이고
봉투 두께가 0.01 이라 그 값이 나온다. 없어져야 할 것은 `forearm·wrist_1 ↔ TrayWallYMinus` 쪽이고,
그것은 lap14 에서 0 줄이 됐다.

## RC-6 병원 전 구간 (`hospital-full`, #527)

재범 결정 9/23: 병원 씬에서 웹 주문 → (필요하면 M0609 보충) → 조제기 → 봉투가 **씬의 컨베이어**로 창구 A1 끝 롤러
(`ConveyorTrack_02/Rollers_01`)까지 → dock_1 의 AMR 합본이 롤러 끝에서 집는다 → 병상 보관함 → 도크.
**L3 미실행.** 오프라인(단위 시험·usd-core)만 봤다. 잰 값과 추정값은 PR 본문 표에 있다.

- 컨베이어: 참조 아래서 씬 그래프가 안 돈다(#240). 스테이지가 `hospital_conveyor_surfaces.json` 의 표면 속도를
  19 몸체에 직접 쓰고, 봉투가 끝 롤러에 닿으면 전부 0 으로 한다(참조 탐침과 같은 방식).
- 조제실 v2 모듈은 `--v2-offset -7.85 9.50` 평행이동이다. 우리 벽·벨트·적재 자리·배출구 상자는 없다.
- `pharmacy/belt_end`·보관함·인식표는 `--zones-file`(zones.hospital.yaml)에서 읽는다.

Isaac 셸 환경은 sim/README 0.5단계 절차 0 그대로다. `$REPO`·`$COMBINED`(ridgeback_ur5.usd)·`$M0609` 는 사이트 값이다.

```bash
# I1 스테이지만: 봉투 하나가 A1 롤러 끝까지 가는가(팔·주행 없음)
~/isaacsim/python.sh $REPO/sim/standalone/pharmacy_stage.py --preset hospital-full \
  --base-usd $REPO/sim/scenes/hospital_navigationv1.usda --amr-start -8.238 4.169 --amr-combined $COMBINED \
  --order-pool $REPO/src/rokey_p3_orchestrator/config/order_pool.hospital.yaml --duration 300 2>&1 | tee /tmp/p3-hf-i1.log
#   다른 셸(시스템 Jazzy, 같은 도메인), `stage ready` 뒤:
ros2 topic pub -w 1 --once /isaac/pharmacy/dispense_request std_msgs/msg/String \
  "{data: '{\"order_id\":\"ord-0001\",\"request_id\":\"r001-0001\",\"v\":1}'}"
timeout -s INT 120 ros2 topic echo /isaac/events

# I2 M0609 보충 한 번: I1 명령에 M0609 자산을 더하고 팔 노드를 띄운다
#   --robot-usd $M0609/Collected_m0609_gripper/m0609_gripper.usd \
#   --urdf $M0609/doosan-robot2/urdf/m0609_isaac_sim.urdf --robot-description $M0609/rmpflow/m0609_description.yaml
ros2 run rokey_p3_manipulation m0609_arm --ros-args -p use_sim_time:=true -p scene_version:=2 -p v2_seed:=7 \
  -p v2_guarded_module_path:=false          # 'v2 계획 캐시: 16/16칸' 을 기다린다
timeout 150 ros2 action send_goal --feedback /m0609/refill rokey_p3_interfaces/action/Refill "{item_id: drug-amox, slot: 0}"

# I3 전 구간(참값 센서)이다. 창 모드 한 바퀴다. 마스터에서 도는 병원 회차는 이것 하나다(재범 9/23).
#   먼저 조제실 입력을 만든다. 한 번만 하면 된다. 씬이나 조제기 에셋이 바뀌면 다시 한다.
#   pxr 이 없으면 준비기가 스스로 Kit 을 headless 로 띄운다. 회차가 아니다. 입력 만들기다.
~/isaacsim/python.sh $REPO/sim/standalone/prepare_workcell_integration.py \
  --base-usd $REPO/sim/scenes/hospital_navigationv1.usda \
  --dispenser-usd $REPO/src/rokey_p3_description/models/dispenser/dispenser.usdc \
  --output ~/markle_tmp/m2-hospital-base-<SHA>
#   stdout 한 줄: {"cells": 18, "obstacles": …, "round_center": [-8.05, 11.115, 0.98]}
#   같은 폴더의 dispenser-placement.json 이 조제기 검사 결과다. scene_geometry=PASS 다.
P3_WORLD=hospital P3_SIM_SENSORS=1 P3_AMR_COMBINED=$COMBINED P3_UR5_ARM_PARAMS=<합본 팔 params> \
  P3_HOSPITAL_SCENE=~/markle_tmp/m2-hospital-base-<SHA>/base.usda \
  P3_WORKCELL_LAYOUT=~/markle_tmp/m2-hospital-base-<SHA>/workcell.json \
  P3_DOMAIN=<도메인> P3_M0609=$M0609 P3_DISPENSER_FILE=<재고 파일> tools/demo_v2.sh up
#   웹에서 ord-0001(bed_a1) 한 건. 끝나면 tools/demo_v2.sh down
```

`P3_WORKCELL_LAYOUT` 은 병원에서 필수다. 비우면 기동이 멈춘다. 빈월드 조제실(`--preset hospital-full`)로 되돌아가는 길은 없다(재범 9/23). 위 준비기가 만든 `base.usda` 를 쓴다. 실습37 의 `integrated-09/base.usda` 는 원통 투입구를 (+0.30, −0.10, 0) 옮긴 저작이다. 조제기 검사에서 멈춘다(#496 결정, 9/23 `3cf412c`).

판정선(결과 전에 고정. 막으려는 위험 → 재는 값 → 기준):

| 단계 | 위험 | 재는 값(줄) | 기준 |
| --- | --- | --- | --- |
| I1 | 씬 기하가 안 실려 끝 판정이 빈 상자로 선다 | `hospital_conveyor … "bodies":19 … terminal_surface` | 19 몸체, 끝 롤러 두께 0 < t < 0.05 |
| I1 | 출발점이 트랙 상자 밖이라 첫 관측에서 벨트가 풀린다 | `hospital belt_model … spawn_on_belt=` | `True`, `WARN hospital spawn` 0 줄 |
| I1 | 스테이지(로봇·풀이 있는 장면)에서 컨베이어가 안 돈다 | `event …DISPENSED…` → `hospital pouch_at_end …` | 한 번씩, `sim_s_since_dispense` ≤ 60 (잰 값 34.58) |
| I1 | 롤러 끝을 넘어 떨어진다 | `belt note=pouch_left_belt` 수, `pouch_at_end` 의 `in_sensor_zone` | 0 줄, `True` |
| I2 | 평행이동한 모듈에서 계획이 달라진다 | 팔 노드 `v2 계획 캐시` | 16/16칸 |
| I2 | 보충이 씬 고정물에 닿는다 | Refill 결과, `refill_ros released … target=`, `contact … touch` | success, `round`, 병원 prim 과의 touch 0 |
| I3 | 한 바퀴가 어디서 끊기는지 모른다 | 오케스트레이터 트립 끝 줄, `/isaac/evaluator/cabinet` | 주문 1건 완료, `bed_a1/cabinet` present=true, AMR 도크 복귀 |

기록: `hospital_conveyor`·`hospital belt_model`·`hospital pouch_at_end` 줄 원문, `stop reason=… rtf=…`,
롤러 끝 봉투 캡처 1장. 기준을 못 넘으면 그 단계에서 멈추고 다음 단계로 가지 않는다.
