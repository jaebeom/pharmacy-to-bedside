# 실습1 — master02 창 모드, 조제실 스택 + 관제 웹

| 항목 | 값 |
| --- | --- |
| 번호 | 실습1 |
| 날짜·시각 | 2026-09-18 10:05:28-10:43:37(KST). 기동 전 확인 10:05:28, PLAY 10:05:42, 스테이지 C-c 10:42:45, 스택·웹 내림 10:43:37 |
| 장소 | `master02`, 창 모드, 도메인 117 |
| 돌린 사람 | 재범 |
| 기동·로그 | `master02` tmux |
| 출처 | 재범 지시, master02 중간 보고(10:11:45), master02 종료 보고. 이 기록은 `master02` 화면을 직접 보지 않고 썼다 |

## 목적

- 처음 목적(재범, 원문 취지): 개발 클론을 `main` 최신으로 올리고, 어제 시연을 최신 버전으로 실습한다.
- 도중에 더한 목적: 관제 웹이 sim 시간 정지를 보여 주는지 확인한다(재범이 창에서 정지 버튼을 누른 이유, 아래 로그 관측).

## 구성

| 부분 | 값 |
| --- | --- |
| Isaac 스테이지 | sim `174bb6a`(PR #128 헤드, 머지 전). `pharmacy_stage.py --preset demo-ros --kit-log-file $KL --kit-log-verbose`. 창 모드 |
| ROS 스택 | `main` `4a00ea8` install. `stub_loop.launch.py use_isaac_adapter:=true pharmacy_only:=true publish_clock:=false emulate_m0609:=false` |
| 관제 웹 | `main` `4a00ea8`. `--host 127.0.0.1 --port 8000 --allow-commands`. 브라우저 firefox(10:06) |
| status_monitor | 띄우지 않았다 |
| 도메인 | 117 |

띄우는 절차는 [master02 스텁 없는 조제실 한 바퀴](../runbooks/master02-pharmacy-stack.md) runbook 과 [`web/README.md`](../../web/README.md)를 따른다.

### 변수와 tmux 줄 원문

개인 경로는 변수로 둔다. 홈 줄임 기호는 `$HOME` 으로 바꿨다. 그 밖은 원문이다.

| 변수 | 9/18 값 |
| --- | --- |
| `W` | `/home/rokey/Dev/cobot3_ws/candidate/174bb6a`(sim) |
| `R` | `/home/rokey/Dev/cobot3_ws/candidate/4a00ea8`(ROS·웹) |
| `I` | `$R/install` |
| `M` | `/home/rokey/cobot3_ws/isaacpjt/M0609` |
| `LOG` | `$HOME/markle_tmp/demo18_stage.log` |
| `KL` | `$HOME/markle_tmp/kit-demo18-$(date +%H%M%S).log`. 실제 파일은 `kit-demo18-100530.log`(1.8 MB) |

```bash
tmux new -s m2-pswatch -d; tmux send-keys -t m2-pswatch 'while sleep 1; do date +%T.%N | cut -c1-12; ps -eo pid,ppid,lstart,etimes,cmd | grep -E "isaacsim|kit/kit|kit/python|python.sh|codex" | grep -v grep; done >> $HOME/markle_tmp/pswatch18.log' Enter
tmux new -s m2-stage -d; tmux send-keys -t m2-stage "cd $W && env -i HOME=\$HOME USER=\$USER TERM=\$TERM PATH=/usr/local/bin:/usr/bin:/bin DISPLAY=:1 XAUTHORITY=/run/user/1000/gdm/Xauthority XDG_RUNTIME_DIR=/run/user/1000 ROS_DISTRO=jazzy RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DOMAIN_ID=117 FASTRTPS_DEFAULT_PROFILES_FILE=\$HOME/.ros/fastdds_whitelist.xml LD_LIBRARY_PATH=\$HOME/isaacsim/exts/isaacsim.ros2.bridge/jazzy/lib \$HOME/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset demo-ros --kit-log-file $KL --kit-log-verbose --order-pool $R/src/rokey_p3_orchestrator/config/order_pool.yaml --robot-usd $M/Collected_m0609_gripper/m0609_gripper.usd --urdf $M/doosan-robot2/urdf/m0609_isaac_sim.urdf --robot-description $M/rmpflow/m0609_description.yaml 2>&1 | tee -i $LOG; echo \"exit=\${PIPESTATUS[0]}\"" Enter
tmux new -s m2-stack -d; tmux send-keys -t m2-stack "source /opt/ros/jazzy/setup.bash && source $I/setup.bash && export ROS_DOMAIN_ID=117 && ros2 launch rokey_p3_bringup stub_loop.launch.py use_isaac_adapter:=true pharmacy_only:=true publish_clock:=false emulate_m0609:=false order_pool_file:=$R/src/rokey_p3_orchestrator/config/order_pool.yaml run_host:=master02 2>&1 | tee \$HOME/markle_tmp/demo18_stack.log" Enter
tmux new -s m2-web -d; tmux send-keys -t m2-web "source /opt/ros/jazzy/setup.bash && source $I/setup.bash && export ROS_DOMAIN_ID=117 && cd $R/web/backend && .venv/bin/python -m app.main --host 127.0.0.1 --port 8000 --allow-commands --static $R/web/frontend --order-pool $R/src/rokey_p3_orchestrator/config/order_pool.yaml --zones-file $R/src/rokey_p3_description/config/zones.yaml 2>&1 | tee \$HOME/markle_tmp/demo18_web.log" Enter
tmux new -s m2-browser -d; tmux send-keys -t m2-browser "DISPLAY=:1 XAUTHORITY=/run/user/1000/gdm/Xauthority firefox http://127.0.0.1:8000/" Enter
```

준비:
- 웹 venv: `cd $R && python3 -m venv --system-site-packages web/backend/.venv && web/backend/.venv/bin/pip install -r web/backend/requirements.txt`
- ROS: `cd $R && colcon build --symlink-install`. 빌드 로그 끝 줄은 `Summary: 7 packages finished [12.6s]` 였다.

로그 파일(`$HOME/markle_tmp/`, 저장소 밖): `demo18_stage.log`, `kit-demo18-100530.log`, `demo18_stack.log`, `demo18_web.log`, `pswatch18.log`, `/clock` 멈춤 시험 snapshot `end18/snap_*.json` 12장, 스크린샷 `end18/screen.xwd`(9.4 MB, PNG 변환 도구 없음).

## 관측

### 사람이 본 것 (재범, 원문 취지 그대로)

1. 로봇이 약통(캐니스터)을 들어올리면 약통이 왔다갔다 흔들린다.
2. 로봇이 뭔가 기둥에 밀린다.
3. 속도가 너무 느리다. 가능 최고 속도의 80% 로 하고 싶다.
4. 1축 레일이 아니라 2축 레일로 구성해야 한다.

### 로그로 본 것 (표의 "10:11:45" 행은 중간 보고, 나머지는 종료 보고)

| 항목 | 값 |
| --- | --- |
| 창 | PLAY 10:05:42 부터 C-c 10:42:45 까지 약 37분 3초 살아 있었다(kit 앱 시각 2,234 s). 그 사이 `app_stopped` 0. 사람 지시로 내렸다 |
| 보충(selfdemo, 레일 + 팔) | 10:11:45 에는 4바퀴 모두 `True`, TIMEOUT 0. 끝까지 28바퀴, `canister_in_inlet=True` 28/28, refill TIMEOUT 1 |
| 트립(Deliver 결과) | 발행기 `r001-0001`(`ord-0002`) `HOLD_RETURN`, reason `pharmacy_only`(정상 완주) |
| 관제 웹 명령 | `POST /api/requests` 1회(재범, `web-1-101010`, `ord-0004` → `HOLD_RETURN` `pharmacy_only` 알람). `POST /api/reset` 0회 |
| 벨트 | xform 기본 몸체. `speed_measured=0.1500`, ratio 1.000 |
| 레일(P2 관련) | 매 바퀴 insert 에서 `rail_y` 가 하한 -0.10 까지 간다. release 에서 `rail_x` 가 5-15 cm 밀린다. 레일 드라이브는 1e5/5e4 |
| 타임라인 STOP | 10:09:52 부터 5회. 재범이 창에서 정지 버튼을 눌렀다(재범 확인). 5/5 자동 복구(`physics_view recovered`) |
| 웹의 시간 정지 표시 | STOP 복구가 곧바로 PLAY 해서 `/clock` 이 2 s 넘게 멈추지 않았다. 그래서 웹에 정지가 뜨지 않았다 |
| 내린 방식 | 10:42:45.443 `m2-stage` 에 tmux C-c. 10:43:37 `m2-stack`·`m2-web` 을 이름으로 C-c 한 뒤 kill-session. 남긴 tmux 세션은 `m2-pswatch`, `m2-browser`(firefox) |
| 스테이지 종료 줄 | 종료 중 `rclpy … RCLError: Failed to publish: publisher's context is invalid`(`m0609_refill_stage.py:914` `publish_joint_states`) 뒤 `[pharmacy_stage] exit code=1 (skipping simulation_app.close(), which exits 0)`, 창 `exit=1`. 판단: SIGINT 종료 경합 |
| 그 밖 | 10:06:43 kit traceback 은 `omni.kit.manipulator.selector`(뷰포트 선택 조작)에서 났다. 동작 영향 없음 |

#### 웹의 `/clock` 멈춤 표시 시험

웹과 스택은 그대로 두고 스테이지만 10:42:45.443 에 C-c 했다. 1 s 간격 snapshot 12장을 떴다.

| 시각 | 웹 상태 |
| --- | --- |
| 10:42:46.450(+1.0 s) | `clock.alive` True, age 1.006. 신호 5개 stale, belt stale. `STATUS_STALE` warn 5개 |
| 10:42:47.477(+2.0 s) | `clock.alive` False, age 2.030. `CLOCK_STOPPED` error "/clock 멈춤" |
| +12.3 s 까지 | `alive` False 유지. 알람 `CLOCK_STOPPED` error 1, `STATUS_STALE` warn 5, `HOLD_RETURN` warn 2 |

멈춤 표시는 C-c 뒤 약 2.0 s(기대 2.0 s)였고, 신호 stale 은 1.0 s 안에 떴다.

## 문제

| 번호 | 무엇(재범) | 고치는 쪽 | PR |
| --- | --- | --- | --- |
| P1 | 약통을 들어올리면 약통이 왔다갔다 흔들린다 | `sim` | #157(`cc89de9`, 머지) |
| P2 | 로봇이 뭔가 기둥에 밀린다(로그: 위 레일 행) | `sim` | #157(`0f31349`, 머지) |
| P3 | 속도가 너무 느리다. 가능 최고 속도의 80% 로 | `sim`(스테이지 selfdemo), 팔(`m0609_arm` 경로) | 스테이지: #157(`cc89de9`, 머지). 팔: 속도 80% 는 #165(머지). 팔 레일 구동 #154·짝 #149 도 머지 |
| P4 | 1축 레일이 아니라 2축 레일로 구성 | `sim` | #157(`0f31349`, 머지) |
| P5 | (로그, 재범이 본 것 아님) 스테이지를 C-c 로 내리면 `publish_joint_states` 가 무효 context 로 publish 해 `exit=1` 로 끝난다 | `sim`(실습1 개선 PR 에 작으면 같이, 아니면 `sim/README.md` 알려진 문제) | #157(`9679d40`, 머지) |

## 다음 실습에서 확인할 것

- P1-P4 를 고친 PR 이 나오면 그 커밋으로 같은 장면을 다시 보고 문제별로 "해소/남음" 을 적는다.
- 웹의 sim 시간 정지 표시: 창의 정지 버튼은 STOP 복구가 곧바로 PLAY 해서 웹에 안 뜬다. 스테이지를 내려 `/clock` 을 멈추면 약 2.0 s 에 `CLOCK_STOPPED` 가 뜬다(이번 시험). 정지 버튼으로도 보이게 할지는 정하지 않았다.
- P5: 스테이지 C-c 뒤 창이 `exit=0` 으로 끝나는지.
