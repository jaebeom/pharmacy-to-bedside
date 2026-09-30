# master02 M0609 보충 장면 띄우기

> **상태: 지난 기록 (2026-09-20 기준).** 지금은 [병원 한 바퀴 런카드](hospital-full.md)를 따른다.

- 대상: `master02` 에서 Isaac M0609 보충 스테이지(`sim/standalone/m0609_refill_stage.py`, 레일 없는 고정 받침)와 시스템 ROS 스택을 띄워 orchestrator → `/m0609/refill` → Isaac 팔 보충을 돌린다.
- 출처: 9/17 `master02` 에서 실제로 친 명령 원문. 이 문서를 쓰며 마스터에서 다시 돌리지 않았다.
  - 개인 경로는 아래 변수로 뺐다.
  - 홈 디렉토리 줄임 기호는 `$HOME` 으로 바꿨다.
  - 그 밖의 명령은 원문 그대로다.
- 9/17 에 이 장면으로 보충 2회가 돌았다(`ab90cd5` teach 세트, [일정](../planning/schedule.md)의 "9/17 저녁 현재").
- 공통 규칙은 [배포 runbook](deployment.md)과 [9/17 부터의 운영](../process/agent-workflow.md#917-부터의-세션-운영)을 따른다. Isaac 셸 환경은 [sim README 0.5단계](../../sim/README.md#05단계-m0609-보충-스테이지).

## 규칙

| 규칙 | 내용 |
| --- | --- |
| 도메인 | **`master02` 는 118**(결정 33, 9/20). `master01` 은 117 이다. 같은 값이면 섞인다([도메인 규칙](../setup/ros2-wired-network.md#도메인-규칙)) |
| 기동 전 확인 | 다른 Isaac 이 떠 있으면 **띄우지 않는다**(아래 1). 9/17 오후 다른 사용자의 Isaac 이 재기동된 관측이 있다([장비 목록](../setup/host-inventory.md#master02-공유-사용-관측-917)) |
| teach 값 | 한 실행에서 뽑은 한 세트만 쓴다. 다른 실행의 값과 섞지 않는다. `joint_6` 은 같은 자세라도 실행마다 2π 만큼 다른 값으로 갈릴 수 있다(기록 미확인). 아래 값은 **예시이고 실행마다 새로 뽑는다** |
| 내리기 | tmux 세션 이름으로 `C-c`(SIGINT)만 보낸다. PID 로 kill 하지 않는다. `pgrep` 은 멈췄는지 보는 읽기 전용 확인에만 쓴다 |

도메인 칸 보충:
- 두 마스터가 같은 유선망이라 같은 값이면 섞인다(결정 33 은 재범 결정이다).
- **명령마다 `ROS_DOMAIN_ID` 를 명시한다.** 셸 기본값에 기대지 않는다(9/17 기준 `master02` 의 `.bashrc` 는 115 였다. 지금 값은 확인하지 않았다).
- 아래 9/17 원문의 `117`·`115` 는 그때 값 그대로 두었다.

## 변수 (`master02` 9/17 기준 값)

| 변수 | 뜻 | 9/17 값 |
| --- | --- | --- |
| `CLONE` | 개발 clone(개인 작업 사본, 배포에 직접 쓰지 않음) | `/home/rokey/Dev/cobot3_ws/ROKEY_P3_A3` |
| `W` | 후보 커밋 worktree(Isaac 스크립트를 여기서 돌린다) | `/home/rokey/Dev/cobot3_ws/candidate/38b08eb` |
| `I` | 시스템 ROS install(`src/` 가 같은 커밋이면 재사용) | `/home/rokey/Dev/cobot3_ws/candidate/5d6a10b/install` |
| `M` | M0609 수업 자산 디렉토리 | `/home/rokey/cobot3_ws/isaacpjt/M0609` |
| `LOG` | Isaac 스테이지 로그 파일 | 덤프에 값 없음 |
| 조제기 설정 | 보충을 유도하는 `dispenser_file` | `$HOME/markle_tmp/dispenser_refill.yaml` (아래 6) |

`I` 는 `5d6a10b` install 이다. 두 커밋의 `src/` 가 같아서 재사용했다(`git diff --stat 5d6a10b 38b08eb -- src` 빈 출력, master02).

## 0. 후보 준비

```bash
cd $CLONE; git fetch origin; git worktree add ../candidate/38b08eb 38b08eb
cd /home/rokey/Dev/cobot3_ws/candidate/5d6a10b && source /opt/ros/jazzy/setup.bash && colcon build --symlink-install > ../5d6a10b_build.log 2>&1
```

## 1. 기동 전 확인 (Isaac 을 띄우기 직전마다)

**아래 명령의 `ROS_DOMAIN_ID=117` 은 9/17 원문 값이다. `master02` 에서 칠 때는 `118` 로 바꾼다.**

```bash
source /opt/ros/jazzy/setup.bash; date +%T; ROS_DOMAIN_ID=117 ros2 topic info /clock --no-daemon --spin-time 2 2>&1 | head -1; P=$(pgrep -af "isaacsim|kit/kit|kit/python" | grep -v -E "rtkit|polkit|pgrep|shell-snapshots"); echo "others:[$P]"; [ -n "$P" ] && exit 3
```

| 결과 | 출력 |
| --- | --- |
| 띄워도 된다 | `Unknown topic '/clock'` 와 `others:[]` |
| 띄우지 않는다 | `others:[<PID> /bin/bash /home/rokey/isaacsim/python.sh /home/rokey/m0617/…]` 처럼 다른 Isaac 이 보인다 |

스택을 띄우기 전에는 `ROS_DOMAIN_ID=117 ros2 topic info /clock --no-daemon --spin-time 3` 이 `Publisher count: 1`, 노드 `_P3ClockGraph_PublishClock` 인지 본다(스테이지가 `/clock` 작성자).

## 2. tmux 세션과 띄우는 순서

| 순서 | 세션 | 무엇 | 준비 신호 |
| --- | --- | --- | --- |
| 1 | `m2-stage` | Isaac 보충 스테이지(`--mode ros`) | 로그에 `[m0609_stage] physics_ready updates=10 playing=True timeline_subscriptions=3` |
| 2 | `m2-arm` | `m0609_arm`(teach 세트를 파라미터로) | `m0609_arm up. robot=m0609 joints=[...] open_loop=False` |
| 3 | `m2-stack` | `stub_loop.launch.py`(M0609 스텁 끔, `pharmacy_only`) | 덤프에 없음 |
| 4 | `m2-monitor` | `status_monitor` | 덤프에 없음 |
| 5 | `m2-loop` | **계획, 미실행, 명령 미정.** `DISPENSER_RESUMED` 뒤 약 10 s 에 `/orchestrator/reset` 을 부르는 것을 10회 반복하는 스크립트(저장소 밖 `$HOME/markle_tmp`). `master02` 공유 때문에 아직 돌리지 않았다 | |

### 2.1 `m2-stage`

Isaac 셸 환경의 정본은 [sim README](../../sim/README.md#05단계-m0609-보충-스테이지)의 `P3_ISAAC_ENV` 배열 방식이다. 이 절은 9/17 에 실제로 친 형태다. 9/17 에는 배열 변수를 쓰지 않고 `env -i` 인자를 풀어서 쳤다.

```bash
tmux new -s m2-stage -d; tmux send-keys -t m2-stage "cd $W && env -i HOME=\$HOME USER=\$USER TERM=\$TERM PATH=/usr/local/bin:/usr/bin:/bin DISPLAY=:1 XAUTHORITY=/run/user/1000/gdm/Xauthority XDG_RUNTIME_DIR=/run/user/1000 ROS_DISTRO=jazzy RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DOMAIN_ID=117 FASTRTPS_DEFAULT_PROFILES_FILE=\$HOME/.ros/fastdds_whitelist.xml LD_LIBRARY_PATH=\$HOME/isaacsim/exts/isaacsim.ros2.bridge/jazzy/lib \$HOME/isaacsim/python.sh sim/standalone/m0609_refill_stage.py --mode ros --attach --respawn-delay-s 3 --robot-usd $M/Collected_m0609_gripper/m0609_gripper.usd 2>&1 | tee -i $LOG; echo \"exit=\${PIPESTATUS[0]}\"" Enter
until grep -q -E "physics_ready|\] error|Traceback" $LOG; do sleep 2; done
```

teach 세트는 먼저 같은 worktree 에서 selfdemo 로 뽑는다(창 모드, `env -i` 부분은 위와 같다). 로그에서 `grep "teach "` 로 7줄이 나온다. 이 실행은 `next=finished` 뒤에도 창이 남아서 C-c 로 내렸다.

```bash
$HOME/isaacsim/python.sh sim/standalone/m0609_refill_stage.py --mode selfdemo --attach --loop 2 --loop-slots ab --robot-usd $M/Collected_m0609_gripper/m0609_gripper.usd --urdf $M/doosan-robot2/urdf/m0609_isaac_sim.urdf --robot-description $M/rmpflow/m0609_description.yaml
```

### 2.2 `m2-arm`

아래 teach 값은 `38b08eb` selfdemo 에서 뽑은 **예시**다. 9/17 에 성공한 보충 2회는 `ab90cd5` 세트였고, 이 `38b08eb` 세트로 arm 과 stack 을 붙인 실행은 아직 없다(다른 사용자의 Isaac 때문에 못 했다, master02).

```bash
tmux new -s m2-arm -d; tmux send-keys -t m2-arm "source /opt/ros/jazzy/setup.bash && source $I/setup.bash && export ROS_DOMAIN_ID=117 && ros2 run rokey_p3_manipulation m0609_arm --ros-args -p use_sim_time:=true -p max_joint_speed:=0.3 -p home_joint_positions:='[0.0,0.0,1.5882,0.0,1.5778,0.0]' -p shelf_approach_joints:='[0.6057,0.1723,1.1838,0.0006,1.7851,-2.5352]' -p shelf_grasp_joints:='[0.6059,0.1740,1.6181,0.0001,1.3502,-2.5360]' -p slot_a_approach_joints:='[-0.6334,0.1711,1.1854,0.0001,1.7841,-3.7749]' -p slot_a_insert_joints:='[-0.6347,0.1670,1.5864,0.0003,1.3887,-3.7764]' -p slot_b_approach_joints:='[-0.8256,0.3890,0.8981,0.0013,1.8540,-3.9675]' -p slot_b_insert_joints:='[-0.8253,0.3588,1.3387,0.0000,1.4451,-3.9671]' 2>&1 | tee \$HOME/markle_tmp/m0609_arm_38b_loop.log" Enter
```

### 2.3 `m2-stack`

```bash
tmux new -s m2-stack -d; tmux send-keys -t m2-stack "source /opt/ros/jazzy/setup.bash && source $I/setup.bash && export ROS_DOMAIN_ID=117 && ros2 launch rokey_p3_bringup stub_loop.launch.py publish_clock:=false use_stub_m0609:=false emulate_m0609:=false pharmacy_only:=true dispenser_file:=\$HOME/markle_tmp/dispenser_refill.yaml run_host:=master02 2>&1 | tee \$HOME/markle_stack_\$(date +%Y%m%dT%H%M%S).log" Enter
```

### 2.4 `m2-monitor`

```bash
tmux new -s m2-monitor -d; tmux send-keys -t m2-monitor "source /opt/ros/jazzy/setup.bash && source $I/setup.bash && export ROS_DOMAIN_ID=117 && ros2 run rokey_p3_orchestrator status_monitor --no-clear 2>&1 | tee \$HOME/markle_tmp/status_monitor.log" Enter
```

### 2.5 스택 없이 팔만 확인할 때

`7049c1a` 때 쓴 명령이다.

```bash
source /opt/ros/jazzy/setup.bash; source $I/setup.bash; export ROS_DOMAIN_ID=117; timeout 150 ros2 action send_goal --feedback /m0609/refill rokey_p3_interfaces/action/Refill "{item_id: drug-amox, slot: 0}"
ros2 topic info /m0609/joint_states -v --no-daemon --spin-time 3 ; (timeout -s INT 8 ros2 topic hz /m0609/joint_states > $HOME/markle_tmp/hz.txt 2>&1 || true); tail -2 $HOME/markle_tmp/hz.txt
```

`ros2 topic hz` 출력을 `| tail` 로 파이프하면 SIGINT 가 셸까지 가서 exit 130 이 났다. 그래서 파일로 리디렉트한다(master02).

## 3. 리셋

```bash
source /opt/ros/jazzy/setup.bash; export ROS_DOMAIN_ID=117; source $I/setup.bash; timeout 60 ros2 service call /orchestrator/reset rokey_p3_interfaces/srv/Reset "{epoch: 0}"
```

- 출력(master02 관측): `rokey_p3_interfaces.srv.Reset_Response(ok=True, message='epoch=2')`.
- 서비스 타입은 `rokey_p3_interfaces/srv/Reset` 이다(master02 관측).
- 요청의 `epoch` 값은 무시되고 항상 +1 이었다(master02 관측). [계약 4절](../architecture/delivery-contract-v1.md#4-시간epochstale)의 #84 이후 규칙과 같다.

## 4. 내리기

```bash
for s in m2-stack m2-monitor m2-arm; do tmux send-keys -t $s C-c; done
until ! pgrep -f "rokey_p3|status_monitor|m0609_arm|ros2 launch" >/dev/null; do sleep 1; done
tmux send-keys -t m2-stage C-c
until ! pgrep -f "kit/python/bin/python3 sim/standalone/m0609_refill_stage.py" >/dev/null; do sleep 2; done
pgrep -af "rokey_p3|m0609|status_monitor|ros2 launch" | grep -v -E "pgrep|daemon"
for s in m2-stack m2-monitor m2-arm m2-stage; do tmux kill-session -t $s; done
```

- ROS 쪽 세 세션을 먼저 내리고, 멈춘 것을 본 뒤 Isaac 을 내린다.
- 스테이지 로그에서 `grep "\] stop"` 가 `[m0609_stage] stop reason=sigint updates=11675 wall_s=196.938 loop_hz=59.28 sim_s=194.583 rtf=0.988` 처럼 나오고, 창에 `exit=0` 이 찍힌다(master02).
- 마지막 `pgrep` 이 빈 출력일 때만 `tmux kill-session` 으로 빈 세션을 정리한다. 무언가 남아 있으면 세션을 닫지 않고 보고한다.
- run 디렉토리의 파일 다섯 개는 [배포 runbook 3](deployment.md#3-run-파일-다섯-개를-확인한다)대로 확인한다. 9/17 두 run 은 다섯 개가 있었다(master02).

## 5. 조제기 설정 파일

`src/rokey_p3_orchestrator/config/dispenser.yaml` 을 복사하고 슬롯 수량만 바꿨다(slot a 5 → 1, slot b 5 → 0). 활성 슬롯이 임계값 1 에 닿아 보충 요청이 나오게 하려는 것이다.

```bash
mkdir -p $HOME/markle_tmp; cp src/rokey_p3_orchestrator/config/dispenser.yaml $HOME/markle_tmp/dispenser_refill.yaml; sed -i -E '/slot: a,/s/count: [0-9]+/count: 1/; /slot: b,/s/count: [0-9]+/count: 0/' $HOME/markle_tmp/dispenser_refill.yaml
```

9/17 파일의 sha256 은 `b12bd67fffabefaa34358cf222154935b47981045e2ef5978b7aeed8fb957163` 이다(원본의 한국어 주석 줄이 빠진 전문 기준, master02).
