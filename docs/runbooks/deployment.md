# 마스터 배포·실행·중지·롤백

마스터 PC 에서 지정 커밋을 배포하고, 실행하고, 멈추고, 되돌리는 절차다.
[공통 규칙](../process/repository-rules.md)은 마스터 PC 에서 이 문서를 먼저 읽으라고 정했다.

- 기준: 릴리스 `v1.1.2`. 병원 동작 설명은 `v1.1.0` = main `f316197`(#797)과 같다. 이 문서를 2026-09-30 에 그 코드와 대조했다. D455 몸체 재질만 #823 에서 다르다.
- 장비: `master01` = `IsaacSim14`, `master02` = `IsaacSim07`([장비 목록](../setup/host-inventory.md)). 둘 다 RTX 5080 Laptop 이다.
- 병원 한 바퀴 명령은 [병원 한 바퀴 런카드](hospital-full.md)에 있다. 이 문서는 그 앞뒤(받기·확인·멈춤·되돌리기)를 다룬다.

## 0. 마스터에서 하는 것과 하지 않는 것

[공통 규칙](../process/repository-rules.md)의 역할 표를 따른다.

| 한다 | 하지 않는다 |
| --- | --- |
| 지정 커밋(릴리스 태그)을 받아 빌드한다 | `src/`·`sim/`·`config/`·합격선을 고친다 |
| 런북 명령으로 띄우고 멈춘다 | 현장에서 소스를 고친다(hotfix) |
| 로그·수치·녹화를 모으고 관측을 정리한다 | 의존성을 올린다 |
| 승인된 롤백과 긴급 정지를 한다 | 임계값을 완화한다 |

- 문제가 나면 [진단 packet](../templates/diagnostic.md)을 이슈나 PR 에 올린다. 고치는 것은 개발 브랜치의 PR 이다.
- 호스트를 재부팅하거나 로그아웃하지 않는다([병원 데모 1절](hospital-demo.md#1-역할)).
- 남의 Isaac 은 내리지 않는다. `tools/demo_v2.sh` 는 다른 Isaac 이 떠 있으면 띄우지 않고 멈춘다.

## 1. 무엇을 배포하나 — 릴리스 태그

| 태그 | 커밋 | 무엇 |
| --- | --- | --- |
| `v1.1.0`(지금) | `f316197` | 카메라 집기 기본. A1 도크 = 적재 자리. 감속기 근접 0.7 m/s. 병원 컨베이어 2배 |
| `v1.0.0` | `a5d1107` | 병원 전 구간. acceptance 회전 7 은 `9760d9d` 트리에서 14/14 였다(12·13 미실행) |
| `v0.5.0` | `a4b1a4e` | 병원 acceptance 회전 1–4. 넷 다 16개를 실패 없이 끝내지 못했다(릴리스 노트) |

- 목록은 `gh release list` 로 본다. 한 태그의 변경·한계는 `gh release view <태그>` 로 본다.
- `v1.1.0` 커밋으로 돌린 acceptance 회전은 없다(릴리스 노트). 동결 protocol v4 를 넘은 것은 `v1.0.0` 회전 7 이다.
- 회전 7 은 참값 집기(`P3_CAMERA_POUCHES=0`)였다. protocol v4 는 카메라 집기 구성을 범위 밖으로 둔다.
- 감속기 긴급정지는 #752 진단만 있다. `v1.1.0` 에도 수정이 없다(릴리스 노트).
- 배포 기록은 `evidence/deployments/` 에 있다. `v0.5.0-rc.1`·`v0.5.0`·`v1.0.0` 이 있다. `v1.1.0` 기록은 이 문서를 고친 시각에 없었다.

## 2. 배포 전

1. 이슈에 실험 슬롯을 예약한다. 누가 돌리는지 이름을 적는다. 두 마스터를 같이 쓰면 한 배포 세트로 잠근다.
2. [기록 틀](../templates/deployment.md)에 host별 SHA·config·환경·롤백 조합을 쓴다. 기록은 `evidence/deployments/` 에 새 파일로 둔다.
3. 작업 중인 실험이 없고 정지 상태인지 확인한다. 원본 수집과 보존 공간을 확인한다.
4. 승인 PR·검사 결과·frozen protocol 을 확인한다. 후보의 의존성·자산은 버전을 고정한다.
5. 릴리스마다 따로 된 디렉토리에서 빌드한다(3절). 기존 build/install 을 다시 쓰지 않는다. 이전 산출물이 섞이기 때문이다.
6. 기동 전 잔류를 정리한다. 관제 창·녹화기·tmux·load 넷을 본다([hospital-full 0절 7](hospital-full.md#0-새-pc-에서-처음-한-번만)).

## 3. 릴리스를 따로 받는다

```bash
cd <개발 clone>
git fetch --tags origin
git worktree add ../release/v1.1.0 v1.1.0
cd ../release/v1.1.0
git rev-parse HEAD        # f316197d3e7b3b64a33a0dd29c4468fde26910a1
git status --porcelain    # 아무것도 안 나와야 한다
source /opt/ros/jazzy/setup.bash
colcon build
```

- `git worktree add ../release/<태그> <태그>` 는 릴리스 노트가 적은 방법이다(`v0.5.0`·`v1.0.0`·`v1.1.0`).
- 개발 clone 에 릴리스를 덮지 않는다. 개발 clone 은 개인 작업 사본이다.
- 실행 셸은 이 디렉토리의 `install/setup.bash` 하나만 source 한다. `tools/demo_v2.sh` 도 이 디렉토리의 것을 쓴다.
- 새 worktree 에는 Git 밖 파일이 없다. 웹 venv·조제기 자산·`config/local/` 이 그렇다. [hospital-full 0절](hospital-full.md#0-새-pc-에서-처음-한-번만)의 2·3 을 이 디렉토리에서 다시 한다.

커밋 SHA 만으로는 부족하다. 실행된 install·설정·씬·모델의 식별도 남긴다.
빌드 산출물이 Git 에 안 올라간다고 해서 작업 트리가 더러워진 것은 아니다. 커밋하지 않은 제품 코드 변경은 허용하지 않는다.

## 4. 실행

1. [셋업](../setup/README.md)의 Isaac·ROS 환경을 확인한다. Isaac 셸은 시스템 ROS 를 source 하지 않는다.
2. 한 PC 로 돌리면 [hospital-full 2절](hospital-full.md#2-한-바퀴)의 명령으로 띄운다. 두 PC 로 나누면 [hospital-demo 10절](hospital-demo.md#10-두-마스터로-나눠-띄우기)을 따른다.
3. `tools/demo_v2.sh status` 의 `tree` 줄이 받은 SHA 인지 본다. 커밋 안 한 변경이 0 파일이어야 한다.
4. 주문 전에 `tools/boot_check.py` 를 돌린다. `--tree-sha <40자>` 를 주면 tree 게이트가 켜진다. SHA·clean·도구 위치를 본다.
5. 끝나는 값이 0 이 아니면 주문을 넣지 않는다. 로그를 보존하고 내린다.
6. 운영 합격 조건은 frozen protocol 을 따른다. 실패하면 로그를 보존하고 출발을 멈춘다.
7. 결과 run 과 누락을 대조한 뒤 슬롯을 반환한다.

증거로 남길 회차는 `P3_RUN_HOST=master01`(또는 `master02`)을 준다.
`demo_v2.sh` 의 기본은 `hostname`(`IsaacSim14`·`IsaacSim07`)이다.
그대로 두면 run ID 가 [evidence run ID 규칙](../../schemas/README.md)(`...-master01-...` 또는 `...-master02-...`)에 안 맞는다.
실습10·22 는 `P3_RUN_HOST` 를 줬다.

`event_logger` 를 손으로 띄울 때도 같다. `run_host` 를 수집 마스터 이름으로 준다.

```bash
ros2 run rokey_p3_orchestrator event_logger --ros-args -p use_sim_time:=true -p run_host:=master02
```

`stub_loop.launch.py` 로 띄우면 같은 값을 launch 인자 `run_host:=master02` 로 준다.
run 디렉토리는 기본 `$HOME/.ros/rokey_p3/runs/<run-id>/` 다.

### 중지

`tools/demo_v2.sh` 로 띄웠으면 그것으로 내린다.

```bash
P3_WORLD=hospital tools/demo_v2.sh down     # tmux 세션 이름으로 C-c. PID kill·pkill·sudo 는 쓰지 않는다
tools/demo_v2.sh status                     # 남은 세션이 없는지 본다
```

- `up` 과 같은 `P3_WORLD` 를 준다. hospital 을 빼고 내리면 tmux `p3v2-nav` 가 남은 일이 있다(9/25 회차73). 지금 `down` 은 월드와 상관없이 모든 역할 세션을 본다.
- 두 PC 면 나머지 PC(웹·스택·주행·팔)를 먼저 내리고 스테이지 PC 를 나중에 내린다([hospital-demo 10.4](hospital-demo.md#104-내리기)).
- 내린 뒤 잔류 0 을 확인한다([hospital-full 0절 7](hospital-full.md#0-새-pc-에서-처음-한-번만)).

`ros2 launch` 를 직접 띄웠으면 **SIGINT** 로 내린다. `event_logger` 는 멈출 때 run 을 닫으면서 `orders.jsonl`·`meta.json` 을 쓴다.
이 두 파일이 없는 run 에는 판정이 없으므로 evidence 로 쓰지 않는다.

1. 터미널에서 띄웠으면 그 터미널에서 Ctrl+C.
2. tmux 안에서 띄웠으면 `tmux send-keys -t <세션> C-c`. `tmux kill-session` 으로 닫지 않는다.
3. docker 로 띄웠으면 launch 가 컨테이너의 PID 1 이 되게 `exec ros2 launch …` 로 시작하고, `docker kill -s INT <컨테이너>` 로 내린다. `docker stop` 은 쓰지 않는다.
4. 멈춘 뒤 run 디렉토리에 `orders.jsonl`·`meta.json` 이 있는지 본다. 없으면 그 run 을 evidence 로 쓰지 않고 [진단 packet](../templates/diagnostic.md)에 적는다.

```bash
docker run -d --name p3-stub <마운트·네트워크 옵션> ros:jazzy-ros-base-noble bash -c \
  "source /opt/ros/jazzy/setup.bash && source install/setup.bash && exec ros2 launch rokey_p3_bringup stub_loop.launch.py run_host:=master02"
docker kill -s INT p3-stub
```

왜 SIGINT 인가:
- `ros2 launch` 는 SIGTERM 을 받으면 자식 노드에 신호를 넘기지 않고 끝난다. 원인은 #65 에서 jazzy launch 소스를 읽고 판단했다. 셸에서 launch 에 `kill -TERM` 을 보내면 launch 만 끝나고 노드가 고아로 남는다(아래 확인).
- `docker stop` 은 SIGTERM 을 보내고 10 s 뒤 SIGKILL 이다. 그래서 `event_logger` 가 run 을 닫지 못한다.
- tmux 창을 닫으면(`kill-window`) SIGHUP 이 간다. 9/17 실측(`main` `7ac85b7`, docker)에서 `event_logger` 는 20 s 넘게 멈춘 채 남았고 두 파일이 없었다. `/events` 에 메시지가 하나 오자 그제야 run 을 닫았다(#73 본문).
  #65 가 건 SIGHUP 처리기는 `spin` 이 메시지를 기다리는 동안 돌지 않기 때문이다. 고치는 변경은 #73 이고, 그 변경을 실제 신호로 확인한 기록은 아직 없다. 그래서 규칙은 `send-keys C-c` 다.

확인(`dev01` docker, `main` `7ac85b7`, launch 를 PID 1 로 둔 컨테이너 둘):
- `docker kill -s INT`: exit 0, `orders.jsonl`·`meta.json` 이 생김.
- `docker stop`: 10 s 뒤 exit 137, 두 파일 없음.
- 셸에서 launch 에 `kill -TERM`(#74 커밋 `2b81b75` 컨테이너, orchestrator 패키지는 `main` 과 같음): launch exit 143. 5 s 뒤에도 노드 7개가 살아 있었고 파일은 `cabinet.jsonl`·`events.jsonl`·`order_status.jsonl` 셋뿐. 남은 노드에 SIGINT 를 보내자 두 파일이 생김.
- tmux 는 이 확인에서 미실행이다(위 9/17 실측이 출처).

마스터에서는 현장 코드를 수정하지 않는다.
문제 발생 시 [진단 packet](../templates/diagnostic.md)을 이슈나 PR 에 올린다.
긴급 정지와 승인된 롤백은 가능하다. 새 실행 기록을 남긴다.

## 5. 롤백

- 기동 실패, heartbeat/clock/인터락 이상, 회귀·protocol 의 중단 조건이면 후보 실행을 멈춘다.
- 원본을 보존한 뒤 양쪽 프로세스를 정지한다. 이전 승인 SHA·설정 조합의 디렉토리로 옮겨 재기동한다.
- 이전 릴리스도 3절처럼 따로 받는다. 예: `git worktree add ../release/v1.0.0 v1.0.0`.
- reset barrier 와 smoke 확인 후 새 run 을 기록한다.
- 이전 상태 확인도 실패하면 동작을 재개하지 않고 packet 을 전달한다.

`v1.1.0` 의 바로 앞 릴리스는 `v1.0.0`(`a5d1107`)이다.
`v1.1.0` 에서 어느 조합으로 돌아갈지 적은 배포 기록은 없다(미확인). 배포 기록의 롤백 칸에 적고 따른다.

자동 deploy 스크립트·self-hosted runner 는 아직 없다.
계정/명령 권한 설치는 [역할 가이드](../process/agent-workflow.md)의 현장 적용 항목이다.

## 부록 — 스텁 루프 절차(9/17 기록)

9/17 에 `master02` 에서 스텁 루프를 돌린 방식을 절차로 옮긴 것이다.
옮겨 적으면서 마스터에서 다시 돌리지는 않았다. 명령은 그때 `main` 코드와 위 "중지" 절 기준이다.
병원 한 바퀴에는 쓰지 않는다. 병원 한 바퀴는 [hospital-full](hospital-full.md)이다.
Isaac M0609 보충 장면 절차([master02 M0609 보충 장면 띄우기](master02-m0609-refill-stage.md))와 스텁 없는 조제실 한 바퀴([master02 스텁 없는 조제실 한 바퀴](master02-pharmacy-stack.md))도 9/17 기록이다.

### 1. 후보 커밋을 따로 받는다

```bash
git worktree add ../candidate/<sha> <sha>
cd ../candidate/<sha>
source /opt/ros/jazzy/setup.bash
colcon build
```

- 후보마다 디렉토리를 새로 만들어 이전 `build`·`install` 과 섞지 않는다(배포 전 5).
- 실행 셸은 이 디렉토리의 `install/setup.bash` 하나만 source 한다.
- `master02` 의 개발 clone(`/home/rokey/Dev/cobot3_ws/ROKEY_P3_A3`)은 개인 작업 사본이다. 9/17 에 HEAD 가 `5107d7e` 였고 추적 안 된 파일이 있었다. 배포에 쓰지 않는다.

### 2. tmux 안에서 띄우고 C-c 로 내린다

```bash
tmux new-session -d -s p3
tmux send-keys -t p3 "source install/setup.bash && ros2 launch rokey_p3_bringup stub_loop.launch.py run_host:=master02" Enter
# 끝낼 때
tmux send-keys -t p3 C-c
```

- 창을 닫거나(`kill-window`) 세션을 죽이지 않는다. 이유는 위 "중지" 절.
- 멈춘 뒤 고아 노드가 없는지 본다. 아무것도 안 나와야 한다.

```bash
pgrep -af rokey_p3
```

- 남은 노드가 있으면 번호로 하나씩 죽이지 말고, 그 노드가 뜬 tmux 세션이나 컨테이너 이름으로 내린다. 9/17 에 PID 목록으로 kill 하다 `systemd --user` 가 섞여 사용자 세션이 통째로 끝난 일이 있었다([세션 운영](../process/agent-workflow.md#917-부터의-세션-운영)).

### 3. run 파일 다섯 개를 확인한다

run 디렉토리는 기본 `$HOME/.ros/rokey_p3/runs/<run-id>/` 다(`log_dir` 로 바꿨으면 그 경로).

```bash
ls $HOME/.ros/rokey_p3/runs/<run-id>/
```

`events.jsonl`, `order_status.jsonl`, `cabinet.jsonl`, `orders.jsonl`, `meta.json` 다섯 개가 있어야 한다.
뒤의 둘이 없으면 run 이 닫히지 않은 것이라 evidence 로 쓰지 않는다.

### 4. 집계기를 돌린다

```bash
python3 tools/aggregate_runs.py --run $HOME/.ros/rokey_p3/runs/<run-id> --protocol experiments/protocols/pharmacy-lap-pilot-v1.json
```

출력 `status` 의 뜻과 9/17 실제 run 결과는 [도구 README](../../tools/README.md#run-디렉토리-집계).
스텁 조합의 시간 값은 성능이 아니다. evidence run manifest 는 사람이 이 출력을 보고 따로 쓴다.
