# 실습15 — master02, 벨트 관측 opt-in 토픽 확인(RC-3a)

| 항목 | 값 |
| --- | --- |
| 번호 | 실습15(계획표). 아래 15b 는 스택을 붙인 A/B 대조다. 실습14(재범 화면 버튼 리허설)는 아직 하지 않았다 |
| 날짜·시각 | 2026-09-20. 15a 09:17:17-09:20, 15b 09:37-09:47(KST) |
| 장소 | `master02`(IsaacSim07), 도메인 117(이 회차 뒤 `master02` 는 118 로 옮겼다), **headless** |
| 돌린 사람 | `master02` 원격 실행(기동·중지)과 읽기 전용 관측 |
| 출처 | master02 관측 보고 |
| 원본 | `master02` `$HOME/markle_tmp/m2-rc3/`: `rc3a.log`(1.1 MB), `rc3a.typescript`+`rc3a.timing`, 스크립트 `run_rc3a.sh` |
| 기록 | 이 기록은 `master02` 화면을 직접 보지 않고 썼다 |

## 목적

[L3 sim·컨베이어 runbook](../runbooks/l3-sim-conveyor.md) 의 RC-3 3a. 벨트 관측 opt-in 을 켰을 때 Isaac JSON 토픽 목록이 런카드 기대대로 바뀌는지 본다.

## 구성

| 부분 | 값 |
| --- | --- |
| 트리 | `release/20260920-644ec0a`. [실습12](practice-12.md) 3회차와 같은 트리이고 재빌드하지 않았다(12c 의 `eba5351` 과는 다르다) |
| 명령 | `--preset demo-ros-refill-v2 --belt-observation --belt-fail-closed --order-pool <repo>/src/rokey_p3_orchestrator/config/order_pool.yaml "${P3_ASSETS[@]}" --headless` |
| 런카드에서 바꾼 것 | 하나(`--headless`). 그 밖은 원문·기본값이고 `--gripper-command-seq`(3b)·`observation_guard`·ArmClearance 는 켜지 않았다 |
| 설정 확인 | `belt_observation=true`, `belt_fail_closed=true`, `ur5=false`, `mode=ros`, `scene=v2`, `view=overview`, `duration=0.0`, `loop=0`, `belt_presurface=false`, `gripper_command_seq=false` |
| 끝 | `stop reason=sigint updates=11127 wall_s=188.000 loop_hz=59.19 sim_s=185.450 rtf=0.986 dispensed=0 render_products=0 ur5=off contact_watch=on`. 런카드 원문에 `--duration` 이 없어 SIGINT 로 내렸다 |

## 관측 (master02)

판정 줄은 **통과**다. 런카드 기대값("`ros json topics pub=` 에 `/isaac/pharmacy/belt_observation` 이 더해진다")과 맞는다.

```text
ros json topics pub=['/isaac/events', '/isaac/pharmacy/belt', '/isaac/pharmacy/belt_observation',
                     '/isaac/pharmacy/dispense_response', '/isaac/sim/reset_response']
sub=['/isaac/pharmacy/dispense_request', '/isaac/pharmacy/pick_notice', '/isaac/sim/reset_request']
```

- RC-1 의 기본 네 개에 `belt_observation` 하나만 더해졌고 새는 토픽은 없다.
- 준비 단계 `step=… ok` 여섯(build_room, build_rail_and_mount_robot, create_conveyor_belt, create_pouch_pool, world_reset, articulation_ready) 모두 ok. `FAILED`·`ERROR`·`Traceback` 0줄.
- 그 밖의 준비 줄: `scene base_usd=-`(병원 씬 없음, 기대대로), `room scene=v2 shelves=4 cells=16 kinds=['cylinder','module']`, `refill_ros on scene=v2 canisters=16`, `refill_ros inventory present=16/16 last_release=None`, `viewport view=overview scene=v2 eye=[0, -2.53, 2.17] target=[0, 0.75, 1.10]`, `belt body=xform presurface=False requested_speed=0.15`.

