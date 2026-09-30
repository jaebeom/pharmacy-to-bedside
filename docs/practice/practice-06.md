# 실습6 — master02, 조제실 장면 v2 스테이지 단독 확인

| 항목 | 값 |
| --- | --- |
| 번호 | 실습6 |
| 날짜·시각 | 2026-09-18 14:32:24-14:42:44(KST) |
| 장소 | `master02` 개발 클론, 창 모드, 도메인 117 |
| 돌린 사람 | 재범(지시 "로컬 최신화 및 실습 진행", 화면 확인, 끝 "내리자. 일단 내리고 기다리자."). 기동·확인 스크립트는 `master02` 원격 셸 |
| 출처 | master02 실습6 보고 원문. 이 기록은 `master02` 화면을 직접 보지 않고 썼다 |

## 목적

[조제실 장면 변경 계획](../planning/pharmacy-scene-v2-plan.md) 의 v2 스테이지(#170)를 단독으로 띄워 확인한다. 팔 노드·스택·웹은 띄우지 않았다.
이어지는 번호: 실습7 = 5분 연속(팔 v2 + `refill_soak`), 실습8 = v2 + 오케스트레이터 + 웹.

## 구성

| 부분 | 값 |
| --- | --- |
| 트리 | 실습5 종료(14:31:12) 뒤 개발 클론을 `git merge --ff-only origin/main` 으로 `7453b3d` → `6f59377`(#170 머지, #167·#168·#171 포함). `colcon build --symlink-install` `Summary: 7 packages finished [3.28s]` |
| 커밋 확인 | `6f59377` 은 `main` 에 있다. #167·#168·#170·#171 모두 머지 |
| 스테이지 | `--preset demo-ros-refill-v2`. #170 본문 명령의 `$P3_REPO` 자리에 개발 클론을 썼다 |

### 변수와 tmux 줄 원문 (`start_v2stage.sh`)

개인 경로는 변수로 둔다. 홈 줄임 기호는 `$HOME` 으로 바꿨다. 그 밖은 원문이다.

| 변수 | 9/18 값 |
| --- | --- |
| `W`, `P` | `/home/rokey/Dev/cobot3_ws/ROKEY_P3_A3`(개발 클론) |
| `M` | `/home/rokey/cobot3_ws/isaacpjt/M0609` |
| `LOG` | `$HOME/markle_tmp/practice6_stage.log` |
| `KL` | `$HOME/markle_tmp/kit-practice6-$(date +%H%M%S).log` → `kit-practice6-143221.log` |

```bash
tmux new -s m2-stage -d; tmux send-keys -t m2-stage "cd $W && env -i HOME=\$HOME USER=\$USER TERM=\$TERM PATH=/usr/local/bin:/usr/bin:/bin DISPLAY=:1 XAUTHORITY=/run/user/1000/gdm/Xauthority XDG_RUNTIME_DIR=/run/user/1000 ROS_DISTRO=jazzy RMW_IMPLEMENTATION=rmw_fastrtps_cpp ROS_DOMAIN_ID=117 FASTRTPS_DEFAULT_PROFILES_FILE=\$HOME/.ros/fastdds_whitelist.xml LD_LIBRARY_PATH=\$HOME/isaacsim/exts/isaacsim.ros2.bridge/jazzy/lib \$HOME/isaacsim/python.sh sim/standalone/pharmacy_stage.py --preset demo-ros-refill-v2 --kit-log-file $KL --kit-log-verbose --order-pool $P/src/rokey_p3_orchestrator/config/order_pool.yaml --robot-usd $M/Collected_m0609_gripper/m0609_gripper.usd --urdf $M/doosan-robot2/urdf/m0609_isaac_sim.urdf --robot-description $M/rmpflow/m0609_description.yaml 2>&1 | tee -i $LOG; echo \"exit=\${PIPESTATUS[0]}\"" Enter
```

## 관측

### 사람이 본 것 (재범 원문)

다섯 가지를 물었고 재범이 번호대로 답했다.

| 번호 | 질문 | 재범 답 |
| --- | --- | --- |
| 1 | 선반 4개가 바닥 2, 위 2 로 보이나 | "이어진 1개의 직사각형 선반으로 보임. 그래서 사각형 원형 위아래로 있음." |
| 2 | 약통 색이 원통 주황·모듈 보라인가 | "원통은 노랑색 모듈은 보라로 보임" |
| 3 | 조제기 앞 파란 원형 수납통과 앞면 구멍이 보이나 | "구멍 및 원형 넣는 곳 보임" |
| 4 | 레일·받침에 무지개 줄무늬가 보이나 | "무지개 줄무늬 보임" |
| 5 | 로봇 가운데 `link_2` 가 이어져 보이나 | "이어져 보임." |

### 로그로 본 것

| 항목 | 값 |
| --- | --- |
| 시각 | 14:32:24 `precheck 14:32:24 clock117=[Unknown topic '/clock'] others:[]` → 스테이지 기동. 14:32:34 `timeline_event type=PLAY sim_time=0.000`(READY). 이어서 `check_v2stage.sh`, 14:33 뷰포트 캡처, 14:37:30 창 캡처 |
| 재고 토픽 | `/m0609/shelf/inventory`(String JSON, reliable, transient_local, depth 1). `--once` 는 긴 문자열이 잘려 `--full-length` 로 다시 받았다. 9693 byte, 키 `v, stamp, scene, source, items, rail, cells, targets, obstacles, last_release`. rail names `rail_x, rail_y, rail_z`, limits `[-1.2,1.2]`·`[-0.1,0.33]`·`[0.0,0.6]`, origin `[0.0,0.3,0.6]`. cells 16 / present 16, obstacles 45, last_release None. Isaac 없는 `python3 sim/standalone/pharmacy_layout_json.py --scene v2` 출력과 stamp 를 빼면 같다 |
| 레일 토픽 | `/m0609/rail/joint_states` name `['rail_x', 'rail_y', 'rail_z']`. `rail_z` 0.30 을 보내고 3 s 뒤 position z 0.2961, 0.0 을 보내고 3 s 뒤 z 1.9e-06 |
| 그리퍼 | true 를 보내도 `/m0609/gripper/holding` `data: false`, 그다음 false 를 보냄. 약통에서 0.81 m 떨어진 곳에서 닫은 grasp miss 라 false 가 기대값이다(#170 본문 "기대 data: false") |
| 스테이지 로그(발췌) | `rail built … rail_z=(Z 0.00..0.60) drive=(100000.0, 10000.0, 50000.0) … pedestal_top_z=0.600` / `room scene=v2 source=임시(9/18 재범 지시, 세준 실제 USD 로 옮길 때 바뀜) shelves=['floor_left', 'floor_right', 'upper_left', 'upper_right'] cells=16 kinds=['cylinder', 'module']` / `link_visuals link_2/visuals made non-instanceable` / `refill_ros inventory present=16/16` / `refill_ros grasp miss distance=0.8068 limit=0.08`(의도한 것) |
| 경고 | `link_2` `non-existent path` 경고 **0줄**(실습1-5 는 매번 2줄). 새로 보인 것: 그리퍼 `onrobot_rg2ft/right_outer_knuckle/visuals/…/node_STL_BINARY_` 의 `getAttributeCount/getTypes called on non-existent path` 2줄, `link_2/visuals/MF0609_2_1/Scene/mesh` `update topology/point without updating normal, fallback to smooth normal` 1줄. `onrobot_rg2ft/world/visuals` `Unresolved reference` 는 자산 쪽이고 이전과 같다 |
| knuckle 경고의 이력 | 새것이 아니다. 9/17 20:42 `kit-204223.log`(`candidate/021a80b`, demo-ros)에서도 `link_2` 경고 대신 이 2줄이 났다. 같은 트리로 띄운 20:38·20:46 은 `link_2` 경고였다 |
| 안정성 | Traceback·FAILED 0, `app_stopped` 0. 타임라인 STOP 은 종료 때의 `STOP sim_time_last=600.283 (closing)` 1줄뿐 |
| 끝 | 재범 "내리자. 일단 내리고 기다리자." → 14:42:42 `m2-stage` tmux C-c → 14:42:44 `stop reason=sigint updates=36005 wall_s=608.054 loop_hz=59.21 sim_s=600.083 rtf=0.987 dispensed=0 render_products=0 ur5=off contact_watch=on`, **`exit=0`**. Isaac 프로세스가 없는 것을 `pgrep` 으로 확인한 뒤 kill-session. 남긴 tmux 세션은 `m2-pswatch`, `m2-browser` |
| 접촉 | contact 줄 7035. touch 2048줄은 16쌍으로 모두 약통↔자기 선반판(쌍마다 128줄, impulse 0.0163-0.0164). 약통이 판 위에 놓인 접촉으로 본다(추정). near 40쌍. `m0609` 가 들어간 contact 줄 0 |
| 보충 | 0(팔 노드 없이 단독 확인) |
| 캡처 | `practice6_viewport.png`(14:33, 뷰포트만), `practice6_window2.png`(14:37:30, Isaac 창만). 두 캡처 모두 색 면이 회색·무지개 줄무늬로 나왔다. 재범 눈으로는 색이 정상이고 줄무늬는 실제로 보인다. xwd 캡처는 색 판정에 쓰지 않는다 |
| 로그 파일 | `$HOME/markle_tmp/` 의 `practice6_stage.log`, `kit-practice6-143221.log`, `practice6_check.log`, `practice6_inventory.txt`·`practice6_inventory_full.txt`·`practice6_inventory.json`, `v2_layout_noisaac.json`, `m0609_knuckle_visuals.txt`, `main_6f59377_build.log`, 스크립트 `start_v2stage.sh`·`check_v2stage.sh`(저장소 밖) |

## 문제

| 번호 | 무엇 | 출처 | 고치는 쪽 | PR |
| --- | --- | --- | --- | --- |
| P9 | 약통이 회색으로 보인다 → **캡처에서만 그렇다.** 재범 눈으로는 원통 노랑, 모듈 보라. 질문의 기대색은 원통 주황이었다 | 재범 답 2, 캡처 | 없음(캡처 도구). 원통 노랑은 정상으로 받았다 | 없음 |
| P10 | 레일·받침에 무지개 줄무늬 | 재범 답 4, 캡처 | `sim` | #175(머지). #175 는 받침·승강판이 겹친 윗면 한 곳만 설명한다. 나머지 면의 줄이 v1 에도 보였는지 재범 확인 대기(렌더·표시 쪽일 수 있다는 판단) |
| P11 | 그리퍼 knuckle `non-existent` 경고 | 로그. 9/17 20:42 에도 있었다(새것 아님). 판단: 매 실행 대상만 바뀌는 인스턴스 채우기 경합(`link_2` 와 같은 종류) | `sim` | #175 의 `58410f5`(머지): 로봇의 모든 instanceable visuals 를 첫 update 전에 해제 |
| P12 | `link_2` normal fallback 경고 1줄 | 로그. 판단: 음영만, 조치 없음 | 조치 없음 | 없음 |
| P13 | 선반 4개가 이어진 직사각형 선반 하나로 보인다. 그래서 사각형·원형 약통이 위아래로 보인다 | 재범 답 1 | `sim` | #175 의 `bfb14f1`(머지): 선반 넷을 색으로 구분(바닥 좌·우 회색 두 톤, 위 좌·우 나무색 두 톤, 위치·크기 그대로). 색 구분으로 충분한지 재범 확인 대기 |

### 앞 실습 문제의 해소/남음

| 앞 문제 | 결과 |
| --- | --- |
| 실습3 P6 로봇 가운데 | `link_2` `non-existent` 경고 0줄, 재범 "이어져 보임" → 해소(#167) |

## 다음 실습에서 확인할 것

- P10·P13: v2 장면 수정판(#175)에서 줄무늬가 없어지고 선반 넷이 색으로 구분되는지 재범이 본다.
- 실습7-a 는 팔 브랜치 `feat/manipulation-m0609-scene-v2` 가 올라오면 트리와 명령을 정한 뒤 한다.
