# master02 스텁 없는 조제실 한 바퀴

> **상태: 지난 기록 (2026-09-20 기준).** 지금은 [병원 한 바퀴 런카드](hospital-full.md)를 따른다.

- 대상: `master02` 에서 Isaac 조제실 스테이지(`sim/standalone/pharmacy_stage.py` ros 모드), `isaac_adapter`, 오케스트레이터, `status_monitor` 를 띄워 조제실 구간(A)을 stub_sim 없이 돈다. 팔 픽과 주행은 스텁이다.
- 상태: **초안.**
  - 두 코드 모두 `main` 에 들어왔다(9/17 18:26-18:37 머지): 스테이지는 PR #100(마지막 커밋 `9d0a441`), 어댑터는 PR #108.
  - 9/17 명령은 `master02` 의 (C)(D) 실행에서 친 원문이다. 개인 경로는 변수로 뺐고 홈 줄임은 `$HOME` 으로 바꿨다. 반복 스크립트만 그때의 주의를 반영해 고친 판이다(아래 `m2-loop`).
- 출처:
  - #108 PR 본문의 master02 절
  - 9/17 저녁 관측([일정](../planning/schedule.md)의 "9/17 저녁 현재", master02)
- 공통 절차는 [M0609 보충 장면 runbook](master02-m0609-refill-stage.md)을 따른다. 기동 전 확인·리셋·내리기는 거기 것을 쓰고 여기서 반복하지 않는다. 9/17 에 친 기동 전 확인 명령과 출력도 그 절과 같았다.

## 9/17 관측 요약

master02 관측. 이 문서를 쓰며 재확인하지 않았다. 도메인 117 개발 확인이고 protocol 밖이라 evidence 가 아니다.