### 이 회차로는 못 보는 것

1. **`dispensed=0` 이고 `belt note=` 줄이 하나도 없다.** `mode=ros` 라 스테이지는 ROS 로 오는 `dispense_request` 를 기다리는데, 이 회차는 스테이지만 띄우고 스택을 붙이지 않았다. 그래서 배출이 일어나지 않았다. 토픽에는 **유휴 값이 흘렀다**(4.99-5.00 Hz, 연속 표본 6개, seq +12/0.2 s, 따로 확인). 못 본 것은 **트립이 도는 중의 전이**다. 런카드 3a 가 정한 범위("여기서는 Isaac JSON 토픽만 본다")와는 맞는다.
2. **`--belt-fail-closed` 단독 효과가 분리되지 않는다.** 런카드가 두 인자를 한 명령에 두기 때문이다. `belt note=pouch_lost` 는 0줄인데 배출이 없었으므로 "fail-closed 가 정상" 의 근거가 되지 못한다.
3. **대조 회차가 없다.** opt-in 을 끈 같은 구성이 없어 비교 기준이 런카드 기대값뿐이다(실습12 는 `--mode selfdemo` 라 preset 이 달라 대조가 안 된다).

셋은 실습15b 의 A/B 회차가 메운다(A = opt-in 켜고 스택 붙임, B = opt-in 빼고 같은 구성). 15b 회차 A 는 09:40 에 트리 `eba5351`, 도메인 118 로 시작했다.

## 15b — 스택을 붙인 A/B 대조

RC-3a 가 못 본 셋을 메우는 회차다. A 는 opt-in 을 켜고 스택을 붙였고, B 는 opt-in 을 끈 같은 구성(기준값)이다.

| 부분 | 값 |
| --- | --- |
| 트리 | `release/20260920-eba5351`([실습12](practice-12.md) 12c 와 같은 트리, 재빌드 없음) |
| 도메인 | **118**. 슬롯을 나눴다(`master01` 117 / `master02` 118). 계기: 09:27:59 에 `master01` 의 기동 전 확인이 117 `/clock` 발행자 1 에서 멈췄고 그 발행자가 12c 였다(GID 일치). 기동 전 118 이 빈 것을 확인했다(발행자 0, 노드 0) |
| 런카드에서 바꾼 것 | 하나(`--headless`) |
| 시연과 다른 점 | `use_stub_m0609:=true`(팔 노드 없음), `dispenser_file` 이 저장소 기본(약품마다 5개라 보충이 없다). 웹은 띄우지 않았다(release 워크트리에 `web/backend/.venv` 가 없다) |
| run | A 1차 `20260920T003753Z-master02-97974dc6`, A 2차 `20260920T003933Z-master02-d5ae04f3`, B `20260920T004646Z-master02-2bf87ffb` |

| | A(opt-in 켬) | B(opt-in 끔, 기준값) |
| --- | --- | --- |
| `ros json topics pub=` | events, belt, **belt_observation**, dispense_response, reset_response(5) | events, belt, dispense_response, reset_response(**4**) |
| 종료 줄 | `sigint … loop_hz=59.31 rtf=0.989 dispensed=2 render_products=0 ur5=off` | `sigint … loop_hz=59.61 rtf=0.994 dispensed=1 render_products=0 ur5=off` |
| `belt note=` | `stop_belt` 2회 | `stop_belt` 1회 |
| `belt note=pouch_lost` | 0줄 | 0줄 |
| `ERROR`·`Traceback` | 0·0 | 0·0 |
| 노드 종료 | 8개 모두 `finished cleanly` | 8개 모두 `finished cleanly` |

**판정: 통과.** A 에만 `/isaac/pharmacy/belt_observation` 이 더해졌고 나머지 목록은 같다. 새는 토픽은 없다.

A 에서 관측 토픽이 실제로 전이한다(`BeltObservation`, Publisher 1, 240 메시지, `seq` 11891 → 14744 단조, epoch 1):

