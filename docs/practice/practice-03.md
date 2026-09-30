# 실습3 — master02, 실습1 문제 개선 확인(3-A)과 오케스트레이터 레일 보충 첫 실물 시험(3-B)

| 항목 | 값 |
| --- | --- |
| 번호 | 실습3 |
| 날짜·시각 | 2026-09-18. 3-A 10:56:03-11:00:3x, 3-B 11:01:59-12:20:28(KST) |
| 장소 | `master02` |
| 돌린 사람 | 재범(화면). 기동·웹 명령은 `master02` 원격 셸 |
| 기동·로그 | `master02` tmux |
| 출처 | master02 종료 보고 원문. 이 기록은 `master02` 화면을 직접 보지 않고 썼다 |

## 목적

| 부분 | 목적 |
| --- | --- |
| 3-A | `selfdemo-refill --refill-loop 4`, 창 모드. [실습1](practice-01.md) P1-P5 개선 확인: 속도 80%·가감속, 접촉 기록, 2축 색 구분, Ctrl-C `exit 0` |
| 3-B | `demo-ros-refill` + 팔 노드 `rail_enabled`(`max_joint_speed` 0.3) + 어댑터 스택(`dispenser_refill` 슬롯 a=1, b=0) + 관제 웹(`--allow-commands`). 오케스트레이터가 `/m0609/refill` 로 레일 보충을 구동하는 첫 실물 시험([실습2](practice-02.md)의 목적을 이어받음). 팔 속도는 아직 0.3 rad/s 다(팔의 속도 80% 커밋 미반영) |

## 구성

