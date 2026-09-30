# 저장소 검사 도구

Python 3.10 이상, 표준 라이브러리만 사용한다. 저장소 루트에서 실행한다.

```bash
python3 tools/check_repository.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tools/evidence.py validate
python3 tools/evidence.py validate --base origin/main
```

`validate`는 `experiments/protocols/*.json`, `evidence/runs/*.json`의 구조와 상호 참조를
검사한다. `--base`는 기준 커밋에 있던 모든 run, frozen protocol, `evidence/reviews/*.md`와
`evidence/deployments/*.md`
(`README.md` 제외)의 수정·삭제도 거부한다. 이미 사용한 protocol의 내용을 고치지 말고 새 ID로
추가한다. run의 정정은 새 ID와 `supersedes`로 연결하며 원본을 보존한다.
Acceptance protocol은 기준 커밋에서 이미 frozen이어야 한다. Protocol freeze와 acceptance
결과 제출은 서로 다른 PR로 진행한다. `--base` 없는 로컬 검사는 이 순서를 확인할 수 없다.

로컬에 확보한 원본 파일의 무결성은 별도로 확인한다.

```bash
python3 tools/evidence.py verify-artifacts \
  evidence/runs/<run-id>.json --artifact-root /path/to/local-artifact-cache
```

상대 artifact URI `sha256/<digest>/stdout.log`는 artifact root 아래 같은 경로에서 찾는다.
외부 URI `s3://bucket/runs/<digest>/stdout.log`는 root 아래
`bucket/runs/<digest>/stdout.log`에서 찾는다. `gs://`, `https://`도 같은 규칙이다.
모든 파일이 존재하고 크기와 SHA-256이 일치해야 성공한다. 다운로드나 네트워크 요청은 하지 않는다.
서로 다른 저장소의 같은 authority/path가 충돌하지 않도록 별도 캐시 루트를 사용한다.

URI는 SHA-256 전체를 경로 한 구간에 포함해야 한다. `latest`처럼 덮어쓰기 쉬운 이름만 있는
키, 쿼리 문자열, 서명 URL, 계정·암호, fragment, percent escape, 상대 경로 탈출을 거부한다.
객체 저장소의 실제 불변성·접근권한·보존 정책은 운영에서 따로 설정한다.

통과 의미는 **형식·참조·기록 보존 조건 충족**이다. 측정 진실성, 전체 시행의 누락 여부,
환경에 대한 허위 선언, 사람의 승인 여부, 통계적 유의성은 이 도구로 입증되지 않는다.
GitHub hosted CI는 GPU나 마스터 PC에 접속하지 않으며 artifact 원본도 자동으로 내려받지 않는다.

## CI 구성

워크플로 둘이 모든 PR·main push 에서 돈다. 무거운 단계(colcon, `sim/tests/` 전체, usd-core)는 경로와 Draft 여부로 건너뛴다.