| sim | mode | occupancy | pouch_zone | pouch_motion | belt_command_applied | 국면 |
| --- | --- | --- | --- | --- | --- | --- |
| 198.400 | 2 | 2 | 1 | 1 | 1 | 이송 중 |
| 202.966 | 2 | 2 | 2 | 1 | 2 | 종단 구역 진입 |
| 203.350 | 2 | 2 | 2 | 2 | 2 | 멈춤 + 정지 명령 |
| 203.716 | 1 | 1 | 0 | 0 | 2 | 회수 뒤 |

런카드의 "이송 중 1·1·1 → 종단 정착 2·2·2, 회수 뒤 mode 1·occupancy 1" 과 맞는다. 같은 트립의 이벤트는 193.000 `REQUEST_ACCEPTED` → 194.016 `DISPENSED` → 203.266 `POUCH_AT_END` → 203.616 `POUCH_PICKED` → 203.933 `ORDER_DONE` → 205.483 `DOCKED` 다. 어댑터의 `dropped`·`observation_*` 는 0건이다.

트립(`events.jsonl` 정본, 세 회차 모두 12단계 완주):

| 회차 | 구간(sim s) | 한 바퀴 |
| --- | --- | --- |
| A 1차 | 94.000 → 106.500 | 12.50 |
| A 2차 | 193.000 → 205.483 | 12.48 |
| B | 34.000 → 46.883 | 12.88 |

- 실습12 RC-1 관측(12.35-13.15)과 같은 범위다. **opt-in 을 켠다고 트립이 느려지지 않는다.** 오히려 끈 B 가 0.3-0.45 s 늦고, 그 차이는 `AMR_DOCKED_LOAD` 까지의 초기 구간(1.02 / 1.00 / 1.40)에서 거의 다 생긴다. **표본이 한 번씩이라 구성 차이인지 회차 산포인지는 단정할 수 없다.**

문서에 남길 셋:

1. `Deliver 결과 success=False [ord-0002=HOLD_RETURN]` 은 결함이 아니다. `pharmacy_only:=true` 의 설계 동작이고 A·B 양쪽에 다 난다([L3 스택 조합 runbook](../runbooks/l3-stack-combos.md) 1절). 증거 실행의 성공 검사에도 `last_status_hold_return_pharmacy_only: true` 가 있다. `master01` 시연 구성에서도 같은 줄이 난다.
2. `--belt-fail-closed` 는 **미확인**이다. A 에서 켜져 있었지만 `belt note=pouch_lost` 가 0줄이다. 봉투를 잃는 상황이 만들어지지 않았으므로 "정상 동작 확인" 이 아니다. 소실을 강제하는 회차가 따로 필요하다.
3. orchestrator 로거 크래시(P28)는 **재현 조건이 만들어지지 않았다**. **P28 재현은 한 run 안에 INFO Note(슬롯 장착)와 WARN Note(보충 실패)가 같이 나와야 한다**(같은 호출 지점의 로그 수준이 바뀔 때만 나기 때문이다). 이번 회차는 그 조건이 없다. 보충이 한 번도 없다(`Refill`·`grasp miss` 0줄, `dispenser_file` 이 저장소 기본). 전량 성공하거나 전량 실패하는 회차도 마찬가지라 수정 전 트리로도 죽지 않는다. `Logger severity cannot be changed between calls` 0건, `process has died` 0건이다.
   **따라서 "master02 에서 재현 안 됨" 이 아니고, 수정 확인으로도 쓸 수 없다.** #342 의 L3 확인은 master01 의 13e 세 회차에서 났다([실습13](practice-13.md)). `--hold-distance 0.0388` 로 한 칸만 성공하게 만들어 INFO Note 와 WARN Note 를 한 run 에 섞었다: 같은 인자·절차로 트리만 바꿔 `45d7fe3` 는 살고 `2c68b73` 는 `rcutils_logger.py:343 in info` 에서 죽었다. 죽은 쪽의 마지막 Note 는 WARN(`Refill drug-ibu: 1/3 번째 실패`)이고, **예외를 일으킨 INFO Note(`슬롯 … 장착`)는 찍히기 전에 터져 로그에 남지 않는다** — 로그만 보면 INFO 가 없어 보이는 것이 정상이다.