| 항목 | 값 |
| --- | --- |
| 코드 | sim `ed91f0b`(실행 때 #100 브랜치 HEAD), ROS `9eaf573`(#108) |
| 작성자 | `/clock` 은 Isaac 하나. `/pharmacy/dispense`·`/sim/reset` 서버는 `isaac_adapter` 하나. stub_sim 은 서버 없음 |
| 결과 | epoch 1-13. 리셋 11회. 집계 `lap_success` 10/11(실패 1 은 아래 주의 1 의 개입). 닫힌 run 12개 모두 파일 다섯 개 |
| 수치(sim s) | `REQUEST_ACCEPTED`→`DOCKED` 8.92-9.82, `DISPENSED`→`POUCH_AT_END` 5.83-6.20(벨트가 실측 0.24 m/s 로 돈 값. 설계 0.15 m/s 면 9.0-9.7, [일정](../planning/schedule.md)의 "9/17 저녁 현재" 벨트 속도 관측). RTF 0.98 |

## 규칙

| 규칙 | 내용 |
| --- | --- |
| 도메인 | `117`(개발 확인용). [보충 장면 runbook 규칙](master02-m0609-refill-stage.md#규칙)과 같다 |
| 기동 전 확인 | 다른 Isaac 이 떠 있으면 띄우지 않는다. 명령과 출력은 [보충 장면 runbook 1](master02-m0609-refill-stage.md#1-기동-전-확인-isaac-을-띄우기-직전마다) |
| 주문 풀 | 같은 내용의 `order_pool.yaml` 을 Isaac `--order-pool` 과 launch `order_pool_file` 에 준다(#108 본문). 9/17 은 Isaac 쪽이 `$W`, launch 쪽이 `$A` worktree 의 파일이었다(두 커밋의 파일이 같은지는 미확인) |
| 작성자 하나 | Isaac ros 모드가 `/clock` 과 `/m0609/*` 도 내므로 launch 에 `publish_clock:=false emulate_m0609:=false` 를 같이 준다. 안 주면 작성자가 둘이다(#108 본문) |
| 내리기 | tmux 세션 이름으로 `C-c`(SIGINT)만. 순서와 확인은 [보충 장면 runbook 4](master02-m0609-refill-stage.md#4-내리기)와 같이 ROS 쪽을 먼저, Isaac 을 나중에 |

## 변수 (`master02` 9/17 기준 값)

| 변수 | 뜻 | 9/17 값 |
| --- | --- | --- |
| `CLONE` | 개발 clone(개인 작업 사본) | `/home/rokey/Dev/cobot3_ws/ROKEY_P3_A3` |
| `W` | #100 스테이지 커밋의 worktree | `/home/rokey/Dev/cobot3_ws/candidate/ed91f0b` |
| `A` | #108 어댑터 커밋의 worktree | `/home/rokey/Dev/cobot3_ws/candidate/9eaf573` |
| `I` | `$A` 에서 빌드한 install | `$A/install` |
| `M` | M0609 수업 자산 디렉토리 | `/home/rokey/cobot3_ws/isaacpjt/M0609` |
| `LOG` | 스테이지 로그 | `$HOME/markle_tmp/pharmacy_ros_ed91f0b.log` |

후보 준비(9/17 원문):

```bash
cd $CLONE; git fetch origin
S=$(git rev-parse --short=7 origin/feat/sim-pharmacy-stage); A=$(git rev-parse --short=7 origin/feat/bringup-isaac-adapter)
git worktree add ../candidate/$S $S
git worktree add ../candidate/$A $A; cd ../candidate/$A && source /opt/ros/jazzy/setup.bash && colcon build --symlink-install > ../${A}_build.log 2>&1
```

빌드 로그 마지막 줄은 `Summary: 7 packages finished [17.2s]` 였다(master02). 이 블록의 `A` 는 짧은 해시이고, 그 뒤 명령의 `$A` 는 worktree 절대 경로다.

## tmux 세션과 순서

| 순서 | 세션 | 무엇 | 볼 것 |
| --- | --- | --- | --- |
| 1 | `m2-stage` | Isaac 조제실 스테이지 ros 모드 | 준비 줄 셋(아래). 스택 전 `/clock` Publisher count 1 |
| 2 | `m2-stack` | `stub_loop.launch.py` + `isaac_adapter` | `isaac_adapter up` 줄과 stub_sim 의 "맡지 않는다" 줄(#108 본문) |
| 3 | `m2-monitor` | `status_monitor` | 화면이 갱신된다 |
| 4 | `m2-loop` | 리셋 10회 반복 스크립트(저장소 밖) | `round N … -> reset: message='epoch=…'` 줄 |

### `m2-stage`

Isaac 셸 환경의 정본은 sim README 의 `P3_ISAAC_ENV` 배열 방식이다. 9/17 에 풀어 쓴 `env -i …` 형태는 [보충 장면 runbook 2.1](master02-m0609-refill-stage.md#21-m2-stage)에 있다.

**정본: `--preset demo-ros`.**
- 출처: [sim README 0.7단계 "시연 때 띄우는 명령"](../../sim/README.md#시연-때-띄우는-명령---preset) 절이다(#100, `9d0a441`).
- 그 절이 기준이다. 아래는 옮긴 것이다(홈 줄임은 `$HOME` 으로 바꿈). 커밋 본문에는 "Isaac 미실행(인자 처리만)" 이었고, 9/18 [실습1](../practice/practice-01.md)이 `--preset demo-ros` 로 37분 돌렸다.

```bash
"${P3_ISAAC_ENV[@]}" $HOME/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset demo-ros \
  --order-pool "$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml" "${P3_ASSETS[@]}" \
  2>&1 | tee -i /tmp/p3-demo-ros.log
grep -m1 'preset=' /tmp/p3-demo-ros.log
```

- `demo-ros` 가 바꾸는 기본값: `--mode ros --ros-refill-selfdemo --ros-pick-stand-in-s 5 --refill-loop 0`, `--rail-drive 1e5 1e4 5e4`. 명령줄에 적은 인자가 preset 보다 이긴다.
- `--ur5` 와 preset 을 같이 쓰려면 `--ros-pick-stand-in-s 0` 을 명시한다. 그렇지 않으면 stage 가 기동을 거부한다(종료 코드 2).
- `--ur5` 에서는 `pick_notice` 를 받아도 봉투를 치우지 않고 세기만 한다.
- 첫 로그 줄 `[pharmacy_stage] preset=demo-ros resolved_args={…}` 로 띄운 값을 확인한다.
- 자산 경로·주문 풀·도메인은 preset 에 없다. `P3_ASSETS`·`P3_REPO` 와 도메인 117 은 현장 값으로 준다.

**9/17 실제로 친 형태**(preset 이전, 창 모드라 `--headless` 없음):

```bash
tmux new -s m2-stage -d; tmux send-keys -t m2-stage "cd $W && env -i HOME=\$HOME USER=\$USER TERM=\$TERM PATH=/usr/local/bin:/usr/bin:/bin DISPLAY=:1 XAUTHORITY=/run/user/1000/gdm/Xauthority XDG_RUNTIME_DIR=/run/user/1000 ROS_DISTRO=jazzy RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DOMAIN_ID=117 FASTRTPS_DEFAULT_PROFILES_FILE=\$HOME/.ros/fastdds_whitelist.xml LD_LIBRARY_PATH=\$HOME/isaacsim/exts/isaacsim.ros2.bridge/jazzy/lib \$HOME/isaacsim/python.sh sim/standalone/pharmacy_stage.py --mode ros --ros-refill-selfdemo --ros-pick-stand-in-s 3 --order-pool $W/src/rokey_p3_orchestrator/config/order_pool.yaml --robot-usd $M/Collected_m0609_gripper/m0609_gripper.usd --urdf $M/doosan-robot2/urdf/m0609_isaac_sim.urdf --robot-description $M/rmpflow/m0609_description.yaml 2>&1 | tee -i $LOG; echo \"exit=\${PIPESTATUS[0]}\"" Enter
```

- `$W`·`$M`·`$LOG` 는 보낸 셸에서 절대 경로로 펼쳐졌다.
- 9/17 은 `--ros-pick-stand-in-s 3` 이었다. preset 은 5 다.
- `--ros-refill-selfdemo` 의 보충은 오케스트레이터와 무관한 화면용이다. 9/17 에는 리셋 간격이 짧아 한 바퀴도 끝내지 못했다.

준비 판단(9/17 원문. `T0` 는 원문에 정의가 없어 앞에 한 줄을 더했다):

```bash
T0=$(date +%s)
until grep -q -E "ros json topics|FAILED|\] error|Traceback" $LOG 2>/dev/null || [ $(( $(date +%s)-T0 )) -ge 180 ]; do sleep 3; done
sleep 5; grep -E "step=|ros json|ros topics|timeline_event|physics_ready|epoch|FAILED|\] error|Traceback" $LOG
```

준비 줄(master02):
- `[pharmacy_stage] ros json topics pub=['/isaac/events', '/isaac/pharmacy/belt', '/isaac/pharmacy/dispense_response', '/isaac/sim/reset_response'] sub=['/isaac/pharmacy/dispense_request', '/isaac/sim/reset_request']`
- `step=… ok` 여섯 줄
- `[pharmacy_stage] timeline_event type=PLAY sim_time=0.000`

스택을 띄우기 전 `/clock` 확인:

```bash
source /opt/ros/jazzy/setup.bash; export ROS_DOMAIN_ID=117; ros2 topic info /clock -v --no-daemon --spin-time 3 2>&1 | grep -E "Unknown|Publisher count|Node name" | head -3
```

정상은 `Publisher count: 1`, `Node name: _P3ClockGraph_PublishClock`, `Node namespace: /` 이다.

### `m2-stack`, `m2-monitor`

9/17 원문:

```bash
tmux new -s m2-stack -d; tmux send-keys -t m2-stack "source /opt/ros/jazzy/setup.bash && source $I/setup.bash && export ROS_DOMAIN_ID=117 && ros2 launch rokey_p3_bringup stub_loop.launch.py use_isaac_adapter:=true pharmacy_only:=true publish_clock:=false emulate_m0609:=false order_pool_file:=$A/src/rokey_p3_orchestrator/config/order_pool.yaml run_host:=master02 2>&1 | tee \$HOME/markle_tmp/stack_C.log" Enter
tmux new -s m2-monitor -d; tmux send-keys -t m2-monitor "source /opt/ros/jazzy/setup.bash && source $I/setup.bash && export ROS_DOMAIN_ID=117 && ros2 run rokey_p3_orchestrator status_monitor --no-clear 2>&1 | tee \$HOME/markle_tmp/status_monitor_C.log" Enter
until grep -q "Deliver 결과" $HOME/markle_tmp/stack_C.log; do sleep 3; done
```

마지막 줄은 첫 바퀴가 끝날 때까지 기다린다.

볼 것(#108 본문):
- 첫 `Deliver` 결과가 `HOLD_RETURN`(`pharmacy_only`)이다.
- run 의 `DISPENSED`·`POUCH_AT_END` 가 `robot_id` `dispenser` 이고 stale 0 이다.
- 리셋 뒤 `RESET_DONE` 과 다음 결과가 나온다.
- 어댑터 로그에 "형식 오류"·"응답이 없다" 줄이 없다.

### 리셋

[보충 장면 runbook 3](master02-m0609-refill-stage.md#3-리셋)과 같다(9/17 에는 `source $A/install/setup.bash` 에 `| grep Reset_Response` 를 붙였다). 요청의 `epoch` 값은 무시되고 항상 +1 이다.

### `m2-loop`

`DOCKED` 를 기다렸다가 5 s 뒤 리셋하는 것을 10회 반복한다. 파일은 저장소 밖(`$HOME/markle_tmp/loop_D.sh`)이다.
아래는 9/17 주의 셋을 반영해 고친 판이다:
- (a) `seq 1 10`
- (b) `DOCKED` 는 `"name": "DOCKED"` 정확 일치로 센다. `grep -c DOCKED` 는 `AMR_DOCKED_LOAD` 도 세서 2 가 나온다.
- (c) 최신 run 은 이름순으로 고른다.

```bash
#!/bin/bash
# 10 resets: wait DOCKED in newest run, +5 s, reset
A=/home/rokey/Dev/cobot3_ws/candidate/9eaf573   # 9/17 값. 현장 값으로 바꾼다
source /opt/ros/jazzy/setup.bash; export ROS_DOMAIN_ID=117
source $A/install/setup.bash
R=$HOME/.ros/rokey_p3/runs
newest() { ls -d $R/*-master02-* | sort | tail -1; }
for i in $(seq 1 10); do
  d=$(newest); T0=$(date +%s)
  until grep -q '"name": "DOCKED"' $d/events.jsonl 2>/dev/null || [ $(( $(date +%s)-T0 )) -ge 180 ]; do sleep 1; d=$(newest); done
  if ! grep -q '"name": "DOCKED"' $d/events.jsonl; then echo "!! round $i no DOCKED in $d $(date +%T)"; exit 1; fi
  sleep 5
  echo "round $i $(date +%T) run=$(basename $d) -> reset: $(timeout 60 ros2 service call /orchestrator/reset rokey_p3_interfaces/srv/Reset '{epoch: 0}' | grep -o "message='[^']*'")"
  sleep 3
done
d=$(newest); T0=$(date +%s); until grep -q '"name": "DOCKED"' $d/events.jsonl 2>/dev/null || [ $(( $(date +%s)-T0 )) -ge 180 ]; do sleep 1; d=$(newest); done
echo "final run $(basename $d) DOCKED=$(grep -c '"name": "DOCKED"' $d/events.jsonl) $(date +%T)"
```

```bash
tmux new -s m2-loop -d; tmux send-keys -t m2-loop "\$HOME/markle_tmp/loop_D.sh 2>&1 | tee -a \$HOME/markle_tmp/loop_D.log" Enter
```

각주: 9/17 원문은 `seq 2 10` 이었다(1회차 뒤 다시 올림). 원문은 `A` 줄 없이 `source` 에 절대 경로를 썼고, 마지막 줄은 `grep -c DOCKED` 였다.

## 주의

1. **반복 스크립트는 최신 run 을 mtime 으로 고르지 않는다. run 디렉토리 이름순으로 고른다.**
   - 9/17 첫 판은 `ls -td $R/*/ | head -1`(mtime)이었다. 닫힌 run 이 늦게 갱신돼 옛 run 을 집었고 `DOCKED` 전에 리셋을 한 번 더 불렀다. 그래서 epoch 3 이 `ABORT`(`reset_interrupted`)로 끝났다(개입 이력).
   - run ID 는 UTC 시각으로 시작하므로 이름순이 시작 순서다.
2. **창 모드 Isaac 은 같은 PC 에서 다른 Isaac GUI 가 뜰 때 꺼진 적이 있다(원인 미확인). headless 는 꺼지지 않았다**(master02).
   - `master02` 는 다른 사용자와 같이 쓴다([장비 목록](../setup/host-inventory.md#master02-공유-사용-관측-917)).
3. **터미널 Ctrl-C 로 launch 를 내리면 노드마다 `process has died … exit code -2` ERROR 줄이 나온다.** 이중 SIGINT 의 정상 표기다.
   - Ctrl-C 는 launch 와 노드가 모두 든 전경 프로세스 그룹에 SIGINT 를 보낸다. 노드는 직접 한 번, launch 가 넘기는 것으로 한 번 받는다.
   - `tmux send-keys C-c` 도 그 창의 전경 프로세스 그룹 전체에 SIGINT 를 보낸다. 터미널 Ctrl-C 와 같다.
   - launch 하나에만 한 번 보내면(launch 가 PID 1 인 컨테이너에 `docker kill -s INT`) 노드 8개 모두 `process has finished cleanly` 로 끝난다.
   - 출처: 9/17 docker 관측. 그룹에 보낸 `kill -INT %1` 은 -2 줄이 나왔고, `docker kill -s INT` 한 번은 cleanly 였다.
4. **순서는 Isaac 스테이지를 먼저 띄워 준비 줄을 확인한 뒤 `stub_loop`(orchestrator·order_generator)를 띄우기를 권한다.** 기동 확인이 쉽기 때문이다.
   - Isaac 스테이지가 늦게 떠도 트립은 끊기지 않는다. 적재 위치에서 기다렸다가 이어진다.
     - 출처: 9/17 docker 재현( `main` `98e0ec8`, `stub_loop use_isaac_adapter:=true pharmacy_only:=true` 를 먼저 띄우고 가짜 Isaac 을 N 초 뒤).
     - N = 0·5·15·40·150 s 모두 첫 트립이 `HOLD_RETURN`(`pharmacy_only`)으로 완주했다.
     - 예: N=40 에서 `REQUEST_ACCEPTED` 3.0, `AMR_DOCKED_LOAD` 4.3, `DISPENSED` 39.8 sim s, 결과 45 s.
     - 한계: Isaac 이 `/clock` 도 내는 구성(`publish_clock:=false`)은 재현하지 않았다.
   - 다만 기다리는 동안 orchestrator·어댑터 로그가 조용하다(WARN 0줄). 기다리는 이유를 WARN 으로 남기는 변경은 #137(orchestrator, 머지), 어댑터 WARN 은 #140(머지)이다. 위 WARN 0줄 관측은 그 전의 것이다.
   - **주행 서버(`GoToZone`)가 늦을 때**는 다르다.
     - orchestrator 는 서버가 안 보이면 `server_wait_s`(10 s)를 기다린 뒤 거부로 본다.
     - `GoToZone` 은 이것을 출발 2회, 복귀 2회까지 되풀이한다(5 s 간격, `goto_max_rejects` 2, 약 40 s).
     - 그 안에 서버가 뜨지 않으면 첫 트립이 `goto_rejected` 로 닫힐 수 있다.
     - 출처: L2 로그 판독. 횟수 분해는 `trip_fsm.py` 에서 읽었다.
5. 이 구성에서 M0609 보충은 오케스트레이터와 연동되지 않는다. 오케스트레이터 보충은 [보충 장면 runbook](master02-m0609-refill-stage.md)의 고정 받침 구성, `--preset demo-ros-refill` + 팔 `rail_enabled`([실습3](../practice/practice-03.md) 3-B, 실습4·5), 장면 v2 `--preset demo-ros-refill-v2` + 팔 `scene_version:=2`([실습8](../practice/practice-08.md))에서 돌았다.