| 워크플로 | job | 무엇 |
| --- | --- | --- |
| `harness.yml`(Evidence harness) | Repository and evidence checks | `check_repository.py`, `tests/` unittest. `sim/`이 바뀌면 `sim/tests/`(Isaac·ROS 없이). Ready·main은 usd-core 한 패스, Draft는 일반 python3 한 패스. `evidence.py validate --base` |
| | Python lint (ruff) | `ruff check .`(설정 `ruff.toml`) |
| `ci.yml`(CI) | Changed paths | 아래 `ci_changed_paths.py` 로 colcon 을 돌릴지 정한다 |
| | L1 · L2 (colcon build + test) | `ros:jazzy-ros-base-noble` 컨테이너에서 `colcon build`·`colcon test`(#129, setup-ros 대신). `ros=false` 이거나 Draft 면 건너뛴다 |
| | CI gate | `if: ${{ !cancelled() }}`. colcon 이 건너뛰어도 끝나므로 required check 로 건다(#145) |

- colcon test step 의 환경: `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`, `ROS_DOMAIN_ID=(GITHUB_RUN_ID + GITHUB_RUN_ATTEMPT) % 101 + 1`, `--executor sequential`(#123). L2 의 발견 확인·내림은 [bringup README L2 테스트 구조](../src/rokey_p3_bringup/README.md#l2-테스트-구조).
- gate 가 `always()` 가 아니라 `!cancelled()` 인 이유: 같은 PR 에 새 push 가 오면 이전 run 이 취소되는데(concurrency), 그때 gate 까지 돌면 취소된 colcon 을 실패로 보고 빨갛게 남았다. 진짜 빌드 실패는 그대로 빨갛다.
- 같은 PR 의 이전 run 은 새 push 가 취소한다. main push 는 취소하지 않는다(커밋마다 검증).

## CI 의 colcon 실행 판정

`ci_changed_paths.py` 는 `.github/workflows/ci.yml` 의 changes job 이 부른다. 두 가지를 한다.

```bash
# 1) 비교 기준 커밋을 고른다(ci.yml 이 부르는 형태)
python3 tools/ci_changed_paths.py --base "$EVENT" "$HEAD" "$PR_BASE" "$PUSH_BEFORE"
# 2) 바뀐 경로를 한 줄에 하나씩 받아 ros=·sim=·usd=·unit=·lint= 를 낸다
git diff --name-only "$BASE" "$HEAD" | python3 tools/ci_changed_paths.py
```

- 기준(`--base`, #148)
  - `pull_request`: HEAD(GitHub merge ref)가 merge 커밋이면 **첫 부모**(merge ref 를 만든 시점의 main 끝)다. 부모가 1개이거나 모르는 커밋이면 `PR_BASE` 로 돌아간다.
  - `push`: `github.event.before`.
  - 기준이 없으면(빈 값·0 40개) 빈 줄을 내고, job 은 무거운 시험을 돈다.
  - 전에는 `github.event.pull_request.base.sha` 와 비교했다. 그 값은 PR 을 열거나 push 한 시점의 main 이라, 그 뒤 main 이 움직이면 main 쪽 변경이 섞였다.
    예: #128(sim/ 7개만 바꿈)이 colcon 을 탔다. #118 뒤 PR run 가운데 이 구멍으로 헛돈 것이 적어도 2 PR·8 run·37.8 분이었다.
- 판정
  - 바뀐 파일이 전부 colcon 이 읽지 않는 경로(어디든 `*.md`, `docs/`, `sim/`, `web/`, `tests/`, 이슈·PR 틀, `CODEOWNERS`)면 `ros=false` 다.
  - `sim/` 또는 `.github/workflows/harness.yml`이 있으면 `sim=true`와 `usd=true`. 문서·src·web만이면 둘 다 false.
  - 문서·실습 사진만이면 `unit=false`·`lint=false`. `check_repository.py`는 그대로 돈다.
  - `tools/`·`experiments/`·`schemas/`는 Ready에서 colcon을 태운다. Draft의 colcon과 usd-core 설치는 워크플로가 생략한다. 경로 판정 값은 그대로다.
- 근거는 파일 docstring, 테스트는 `tests/test_ci_changed_paths.py`(#128 모양의 임시 git 저장소로 기준 고르기를 본다).

로컬에서 PR 의 판정을 미리 볼 때는 PR 자신의 변경만 넣는다.

```bash
git diff --name-only origin/main...HEAD | python3 tools/ci_changed_paths.py
```

## 시연 한 명령 (`demo_v2.sh`)

v2 시연(Isaac v2 스테이지 → 팔 노드 v2 → 어댑터 스택 → 관제 웹)을 tmux 세션 이름으로 띄우고 내린다.
9/21 시연용으로 만들었다. 지금은 병원 acceptance 회차와 발표 촬영도 이 명령으로 띄운다.
명령은 실습7·8 의 master02 절차(stage·arm·stack·web 네 줄)를 옮긴 것이다. `tools/demo_v2.sh cmds` 로 칠 명령을 먼저 볼 수 있다.

`v1.1.0`(`f316197`) 기준 주요 환경 변수다. 전체 목록은 스크립트 머리 주석과 `tools/demo_v2.sh env` 다.

| 변수 | 기본 | 뜻 |
| --- | --- | --- |
| `P3_WORLD` | `demo` | `demo`(조제실), `emptyworld`(빈월드 한 바퀴), `hospital`(병원 전 구간, 주행 Nav2) |
| `P3_ROLES`·`P3_PEER` | 월드의 전부 · 없음 | 두 PC 모드. 스테이지 PC 는 `stage`, 나머지 PC 는 `arm nav stack web`. 절차는 [병원 데모 10절](../docs/runbooks/hospital-demo.md) |
| `P3_V2_RAIL_SELECT` | `preferred_first` | M0609 보충 레일 후보 순서. #391 에서 opt-in 으로 들어왔고 #797(`v1.1.0`)에서 기본이 됐다. `first_feasible` 은 되돌리기 |
| `P3_V2_GUARDED_MODULE_PATH` | `false` | 새 모듈 경로. 아래 "새 모듈 경로 검증" |
| `P3_CAMERA_POUCHES`·`P3_CAMERA_TAGS` | 병원 `1`, 그 밖 `0` | 봉투·인식표를 손 카메라 QR 로 읽는다 |
| `P3_CONTAINER_QR` | 병원 `1`, 그 밖 `0` | 보충 전 약통 QR 확인 |
| `P3_WEB_HOST`·`P3_WEB_PORT` | `127.0.0.1` · `8000` | 웹 bind. 웹 인자는 [`web/api.md` §10.3](../web/api.md) |

병원 카메라 기본값을 드러내 적은 기록은 [`config/hospital-camera-delivery.sh`](../config/hospital-camera-delivery.sh) 다([config README](../config/README.md)).
팔 명령은 `v2_guarded_module_path:=false`를 명시해 노드의 기본값이 바뀌어도 기존 시연 경로를 유지한다.

```bash
export P3_DOMAIN=117 P3_M0609=/path/to/M0609 P3_DISPENSER_FILE=/path/to/dispenser_refill.yaml   # master02 값은 실습 기록
export P3_BROWSER=firefox                 # 웹 창도 띄울 때(없으면 안 띄운다)
# 발표장 화면이 master02 패널(2048x1152)과 다르면: export P3_SCREEN_SIZE="1920 1080"
tools/demo_v2.sh up        # 기동 전 확인 → stage(PLAY 대기) → arm(계획 캐시 16/16 대기) → stack(orchestrator up) → web(HTTP 응답) → 브라우저
tools/demo_v2.sh status    # 세션마다 떠 있는지, 준비 줄·exit·오류 줄, 도메인의 /clock 발행자 수
tools/demo_v2.sh down      # browser·cap·web·stack·arm 에 C-c → 다 내려가면 3 s 뒤 stage 에 C-c. exit 코드를 적는다
```

- **기동 전 확인에서 멈추는 경우**(아무것도 띄우지 않고 exit 3): 같은 이름의 세션이 이미 있다 / 이 기계에 다른 Isaac 이 떠 있다(`pgrep -af` 로 보기만 하고 목록을 출력. 절대 내리지 않는다) / 이 도메인에 `/clock` 발행자가 있다.
- **새 모듈 경로 검증:** `P3_V2_GUARDED_MODULE_PATH=true tools/demo_v2.sh cmds`로 명령을 확인한 뒤,
  같은 환경 변수로 `up`을 실행한다. 기본값은 false이며 true/false 이외 값은 어떤 역할도 띄우기 전에 exit 2로 거부한다.
  `env`와 팔 기동 명령 로그에 선택값이 남는다. `P3_ARM_CMD`가 있으면 그 전체 명령의 설정이 우선한다.
  guarded 경로의 Isaac L3·완주 검증은 미실행이며, 기존 시연 기록을 새 경로의 증거로 사용하지 않는다.
- **준비 줄을 시한 안에 못 보면** 거기서 멈추고 로그 끝을 보여 준다(exit 4). 이미 띄운 것은 `down` 으로 내린다.
- **시계 동기화**: 기동 전 확인에서 `timedatectl show -p NTPSynchronized --value`(읽기만)가 yes 가 아니면 멈추지 않고 경고만 한다. 웹 백엔드가 신선도를 벽시계로 잰다. 계약 4절과 다르다. 백엔드는 #219 다. `v1.1.0` 에서도 그대로다. 시계가 보정될 때 한 번 틀어질 수 있다. 동기화 뒤 web 만 다시 띄운다. `status` 에도 한 줄 나온다.
- **안 내려가면 보고만 한다.** `P3_DOWN_TIMEOUT_S`(30 s) 안에 `exit=` 가 없으면 그 세션을 그대로 두고 stage 는 내리지 않는다(exit 1). kill·pkill·sudo 는 쓰지 않는다.
- 로그: `P3_LOG_DIR`(기본 `$HOME/p3_demo_logs`)의 `<기동시각>-stage.log`·`-kit.log`·`-arm.log`·`-stack.log`·`-web.log`. 각 로그 끝에 `exit=N` 이 남는다.
- **지금 도는 것이 고친 그것인가**(9/18 공통 규칙): `up` 이 첫 줄에 저장소 sha·커밋 시각·커밋 안 한 변경 수·install(`setup.bash`) 시각을 찍고 `<기동시각>-tree.txt` 에 남긴다.
  install 이 커밋보다 오래됐으면 경고를 붙인다. `status` 는 띄울 때와 지금의 값, 세션마다 기동 시각을 같이 보여 준다. 브라우저 프로필은 기동마다 새로 만들어 지난 프론트 캐시를 쓰지 않는다.
- **화면 반반**(재범 9/18: 왼쪽 Isaac, 오른쪽 웹): `P3_SCREEN_SIZE`(기본 `2048 1152`)로 Isaac 에 `--window-half left --screen-size W H` 를 넘기고(스테이지가 이 인자를 알 때만. Simu `feat/sim-view-aspect`), 브라우저를 W/2 x H 로 연다(`firefox --new-instance --profile <로그 디렉토리>/browser-profile -width -height`).
  창 위치는 스크립트가 못 정한다(master02 에 wmctrl·xdotool 없음). 창 관리자가 무시하면 Isaac 창은 **Super+←**, 웹 창은 **Super+→**.
- 웹 주소에는 프론트 시연 모드 쿼리 `?demo=1`(#217)이 기본으로 붙는다(`P3_WEB_QUERY`). 일반 화면은 `P3_WEB_QUERY=` 로 빈 값을 준다. 폭을 자동으로 바꾸지는 않는다(창 크기는 위 `P3_SCREEN_SIZE`).
- 캡처: `P3_CAPTURE_EVERY=5` 면 5 s 마다 화면을 저장한다(`<기동시각>-shots/`). 있는 도구만 쓴다(gst-launch-1.0 ximagesrc → png, 없으면 xwd, 둘 다 없으면 끔). `P3_CAPTURE_WINDOW` 로 창 이름을 주면 xwininfo 가 있을 때 그 창만.
- 경로·도메인·자산·재고 파일은 전부 환경 변수다(`tools/demo_v2.sh env` 로 본다, 목록은 스크립트 머리 주석).
- 검증: GPU 없는 docker(`p3-verify/jazzy-tmux:local`)에서 스테이지·팔을 가짜로 바꿔(`P3_STAGE_CMD`·`P3_ARM_CMD`) up/status/down 과 멈춤 셋을 봤다. 실물(master02)은 실습9.

## 병원 주문 10건 (`hospital_orders.py`)

관제 웹 API(`--allow-commands`)로 병원 주문 10건을 줄 세워 넣고 판정한다(긴급 끼어듦·병실 묶음 1건 포함).
표준 라이브러리만 쓰고 ROS 를 직접 부르지 않는다. 절차·판정은 [병원 데모 4.1절](../docs/runbooks/hospital-demo.md).

```bash
python3 tools/hospital_orders.py --web http://127.0.0.1:8000 --out $HOME/p3_demo_logs/orders-$(date +%H%M%S)
```

## 기동 직후 점검 (`boot_check.py`)

주문을 넣기 **전에** 화면·시계·녹화를 본다(9/24 도입). 하나라도 걸리면 끝난 값 5 이고, 그때는 주문을 넣지 않는다.
걸리면 마지막 줄이 `[boot_check] FAIL <점검> — 회차 중단` 이다. 막대 두 줄 사이다. stderr 에도 나온다.
결과 한 줄은 stage 로그 옆 `SUMMARY.txt` 에 덧붙인다. `--summary` 로 바꿀 수 있다.

```bash
source /opt/ros/jazzy/setup.bash && export ROS_DOMAIN_ID=<도메인>
python3 tools/boot_check.py --stage-log <stage 로그> --record <녹화 파일>
```

점검은 여섯이다. `stale` 은 지난 회차가 남긴 것이다. 관제 창이 둘 이상이면 걸린다. 화면 녹화기가 하나보다 많으면 걸린다. 셸만 남은 `p3v2-*` tmux 세션이면 걸린다. 목록을 찍는다. `--load-baseline`(또는 `P3_LOAD_BASELINE`)을 주면 1 분 load 가 그 2 배를 넘을 때도 걸린다. 죽이지는 않는다. 정리는 사람이 한다. `window` 는 `demo_window_layout.py --check-only` 다. `lock` 은 화면 잠금이다. 못 읽으면 걸림이다. `viewport` 는 stage 로그의 `viewport camera resolution=` 이 0 보다 크다. `clock` 은 시각이 흐른다. `/clock` 발행자는 둘 이상이 아니다. `record` 는 녹화 파일 크기가 15 s 사이에 는다. 녹화 없이 도는 회차는 `--skip record` 다. `tools/` 째 쓴다. 창 점검이 옆의 `demo_window_layout.py` 를 부른다.

트리 게이트다. 카드가 준 SHA 로 `--tree-sha <40자>` 를 주면 `tree` 점검이 켜진다. 실행 트리의 HEAD 가 같아야 한다. `git status --porcelain` 이 비어야 한다. boot_check 가 그 트리의 추적 파일이어야 한다. 실행 중인 `hospital_orders.py` 도 그렇다. `demo_v2.sh` 도 그렇다. `--need <경로>` 가 있어야 한다. `--need profile:<이름>` 도 있어야 한다. 한 줄 `[boot_check] tree=<12자> clean=<y/n> tools=<in-tree/copy> need=<ok/missing:…>` 를 찍는다. `--skip tree` 는 받지 않는다.

## 회차 뒤 녹화 QA (`record_qa.py`)

회차를 내리자마자 녹화 파일을 본다(재범 9/24 "녹화가 핵심"). ffprobe 로 영상 패킷을 한 번 훑는다. 디코드는 없다.

```bash
python3 tools/record_qa.py --record <녹화 파일> --wall-s <녹화를 켜 둔 벽시계 s>
python3 tools/record_qa.py --record <녹화 파일> --started <시작 시각> [--ended <닫은 시각>]   # epoch·날짜 포함 ISO·HH:MM:SS, 자정 넘김도 맞다
```

한 줄 `record_qa: fps=.. frames=.. dur=.. wall=.. drop=.. corrupt=.. disk=.. — OK|녹화 결손(<이유>)` 를 찍는다. 녹화 파일 옆 `SUMMARY.txt` 에 덧붙인다.
기준은 fps 29 이상이다. 길이는 벽시계와 ±2 % 다. 손상은 0 이다. 드롭은 2 % 이하다. 디스크 여유는 20 GB 이상이다. 끝나는 값 0 은 OK 다. 5 는 결손이다.
시작 전 디스크 여유는 `boot_check.py` 의 `disk` 점검이 본다.

## 시연 창 배치 (`demo_window_layout.py`)

발표 화면을 반반으로 쓴다(왼쪽 Isaac, 오른쪽 웹, 재범 9/18). `tools/demo_v2.sh up` 이 끝난 뒤 발표자가 한 번 돌린다.
`demo_v2.sh` 는 건드리지 않는다(9/21 시연 보호: preset·stub_loop·demo_v2.sh 는 시연 끝까지 그대로다).

```bash
python3 tools/demo_window_layout.py            # Isaac 창을 왼쪽 반, 웹 창을 오른쪽 반으로 옮기고 올린다
python3 tools/demo_window_layout.py --list     # 창이 안 잡히면 제목·WM_CLASS 목록부터 본다
python3 tools/demo_window_layout.py --check-only   # 옮기지 않고 지금 자리가 맞는지만 본다(손·Wnck 배치 뒤 확인)
```

- 옮기기는 창 관리자에게 **요청**한다(EWMH `_NET_MOVERESIZE_WINDOW`, 보낸 쪽 "도구", 중력 STATIC = 좌표를 클라이언트 창 기준으로). 먼저 최대화·타일·전체화면 상태를 빼 달라고 하고 빠질 때까지 최대 1 s 기다린다.
  그 뒤 창 좌표가 연속 두 번 같게 읽힐 때까지 최대 2 s 기다린다. 요청을 안 받는 창 관리자면 옛 방식(`XMoveResizeWindow`)으로 한 번 더 해 본다.
  관리 중인 창에 직접 이동을 걸면 mutter 가 무시하거나 되돌린다(9/20 master01: 요청이 통째로 무시됐다).
- 설치가 필요 없다. python3 표준 라이브러리 `ctypes` 로 `libX11` 을 부른다(master01·master02 에 wmctrl·xdotool 이 없다).
  실습9 에서 master02 의 firefox 를 같은 방법으로 옮겼다. `gi` 의 Wnck 로도 되지만(9/20 새벽 master01) 여기서는 쓰지 않는다.
- **우리 두 창만** 옮기고 올린다. 다른 창은 최소화하지 않는다(남의 창이다).
- 자리는 `_NET_WORKAREA`(위 막대를 뺀 영역)를 그대로 반으로 나눈 값이다. 그 속성이 없으면 `--screen W H`, 그것도 없으면 화면 크기를 쓴다.
  `--screen` 에 기본값은 없다(호스트마다 다르다: master01 1920x1080, master02 2048x1152). 준 값이 그대로 쓰인다.
- 창 관리자가 요청과 다르게 놓을 수 있다(9/18 master02: 요청 y 0 → 실제 +9). 고치지 않고 배치 뒤 **실제 좌표를 다시 읽어** 한 줄로 찍는다.
  9/20 새벽 master01(1920x1080)에서 **손으로** 놓은 값은 Isaac 66,32 894x1048 / firefox 1026,32 894x1048 이었다. 규칙이 아니라 그때 값이다.
- 창은 제목(`_NET_WM_NAME`·`WM_NAME`)과 `WM_CLASS` 로 고른다. 기본 식은 master02 실측이다. Isaac 은 `isaac sim python` 이다. 호스트 이름 `IsaacSim14` 의 터미널을 잡지 않는다. 9/24 다. 웹은 `navigator|p3 관제` 다. firefox 대화상자 `Firefox` 와 가른다. master02 의 Chrome --app 창(제목 `P3 관제 · 개발자`)도 잡는다. 9/24 다. 다르면 `--isaac`·`--web` 으로 준다. `boot_check.py` 도 `--isaac` 을 그대로 넘긴다. `--web` 도 그대로 넘긴다.
- 옮긴 뒤(또는 `--check-only` 면 지금 자리로) 배치가 됐는지 본다. 창 중심이 맡은 반쪽 안에 있고, 위치가 ±80 px·크기가 ±120 px 안이어야 한다.
  아니면 `배치 실패: … 요청 … → 실제 …(이유)` 를 찍고 **종료 코드 4** 로 끝난다. 9/20 master01 에서는 요청이 통째로 무시됐는데도 0 으로 끝났다(#339 뒤 관측, x 가 877 px 어긋남).
  허용값은 관측된 창 관리자 밀림(y +9·+37, 크기 ±33 안팎)을 통과시키고 "안 움직임" 을 걸리게 잡은 것이다.
- 창을 못 찾거나 `libX11`·`DISPLAY` 가 없으면 아무것도 옮기지 않고 이유와 손으로 하는 법(Isaac 창에 Super+←, 웹 창에 Super+→)을 찍고 종료 코드 3 으로 끝난다.
- 종료 코드가 3 이든 4 든 시연 절차는 같다: 손으로 붙이거나(Super+←/→) Wnck 방식으로 옮기고, `--check-only` 로 확인한다.

## run 디렉토리 집계

`aggregate_runs.py` 는 `event_logger` 의 run 디렉토리 하나를 protocol 의 지표로 모은다.
`event_logger` 는 run 마다 파일 다섯(`events.jsonl`, `order_status.jsonl`, `cabinet.jsonl`, `orders.jsonl`, `meta.json`)을 쓴다.
집계기는 `events.jsonl`, `order_status.jsonl` 이 꼭 있어야 하고, 그 run 이 닫혀 있으면 `orders.jsonl`, `meta.json` 도 읽는다. `cabinet.jsonl` 은 읽지 않는다.
출력의 `metrics` 는 run manifest 의 `metrics` 항목 형식이다. **manifest 는 사람이 이 출력을 보고 따로 쓴다.**

```bash
python3 tools/aggregate_runs.py --run /path/to/runs/<run-id> \
  --protocol experiments/protocols/pharmacy-lap-pilot-v1.json [--trip-limit-s 600] [--json]
```

- 계산 규칙은 `pharmacy-lap-pilot-v1` 과 `hospital-full-acceptance-v1`·`v2`·`v4` 의 정의를 구현한다(`SUPPORTED_PROTOCOLS`).
  - 병원 protocol 은 attempt 폴더를 `hospital_full_metrics.py` 로 읽는다(`--attempt N`). 두 PC 회차는 `--run` 을 두 번 준다.
  - 다른 protocol ID 나 규칙이 없는 지표 이름을 받으면 오류로 끝난다.
  - 지표 이름과 단위는 protocol 파일에서 읽고, protocol 에 없는 지표는 내지 않는다.
- 지표 일곱(`pharmacy-lap-pilot-v1`). 시간은 모두 `events.jsonl` 의 sim time `stamp` 차이다. 한 구간의 끝이 없으면 null(누락)이다.

  | 지표 | 단위 | 구간·값 |
  | --- | --- | --- |
  | `lap_s` | s | `REQUEST_ACCEPTED` 부터 같은 `request_id` 의 `DOCKED` 까지 |
  | `load_s` | s | `REQUEST_ACCEPTED` 부터 `LOAD_DONE` 까지 |
  | `dispense_to_end_s` | s | 그 트립 주문의 `DISPENSED` 부터 같은 `order_id` 의 `POUCH_AT_END` 까지 |
  | `return_s` | s | `RETURNED` 부터 `DOCKED` 까지 |
  | `refill_s` | s | 그 epoch 의 첫 `REFILL_REQUESTED` 부터 그 뒤 첫 `REFILL_DONE` 까지. 보충 요청이 없으면 null |
  | `pick_attempts` | count | 그 트립 주문의 `PICK_ATTEMPT` 개수 |
  | `lap_success` | ratio | 주문마다 `ORDER_DONE` 있음, 마지막 상태 `HOLD_RETURN`(`pharmacy_only`), `DOCKED` 있음, `lap_s` 가 `--trip-limit-s` 이하면 1, 아니면 0. 주문 상태 기록이 없으면 null |

- 트립은 한 epoch 안의 `request_id` 다.
  - 시간 지표는 `events.jsonl` 의 `stamp`(sim time) 차이다.
  - arm·isaac 이벤트는 `order_id` 로 맞춘다.
  - `stale` 이벤트는 쓰지 않는다.
- `status` 값:
  - `trial`: 센 트립이 하나다.
  - `trial_without_start`: `REQUEST_ACCEPTED` 가 없다. 지표는 전부 null.
  - `not_a_trial`: epoch 1 이거나 epoch 을 모른다.
  - `ambiguous`: 센 트립이 둘 이상이다. exit 1.
- epoch 1 트립은 목록에 남기되 `excluded` 로 표시한다.
- `lap_success` 의 `--trip-limit-s` 는 그 run 에서 쓴 orchestrator `trip_limit_s` 값을 준다.
- 주문 상태 기록이 없으면 `lap_success` 는 0 이 아니라 null(누락)이다.
- 출력의 `metrics` 는 내보내기 전에 `evidence.py` 의 run schema 와 누락값 규칙으로 검사한다.
  통과해도 원본이 완전하다거나 시행이 protocol 대로 돌았다는 뜻은 아니다.

### 실제 run 으로 돌린 기록

9/17 에 `master02` 에서 `main` `fd13a46`·`c3ca8fa` 로 스텁 루프를 돌리고, 그 run 디렉토리(epoch 2-11)에 이 집계기를 돌렸다.
스텁 조합이라 시간 값은 스텁이 정한 대기 시간이다. 성능 수치로 쓰지 않는다. evidence run 으로도 올리지 않았다.
이 절을 쓸 때 그 출력 원문은 보지 않았다. 아래는 세 경우의 출력 모양을 위 규칙과 코드로 정리한 것이다.

| 경우 | 출력 |
| --- | --- |
| 기동 직후 epoch 1 디렉토리 | `status` `not_a_trial`, `metrics` null. 트립은 목록에 `excluded` 로 남는다 |
| 리셋 뒤 요청이 오기 전에 끝난 epoch | `status` `trial_without_start`, 지표 일곱 개가 모두 null(`missing_count` 1) |
| 트립 중 리셋으로 끊긴 epoch | 트립 하나라 `status` `trial`. 주문 마지막 상태가 `ABORT`(`reset_interrupted`)면 `lap_success` 는 0. 그 상태가 이 디렉토리에 없으면(다음 run 에 `late` 로 간 경우) null. `DOCKED` 가 없어 `lap_s` 는 null |

- #87 이 `meta.json` 에 `closed_by_reset_epoch` 를, `order_status.jsonl` 행에 `late` 표시를 더했다. 집계기는 이 둘을 아직 쓰지 않는다(후속).
  - `late` 행도 다른 행과 똑같이 `request_id` 로 트립에 붙는다. 이전 epoch 요청의 늦은 상태는 새 run 에 있어도 그 run 의 트립 `request_id` 와 달라 지표에 들어가지 않는다.
  - `closed_by_reset_epoch` 는 출력에 나오지 않는다. 리셋으로 닫힌 run 인지는 `meta.json` 을 직접 본다.
  - `cabinet.jsonl` 의 `pre_reset`·`used` 표시도 읽지 않는다(`pharmacy-lap-pilot-v1` 지표에 보관함 관측이 없다).

## 그 밖의 도구

위 절에 없는 파일이다. 한 줄 설명은 각 파일 머리 docstring 에서 옮겼다.

| 파일 | 하는 일 |
| --- | --- |
| `hospital_full_metrics.py` | `hospital-full-acceptance-v1`·`v2`·`v4` 의 attempt 폴더(로그·`event_run/`·`boot_check.txt`·녹화 QA 등)에서 지표를 센다. `aggregate_runs.py` 가 부른다 |
| `judge_run.py` + `judge_criteria.example.yaml` | 회차 로그와 run 기록을 읽기만 하고 보충·낙하·거부 등을 센다. 센 값 옆에 근거 원문 한 줄을 낸다. 판정선은 `--criteria` 파일에 있다 |
| `round_summary.py` | 한 회전의 run 기록 여럿에서 `attempt_success` 성공률과 `failure_class`(robot·infra·operator)별 건수를 낸다. `--pass-ratio`(기본 0.9)는 표시용이다. 판정선은 protocol `purpose` 다 |
| `hw_watch.py` | GPU 온도(87 도)·스로틀·load 기준선 2 배·전력 급락을 감시하고 문제일 때만 한 줄 낸다. 잔류 프로세스 판정은 `boot_check.py` 의 것을 그대로 쓴다 |
| `ci_test_counts.py` | `colcon test` 뒤 패키지별 실행된 시험 수를 찍는다. 시험 파일이 있는데 실행 0 개면 실패한다. skip·xfail 수는 `ALLOWED` 표와 같아야 한다(`ci.yml` 이 부른다) |
| `check_dispenser_asset.py` | 조제기 USD 자산의 hash·크기·구조·입구 기준점을 metadata 와 대조한다. `pxr`(usd-core)이 필요하다 |
| `git-hooks/pre-push` | 머지된 PR 의 브랜치에 커밋을 더 올리는 push 를 막는다. 설치는 클론마다 `git config core.hooksPath tools/git-hooks` 다 |

각 도구의 시험은 [`tests/`](../tests/README.md) 에 있다.