덧: 처음에 "A 1차에 중간 이벤트가 빠졌다" 고 보고됐다가 정정됐다. 그때 본 파일이 `topic echo` 의 부분 표본이었고, run 디렉토리 원본에는 세 회차 모두 12단계가 온전하다. 이벤트는 run 디렉토리의 `events.jsonl` 을 정본으로 쓴다.

## 캡처·녹화

15a·15b 모두 없다. **왜 없는가**: `--headless` 로 돌았고, 그 시점 `master02` 에는 계정 `rokey` 가 쓸 수 있는 X 디스플레이가 없었다([실습12](practice-12.md) 12c 의 확인 항목과 같다). preset `demo-ros-refill-v2` 가 `view=overview` 를 설정하므로(로그에 `viewport view=overview` 가 찍혔다) **창 모드였다면 이 뷰로 화면이 남았을 회차**다.

시점 주의: 9/20 09:3x 에 재범이 `Xvfb` 를 설치했다(`/usr/bin/Xvfb`, master02 보고). 그 뒤 회차부터는 로그인 없이도 가상 디스플레이로 창 모드 녹화가 된다. 실습12·15·12c 의 "영상 없음" 사유는 설치 전 것이라 그대로 유효하다.

**자동 로그인은 두 마스터 어디에도 설정돼 있지 않았다(9/20 10:0x 확인).** 그때 `master01`·`master02` 의 `custom.conf` 는 sha256 이 같고(`a497ef00…40a5a`) 둘 다 원본이었다. `master01` 이 창 모드를 쓰는 이유는 자동 로그인이 아니라 9/16 21:31 의 콘솔 로그인이 아직 살아 있기 때문이다(`Type=x11`, `/tmp/.X11-unix/X1` 소유자 `rokey`). `master02` 는 매일 재부팅되므로 그 방법이 통하지 않는다.

**`master02` 자동 로그인은 10:23:42 에 적용됐다**(13:0x 재확인). `[daemon]` 절이다. **앞 문단의 "설정돼 있지 않다" 는 10:0x 시점이다.** 근거: `custom.conf` 에 `AutomaticLoginEnable=true`·`AutomaticLogin=rokey` 가 들어갔고 sha256 이 `a497ef00…40a5a` 에서 **`8e1ebbe7…5bda`**(600 B)로 바뀌었다. 10:23:43 에 gdm 이 재시작되며 logind session 66(`rokey`, seat0, tty2, `Type=x11`)이 올라왔고 `/tmp/.X11-unix/X0` 의 소유자가 `rokey` 가 됐다. `master01` 은 여전히 미설정이다(13:0x 재확인. mtime 2026-08-28 17:10:06, sha256 `a497ef00…40a5a`, 활성 `AutomaticLogin` 줄 0, gdm 기동 2026-09-16 21:30:53 으로 오전 값과 같다). **이제 두 기계의 `custom.conf` 해시는 갈린다.** **이 문단 앞쪽의 sha256 과 "설정돼 있지 않다" 는 10:0x 시점 값이다.**

대체 증거: `rc3a.log`, `scriptreplay -t rc3a.timing rc3a.typescript`.

## 문제

새로 생긴 문제는 없다. 15a 가 못 본 셋 가운데 실제 관측 흐름과 대조 기준은 15b 가 메웠고, `--belt-fail-closed` 는 아직 미확인이다.

## 다음 실습에서 확인할 것

- `--belt-fail-closed`: 봉투 소실을 강제하는 회차.
- P28 재현 조건(보충이 나는 재고)으로 한 회차를 돌릴지는 `master01` 실습13c 결과를 보고 정한다.
- 도메인 배정(`master01` 117 / `master02` 118): 슬롯 단위로 나눈 것이고 영구 여부는 재범 결정 대기다. `docs/setup/ros2-wired-network.md` 의 조 배정은 115-121 이다.