| 부분 | 값 |
| --- | --- |
| 트리 | `master02` 의 `candidate/practice-03` = `main` `bfdec83`(#154 포함)에 `git merge --no-ff origin/feat/sim-practice1-fixes`(#157 `9679d40`, #149 `ae340db`·#128 `174bb6a` 포함) → `7cd4b90`(`git merge --no-ff --no-edit`, detached). push 하지 않았다. 빌드 `Summary: 7 packages finished [12.6s]`. 실행 코드는 `main` `eda7cb4` 와 같다. 웹은 `candidate/practice-02` 의 venv python 으로 `practice-03` 의 `web/backend` 를 띄웠다 |
| 커밋 확인 | `bfdec83` 은 `main` 에 있다(#154 머지 커밋). `9679d40` 은 #157(`feat/sim-practice1-fixes`, 이후 `main` 에 머지)의 헤드이고 `ae340db`·`174bb6a` 를 조상으로 갖는다. #128 은 그 뒤 `main` 에 머지됐다(`b0e30b0`). `7cd4b90` 은 원격에 없어 확인할 수 없다 |
| 명령 | 아래 원문 |

### 변수와 tmux 줄 원문

개인 경로는 변수로 둔다. 홈 줄임 기호는 `$HOME` 으로 바꿨다. 그 밖은 원문이다.

| 변수 | 9/18 값 |
| --- | --- |
| `P` | `/home/rokey/Dev/cobot3_ws/candidate/practice-03` |
| `I` | `$P/install` |
| `M` | `/home/rokey/cobot3_ws/isaacpjt/M0609` |
| `LOG` | 3-A `$HOME/markle_tmp/p3a_stage.log`, 3-B `$HOME/markle_tmp/p3b_stage.log` |
| `KL` | `$HOME/markle_tmp/kit-practice3A-$(date +%H%M%S).log` → `kit-practice3A-105600.log`. 3-B 는 `kit-practice3B-110156.log` |

3-A:

```bash
tmux new -s m2-stage -d; tmux send-keys -t m2-stage "cd $P && env -i HOME=\$HOME USER=\$USER TERM=\$TERM PATH=/usr/local/bin:/usr/bin:/bin DISPLAY=:1 XAUTHORITY=/run/user/1000/gdm/Xauthority XDG_RUNTIME_DIR=/run/user/1000 ROS_DISTRO=jazzy RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DOMAIN_ID=117 FASTRTPS_DEFAULT_PROFILES_FILE=\$HOME/.ros/fastdds_whitelist.xml LD_LIBRARY_PATH=\$HOME/isaacsim/exts/isaacsim.ros2.bridge/jazzy/lib \$HOME/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset selfdemo-refill --refill-loop 4 --kit-log-file $KL --kit-log-verbose --robot-usd $M/Collected_m0609_gripper/m0609_gripper.usd --urdf $M/doosan-robot2/urdf/m0609_isaac_sim.urdf --robot-description $M/rmpflow/m0609_description.yaml 2>&1 | tee -i $LOG; echo \"exit=\${PIPESTATUS[0]}\"" Enter
```

3-B(스테이지 줄의 `env -i …` 부분은 3-A 와 같다. 원문도 줄여 보냈다):

```bash
tmux new -s m2-stage -d; tmux send-keys -t m2-stage "cd $P && env -i … \$HOME/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset demo-ros-refill --kit-log-file $KL --kit-log-verbose --order-pool $P/src/rokey_p3_orchestrator/config/order_pool.yaml --robot-usd $M/Collected_m0609_gripper/m0609_gripper.usd --urdf $M/doosan-robot2/urdf/m0609_isaac_sim.urdf --robot-description $M/rmpflow/m0609_description.yaml 2>&1 | tee -i $LOG; echo \"exit=\${PIPESTATUS[0]}\"" Enter
tmux new -s m2-arm -d; tmux send-keys -t m2-arm "source /opt/ros/jazzy/setup.bash && source $I/setup.bash && export ROS_DOMAIN_ID=117 && ros2 run rokey_p3_manipulation m0609_arm --ros-args -p use_sim_time:=true -p rail_enabled:=true -p max_joint_speed:=0.3 2>&1 | tee \$HOME/markle_tmp/p3b_arm.log" Enter
tmux new -s m2-stack -d; tmux send-keys -t m2-stack "source /opt/ros/jazzy/setup.bash && source $I/setup.bash && export ROS_DOMAIN_ID=117 && ros2 launch rokey_p3_bringup stub_loop.launch.py use_isaac_adapter:=true pharmacy_only:=true publish_clock:=false emulate_m0609:=false use_stub_m0609:=false dispenser_file:=\$HOME/markle_tmp/dispenser_refill.yaml order_pool_file:=$P/src/rokey_p3_orchestrator/config/order_pool.yaml run_host:=master02 2>&1 | tee \$HOME/markle_tmp/p3b_stack.log" Enter
tmux new -s m2-web -d; tmux send-keys -t m2-web "source /opt/ros/jazzy/setup.bash && source $I/setup.bash && export ROS_DOMAIN_ID=117 && cd $P/web/backend && /home/rokey/Dev/cobot3_ws/candidate/practice-02/web/backend/.venv/bin/python -m app.main --host 127.0.0.1 --port 8000 --allow-commands --static $P/web/frontend --order-pool $P/src/rokey_p3_orchestrator/config/order_pool.yaml --zones-file $P/src/rokey_p3_description/config/zones.yaml 2>&1 | tee \$HOME/markle_tmp/p3b_web.log" Enter
```

재고 파일 `$HOME/markle_tmp/dispenser_refill.yaml`: 약품마다 slot a count 1, slot b count 0, shelf 그대로. 스크립트는 `start_practice3A.sh`, `start_practice3B.sh`(저장소 밖).

## 관측

### 사람이 본 것 (재범 원문)

- 10:59(3-A 중): "이슈가 좀 있는데.... Screenshot from 2026-09-18 10-59-12 이거에서 보면 로봇이 중간이 짤려져 있음... 속도는 괜찮고, 레일 모양도 괜찮음. 그리고 지금 멈췄음. 상황 공유하고 일단 다시 실습 올려. 그리고 웹도 올리고. 그래야 지금 실습을 보여줄 수 있을 것 같거든?"
  - "지금 멈췄음" 은 4번째 바퀴의 `next=finished`, 곧 정상 종료다.
  - 스크린샷은 `master02` 의 `Pictures/Screenshots/Screenshot from 2026-09-18 10-59-12.png`(저장소 밖).
- 11:04(3-B 중): "또정지했다". 그때는 요청이 끝나 대기 중이었을 뿐 정지가 아니었다.
- 12:20: "실습4-B 시작".

### 로그로 본 것 — 3-A

| 항목 | 값 |
| --- | --- |
| 시각 | 10:56:03 기동 전 확인(`others:[]`, 117 `/clock` 0), PLAY 10:56:13, 11:00:3x `m2-stage` tmux C-c |
| 보충 | 4바퀴(a/b/a/b) 모두 `canister_in_inlet=True`. 28.383·28.583·28.300·28.583 sim s(실습1 64 s → 28 s, P3 80%) |
| TIMEOUT | refill TIMEOUT 4. 매 바퀴 `above_inlet` error 0.0338-0.0352 m, `extra_s` 6.08, 그때 `joint_3` 0.115-0.117 rad |
| 접촉(P2) | 실제 힘: `link_4`↔`DispenserBody` impulse 540.6(c2b·c4b release), `link_5`↔`DispenserBody` 431.3(c3a retreat)·282.0(c1a retreat)·44-45(insert). 선반 쪽 `link_2`↔`ShelfBoard2`, `link_4`↔`ShelfSideRight` 는 impulse 0(근접 보고) |
| P6 경고 | `getAttributeCount/getTypes called on non-existent path /World/P3Pharmacy/Arm/Mount/m0609/link_2/visuals/MF0609_2_1` 4줄, onrobot `Unresolved reference` 1줄. 자산에는 `MF0609_2_1` 메시가 있다(pxr 로 확인) |
| 종료(P5) | `stop reason=sigint updates=15917 wall_s=271.578 loop_hz=58.61 sim_s=265.283 rtf=0.977 dispensed=22 render_products=0 ur5=off contact_watch=on`, **`exit=0`** |

### 로그로 본 것 — 3-B

| 항목 | 값 |
| --- | --- |
| 시각 | 11:01:59 기동(`others:[]`, `/clock` 0), 11:02:18 READY. 12:20:28 재범 지시로 `m2-stack`·`m2-web`·`m2-arm` → `m2-stage` tmux C-c |
| 종료 | 생존 wall 4729.7 s(약 79분). `stop reason=sigint updates=271229 wall_s=4729.718 loop_hz=57.35 sim_s=4518.917 rtf=0.955 dispensed=1 … contact_watch=on`, **`exit=0`** |
| 트립 | 2개(발행기 `r001`, 11:04:52 웹 리셋 뒤 `r002`), 모두 `HOLD_RETURN` `pharmacy_only` |
| 웹 명령 | `POST /api/reset` 1회(재범 "또정지했다" 뒤 넣음), `POST /api/requests` 0 |
| 보충 | 2회 성공(오케스트레이터 `/m0609/refill` → 팔 노드 레일 + M0609). 1차: REQUESTED 7.07 → grasp 21.217 → released `inlet=a` 40.500 → `REFILL_DONE` 42.93(35.9 s). 2차: REQUESTED 166.28 → grasp 180.433 → released `inlet=a` 201.317 → `REFILL_DONE` 203.83(37.6 s). 팔 로그 실패 0, "레일이 밀려" 0 |
| 접촉 | `link_4`↔`DispenserBody` impulse 10.04(sim 38.8)·7.95·7.78·4.35. 선반 쪽 impulse 0. 손가락↔`InletBWallXMinus` 11.2 |
| 타임라인 STOP | 2회(sim 248.383·250.717 = 11:06:24·11:06:27), 2/2 `physics_view recovered`. 누른 사람이 있었는지는 확인하지 못했다. 종료 때 closing STOP 1 |
| 스택 | stale/unknown 판정 0 |

로그 파일(`$HOME/markle_tmp/`, 저장소 밖): 3-A `p3a_stage.log`, `kit-practice3A-105600.log` / 3-B `p3b_stage.log`, `kit-practice3B-110156.log`, `p3b_arm.log`, `p3b_stack.log`, `p3b_web.log`.

## 문제

| 번호 | 무엇 | 출처 | 고치는 쪽 | PR |
| --- | --- | --- | --- | --- |
| P6 | 로봇 가운데가 안 그려진다 | 재범 "로봇이 중간이 짤려져 있음", 로그 `link_2/visuals/MF0609_2_1` non-existent 4줄 | `sim` | #162(머지) |
| P7 | 조제기 앞면 충돌 | 로그 `link_4`·`link_5`↔`DispenserBody` impulse(3-A 540.6·431.3, 3-B 10.04). 재범이 실습1 에서 말한 "기둥"(P2)으로 봤고 재범 확인 대기 | `sim` | #162(머지, 투입구 0.07 m 띄움) |
| P8 | `above_inlet` 도달 한계(error 0.0338-0.0352 m > 0.03) | 로그 3-A TIMEOUT 4 | `sim`·팔 | #162·#165(둘 다 머지) |
| 대기 표시 | 보충 대기를 멈춤으로 보게 된다 | 재범 3-B "또정지했다" | 웹 | #163(머지) |

P6·P7 의 PR 은 #162 제목("로봇 가운데 안 그려짐(link_2 인스턴스), 조제기 앞면 충돌(투입구 0.07 m 띄움), above_inlet 도달 한계")으로 적었다.

### 실습1 문제의 해소/남음 (3-A)

| 실습1 | 결과 |
| --- | --- |
| P1 약통 흔들림 | 재범 말·master02 보고에 없다. 미확인 |
| P2 기둥에 밀림 | P7 로 이어짐(해석, 재범 확인 대기) |
| P3 속도(스테이지) | 재범 "속도는 괜찮고", 바퀴 64 s → 28 s → 해소 |
| P4 2축 레일 | 재범 "레일 모양도 괜찮음" → 해소 |
| P5 Ctrl-C `exit=1` | 3-A·3-B 모두 `exit=0` → 해소 |

## 다음 실습에서 확인할 것

- P6·P7·P8 을 고친 판(#162·#165)으로 같은 장면을 본다. [실습4](practice-04.md) 가 그 트리다.
- 3-B 의 두 번째 보충이 웹 리셋 없이 이어지는지.
