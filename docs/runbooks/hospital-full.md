# 병원 전 구간 한 바퀴 (P3_WORLD=hospital)

순서는 이렇다. 웹 주문이다. M0609 가 보충한다. 조제한다. 봉투는 씬 컨베이어로 창구 A1 롤러 끝까지 간다. 합본 AMR 의 UR5 가 집어 트레이에 싣는다. Nav2 로 병상까지 간다. 협탁에 내려놓는다. 도크로 복귀한다. 그 다음 `ORDER_DONE` 이다. 재범 결정 #527 이다. preset 은 #553 이다.

마스터에서 도는 병원 회차는 **창 모드 전 구간 한 바퀴 하나**다(재범 9/23). 기동만·보충만 같은 부분 회차는 돌리지
않는다. 확인이 필요하면 오프라인(usd-core·단위 시험)으로 하고 Isaac 은 한 바퀴 안에서 본다.

- 기준: 릴리스 `v1.1.0` = main `f316197`(#797). 2026-09-30 에 `tools/demo_v2.sh`·`sim/standalone/pharmacy_stage.py` PRESETS 와 대조했다.
- `v1.1.0` 기본은 **카메라 집기**다. 봉투는 A1 모듈 탁자에 정착한다. AMR 은 A1 도크(= 적재 자리)에서 움직이지 않는다. 그 자리에서 집는다(#790, #797).
- `v1.1.0` 트리로 돈 한 바퀴 L3 기록은 이 문서를 고친 시각에 없었다. #797 은 L3 미실행으로 병합됐다. 카메라 배송 성공은 `05b8e28` 의 `bed_a1` 1건이다([실습45](../practice/simworld/practice-45.md)).
- 동결 protocol v4 를 넘은 구성은 `v1.0.0` 회전 7(`9760d9d`, 참값 집기)이다([회전 장부](../reha/campaigns.md)). 3.2 절을 본다.
- 받는 법·멈추는 법·되돌리는 법은 [배포 런북](deployment.md)이다. 런북 전체 목록은 [런북 색인](README.md)이다.

## 0. 새 PC 에서 처음 (한 번만)

README 와 이 문서만 보고 새 clone 에서 한 바퀴를 돌았다. 첫 시도가 주문 전에 멈췄다. master01 회차32 다. 5a51804 다. #240 이다.
그때 막힌 줄을 여기 순서대로 푼다. 이미 도는 PC 는 건너뛴다.

1. **받기와 빌드.** 릴리스는 따로 된 디렉토리로 받는다([배포 런북 3절](deployment.md#3-릴리스를-따로-받는다)).
   `git worktree add ../release/v1.1.0 v1.1.0` 다음 그 디렉토리에서 `colcon build`. `P3_INSTALL` 기본이 `$REPO/install` 이다.
   새 worktree 에는 아래 2·3 의 Git 밖 파일(웹 venv, 조제기 자산)이 없다. 그 디렉토리에서 다시 한다.
2. **웹 백엔드 venv.** `demo_v2.sh` 는 `web/backend/.venv/bin/python` 으로 웹을 띄운다(`P3_WEB_PY`). 없으면 만든다.
   `--system-site-packages` 가 빠지면 venv 안에서 `rclpy` 가 안 보여 실물 모드가 죽는다([web/backend/README](../../web/backend/README.md)).

   ```bash
   cd web/backend && python3 -m venv --system-site-packages .venv && . .venv/bin/activate \
     && pip install -r requirements.txt && deactivate && cd -
   ```

3. **조제기(DPB-80) 자산.** 병원 씬은 조제기를 `sim/material/etc/Automatic+Blister+Packing+Machine+(DPB-80)/model.usd`
   에서 찾는다(`hospital_navigationv1.usda` 의 `../material/etc/…`). 팀 자산 ZIP 을 받아 **그 경로에** 풀어 둔다.
   `sim/README.md` 의 "ZIP 을 `sim/outputs/` 에 두면 `hospital_main.py` 가 푼다" 는 **다른 실행 경로**(`hospital_main.py`)의
   이야기다 — 이 런카드(`pharmacy_stage.py`)는 그 자리를 보지 않는다. 경로가 틀리면 조제기가 빠진 채 기동한다.
   ZIP 은 GitHub Release 태그 `assets/hospital-20260918` 의 비공개 첨부로 받는다.
   저장소는 private 다. 익명 `curl` 은 404 다.
   저장소 읽기 권한의 `gh` 로 받는다.

   ```bash
   gh release download assets/hospital-20260918 -R jaebeom/ROKEY_P3_A3 -D sim/outputs
   (cd sim/outputs && sha256sum -c ../scenes/hospital_assets.sha256)
   unzip -q -o sim/outputs/hospital-custom-assets-20260918.zip material/etc/* -d sim
   ```

   `f519fb2c3f0e386f99b27e7ce707db7a14c2f2730c0959ec6f472293d2410144` 는 **자산 ZIP**
   (`hospital-custom-assets-20260918.zip`)의 전체 SHA-256 이다. 위 `sha256sum -c` 가 이 값을 대조한다.
   풀고 나면 기대 파일은 `sim/material/etc/Automatic+Blister+Packing+Machine+(DPB-80)/model.usd` 다. 그 파일의
   전체 SHA-256 은 `731307e2c6ca2e3e9ea790112fba1bbd6e399023cf4ca84b818c1a5b631cb3ef` 다(9/25 계산).
   예전 이 절은 f519fb2c… 를 model.usd 의 값처럼 적었다. 착오였다. ZIP 은 `sim/outputs/` 에만 둔다. `sim/material/` 에 안 풀면 조제기가 빠진 채 기동한다.
4. **합본 AMR·M0609 자산.** `P3_AMR_COMBINED`(합본 `ridgeback_ur5.usd`)와 `P3_M0609`(아래에 `Collected_m0609_gripper/`·
   `doosan-robot2/urdf/`·`rmpflow/`) 는 저장소에 없다. master01 에서 쓴 것(9/24 관측)은 이렇다.
   - `ridgeback_ur5.usd`: Isaac Sim 5.1 **공식 자산** `Isaac/Robots/Clearpath/RidgebackUr/ridgeback_ur5.usd` 를 Isaac
     Collect Asset 으로 모은 사본이다(경로에 `omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1/…`
     가 그대로 남아 있다). 7,522,862 B 다. sha256 앞은 `908061d3` 다. master02 와 같다. 스테이지가 팔 받침·트레이를 자기
     레이어에 덧대므로 자산 파일은 손대지 않은 원본이다. 모은 사본 대신 공식 자산 서버 주소를 그대로 줘도 되는지는
     **미확인**이다.
   - `P3_M0609`: P2 저장소 `jaebeom/cobot3_ws` 의 `isaacpjt/M0609/` 다(`Collected_m0609_gripper`·`doosan-robot2`·`rmpflow`).
     그 저장소를 받을 권한이 있어야 한다.
   - 누가 언제 모았는지는 기록이 없다. 새 PC 에서는 두 경로를 위처럼 맞추고 `sha256sum` 을 회차 보고에 적는다(3.2 절).
5. **화면·브라우저.** `P3_SCREEN_SIZE` 기본은 `"2048 1152"`(master02 패널)다. 다른 모니터면 그 값을 준다(master01 은
   `"1920 1080"`). `P3_BROWSER` 기본은 비어 있다. **웹 창이 안 뜬다.** boot_check 가 웹 창을 못 찾는다. 주문 전에
   멈춘 자리다. 2절 명령처럼 `P3_BROWSER=firefox` 를 준다.
6. **계획 캐시.** M0609 계획은 `~/.cache/rokey_p3/plan_cache/<키>.pkl` 에 남는다. 키가 씬·조제기·코드의 해시라 입력이
   같으면 다시 써도 같은 계획이다 — 지우지 않아도 된다. **캐시 없이 처음부터** 도는지 보고 싶을 때만 그 폴더를 옆으로
   옮긴다(`mv ~/.cache/rokey_p3/plan_cache ~/.cache/rokey_p3/plan_cache.off`). 첫 기동은 18칸을 새로 푸느라 그만큼 길다.

7. **회차마다: 기동 전 잔류 정리, 종료 뒤 잔류 0 확인.** 한 번만이 아니라 **매 회차** 한다. 9/24 master02 에 관제 창이
   60개 남아 있었다. 15시간 된 녹화기가 남아 있었다. load 는 18.3 이었다. 그 상태로 회차가 돌았다. #576 재발
   방지대책이다. 그 회차들의 rtf 는 잔류 부하가 남은 값이다.

   기동 전(아무것도 안 띄운 상태)에서 넷을 본다. 하나라도 어긋나면 **띄우지 않는다.** 자기가 연 것이 아니면 끄지
   않는다. 목록을 회차 보고에 붙인다. 주인에게 묻는다. 자동으로 죽이지 않는다.

   | 무엇 | 명령 | 기대 |
   | --- | --- | --- |
   | 관제 창(브라우저) | `pgrep -fc -- '--new-instance --profile .*-browser-profile'` | 기동 전 0. 기동 뒤 1 |
   | 녹화기 | `pgrep -af 'gst-launch-1.0\|rec_guard\|ffmpeg'` | 없다. 마스터 녹화는 `rec_guard.sh` 가 `gst-launch-1.0 … ximagesrc` 를 띄운다 |
   | tmux | `tmux ls` | `p3v2-*` 세션 없음(다른 세션도 없어야 한다) |
   | load | `cat /proc/loadavg` 첫 값 | 그 장비 유휴 기준선의 2배 이하. 기준선은 회차 보고에 적는다 |

   `boot_check` 의 `stale` 점검이 기동 뒤에 이 넷을 본다(#676, `P3_LOAD_BASELINE`). 기동 전에는 `boot_check` 가 돌지 않으므로 위 표를 손으로 본다.

   끝나면 `P3_WORLD=hospital tools/demo_v2.sh down` 을 한다(up 과 같은 월드). master01 9/25 회차73 은 월드 없이 내려
   tmux `p3v2-nav` 가 남았다. 지금 `down` 은 월드와 상관없이 역할 세션을 다 본다(`DOWN_ALL`). 자기가 연 녹화기와 창을 닫는다. 위 표를 다시 본다. **잔류 0** 을 확인한다. 회차 보고
   (5줄)에 "잔류 0" 한 줄을 넣는다. 0 이 아니면 무엇이 남았는지 적는다.

**주의.** 자산 ZIP release 는 비공개다. 인증 없이 `curl` 로 받으면 404 다(master01). 받는 법은 위 `gh` 다. 일반 공개는 하지 않는다. G7 후속이다.
합본 AMR 경로는 이 ZIP 이 아니다. M0609 경로도 이 ZIP 이 아니다. 사이트 값이다.

## 1. 조제실 입력을 먼저 만든다

씬과 조제기에서 base 와 워크셀을 함께 만든다. 한 번만 하면 된다. 씬이 바뀌면 다시 한다. 조제기 에셋이 바뀌면 다시 한다. 준비기가 바뀌면 다시 한다.

```bash
~/isaacsim/python.sh $REPO/sim/standalone/prepare_workcell_integration.py \
  --base-usd $REPO/sim/scenes/hospital_navigationv1.usda \
  --dispenser-usd $REPO/src/rokey_p3_description/models/dispenser/dispenser.usdc \
  --output ~/markle_tmp/m2-hospital-base-<SHA>
```

- 출력 폴더에 넷이 생긴다: `base.usda`·`workcell.json`·`measurements.json`·`dispenser-placement.json`.
  (`manifest.json` 은 **없다** — 전에 이 문서가 있다고 적었는데 틀렸다.)
- `dispenser-placement.json` 이 조제기 검사 결과다(`scene_geometry: PASS`).
- stdout 끝에 한 줄: `{"cells": 18, "obstacles": …, "round_center": [-8.05, 11.115, 0.98], "collision": {"shelf": "boxes", …}}`.
  출력을 파일로 돌리면 이 줄이 빠질 수 있었다 — Kit 가 프로세스를 끝내기 전에 버퍼를 안 비웠다(master01 회차32 의
  `prepare.log`). 준비기가 이제 바로 비운다. 종료 코드 0 과 위 파일 넷이 성공의 기준이다.
- `pxr` 이 없으면 준비기가 스스로 Kit 을 headless 로 띄운다. 회차가 아니라 입력 만들기다.
- **실습37 의 `integrated-09/base.usda` 를 그대로 쓰지 않는다.** 그 파일은 원통 투입구를 (+0.30, −0.10, 0) 옮겨 저작했다. 그래서 조제기 검사에서 멈춘다. 재범 9/22 결정 #496 이다. 투입구를 옮기지 않는다.
  그 회차의 입력은 `experiments/fixtures/hospital-integrated-09/` 에 보존돼 있다 — 재현 자료이지 실행 입력이 아니다.

## 2. 한 바퀴

```bash
# v1.1.0 병원 기본은 카메라 집기다(봉투·인식표 QR, A1 탁자 정착, 도크 = 적재). 동결 protocol v4 회차면
# P3_CAMERA_POUCHES=0 을 더한다(3.2 절 명령). 증거 회차면 P3_RUN_HOST=master01(또는 master02)도 준다.
P3_WORLD=hospital P3_SIM_SENSORS=1 \
  P3_AMR_COMBINED=<ridgeback_ur5.usd> P3_M0609=<M0609 자산 루트> \
  P3_HOSPITAL_SCENE=~/markle_tmp/m2-hospital-base-<SHA>/base.usda \
  P3_WORKCELL_LAYOUT=~/markle_tmp/m2-hospital-base-<SHA>/workcell.json \
  P3_DISPENSER_FILE=$REPO/src/rokey_p3_orchestrator/config/dispenser.hospital-v0.yaml \
  P3_BROWSER=firefox P3_SCREEN_SIZE="<W H>" \
  P3_DOMAIN=<도메인> tools/demo_v2.sh up
# 웹 창(firefox)에서 ord-0001(bed_a1) 한 건. 끝나면 P3_WORLD=hospital tools/demo_v2.sh down, 그다음 0절 7 의 잔류 0 확인
```

`P3_BROWSER` 가 없으면 웹 창이 안 뜨고, `P3_SCREEN_SIZE` 가 모니터와 다르면 화면 반반 배치가 어긋난다(0절 5).

**주문 전 점검 — `up` 이 끝나고 브라우저 창이 뜬 다음, 주문을 넣기 전에 둘을 차례로 돌린다**(9/24, #625).

```bash
python3 tools/demo_window_layout.py --screen <W> <H>        # 창 배치. P3_SCREEN_SIZE 와 같은 값. 창이 없으면 30 s 기다린다

# boot_check 는 스택과 **같은 ROS 환경**에서 돌린다(아래 설명)
source /opt/ros/jazzy/setup.bash && source $REPO/install/setup.bash
export ROS_DOMAIN_ID=<P3_DOMAIN 과 같은 값>
[ -f ~/.ros/fastdds_whitelist.xml ] && export FASTRTPS_DEFAULT_PROFILES_FILE=~/.ros/fastdds_whitelist.xml
# 두 PC 모드(P3_PEER 를 줬을 때)면 이것도: export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
python3 tools/boot_check.py --stage-log ~/p3_demo_logs/<기동시각>-stage.log --record <녹화 파일> \
  --costmap-topic /amr_1/global_costmap/costmap --nav-log ~/p3_demo_logs/<기동시각>-nav.log \
  --tree-sha <카드가 준 40자 SHA>     # v1.1.0 이면 f316197d3e7b3b64a33a0dd29c4468fde26910a1
```

- **ROS 환경이 스택과 달라지면 `/clock` 이 안 보여 `clock` 점검이 걸린다**(master01 회차 관측, 9/24). `demo_v2.sh` 는
  역할마다 `source <P3_ROS_SETUP> && source <P3_INSTALL>/setup.bash && export ROS_DOMAIN_ID=<P3_DOMAIN>` 을 준다(`ros_env`).
  Isaac 은 **한 PC 모드라도** `P3_FASTDDS_PROFILE`(기본 `~/.ros/fastdds_whitelist.xml`) 파일이 있으면 그 프로필로 뜬다
  (`stage_cmd`). 두 PC 모드면 모든 역할에 그 프로필과 `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET` 이 붙는다. 위 블록이 그
  셋을 맞춘다. `P3_ROS_SETUP`·`P3_INSTALL`·`P3_FASTDDS_PROFILE` 을 바꿨으면 같은 값을 쓴다.

- `boot_check` 가 끝나는 값이다. **0 은 통과다. 5 는 하나라도 걸린 것이다.** 2 는 인자가 잘못이다. 걸리면 마지막 줄이
  `[boot_check] FAIL <점검> — 회차 중단` 이다. **5 면 주문을 넣지 않는다.** 내린다. 원인부터 본다.
- 스테이지 로그는 `$P3_LOG_DIR/<기동시각>-stage.log` 다(기본 `~/p3_demo_logs`, `up` 끝 줄에 경로가 나온다).
- 녹화는 `demo_v2.sh` 가 하지 않는다. `up` **전에** 따로 켠 녹화 파일을 준다(`record` 점검이 그 크기가 느는지 본다).
- 창은 늦게 뜰 수 있다. 회차33·73 은 웹 창이 늦게 떠 창 배치가 `창을 못 찾음: ['web']`(3)으로 끝났고, 그 뒤
  `window` 가 걸렸다. 창 배치는 창이 없으면 `--wait-s`(기본 30 s) 동안 다시 찾는다. `boot_check` 는 창이 자리에 올 때까지
  `--window-wait-s`(기본 20 s) 기다린다. **창 배치가 0 으로 끝난 뒤에 `boot_check` 를 돌린다.** 창 배치가 3 이면 웹 창이
  떴는지 보고 창 배치부터 다시 돌린다.
- `boot_check.py` 는 #625 로 main 에 들어왔다. 그 전 SHA 에는 없다.
- **`--costmap-topic`·`--nav-log` 는 v1.0 회전부터 기본이다**(9/27 결정, "기능 기본 ON" — 9/23 교훈).
  `costmap` 점검(#742, 회차133 #240 5848721883): 전역 코스트맵이 Nav2 기본 빈 격자
  (5x5 m)로 남아 로봇이 범위 밖이 되는 사고를 주문 전에 잡는다. `--costmap-topic` 을 안 주면 이 점검은
  늘 통과다. 플래그가 생기기 전 SHA(campaign3·4 의 `a4b1a4e` 등)에서는 이 두 플래그를 뺀다.
- **`--tree-sha` 를 주면 tree 게이트가 켜진다.** 지금 트리가 그 SHA 인지, 작업 트리가 깨끗한지, `boot_check`·
  `demo_v2.sh`·`hospital_orders.py` 가 그 트리 안의 파일인지 본다. `tree` 는 `--skip` 으로 뺄 수 없다(`boot_check.py` 머리 주석).

| 값 | 기본 | 뜻 |
| --- | --- | --- |
| `P3_WORKCELL_LAYOUT` | 없음 (**필수**) | 1절이 만든 `workcell.json`. 비우면 기동이 멈춘다 — 빈월드 조제실로 되돌아가는 길은 없다(재범 9/23) |
| `P3_HOSPITAL_SCENE` | `sim/scenes/hospital_navigationv1.usda` | 1절이 만든 `base.usda` 를 준다. 기본값(씬 원본)은 조제실이 없다 |
| `P3_AMR_COMBINED` | 없음 (**필수**) | 합본 ridgeback_ur5. 병원에서 봉투를 집는 팔이 이것이다 |
| `P3_DISPENSER_FILE` | 없음 (**필수**) | `dispenser.hospital-v0.yaml` 을 준다. #791 뒤 선반 논리 재고는 약품마다 9통이다. #791 전 회차에서는 한 바퀴에 모듈 보충(기동 직후)과 원통 보충(첫 봉투 뒤)이 각각 났다. v1.1.0 에서 같은지는 L3 미확인이다 |
| `P3_CAMERA_POUCHES` | `1`(병원) | 재범 9/29 "QR 반드시 찍고"(#784). 봉투 QR 이 주문과 맞아야 집는다. **동결 protocol v4 회차는 `0` 을 명시한다**(v4 는 참값 집기 구성이다. 카메라 회차는 새 protocol 이다). 이 값이 아래 여러 기본을 가른다. 아래 행에 "카메라 · 참값" 으로 나눠 적었다 |
| `P3_AMR_START` | 카메라 `-8.266 4.102` · 참값 `-8.995 4.686` | 둘 다 그 구성의 zones 파일에 있는 `dock_1` 이다. `dock_1` = `load` 다(#790 B안, #797). 카메라 자리는 `zones.hospital-receiver.yaml`, 참값 자리는 `zones.hospital.yaml` 이다. 전 값은 `-7.272 4.784`(9/25 벽 앞)·`-8.238 4.169` 였다 |
| 도크 정차(9/29 모듈 왼쪽) | 참값 zones: dock_1 (−8.995, 4.686) = `load` · dock_2 (−6.015, 4.686) · dock_3 (−3.018, 4.686) · dock_4 (−0.076, 4.686), yaw −90°. 카메라 zones: dock_1 = `load` (−8.266, 4.102), dock_2–4 는 같다 | 재범 9/29 B안(A1 도크 = 적재 자리) 뒤 "도킹 스테이션 옮길꺼면 다 옮겨야지": 넷 다 제 모듈 왼쪽, A1 도크와 같은 상대 자리(모듈 왼끝에서 0.577 m, #795). 카메라 구성의 dock_1 은 #797 이 탁자 앞 적재 자리로 옮겼다. 전에는 9/25 벽 앞(모듈 오른쪽, dock_2 −4.292 · dock_3 −1.295 · dock_4 1.646, y 4.784). **떠날 때는 접근점까지 곧게 물러난 뒤 돈다** — 도크에서 제자리로 돌면 옆 모듈(중심↔모듈 0.577 < 회전 반경 0.638)에 닿는다(회차77, #240 5820319699). 접근점에서 모듈까지 회전 반경 + 0.10 m. 여벌 AMR(N=2·4)은 dock_2–4 에 선다. `hospital_nav.dock_like_load_pose`, navigation `routes.DEPART_BY_SLIDE_KINDS` |
| `P3_ZONES`·`P3_ROUTES` | 카메라 `zones/routes.hospital-receiver.yaml` · 참값 `zones/routes.hospital.yaml` | 주행·웹·스테이지가 같은 파일을 받는다(`up` 이 대조하고 다르면 멈춘다). 두 벌은 `sim/standalone/hospital_nav_files.py` 로 다시 만든다(7절, [hospital-nav-l3 5절](hospital-nav-l3.md#5-다시-만들기isaac-없이)) |
| `P3_ORDER_POOL` | `order_pool.hospital.yaml` | 스택·웹·스테이지가 같은 파일을 받는다 |
| `P3_UR5_ARM_PARAMS` | 카메라 `ur5_arm.amr-combined.camera-receiver.yaml` · 참값 `ur5_arm.amr-combined.gripper.yaml` | 주지 않으면 `demo_v2.sh` 가 고른다. 카메라 판은 추가 하강 0.05 m 실측 보정이 들어 있다(#796, 근본 수정 아님) |
| `P3_HOSPITAL_RECEIVER_PRIM` | 카메라 `/World/P3Base/Scene/Environment/hospital/SM_SideTable_02a_74` · 참값 없음 | A1 모듈 탁자다. 봉투가 여기 정착한다. 빈 값을 주면 끈다. 그때는 `P3_ZONES` 도 `zones.hospital.yaml` 로 준다(`demo_v2.sh` 머리 주석) |
| `P3_BELT_VIEW_OFFSET`·`P3_DISPENSE_WHILE_DISPATCHING` | 카메라 `0`·`true` · 참값 (쓰지 않음)·`false` | 카메라 기본은 적재 자리로 가는 동안 첫 조제를 시작한다(#796 프로필). 관측점 오프셋은 카메라 집기에서만 스택에 넘어간다 |
| `P3_V2_RAIL_SELECT` | `preferred_first` | M0609 레일 후보 순서다. #797 에서 기본이 됐다(재범 9/29 "디폴트로 켜서"). 되돌리기는 `first_feasible` 이다 |
| `P3_BELT_TIMEOUT_S` | `60` | 잰 운반 34.58 s(#240)보다 넉넉히. 34.58 s 는 컨베이어 배율 1 에서 잰 값이다. #789 가 preset 배율을 2 로 올렸다. 2 배에서 잰 운반 시간은 아직 없다 |
| `P3_DISPENSE_TIMEOUT_S` | `30` | 어댑터가 Isaac 조제 응답을 기다리는 wall 시한. 계약 기본 2 s 로는 병원 틱이 길어 거부된다. 10 에서 ord-0009 가 `not_ready` 로 3회 거부됐다. #660(afc1135) 뒤 `tools/demo_v2.sh` 의 hospital 기본이 30 이다 |
| `P3_STAGE_TIMEOUT_S` | `900` | 병원은 충돌체를 굽느라 기동이 길다 |
| `P3_LOAD_BASELINE` | master01 `8.4` · master02 `13.2` | `boot_check` stale 의 load 기준선이다. 1 분 load 가 그 2 배를 넘으면 걸린다. 값은 잔류를 정리한 N=1 회차의 load 중앙이다. master01 은 회차46 이다. master02 는 `af78350` 이다. 출처는 `docs/presentation/challenge-multipc-bench.md`(main `dd5f240`) 다 |
| `P3_ARM_READY` | `완료 종류: .*cylinder` | 팔이 종류별 집계 뒤 찍는 줄. 18칸이라 빈월드의 `16/16칸` 을 기다리면 안 된다 |
| `P3_CAMERA_TAGS` | `P3_CAMERA_POUCHES` 를 따름 | 병상·스테이션 인식표(pt-·st-)도 손 카메라 QR 로 읽는다(`scan_tag_source:=camera`). `demo_v2.sh` 가 팔 params 의 `tag_standoff_m` 이 0 보다 큰지 본다. `0` 이면 인식표만 참값이다 |
| `P3_CAMERA_VIEW` | `0` | `1` 이면 QR 추적 영상 `/amr_1/hand_camera/qr_view` 를 `rqt_image_view` 창으로 띄운다(#787). 카메라 집기일 때만 뜬다 |
| `P3_STAGE_ARGS` | 없음 | 스테이지에 더 줄 인자. 예 `--seed 7 --workcell-empty-cells 6` (약통 시드 배치). 병원 preset 기본은 18칸을 다 채운다(`workcell_empty_cells` 0, #791) |

### Play/Stop

Isaac 툴바 Stop 을 눌렀으면 이 순서로 잇는다. Stop 이다. 자동 Play 다. `POST /api/reset` 이다. 주문이다.
Stop 을 누르면 스테이지가 스스로 다시 Play 한다. `physics_view recovered` 다. 몸체는 USD 에 작성된 자세로 돌아간다. 그래서 주문 전에 리셋이 필요하다.
AMR 까지 되살아나는 것은 `79a0800` 부터다. #641 이다. 회차39 에서 두 주문 모두 5/5 였다. 그 전 SHA 는 AMR 이 멈춘다. 회차37 이다.

## 3. 판정 다섯 장면

앞 장면을 못 넘으면 뒤는 보지 않는다.

| # | 장면 | 보는 줄 | 기준 |
| --- | --- | --- | --- |
| ① | 조제실이 섰다 | `workcell_stock seed=… present=…/18`, `canister_settle … max_move_m=`, `v2 계획 캐시 종류별: cylinder=9/9 module=9/9. 완료 종류: cylinder, module` | 약통이 판 위에 서 있고(움직임 5 mm 미만) 18칸이 다 풀린다 |
| ② | M0609 보충 두 번 | `refill_ros released … target=round` 와 `… target=module`, `REFILL_DONE` | 종류마다 한 번씩. 병원 prim 과의 touch 0 |
| ③ | 봉투가 A1 끝까지 | `hospital_conveyor … "bodies":19,"node_targets":19`, `hospital pouch_at_end … in_sensor_zone=True` | `sim_s_since_dispense` ≤ 60(잰 값 34.58), `pouch_left_belt` 0줄 |
| ④ | 합본이 집어 싣는다 | `pouch placed … in_slot=True offset_xy=`, `PickPouch … ok` | 트레이 칸 안. 놓기 오차는 기록만 한다 |
| ⑤ | 병상·복귀·주문 | `GoToZone bed_a1` SUCCEEDED, `bed_a1/cabinet present=true`, `ORDER_DONE`, AMR 이 도크 | 주행 touch 0, 주문 1건 완료 |

위 줄 이름은 참값 집기 회차(protocol v4)에서 쓴 것이다. `v1.1.0` 카메라 기본에서는 둘이 다르다.

- ③: 봉투가 롤러 끝이 아니라 A1 탁자에 정착한다. 기동 줄 `hospital receiver prim=… settle_s=1.0` 이 나온다. 정착을 알리는 줄의 이름은 이 문서에서 코드와 대조하지 않았다(미확인).
- ③: 기준 60 s 와 잰 값 34.58 s 는 컨베이어 배율 1 의 것이다. 배율 2(#789)의 값은 아직 없다.
- ④·⑤: 봉투 `ord-` QR 과 병상 `pt-` QR 을 손 카메라로 읽는다. [실습45](../practice/simworld/practice-45.md)는 `AUTH_OK` 뒤 `ORDER_DONE`·`DELIVERED`·`DOCKED` 였다.
- 카메라 집기에서 `bed_a1` 밖 목적지와 반복 신뢰성은 확인하지 않았다(#796, #797).

### 3.1 골든 회차

같은 골든 SHA 로 돈 회차를 한 줄씩 적는다. 기록은 `docs/reha/`, 원문은 #240 이다.

| 날짜 | SHA · 장비 · 구성 | 다섯 장면 | DELIVERED · touch · rtf | 원문 · 기록 |
| --- | --- | --- | --- | --- |
| 9/23 23:23 | `4d01333` · master02 · 합본 **N=2**(`amr_2` dock 대기) | 5/5 | **state 는 2 다. DELIVERED 다.** /Amr/ touch 는 0 이다. rtf 는 0.429 다. stall 은 1 이다 | #240 5796814149 다. [리하04](../reha/reha-04.md) 다. 촬영 2대 판정을 충족한다. 감속기는 `여유 모름` 이다. 50 % 로 고정이다. #620 이다 |

### 3.2 기준 구성 — 릴리스와 골든

회차 보고는 이 절을 가리킨다. 9/27 `v0.5.0-rc.1` 부터 기준 SHA 는 릴리스 태그와 [배포 기록](../../evidence/deployments/README.md)으로 남았다.

| | 태그 · 커밋 | 구성 | 판정 기록 |
| --- | --- | --- | --- |
| 지금 릴리스 | `v1.1.0` · `f316197` | 카메라 집기 기본(2절 명령) | acceptance 회전 없음(릴리스 노트). 한 바퀴 L3 기록 없음 |
| 마지막 acceptance 통과 | `v1.0.0` · `a5d1107`(회전 7 은 `9760d9d` 트리) | 참값 집기, protocol v4(아래 명령) | 회전 7 14/14, attempt 12·13 미실행([회전 장부](../reha/campaigns.md), [v1.0.0 배포 기록](../../evidence/deployments/2026-09-28-jaebeom-v1-0-0.md)) |

- 아래 명령을 `v1.1.0` 트리에서 돌리면 회전 7 과 다른 구성이다. 컨베이어 2배(#789), 감속기 근접 0.7 m/s(#788), 도크 = 적재(#790), 조제실 가득·소모(#791), 도크 벽 반투명(#792), 레일 `preferred_first`(#797)가 더해졌다.
- 그 구성으로 돈 회전 기록은 이 문서를 고친 시각에 없었다.
- 감속기 긴급정지 수정은 `v1.1.0` 에도 없다. #752 는 진단이다(릴리스 노트).
- 바꾸고 싶은 것은 실험 SHA 로 돌린다. 회차마다 변수는 하나다(운영 규칙 ③).

**지난 골든 기록(9/23–9/25).** 골든은 그때 팀이 합의한 한 점이었다. 새 골든은 검증 통과와 판정선 한 바퀴 통과가 둘 다 있어야 섰다(규칙 ④).
마지막 골든은 골든-4 `aca8840` 이었다. 아래 줄은 그때 기록이다.

- 9/25 골든 후보는 main `0b1319b` 였다(9/25). 그 뒤 `v0.5.0-rc.1`·`v0.5.0` 태그가 찍혔다([v0.5.0 배포 기록](../../evidence/deployments/2026-09-27-jaebeom-v0-5-0.md)).
  - main `0b1319b` = RC-4 `64e5ab7`(#706) + campaign 2 스택(#712: 보관함 참값이 안에 있는 주문마다 present, 상판 비전
    계측, 간호스테이션 칸 B 하나, 로비 범례) + 자산 해시 정오표(#715: 0절 `f519fb2c…` 는 자산 ZIP, 조제기 `model.usd` 는
    `731307e2…`) + phase F 집계(#714).
- **RC-4 확정 `64e5ab7`**(9/25, PR #706, main 에 들어갔다). RC-4 = RC-3(`7bf81cc`: 속도 90 %·트레이 홀더·셀 바닥·더미 2·보행자 2·
  기록 줄) + 비전 v1·더미/보행자 양보 + 목적지 B·C·D(실물 협탁) + 도크 벽 앞·언도킹 + 칸 비켜 놓기 + `down` 전 역할.
  - 목적지: 병동은 B `station_b` 다. 병실은 C 병동 입구 복도 협탁 `station_c`(C1)·`station_d`(C2) 다. 병상은 D 다.
    테이블은 `st-<zone>` 다. 침상은 `pt-<환자>` 다. 정차·놓는 점은 계약 v1 3절 "병원 배송 목적지 B·C·D" 표다.
  - 도크: 아래 표의 "도크 정차" 줄. 떠날 때 접근점까지 곧게 물러난다. 그 뒤에 돈다.
  - 증거: master01 촬영 구성 회차82–87(C1·C2·B 1인, C2 병실 묶음 3봉투, Play/Stop, N=2) 전부 통과·touch 0,
    #240 5820894798·5821025019·5821695136 외. master02 beds-all 13 요청 13/13·touch 0·rtf 0.397·134 분.
    수정 전 6812ee5 는 두 마스터 모두 dock_1 언도킹 접촉(회차77·78, master02 touch 37)이었다.
  - 미확인: 3봉투 월드 xy 수치는 로그 줄이 없다. 리셋 뒤 `m0609_max_rad` 0.306 은 기록만이다.
  - 동결 protocol attempt 11(D1–D10 10건)은 `tools/hospital_orders.py --profile default --batch ""` 로 돈다.
    `--profile beds-all` 은 테이블까지 13 요청이다.
- 골든-4 `aca8840` 은 골든-3 에 접근점 회전 수정을 더한 것이다. #639 다.
  방향은 회전 여유가 트인 접근점에서만 제자리로 맞춘다. 정차 자리까지는 방향을 고정한다. 옆걸음으로 든다.
  접근점은 막힌 칸 가장자리 기준으로 다시 골랐다. 침상 여섯 곳이 옮겨졌다. load 도 옮겨졌다.
  138cbac 10건의 5건째다. bed_a3 로 돌았다. 팔 받침이 D3 협탁에 닿았다. 그 접촉을 막는다.
  master01 회차35(bed_a3)는 5/5 다. 접촉은 0 이다. rtf 는 0.699 다. yaw 맞춤은 4.6–5.2 s 다.
  master01 회차36(ord-0001)은 5/5 다. touch 는 0 이다. rtf 는 0.663 이다. 복도는 78 s 다. #240 5801363458 이다.
  master02(ord-0001)는 5/5 다. touch 는 0 이다. ArmRiser 도 0 이다. rtf 는 0.444 다. yaw 맞춤은 3.9–4.7 s 다.
  골든-4 에서는 Play/Stop 이 안 된다. Stop 뒤 AMR 이 멈춘다. 회차37 이다. exp `79a0800` 이 고쳤다. 회차39 다. #641 이다. 절차는 2절 끝이다.
- supersedes: 골든-3 `5a51804` 는 기록만 남긴다. 골든-4 `aca8840` 이 대체한다(9/24).
- 골든-3 `5a51804` 은 골든-2 에 감속기 "넓다" 판정을 더한 것이다. #631 이다.
  far 안에 장애물이 없고 창 어딘가에 있으면 넓다고 본다. 전에는 모름으로 읽어 50 % 였다.
  결정 ①을 채웠다. #576 이다.
  master02 는 5/5 다. touch 는 0 이다. DELIVERED 다. rtf 는 0.446 이다. 100 % 는 10줄이다.
  master01 회차28 은 5/5 다. touch 는 0 이다. DELIVERED 다. rtf 는 0.700 이다. 100 % 는 9줄이다. #240 5799586820 이다.
  master01 odom 중앙은 0.50 에서 0.74 m/s 가 됐다.
  복도 DEPARTED→ARRIVED 는 99 s 에서 72 s 다.
  master02 rtf 0.446 은 그 장비의 평소 값이다. 같은 밤 N=1 이 0.451·0.457·0.451 이었다.
- supersedes: 골든-2 `138cbac` 은 기록만 남긴다. 골든-3 `5a51804` 가 대체한다(9/24).
  10건 연속 회차는 138cbac 로 이미 진행 중이라 그대로 둔다.
- 골든-2 `138cbac` 은 골든-1 에 스캔 토픽 수정을 더한 것이다. 코스트맵 장애물 층이다. 커밋은 810af9a 다.
  결정 ①을 채웠다. #576 이다.
  master02 는 5/5 다. touch 는 0 이다. DELIVERED 다. rtf 는 0.550 이다. #240 5798100488 이다.
  master01 회차24 는 5/5 다. touch 는 0 이다. DELIVERED 다. rtf 는 0.676 이다. #240 5798652432 이다.
  감속기가 처음으로 실제 여유로 제한을 바꿨다. 29회다. 53회다.
  master01 odom 최고는 1.00 이다. 중앙은 0.50 이다.
  복도 DEPARTED→ARRIVED 는 113 s 에서 99 s 다.
- 골든-1 `4d01333` 은 기록만 남긴다. supersedes 다. 골든-2 `138cbac` 가 대체한다. 9/24 다.

protocol v4(참값 집기) 회차의 명령은 이렇다. 1절 준비기로 `base.usda`·`workcell.json` 을 먼저 만든다.
`P3_CAMERA_POUCHES=0` 이면 `demo_v2.sh` 가 참값 쪽 기본을 고른다. zones 는 `zones.hospital.yaml`, 출발은 `-8.995 4.686`, 팔은 gripper 판, 탁자 정착은 끔이다.

```bash
P3_WORLD=hospital P3_SIM_SENSORS=1 P3_CONTAINER_QR=1 P3_CAMERA_POUCHES=0 \
  P3_AMR_COMBINED=<ridgeback_ur5.usd> P3_M0609=<M0609 자산 루트> \
  P3_HOSPITAL_SCENE=~/markle_tmp/m2-hospital-base-<SHA>/base.usda \
  P3_WORKCELL_LAYOUT=~/markle_tmp/m2-hospital-base-<SHA>/workcell.json \
  P3_DISPENSER_FILE=$REPO/src/rokey_p3_orchestrator/config/dispenser.hospital-v0.yaml \
  P3_BROWSER=firefox P3_SCREEN_SIZE="<W H>" \
  P3_DOMAIN=<도메인> tools/demo_v2.sh up
```

`P3_STAGE_ARGS` 는 비운다. 골든 시절 규칙은 "인자를 더 주면 골든이 아니다" 였다. 촬영 뷰(`--view <이름>`)만 예외였다.

| 값 | v4 회차(참값) | 비고 |
| --- | --- | --- |
| `P3_AMR_COUNT` | `1` | 촬영은 `2` 다. 골든 N=2 는 5/5 다. DELIVERED 다. touch 는 0 이다. 3.1 표다. 리하04 다. protocol v4 의 N=2 는 attempt 9·10 이다 |
| `P3_SIM_SENSORS` | `1` | 봉투는 참값 센서로 집는다 |
| `P3_CAMERA_POUCHES` | `0`(**명시**) | #784 뒤 병원 기본은 `1`(카메라 QR)이다. v4 는 참값 집기라 `0` 을 줘야 같은 구성이다. 안 주면 v4 밖 회차가 된다 |
| `P3_CONTAINER_QR` | `1` | 약통 QR 면과 M0609 손 카메라 |
| `P3_DISPENSE_TIMEOUT_S` | `30` | 계약 기본 2 s 는 병원 틱에 짧다. 10 에서 ord-0009 `not_ready` 3회였다. #660(afc1135) 뒤다. `demo_v2.sh` 기본은 30 이다 |
| `P3_STAGE_TIMEOUT_S` | `900` | 충돌체를 굽느라 기동이 길다 |
| 속도(exp/speed-90) | M0609 관절 2.356/2.356/2.827/3.534/3.534/3.534 rad/s·TCP 0.9 m/s, 추종기 0.9 m/s·0.9 m/s²·slow_radius 1.5 m·0.9 rad/s·1.8 rad/s² | 재범 9/24 20:4x "속도 90% 바로" 다. M0609 은 두산 사양의 90% 다. 추종기는 Nav2 상한(1.0 m/s·1.0 rad/s·1.0/2.0)의 90% 다. Nav2 최고 1.0 은 그대로다. UR5 는 그대로다. 레일(0.8)은 그대로다. 벨트는 그대로다. 관절 가속은 그대로다. 표는 `docs/analysis/2026-09-24-speed-90-plan.md` 다. RC-3 부터 main 값이다(`module_path.py`·`navigation_params.yaml`). v1.1.0 기동의 감속기 근접은 0.7 m/s 다(#788, 아래 작은 표). 회전 7·골든은 0.5 m/s 였다 |
| `pouch_pool`(스테이지, preset 기본) | `15` | `HOSPITAL_POUCH_POOL`(`sim/standalone/pharmacy_stage.py`)이다. 풀 8 에서 ord-0009·0010 이 `pool_exhausted` 로 거부됐다. 12 = 주문 풀 10 + 여벌 2 였고(#643), 9/25 테이블 주문 셋(B·C1·C2)이 더해져 15 = 13 + 여벌 2 다. `docs/architecture/stage-arguments.md` 1절이다 |
| `P3_ARM_READY` | `완료 종류: .*cylinder` | 18칸이다. 빈월드의 `16/16칸` 을 기다리지 않는다 |
| `tray_clip`(스테이지, preset 기본, RC-3·4) | 켬 | 칸에 멈춘 봉투를 트레이에 붙이고 팔이 잡으면 푼다(`fcec7a8`). RC-2 10/10, 밀림 최대 0.0205 m 다. 끄기는 `--no-tray-clip` 이다 |
| `hospital_decor`(스테이지, preset 기본, RC-3·4) | 켬 | 바닥 안내선·자리 표시·충전 표시에 M0609 셀 바닥(`0cfdb93`)이 더해진다. RC-4 는 B 파랑·C 초록·D 노랑 유도선·정차 칸·테이블 윗면 색과 로비 범례를 더한다. 충돌체가 없다. 끄기는 `--no-hospital-decor` 다 |
| `traffic_dummies`(스테이지, preset 기본, RC-3·4) | `2` | `HOSPITAL_TRAFFIC_DUMMIES` 다. 로비·복도 고정 루프 0.5 m/s, 진짜 AMR 이 1.5 m 안이면 선다. 끄기는 `--traffic-dummies 0` 이다 |
| `pedestrians`(스테이지, preset 기본, RC-3·4) | `2` | `HOSPITAL_PEDESTRIANS` 다. 로비·병동 앞 복도 왕복 선에 한 명씩, 0.8 m/s(`63eeb29`). RC-4 는 AMR 1.5 m 안이면 선다(`0537e61`). 2.2 m·2 s 에 재개한다. 끄기는 `--pedestrians 0` 이다 |
| `conveyor_speed_scale`(스테이지, preset 기본, v1.1.0) | `2.0` | `HOSPITAL_CONVEYOR_SPEED_SCALE` 다(#789). 잰 표면 속도에 곱한다. 회전 7 은 배율 1 이었다. 되돌리기는 `--conveyor-speed-scale 1` 이다. 끝 롤러 튐·분기 낙하·A1 정착은 L3 미확인이다 |
| `workcell_empty_cells`·`workcell_consume`(스테이지, preset 기본, v1.1.0) | `0`·켬 | 선반 18칸을 다 채운다. 쓴 약통은 선반으로 안 돌아오고 바닥 아래로 치운다. 리셋이 다시 채운다(#791). #791 전 preset 은 4칸을 비웠고 쓴 약통이 돌아왔다 |
| `dock_wall_opacity`(스테이지, preset 기본, v1.1.0) | `0.35` | `HOSPITAL_DOCK_WALL_OPACITY` 다(#792). 조제실 남쪽 도크 벽의 재질만 바꾼다. 라이다·rtf 영향은 L3 미확인이다 |

스테이지 기본값은 preset `hospital` 이 준다. 인자로 주지 않는다.

감속기 정지 규칙(#721)과 더미 경로(#720)의 계산 한계다. 골든 값이 아니다. 발동은 미검증이다.

- 정지 문턱은 몸체 앞끝 0.6 m 다. Nav2 `max_speed_xy` 는 1.0 m/s 다. `decel_lim_x` 는 −1.0 m/s² 다.
- 1.0 m/s 에서 제동 거리는 0.5 m 다(v²/(2a)). 0.6 m 에서 규칙을 걸면 남는 마진은 0.1 m 다.
- 이 0.1 m 는 코스트맵 지연과 추종 오차를 빼지 않았다. 지연이 있으면 마진은 더 짧다. 접촉이 없다는 뜻이 아니다.
- `--block-path` 기본은 꺼짐이다. 캡슐은 몸체 중심 1.5 m 에서 나타난다. 앞끝 간격은 1.0 m 다. 0.6 m 문턱까지 0.4 m 이고, 1.0 m/s 에서는 0.4 s 다.
- 그 사이에 Nav2 가 진행 방향 띠(반폭 0.42 m) 밖으로 비키면 `governor stop` 은 안 찍힌다. 우회가 되면 발동 로그가 없다.
- `station_a` 행은 캡슐 자리 (4.54, 4.21) 을 안 지난다. 발동 시험은 load 에서 병동이나 `station_b` 로 가는 주문이어야 한다.
- L3 에서 볼 순서는 `block_path placed` 다음 `governor stop reason=obstacle dist=` 다. 그 다음 `block_path lifted` 와 `governor resume dist=` 다. `governor stop` 이 0줄이면 그 회차는 발동을 확인한 것이 아니다.


RC-3·4 스테이지 로그의 기록 줄이다. 판정선이 아니다. protocol #697 (g) 의 metric 이 이 줄을 읽는다.

- 봉투 스폰: 스폰마다 `spawn index=<i> pool_slot=<s> order_id=<id> path=… xyz=<x,y,z> yaw=… seed=<seed> epoch=<e>` 한 줄.
- 리셋 뒤 자세: `/sim/reset` 1 s(sim) 뒤 `reset pose epoch=<e> after_s=1.0 amr_dxy=<m> amr_dyaw=<rad> amr_arm_max_rad=<rad> m0609_max_rad=<rad>` 한 줄.
  `amr_dxy` 는 출발 자리(dock_1)에서 벗어난 거리다. `*_max_rad` 는 기동 때 잡은 홈 대비 최대 관절 오차다. 못 읽으면 `-` 다.
- 회피 구간: 보행자·더미가 AMR 중심 2.0 m 안에 들면 `encounter start who=<ped_i|dummy_i> dist_min=<m> sim=<s>`, 2.1 m 밖으로
  나가면 `encounter end who=… dist_min=<m> sim=<s>`(end 의 dist_min 이 그 구간 최솟값, `7bf81cc`).
- 한 정거장 여러 봉투(RC-4): 팔 로그 `정거장 칸 N: <주문> 를 <zone>/cabinet x ±0.15 m 에 놓는다`(첫 봉투는 줄 없음 = 가운데).

| 항목 | v1.1.0 | 근거 |
| --- | --- | --- |
| `--rail-drive` | `1e5 1e4 5e4` | master02 94f19fb. loop stall 5 → 0. preset `VERIFIED_RAIL_DRIVE` 다 |
| `--render-every` | `2` | master01 `5a10c79` 다. 회차 11 이다. 회차 12 다. rtf 는 0.418 에서 0.690 이다. 둘 다 5/5 다 |
| 최고 속도 | `1.0 m/s` | 1.5 는 되돌렸다. 적재 자리 touch 가 났다(4절) |
| 근접 속도 | `0.7 m/s` | #788(`slow_speed_mps`, `nav2_params.yaml`). 회전 7 과 골든은 `0.5 m/s` 였다(#240 의 잰 값). 0.7 의 touch·정차는 L3 미확인이다 |

씬은 `sim/scenes/hospital_navigationv1.usda` 이고 sha256 앞 16자는 `8c144b9b85b1967e` 다.
`ridgeback_ur5.usd`·M0609 자산은 사이트 값이다. 여기서 못 잰다. 회차 보고가 경로와 sha256 을 적는다.

한 바퀴 판정선은 다섯이다. 골든 시절에는 하나라도 못 넘으면 골든이 아니었다.
acceptance 회전의 판정선(성공 ≥ 15/16, 실패 분류 의무)은 동결 protocol `experiments/protocols/hospital-full-acceptance-v4.json` 의 §7 이다.

| # | 보는 것 | 기준 |
| --- | --- | --- |
| ① | 3절 다섯 장면 | 5/5 |
| ② | 주문 | `ORDER_DONE`, 상태 `DELIVERED` |
| ③ | AMR 본체 접촉 | `contact found touch a=…/Amr/base_link…` 0줄 |
| ④ | 속도 | rtf ≥ 0.35 다. N=1 과 N=2 가 같다. #576 재범 결정 ① 이다 |
| ⑤ | 모듈 투입 뒤 낙하 | 0 (#397) |

④ 의 옛 값은 "N=1 rtf ≥ 0.6" 이었다. 골든-1 을 확정할 때 쓴 값이다. 기준은 master01 회차18 의 0.686 이다.
옛 값은 장비를 넘어 쓸 수 없다. rtf 는 장비마다 절대값이 다르다. master02 는 같은 SHA 에서 더 낮게 나온다.
재범 결정 ①이 이 값을 대체했다. #576 이다. 9/24 00:11 에 승인했다.
138cbac 결과보다 먼저 정했다. 그 결과는 00:55 다.
rtf 는 **같은 장비끼리만** 비교한다. 켬/끔 같은 한 변수 비교도 같은 장비·같은 주문으로 한다.

## 3.3 바닥 표시(데코)

병원 preset 은 바닥에 유도선을 칠한다. 정차 칸을 칠한다. 글자 판을 칠한다(재범 9/24, `p3sim/hospital_decor.py`). 끄려면
`P3_STAGE_ARGS=--no-hospital-decor`. 기동에 이 줄이 나온다.

    hospital_decor strips=17 labels=16 skipped=0 merged=['dock_1<load', 'bed_b6<bed_b3'] meshes=2 materials=2 …

| 무엇 | 자리 | 색 |
| --- | --- | --- |
| 유도선 | `routes.hospital.yaml` 의 적재→간호사실, 간호사실→bed_a1, 간호사실→bed_b1 | 파랑·초록·주황 |
| 정차 칸 | 적재·도크 넷·간호사실·침상 열(몸체 크기 + 5 cm) | 노랑 |
| 글자 판 | 칸마다 이름. 아틀라스 `sim/assets/decor/labels.png` 한 장 | 노랑 바탕·검은 글자 |

지키는 것(9/24 예산). rtf 는 −0.02 이내다. 기동은 +3 s 이내다. VRAM 은 +0.3 GB 이내다.

- **전부 바닥 1.5 mm 안이다.** RTX 라이다는 시각 메시도 본다. 세운 소품은 #620 으로 살아난 장애물 층에
  가짜 장애물로 찍힌다.
- 물리는 0이다. 메시는 둘이다. 재질은 둘이다. 텍스처는 한 장이다. RGB 다. 알파는 없다. 한 번 세운다. 매 틱 쓰지 않는다.
- 조제실 워크셀 안에는 두지 않는다(M0609 손 카메라 시야).
- 글자 판 바탕은 채도 높은 노랑이다. 카메라 봉투 검출기가 찾는 "밝고 채도 낮은 덩어리" 가 아니다.
- 겹치는 정차 칸은 먼저 선 칸이 테두리를 갖는다. 진 칸은 글자만 남는다(`merged`).

글자를 바꾸면 `python3 sim/standalone/make_decor_atlas.py` 로 아틀라스를 다시 만든다. PNG·JSON 을 같이
커밋한다. 한글 글꼴(Noto Sans CJK KR)이 있는 곳에서 만든다. 마스터에 그 글꼴이 있다는 보장이 없다.
결과물을 Git 에 둔다. 시험(`sim/tests/test_hospital_decor.py`)이 글자 목록과 아틀라스를 대조한다.

**미실행**: 렌더 모양은 마스터 회차가 본다. 성능은 마스터 회차가 본다. 켬/끔 두 회차로 판정한다.

## 4. 알려진 실패와 원인 (2026-09-23)

같은 자리를 두 번 밟지 않게 남긴다. "고침" 은 그 SHA 부터 안 난다는 뜻이다.

| 원문 | 원인 | 고침 |
| --- | --- | --- |
| `add_base_scene: ValueError: Inlets/PillSupport geometry/anchor transform override` | 실습37 base.usda 가 원통 투입구를 (+0.30, −0.10, 0) 옮겨 저작했다. 기동 검사가 #496 결정대로 막는다 | 준비기로 base·workcell 을 다시 만든다 (`3cf412c`) |
| `ModuleNotFoundError: No module named 'pxr'` | master02 는 Kit 앱 없이 `pxr` 을 내놓지 않는다 | 준비기가 스스로 headless Kit 을 띄운다 (`c66c882`) |
| `hospital_conveyor: 컨베이어 노드가 가리키지 않는 몸체다` | 준비기가 씬 컨베이어 그래프를 꺼서 노드가 안 보였다(비활성 프림은 `Usd.PrimRange` 가 건너뛴다) | `/World/Conveyor` 아래는 건드리지 않는다 (`39d1ce5`) |
| `getMaterialFromInternalFaceIndex … returning NULL` 419,292줄, rtf 0.32 | 약통 18개가 선반 삼각 메시 위에 늘 닿아 매 스텝 접촉 보고 | 약통 접촉 문턱 5 N + 선반을 상자 충돌체로 (`396958e`·`232931c`) |
| 선반 위 모듈이 기울어 떨어지고 위층이 떠 보인다 | `convexDecomposition` 껍질이 판을 두껍게·기울게 만들었다 | 층 판마다 잰 두께의 얇은 상자 + 모서리 기둥 넷 (`232931c`) |
| 봉투가 출발점에 그대로, `belt note=at_end_timeout` | Play 뒤 첫 스텝에서 잰 표면 속도가 0 으로 돌아갔다 | 매 틱 맞춰 둔다(`4ef1cb4`) + 끝 롤러 처리(`41725ff`) |
| `v2 계획 캐시: 9/18칸`, 원통 아홉이 `넣기(round) — 후보 1/2곳` | 기준 투입구가 실습37 자리보다 안쪽이라 레일 후보 둘이 다 떨어졌다 | `rail_round` 에 yaw 0 후보 넷 추가 → 18/18 (`3b76030`) |
| `waypoint 도착 못 함 (10.0 s sim)` → `grasp_pose: 이동 실패` | `joint_states` 공백 0.67–1.13 s 동안 시한만 갔다 | 상태 공백은 시한에서 뺀다 + 남은 관절 차를 남긴다 (`35fb28a`) |
| `PickPouch … not_detected (검출 0건)` | 트레이 칸에 든 봉투를 **세계 속도**로 막았다. 차체와 같이 움직이니 0 이 아니다 | 칸 안 봉투는 정지 조건을 보지 않는다 (`5cb6542`) |
| `Dispense …: 거부로 답한다. 2 s 안에 응답이 없다` | 계약 기본 2 s(wall)가 병원 틱(0.67–1.13 s) 두세 개다 | 병원만 10 s (`5cb6542`) |
| `up 중단(arm)`, `완료 종류:` 줄이 안 나온다 | 파일 계획 캐시가 모든 칸을 채우면 precompute 가 안 돌아 요약이 안 나갔다 | 요약이 밀려 있으면 풀 것이 없어도 돌린다 (`fe12f5d`) |
| 적재 자리에서 `Amr/base_link` ↔ 컨베이어·사이드테이블 touch(impulse 3.6–4.1k) | 최고 속도 1.5 m/s 의 오버슈트다. 정차 자리 차체 가장자리에서 사이드테이블까지 0.1 m 남짓이다 | 최고 속도 1.0 으로 되돌렸다 (`42d73f8`) |
| N=2 에서만 병상 `PickPouch … not_detected` | N=2 버그가 아니다. 적재 때 `in_slot=True` 였다. 가는 길 touch(impulse 3808)로 봉투가 칸을 벗어났다 | 속도 되돌림으로 덮였다. 골든 N=2 5/5(리하04) |
| `speed limit 50% (여유 모름)` 한 줄, odom 은 1.00 m/s | `controller_server` 구독이 VOLATILE 이다. 감속기가 먼저 낸 한 장을 못 받았다 | 1 s 마다 다시 낸다 (#620) |
| 코스트맵은 오는데 `여유 모름` 만 | 두 코스트맵 장애물 층이 `/amr_1/local_costmap/scan` 을 들었다. 아무도 안 내는 토픽이다 | `<robot_namespace>/scan` (#620, `hospital-nav-l3.md` 8절) |

조용한 실패를 먼저 의심한다. 위 표 끝의 셋은 오류가 없다. 경고도 없다. 구독은 붙었다. 메시지도 왔다.
내용이 비어 있었다. `ros2 node info <노드>` 로 무엇을 실제로 구독하는지 먼저 본다.

아직 안 고친 것: **틱이 긴 것 자체**(rtf 0.375, `joint_states` 공백). `--render-every 2` 는 rtf 를 올렸다.
틱 길이 자체는 그대로다. 틱이 0.25 s 를 넘으면
`loop stall wall_s=… recent_calls=…` 가 그 틱의 호출을 남긴다 — 그 줄로 원인을 가린다.
약통 QR `container_refused … reason=unreadable` 은 QR·카메라 판독 쪽 문제다. 이 문서 범위 밖이다.

`v1.1.0` 에 남은 것(릴리스 노트와 잠금 표 기준):

- 감속기 긴급정지 감지는 고치지 않았다. #752 는 진단이다.
- M0609 자기 충돌 수정 PR 은 `v1.1.0` 에 없다. v1.0.1 잠금 표에 "PR 없음" 으로 남았다(#772 5891599172).
- 다중 PC 는 `v1.0.0`·`v1.1.0` SHA 에서 검증하지 않았다(`v1.0.0` 배포 기록, #772 5891599172).

## 5. 같이 볼 것

- [런북 색인](README.md) — 현행과 지난 기록
- [병원 데모](hospital-demo.md) — 웹 요청·관찰·두 PC·촬영 화면
- [병원 주행 L3](hospital-nav-l3.md) — Nav2 구성과 지도·구역 재생성
- [컨베이어 L3 런카드](l3-sim-conveyor.md) RC-6 — I1·I2 와 명령 원문(지난 기록)
- [실습38 인계](practice38-handoff.md) — 1350개 진열과 18칸의 차이(지난 기록)
- `experiments/fixtures/hospital-integrated-09/` — 9/22 성공 회차의 입력 사본(재현 자료)

## 6. 촬영 테이크 (재범 9/24 14:4x 확정)

녹화는 **두 파일**이다. 스테이지 뷰포트 1920×1080 한 파일, 웹 화면 한 파일이다. 한 화면을 반반으로 찍던 방식(1280×840·15 fps)은 쓰지 않는다.
두 PC 로 띄운다(두 PC 절차는 [hospital-demo 10절](hospital-demo.md#10-두-마스터로-나눠-띄우기)).
master01 은 스테이지만 화면 전체로 띄운다. master02 는 나머지와 웹 창을 띄운다.

| 무엇 | 어디서 | 값 |
| --- | --- | --- |
| 스테이지 창 | master01(화면 1920×1080) | `P3_ISAAC_WINDOW=full P3_SCREEN_SIZE="1920 1080" P3_RENDER_MAX=1920x1080` |
| 웹 창 | master02 | `P3_BROWSER=firefox`(또는 그 PC 의 관제 창). 웹 창은 맨 위에 둔다 |
| fps | 둘 다 | **30**. `record_qa` 합격선이 fps ≥ 29 다 |
| 뷰 | master01 | `P3_STAGE_ARGS="--view <이름>"`(3절: 촬영 뷰만 골든 예외). 조제실 전체는 `m0609_overhead`다. 이 뷰만 Perspective 초점거리를 14.0 mm(가로 약 74°)로 넓힌다. 동쪽 앞 모서리 3 m 높이에서 약 22°로 비스듬히 본다(`p3sim/views.py`). 천장·조명은 정지 캡처로 확인한다 |

렌더 1920×1080 은 테이크에서만 쓴다. 기본 상한 1280×720 은 rtf 때문에 둔 값이다([stage-arguments](../architecture/stage-arguments.md)).

### 6.1 순서

1. 두 PC 에서 잔류 확인을 한다(0절 7). 디스크는 녹화 폴더에 20 GB 이상 비어 있어야 한다.
2. **up 전에** master01 에서 뷰포트 녹화를 시작한다. 화면 전체를 찍는다.

   ```bash
   T=~/takes/$(date +%m%d-%H%M)-take1; mkdir -p $T
   gst-launch-1.0 -e ximagesrc use-damage=false startx=0 starty=0 endx=1919 endy=1079 \
     ! videoconvert ! videorate ! video/x-raw,framerate=30/1 \
     ! x264enc tune=zerolatency speed-preset=veryfast ! matroskamux ! filesink location=$T/viewport-1.mkv &
   echo $! > $T/viewport.pid; date +%s > $T/viewport.start
   ```

3. 두 PC 를 차례로 up 한다(hospital-demo 10.2). master01 의 `boot_check` 는 `--skip window` 로 돌린다. 창 점검은 반반 배치를 보기 때문이다.
4. master02 는 웹 창이 뜬 뒤 웹 녹화를 시작한다. 창 id 로 찍는다.

   ```bash
   XID=$(xwininfo -root -tree | grep -F 'P3 관제' | head -1 | awk '{print $1}')
   gst-launch-1.0 -e ximagesrc xid=$XID use-damage=false \
     ! videoconvert ! videorate ! video/x-raw,framerate=30/1 \
     ! x264enc tune=zerolatency speed-preset=veryfast ! matroskamux ! filesink location=$T/web-1.mkv &
   echo $! > $T/web.pid; date +%s > $T/web.start
   ```

5. 녹화를 시작한 뒤 60 s 마다 두 파일 크기가 느는지 본다. 안 늘면 그 파일을 닫는다. 번호를 올린 새 파일로 다시 시작한다(`-2.mkv`).
6. 주문을 넣는다. `DOCKED` 뒤 10 s 에 두 녹화를 닫는다. `kill -INT $(cat $T/*.pid)` 로 닫는다. INT 라야 EOS 가 나가 파일이 닫힌다.
7. 파일마다 `record_qa` 를 돌린다. 벽시계는 시작 기록부터 닫을 때까지다. `tools/record_qa.py` 는 #676(`00da79f`)으로 main 에 들어왔다.

   ```bash
   python3 tools/record_qa.py --record $T/viewport-1.mkv --wall-s $(( $(date +%s) - $(cat $T/viewport.start) ))
   ```

   줄은 `record_qa: fps=.. frames=.. dur=..s wall=..s drop=.. corrupt=.. disk=..GB — OK|녹화 결손(<이유>)` 이다. 기준은 넷이다. fps ≥ 29, 길이 = 벽시계 ±2 %, 손상 0, 드롭 ≤ 2 % 다. 끝나는 값 0 은 OK, 5 는 결손이다.
8. **원본은 지우지 않는다.** 결손 파일도 남긴다. `sha256sum $T/*.mkv > $T/SHA256SUMS` 를 만든다. 회차 보고에 폴더와 SHA256SUMS 를 적는다.
9. 결손이면 재테이크한다. 한 장면에 3번까지다. 3번째도 결손이면 멈추고 원인을 보고한다. `record_qa` 의 이유와 녹화 중 load 를 적는다.

### 6.2 한계 (미확인)

- 이 절을 쓸 때(9/24)는 L3 미실행이었다. 첫 테이크에서 확인할 것은 셋이었다. 렌더 1920×1080 에서의 rtf, 30 fps 녹화 부하, `record_qa` 판정이다. 그 뒤 테이크 기록은 [master01 녹화 목록](../reha/recordings-master01.md)·[master02 녹화 목록](../reha/recordings-master02.md)에 있다.
- 뷰포트 녹화는 Isaac **창 전체**를 찍는다. 창 안의 메뉴·패널만큼 뷰포트 영역이 1920×1080 보다 작다. UI 를 숨겨 뷰포트만 채우는 설정은 확인하지 않았다.
- 창 id 녹화(`xid=`)는 창이 가려지면 가린 창까지 찍힐 수 있다(X11). 웹 창을 맨 위에 둔다.
- 한 PC 로 찍어야 하면 화면이 모자라 1920×1080 뷰포트가 안 나온다. 이 절 밖이다.
- `v1.1.0` 카메라 기본에서 `conveyor_a1`·`a1_pick` 뷰가 새 적재 자리(−8.266, 4.102)를 담는지는 확인하지 않았다. 두 뷰는 참값 적재 자리(−8.995, 4.686) 기준으로 골랐다(`p3sim/views.py` 주석).


## 7. 9/29 카메라 배송 성공 설정

**`v1.1.0`(#797) 부터 병원 카메라 기본값이 이 설정이다**(`tools/demo_v2.sh`, P3_CAMERA_POUCHES=1 일 때).
#797 과 코드 주석의 "v1.0.1" 은 이 기본을 가리킨다. 태그는 `v1.1.0` 으로 나갔다.
그 기본에서는 재범 9/29 B안("그 자리에서 바로")대로 A1 충전 도크(dock_1)가 탁자 앞 적재 자리
(−8.266, 4.102, −90°)다. 옛 dock_1(−8.995, 4.686)에서 탁자 정착점까지 팔 밑동 수평이 0.741 m 라
적재 한도 0.70 을 넘어 도크를 옮겼다. dock_2–4 는 #795 자리 그대로다. 아래 `source` 는 값을 드러내는 기록용이다.

`bed_a1` 한 건이 카메라 파지·환자 인증·전달·도크 복귀까지 성공한 회차의
코드와 현장값을 함께 보존했다. [원본 회차](../practice/simworld/practice-45.md)는
수정하지 않는다. 이 통합본은 #795의 dock_2–4 왼쪽 배치를 유지한다.
이 배치와 성공 설정을 합친 새 커밋의 L3는 미실행이다.

PC별 자산·설치·로그 설정을 먼저 적용한다. 저장소 루트에서 실행한다.
프로필은 시뮬레이터를 자동 시작하지 않는다.

```bash
source config/hospital-camera-delivery.sh
bash tools/demo_v2.sh cmds
# 출력 명령을 확인한 뒤 기존 병원 기동 절차로 시작한다.
```

프로필은 탁자 정착 감지, 카메라 봉투·환자 태그 판독, 손목 고정 파지,
적재 접근 중 첫 조제를 켠다. 기본 병원 설정과 다른 적재 위치는
`zones.hospital-receiver.yaml`, 경로는 `routes.hospital-receiver.yaml`이다.
두 파일은 아래처럼 함께 재생성한다.

```bash
python3 sim/standalone/hospital_nav_files.py --receiver --zones > src/rokey_p3_description/config/zones.hospital-receiver.yaml
python3 sim/standalone/hospital_nav_files.py --receiver --routes > src/rokey_p3_description/config/routes.hospital-receiver.yaml
```

팔 설정은 `ur5_arm.amr-combined.camera-receiver.yaml`이다. 추가 하강 0.05 m는
해당 회차의 실측 보정이다. odom/base 높이 불일치의 근본 수정은 아니다.
다른 자산에 그대로 적용한 결과, 다른 병실 및 반복 신뢰성은 확인하지 않았다.
호스트 경로는 `config/local/`에 둔다. 원본 영상·실패 로그는 외부에 보존한다.

최신 성공 영상은 master02
`/home/rokey/markle_tmp/m2-near-tag-auth-fix-20260929/delivery-success.mp4`다.
전체 녹화는 같은 폴더의 `clip-1.mkv`다. 이전 시점별 촬영은
[master02 녹화 목록](../reha/recordings-master02.md)에 있다.
