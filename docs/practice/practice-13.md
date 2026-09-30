# 실습13 — master01, 시연 경로 보강(거부 세 가지, 대본 5바퀴)

| 항목 | 값 |
| --- | --- |
| 번호 | 실습13(계획표). 아래 13b 는 새 후보 트리로 다시 돌린 것이고, 그 뒤 증거 실행이 이어진다 |
| 날짜·시각 | 2026-09-20(KST). 13 08:54:52-09:13, 13b 09:33:23-09:42:38, 증거 실행 09:45:01-09:50:31 |
| 장소 | `master01`(IsaacSim14), 도메인 117(9/20 슬롯 배정: `master01` 117·`master02` 118), **headless** |
| 돌린 사람 | `master01` 원격 실행(기동·중지·집계)과 읽기 전용 관측(둘째 기록) |
| 출처 | 실행 보고와 관측 보고 |
| 기록 | 이 기록은 `master01` 화면을 직접 보지 않고 썼다 |

## 목적

시연 경로를 보강한다. 확정 대본 1회에 더해 거부 세 가지(보충 중 묶음, 리셋 직후 barrier, 쓴 주문)를 일부러 만들고, 대본을 5바퀴 돌리며 자원을 1분 간격으로 적는다.

**결과: 3바퀴째에 orchestrator 가 크래시로 죽어(exit 1) 5바퀴를 마치지 못했다(P28).**

## 구성

| 부분 | 값 |
| --- | --- |
| 관측 첫 줄 | 트리 `2c68b73cd0f1`, 커밋 안 한 변경 0. 커밋 2026-09-20 03:07:01, `install/setup.bash` 03:10:36. 기동 stage 08:54:52·arm 08:55:01. 계획 캐시 새로 풂(16/16, 59.7 s, 08:56:01). 이후 트립은 `(캐시, 고르기까지 0.00 s)` |
| 모드 | headless(`"headless":true`, `--screen-size 2048 1152 --window-half left`) |
| 인자 | `--preset demo-ros-refill-v2`, scene v2, `v2_seed:=7`, `v2_guarded_module_path:=false`, `ROS_DOMAIN_ID=117`. `"ur5":false` 는 **의도된 구성**이다(시연 경로는 UR5 가 스텁, P27 확인은 [실습12](practice-12.md)) |
| 웹 백엔드 | 코드·정적 파일·설정은 `2c68b73`, 파이썬 인터프리터와 venv 패키지만 `release/20260920-419b20b` 것을 썼다 |
| 대본 | `lap.sh`(요청 ID `p13-e<N>-single` 등) |

## 관측

### 트립과 거부

- 웹 `POST /api/requests`: 200 OK 5회, **409 Conflict 10회**. `POST /api/reset`: 202 Accepted 3회.
- 스택의 `Deliver goal 거부`(WARN): `진행 중 트립이 있다(상태 DISPATCHING/WAIT_BELT, 트립 p13-c-5)` 3회, `ord-0001 는 이미 쓴 주문이다` 1회.
- 거부마다 `order_generator` 가 ERROR 로 `Deliver goal 이 거부됐다. 다음 요청으로 넘어간다.` 를 찍는다. **대본대로 난 거부의 알림이고 고장이 아니다.**

### 보충과 이벤트

epoch 5(`20260920T000116Z-master01-d8e9ce3c`), sim s:

| 이름 | stamp | 주문·detail |
| --- | --- | --- |
| `DISPENSER_PAUSED`·`REFILL_REQUESTED` | 380.083 | `ord-0002` |
| `DISPENSER_PAUSED`·`REFILL_REQUESTED` | 393.617 | `ord-0001` |
| `REFILL_DONE` | 402.650 | drug-ibu, module, `upper_left/r0c0`, `clearance` 0.02 |
| `DISPENSER_RESUMED` | 406.450 | |
| `REFILL_DONE` | 425.167 | drug-amox, cylinder, `floor_left/r1c1`, `clearance` 0.0108 |
| `DISPENSER_RESUMED` | 428.050 | |

- `REFILL_REQUESTED` → `REFILL_DONE` 22.567·31.550 s, `REFILL_DONE` → `DISPENSER_RESUMED` 3.800·2.883 s.
- epoch 6(마지막)은 `DISPENSER_PAUSED`·`REFILL_REQUESTED` 만 있고 `REFILL_DONE`·`DISPENSER_RESUMED` 가 없다. **조제기는 PAUSED 인 채로 끝났다.**

### 보충 실패(sim 465.217) — 크래시의 방아쇠

- 스테이지: `refill_ros grasp miss distance=0.0875 limit=0.08 tcp=[-1.1500, 0.8700, 1.2400] nearest=upper_left/r0c0 canister=[-1.1339, 0.9559, 1.2439]`. `attached` 줄은 없다. 부착이 거부됐다.
- 약통 홈은 `[-1.1500, 0.9100, 1.2400]` 이다. 실패 때 약통은 홈에서 0.0487 m 떨어져 있었다.
- 약통이 선반 널에 얹힌 접촉점 `at=` 는 401.217-463.217 sim s 의 표본 31개에서 `[-1.180, 0.960, 1.170]` 로 소수점 세 자리까지 같았다. 465.217(=`grasp miss` 틱)에 `[-1.170, 1.005, 1.170]` 로 처음 바뀌었다. 리셋(epoch 6, sim 453.2-454.0 추정) 앞뒤 표본도 같은 값이다.
- 같은 틱에 약통이 널을 누르는 힘만 달라졌다: 표본 31개 내내 impulse 0.0163-0.0164 였다가 465.217 에 0.0121 이다.
- 팔↔약통 접촉은 464.700-465.117 에만 있다. 401-463 구간에는 한 줄도 없다.
- 직전 465.117 에 `right_inner_finger` 가 `sep=0.0086` 까지 붙었다. 성공한 387 회차의 같은 손가락은 `sep=0.0987` 이었다. 다른 부위(0.0998-0.1044)는 성공 회차 범위와 같다.
- 이번 접근의 팔↔약통 접촉 7줄은 **전부 `near`, `impulse=0.0000`** 이다. "밀었다" 를 힘으로 보이지는 못했다.
- 뒤 추출(master01 로그, 9/20): 약통은 sim 0-463.217 의 표본 226개에서 좌표가 같았고 465.217 에 옮겨진 뒤 끝까지 그 자리다. 같은 틱의 널 impulse 0.0121 은 표본 492개 가운데 유일하게 다른 값이다. 실패 접근에서 `right_inner_finger` 만 y 로 6.7 cm 더 깊이 들어갔고 나머지 여섯 부위는 성공 회차와 같다. 실패 뒤 재시도는 없다(orchestrator 가 죽었다).
- **외부 `/clock` 혼입은 배제됐다**(같은 추출). 9/20 09:28 에 두 마스터가 도메인 117 을 함께 써서 `master01` 의 기동 전 확인이 `master02` 의 `/clock` 을 본 일이 있었지만, 이 실습 구간의 교란 원인은 아니다.
- 이웃 약통은 아니다. 412.617-422.267 에 `floor_left/r1c1` 을 쥐고 있었지만 r0c0 의 접촉 쌍에 그 칸이 없다. 접촉한 이웃은 `upper_left/r1c0` 뿐이고 33줄 모두 `near`·impulse 0 이다.
- 같은 칸을 앞서 성공했을 때(`draw=8`)와 실패했을 때(`draw=10`)의 팔 계획 줄은 한 글자도 다르지 않다.
- 성공 grasp 의 판정 거리는 0.0400 7회, 0.0401 1회, 0.0373 1회다.
- 팔: 계획 15단계, 여유 0.020 m 로 다른 `upper_*` 회차와 같다(성공 회차와 같은 줄). 단계 시간은 `plan 0.00, rail_to_shelf_z 1.67, rail_to_shelf_xy 2.05, shelf_front 2.32, grasp_pose 1.07, grasp 9.60`(합 16.70). **`grasp` 만 평소 0.50 에서 9.60 으로 튀었다.** 그 뒤 WARN `Refill drug-ibu: 실패. grasp: holding 이 2.0 s 안에 true 가 되지 않았다`. arm 로그의 `실패` 는 이 한 줄뿐이다.

코드에서 확인한 것(`2c68b73`·`origin/main` 동일):

- `limit=0.08` 은 스테이지 인자 `--hold-distance` 기본값이다(`pharmacy_stage.py` 275행). 그리퍼를 닫은 틱의 TCP-약통 거리로 부착을 판정한다(1251-1260행).
- 리셋의 `restore_canisters` 와 respawn 은 둘 다 약통을 `canister_home` 으로 순간이동시키고 선속도·각속도를 0 으로 만든다(1037-1042행, 1199-1208행). 위 시계열과 합치면 **둘 다 이번 이탈의 원인이 아니다.**
- 단계 시간 줄은 sim s 다. `hold_timeout_s` 기본값이 2.0 이고, `grasp` 단계에는 그리퍼 닫기·`grasp_settle` 대기·holding 대기가 함께 들어간다. "2.0 s 시한" 과 "단계 9.60" 은 모순이 아니다.

### orchestrator 크래시(09:02:56)

```text
[WARN] [m0609_arm]: Refill drug-ibu: 실패. grasp: holding 이 2.0 s 안에 true 가 되지 않았다
[INFO] [orchestrator]: p13-e3-single: 노드 종료(shutdown). 트립을 끝내지 않고 Deliver goal 을 abort 한다.
ValueError: Logger severity cannot be changed between calls.
[ERROR] [orchestrator-1]: process has died [pid 385954, exit code 1, …]
```

- Traceback: `orchestrator_node.py:808 main → executor.spin()` → `:725 _on_result` → `:773 _feed` → `:540 _run` → `rclpy/impl/rcutils_logger.py:313`.
- **죽은 것은 orchestrator(pid 385954) 하나뿐이다.** `event_logger`·스텁들·`isaac_adapter`·`order_generator`·stage·arm·web 은 살아 있다가 09:11 `down` 때 SIGINT 로 `process has finished cleanly` 로 끝났다. 처음에는 "스택이 반만 죽었다" 고 보고됐다가 정정됐다(`pgrep … | head -12` 가 목록을 잘랐다). 자원 기록도 이것과 맞는다: 팔을 뺀 `rokey_p3_*` RSS 합이 579 MB → 503 MB 로 76 MB(= orchestrator 한 몫)만 줄었다.
- 그래서 상태는 "orchestrator 가 없어 트립·보충이 더 진행되지 않고, 나머지 노드와 웹은 살아 있는" 것이다. 웹은 계속 200 을 준다. 마지막 run 은 조제기가 PAUSED 인 채로 끝났다.
- 코드 확인: `orchestrator_node.py` 540행이 `{'info': log.info, 'error': log.error}.get(command.level, log.warning)(command.text)` 다. `origin/main` 도 같다. rclpy 의 `rcutils_logger` 는 호출 지점마다 severity 를 캐시하므로, 같은 줄에서 수준이 바뀌면 `ValueError` 가 난다. 이 형태는 `7e6f85b`(2026-09-17)에서 들어왔다.

### run

| run | epoch | 주문 | events | 비고 |
| --- | --- | --- | --- | --- |
| `20260919T235603Z-master01-09edfa52` | 1 | 4 | 51 | |
| `20260919T235724Z-master01-37c2034d` | 2 | 4 | 53 | |
| `20260919T235850Z-master01-570d6f8c` | 3 | 1 | 18 | 리셋 직후 409 구간과 시각이 맞는다 |
| `20260919T235946Z-master01-01ae8e47` | 4 | 4 | 53 | |
| `20260920T000116Z-master01-d8e9ce3c` | 5 | 4 | 53 | |
| `20260920T000235Z-master01-6f161c92` | 6 | 2 | 22 | 크래시 뒤에도 `event_logger` 가 닫았다 |

- 모든 run 이 파일 5개이고 `stale`·`late`·`pre_reset` 은 0 이다. `$HOME/.ros/rokey_p3/runs` 는 16개(기동 전 10 + 이번 6)다.
- `aggregate_runs.py` 결과는 보고 대기다.

### 접촉·이상·자원

- 접촉 누계(08:59): `found near` 1293, `found touch` 22, `persist near` 5523, `persist touch` 2249. `touch` 의 대부분은 약통이 선반 널에 얹힌 것이다(해석). 팔 쪽 `touch` 는 잡는 순간이다(`right_inner_finger ↔ Shelf/floor_left_r1c0 impulse=1.2069`).
- 이상: Isaac `[Error]` 0, `[Warning]` 119(대부분 확장 deprecation), `app_stopped` 0, `rail_overlap` 보고 0. orchestrator INFO 12·WARN 5·ERROR 0. `order_generator` ERROR 4(거부 알림). launch ERROR 1(`process has died`, 진짜 고장). arm WARN 1(보충 실패).
- 종료 줄: `stop reason=sigint updates=59809 wall_s=999.224 loop_hz=59.86 sim_s=996.817 rtf=0.998 dispensed=2 render_products=0 ur5=off`. `down` 의 exit 코드는 보고 대기.
- 자원(1분 간격): kit RSS 4857-4858 MB, arm 79 MB, stack 579 MB, web 100 MB, GPU 2335-2339 MiB(util 24-30%), RAM 12Gi. master01 실행 기록과 맞는다(같은 pid, 8분간 RSS 약 2.8 MB 증가). **자원 때문에 죽은 것이 아니다.**
- 08:56-08:58 의 load1(3.75-8.31)은 관측 샘플러 3개가 겹쳐 돈 구간이라 높게 찍혔을 수 있다. 잘못 계산된 행 4개는 따로 보관했다.
- `respawn`·`reset` 줄에는 `sim_time` 이 없다. 앞뒤 줄로 추정한 값이다: r0c0 respawn 약 401.2(`respawn_delay_s` 2.0 과 맞고 널 접촉이 401.217 에 새로 생겼다), epoch 6 리셋 약 453.2-454.0. **추정값이다.**
- `refill_ros inventory` 줄에도 `sim_time` 이 없다. 줄 안의 `last_release` 에만 있다.
- `scene base_usd=-` 와 `room scene=v2 source=임시` 는 [실습11](practice-11.md) P26 (a) 재현이다.
- `orchestrator` 보충 줄의 `arm lot_id=-` 는 정상이다. 팔은 로트를 지어내지 않고(`m0609_arm_node.py` 머리 주석) 재고는 orchestrator 선반 값으로 채운다(`refill_planner.py`).
- 스테이지 `seed` 0 과 팔 `v2_seed` 7 은 서로 다른 손잡이다(봉투 생성 seed / v2 칸 뽑기 seed).

캡처·녹화: 없다. **왜 없는가**: headless 로 돌려 화면이 없고(`"headless":true`, 종료 줄 `render_products=0`), 둘째 기록인 관측은 읽기 전용이라 뷰포트를 띄우지 않는다. 대신 남은 증거는 stage·arm·stack·web·kit 로그 5개, run 디렉토리 6개(각 파일 5개), 1분 간격 자원 표다(해시 목록은 따로 보냈다).

## 13b — 새 후보 `45d7fe3`, 확정 대본 5바퀴 (창 모드 + 녹화)

| 부분 | 값 |
| --- | --- |
| 트리 | `45d7fe3b065d`(커밋 안 한 변경 0). 새 v0.3.0 후보다 |
| 구성 | `demo_v2.sh up`, `DISPLAY=:1` 1920×1080, `P3_CAPTURE_EVERY=30`, 웹 venv 는 `419b20b` 것, `ROS_DOMAIN_ID=117`. 기동 전 확인 통과(`/clock` 0). PLAY 11 s, 계획 캐시 16/16 새로 풂(64.7 s). 부하는 60 s 샘플러 하나, 폴링 없음 |
| 끝 | `stop reason=sigint updates=32214 wall_s=541.991 loop_hz=59.44 sim_s=536.900 rtf=0.991 dispensed=4 ur5=off`. web·stack·arm·stage `exit 0`, 잔여 프로세스 0 |

**5바퀴 15트립 모두 `DOCKED` 다.** run 디렉토리 6개 모두 파일 5개, 409 는 0건이다.

| 바퀴(epoch) | 트립 `REQUEST_ACCEPTED`→`DOCKED`(sim s) | 보충 `REQ`→`DONE`(sim s) |
| --- | --- | --- |
| epoch1(기동 직후, 자동 주문만) | 17.65 | 19.92 |
| 1(ep2) | 12.42, 12.80, 22.72 | 23.13, 30.00 |
| 2(ep3) | 12.87, 12.90, 23.23 | 22.52, 31.55 |
| 3(ep4) | 12.47, 13.08, 22.72 | 21.92, 28.28 |
| 4(ep5) | 12.70, 13.02, 23.05 | 22.77, 30.63 |
| 5(ep6) | 12.47, 12.70, 22.23 | 22.67, 31.55 |

- 보충 두 값은 **한 바퀴 안의 서로 다른 두 보충**의 `REFILL_REQUESTED` → `REFILL_DONE` 이다(재개까지 더한 값이 아니다).
- **긴 쪽에는 앞 보충을 기다린 시간이 섞여 있다**(master01 로그 추출). 둘째 보충의 `REFILL_REQUESTED` 는 첫째의 `REFILL_DONE` 보다 늘 먼저 온다(6/6, 7.30-9.12 s). 대기는 7.30-9.12 s(평균 8.19)다. 그것을 빼면 순수 보충 시간은 모듈 19.92-23.15 s(n=11, 평균 21.99)와 원통 20.88-22.92 s(n=6, 평균 22.18)로 겹친다(평균 차이 0.19 s). 보충 goal 은 한 번에 하나이고 `REFILL_REQUESTED` 는 goal 을 보낼 때가 아니라 조제 시점에 나간다.
- 이 자료에서는 **약통 종류 차이를 가릴 수 없다.** 원통이 예외 없이 둘째 보충이라 종류와 순서가 교란돼 있다("종류가 가른다" 는 첫 해석은 철회됐다). 가리려면 원통이 첫째로 오는 바퀴가 필요하다. `DONE` → `DISPENSER_RESUMED` 가 3.80-3.83 s 와 2.85-2.88 s 로 갈리는 것도 같은 이유로 못 가린다.
- 1인 트립 `REQUEST_ACCEPTED` → 그 바퀴의 마지막 `DISPENSER_RESUMED` 는 32.33-35.47 s 다(1인 `DOCKED` 기준으로는 19.25-22.75 s). 팀원용 버튼 리허설 문서(#355)의 "1인을 보내고 약 32-35초 뒤에 PAUSED 가 사라진다" 가 이 값이다(평균 34.33). 대본과도 맞는다. 13b 에서 묶음 요청이 실제로 수락된 시각은 그 바퀴 마지막 `DISPENSER_RESUMED` 의 4.1 s 뒤였다.
- **orchestrator 는 기동 때의 PID 397626 그대로 끝까지 살아 있었다.** 스테이지 `grasp miss` 0건, 팔 "Refill … 실패" 0건이다. 그래서 **#342(P28 수정)의 L3 확인은 "보충 실패가 안 나서 미실행"** 이다. 일부러 실패를 만들지 않았다.
- epoch1 트립만 길었던 이유(스택 WARN): `[stub_fleet] arm/at_home 이 true 가 아니거나 오래됐다. 출발을 거부한다`(09:34:57) → `[orchestrator] r001-0001: 복귀(도크로) 대기 5 s`(09:35:02) → 정상 진행. 이 WARN 은 드물게 난다(이번 13b 1건, 실습13 1건, 증거 실행 0건, 새벽 회차 0건).
- WARN/ERROR: 팔 12/0(`joint_states`·`rail/joint_states` 수신 공백 0.21-0.23 s wall 6쌍, stale 기준 1.0 s 미만), 스택 3/0, 웹 0/0, 스테이지 101/0(kit 경고).
- `DISPENSER_PAUSED` 와 `REFILL_REQUESTED` 의 stamp 는 17건 전부 같다(조제 시점에 같이 나간다). `REFILL_DONE`·`DISPENSER_RESUMED` 에는 `order_id` 가 없어 도착 순서로 짝지었다(근거는 `REFILL_DONE` detail 의 `item`).
- 단계 시점 snapshot 78개 가운데 `*-resumed-*` 11개는 모두 `paused_item_ids=[]`·`refilling=false` 이고 `stale=true` 는 0개다. 실습13 의 "`RESUMED` 뒤 paused 가 약 8 s 남음" 은 재현되지 않았다. 다만 `*-single-docked-*` 10건에는 `paused_item_ids` 가 남은 채 `refilling=false` 인 표본이 있다(앞 보충의 `DONE` 과 다음 goal 시작 사이). 위 "둘째 보충이 8 s 기다린다" 와 같은 현상으로 보이지만 확정하지 못했다. snapshot 의 필드 이름은 `dispenser.{stamp, wall, stale}` 다.

**창 배치 도구(#339) 결함을 실물에서 봤다.**

```text
[demo_window_layout] isaac 0x03000009 요청 66,32 927x1048 → 실제 66,69 960x990
[demo_window_layout] web 0x04000004 요청 993,32 927x1048 → 실제 116,69 960x1011
rc=0
```

**13b 때는 웹 창이 안 옮겨졌는데 종료 코드는 0 이었다**(x 116, 요청 993). 그때는 새벽 방식(`gi` Wnck)으로 다시 맞췄고 Isaac 66,32 894×1048 / firefox 1026,32 894×1048 로 들어갔다.

**지금 기준은 runbook(#366·#368)이다.** #353(`c78917f`)·#354(`c83364b`) 머지 뒤 `tools/demo_window_layout.py` 는 13e 세 번·14p 두 번, 모두 rc=0 에 isaac `66,69 927x1011` / web `993,69 927x1011` 로 같았다. 전제는 브라우저 창이 화면에 보인 뒤에 부르는 것이다(`up` 직후 1 s 안에 부르면 rc 3).

캡처·녹화: **있다.** `master01` `$HOME/markle_tmp/p13b/`(저장소 밖): 녹화 `rec-p13b.mp4`(09:33:20-09:42:41, 1920×1080 15 fps, 8,486,033 B, sha256 `71bff249…`), 단계 캡처 43장(18,193,795 B), 30 s 주기 17장(8,407,172 B), 단계 snapshot `snap-*.json` 35개, 로그 7개(`SHA256SUMS` 60줄, sha256 `489673b8…`). 저장소에는 넣지 않는다(크기). `SHA256SUMS` 의 경로는 그 회차 디렉토리(`$HOME/markle_tmp/p13b/`) 기준 상대경로다. **`master01` 에는 통합 인벤토리가 없고 회차 디렉토리마다 `SHA256SUMS` 가 있다**(10개 파일, 해시 항목 합계 341줄. `master02` 는 반대로 통합 파일 하나다). 13c 것은 `p13c/SHA256SUMS`(20,653 B, 196줄, 10:14:48, sha256 `33063c68…`)다. `master01` 의 `$HOME` 도 `/home/rokey` 이고 심볼릭 링크가 아니다. 주의: 같은 폴더의 `snap-*.json` 과 `shots/` 에 실습13c 로 보이는 09:57-10:04 파일이 섞여 있다. 구분은 확인 대기이고, `SHA256SUMS` 60줄은 13b 보고 시점 기준이라 그대로 유효하다.

## 13c — P30 재현율 10바퀴 (접촉 로그 40배)

`master01` 관측. 산출물 `$HOME/markle_tmp/p13c/`.

| 항목 | 값 |
| --- | --- |
| 트리 | `6740515ea395`(커밋 2026-09-20 09:51:01, 커밋 안 한 변경 0). `install/setup.bash` 09:54:50 |
| 시작 / 끝 | 09:55:08 / 10:12:15 |
| 도메인 | 117 |
| 인자 | `--preset demo-ros-refill-v2`, `--contact-log-every-s 0.05`(진단), 창 모드 |
| 바퀴·트립 | run 11개 = epoch1 + 10바퀴, 트립 33/33 DOCKED |
| 종료 줄 | `stop reason=sigint updates=54875 wall_s=1013.943 loop_hz=54.12 sim_s=914.583 rtf=0.902 dispensed=4 render_products=0 ur5=off` |

- **P30(집는 순간 약통이 밀림)은 10바퀴에서 한 번도 재현되지 않았다. 0/21 이다.** stage 로그의 `refill_ros grasp attached` 21건, `refill_ros grasp miss` **0건**.
- **보충 21회, 실패 0회.** arm 로그 `실패` 0건, orchestrator `번째 실패` 0건. 실패가 한 줄도 없어 인용할 원문이 없다 — **"없음" 자체가 근거**이고 `grep -c` 전수 결과다.
- `rtf 0.902` / `loop_hz 54.12` 는 다른 회차(0.993 / 59.6)보다 낮다. `--contact-log-every-s 0.05` 로 접촉 줄을 40배 촘촘히 남긴 탓이다. **다만 sim 시간 기준 값은 흔들리지 않았다** — 보충 구간은 13b 와 평균 0.19 s 차이다.
- **13c 트리만 다르다. 의도다.** `--contact-log-every-s` 가 #351(09:41 머지)에 있어 `45d7fe3` 로는 못 켠다. `6740515` 는 #352 머지 커밋이고 `45d7fe3` 의 후손이다. `45d7fe3..6740515` 의 `src/`·`tools/` 차이는 0 이다(`git diff --stat` 확인. 바뀐 것은 `sim/` 의 opt-in 인자와 문서뿐). 13b 와 13d 이후는 `45d7fe3b065d` 다.
- 캡처·녹화: **있다.** `rec-p13c.mp4`, `shots/`, `SHA256SUMS` 196줄(sha256 `33063c68…`).

P30 은 아래 문제 칸에 적힌 대로 9/19 에 한 번 본 현상이다. **10바퀴 0회이므로 재현율은 낮고, 이 자료로는 빈도를 셈할 수 없다.** 결정 34(시연 뒤 수정, 운영으로 완화)는 그대로다.

## 13d — 전량 실패 주입 (`--hold-distance 0.01`)

| 항목 | 값 |
| --- | --- |
| 트리 | `45d7fe3b065d`(커밋 09:25:56, 변경 0) |
| 시작 / 끝 | 10:15:13 / 10:19:32 |
| 주입 | `--hold-distance 0.01` — 부착 판정 한계를 기본 0.08 에서 좁혀 **모든 파지를 강제 실패** |
| 결과 | `grasp miss` 8 / `attached` **0** / arm 실패 7 / 재시도 WARN 7 |
| 크래시 | `process has died` 0, `Logger severity` 0 |
| orchestrator 로그 수준 | INFO 1 · WARN 7 |
| 종료 줄 | `updates=14749 wall_s=247.481 loop_hz=59.60 sim_s=245.817 rtf=0.993 dispensed=1` |
| 캡처·녹화 | 있다 — shots 28장, mp4 1 |

기대(3회 실패 후 포기, orchestrator 생존)대로 끝났다. **그러나 이것은 #342 의 실물 확인이 아니다.** INFO 1건은 기동 줄(`orchestrator up …`)이고 Note 호출 지점이 아니며, 전량 실패라 성공 Note(`슬롯 … 장착`)가 원천적으로 안 나왔다. **P28 은 한 run 안에 INFO Note 와 WARN Note 가 같이 나와야 재현된다**([실습15](practice-15.md)) — 13d 는 그 조건을 만들지 못했다.

## 13e — #342 의 실물 확인 (성공과 실패를 한 run 에 섞었다)

세 회차 모두 `--hold-distance 0.0388`. 이 값은 `upper_*/r1c0` 칸만 성공하고 나머지는 실패해 **한 run 안에 성공 Note(INFO)와 실패 Note(WARN)가 함께 나온다.**

| | 13e-a | 13e-b (대조군) | 13e-a2 |
| --- | --- | --- | --- |
| 트리 | `45d7fe3b065d`(수정본) | **`2c68b73cd0f1`(수정 전)** | `45d7fe3b065d` |
| 시작 / 끝 | 10:23:05 / 10:25:59 | 10:26:19 / 10:28:54 | 10:30:07 / 10:34:46 |
| `grasp miss` / `attached` | 3 / 1 | 1 / 1 | 4 / 1 |
| arm 실패 / 재시도 | 2 / 2 | 1 / 1 | 4 / 4 |
| orchestrator 로그 수준 | **INFO 2 · WARN 2** | INFO 1 · WARN 1 | **INFO 2 · WARN 4** |
| `process has died` | **0** | **1** | **0** |
| `Logger severity` | **0** | **2** | **0** |
| 종료 줄 rtf | 0.993 | 0.995 | 0.993 |
| 캡처·녹화 | shots 11 · mp4 1 | shots 8 · mp4 1 | shots 16 · mp4 1 |

- a 와 a2 는 INFO 2건(기동 1 + `슬롯 … 장착` 1)과 WARN 2·4건이 한 run 에 같이 나왔고 **죽지 않았다.** b 는 같은 인자·같은 절차인데 옛 트리라 **죽었다.**
- **따라서 INFO+WARN 공존이 실제로 만들어졌고 `45d7fe3` 가 그것을 지나 살아남았다. 이것이 #342 의 실물 확인이다.** a2 는 WARN 이 4건이라 수준이 더 여러 번 바뀐 회차이고, a 와 같은 결과라 재현도 된다.
- b 가 죽은 자리: `orchestrator_node.py:540` → `rcutils_logger.py:343 in info` → `ValueError`. 직전 Note 는 WARN 이고 예외를 일으킨 INFO 는 찍히기 전에 터져 로그에 없다.
- `Logger severity` 2건은 Traceback 본문 줄과 마지막 `ValueError:` 줄 둘 다에 그 문구가 있어서다. **사건은 1건이다.**

## 증거 실행 — 후보 `45d7fe3`, 창 모드 + 녹화

frozen protocol 은 화면 모드를 정하지 않아 이번에는 **창 모드 + 녹화**로 돌렸다(새벽 `2c68b73` 회차는 headless 였다). 웹 요청 없이 자동 요청만 쓰고 리셋은 웹 `POST /api/reset` 3회다. 시드는 Isaac 에 인자가 없어 시행 번호로만 썼다(protocol purpose 8).

| 시행 | seed | epoch | run | status | lap_s | load_s | dispense_to_end_s | return_s | refill_s | pick_attempts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 분모 제외 | | 1 | `20260920T004616Z-master01-aab0b7d8` | not_a_trial | 12.400 | 10.833 | 9.117 | 1.033 | 19.933 | 1 |
| 1 | 0 | 2 | `20260920T004654Z-master01-5b972624` | trial | 12.267 | 10.967 | 9.117 | 1.033 | 23.150 | 1 |
| 2 | 1 | 3 | `20260920T004728Z-master01-3d3b5717` | trial | 12.850 | 11.350 | 9.667 | 1.033 | 21.400 | 1 |
| 3 | 2 | 4 | `20260920T004759Z-master01-845fb1b5` | trial | 13.267 | 11.283 | 9.317 | 1.017 | 22.550 | 1 |

- 시행 3개 모두 `lap_success` 1 이고, `success_checks` 다섯 항목이 네 run 모두 true 다. protocol sha256 `7fcf25bd…`, run `created_at` 00:46-00:48Z 는 `frozen_at` 뒤다.
- 확정 대본 1회(epoch 5, `20260920T004840Z-master01-c269215c`): 자동 긴급 → 웹 1인 `ord-0001`(200) → PAUSED 가 빈 뒤 웹 묶음 `ord-0003`+`ord-0004`(200). 세 트립 모두 `DOCKED`, 409 0건. **요청은 화면 버튼이 아니라 같은 payload 의 HTTP 요청이다. 버튼 경로는 실습14 몫이고 아직 미실행이다.**
- 종료 줄 `stop reason=sigint updates=18812 wall_s=315.665 loop_hz=59.59 sim_s=313.533 rtf=0.993 dispensed=4 ur5=off`. WARN/ERROR: 팔 6/0, 스택 1/0(SIGINT), 웹 0/0, 스테이지 104/0(kit). run 5개 모두 파일 5개.
- **독립 리뷰와 `verify-artifacts` 는 미실행이다.** `evidence/runs` 기록은 따로 PR 로 올린다(기존 `2c68b73` 3건은 그대로 둔다). 이 실습 문서는 evidence 가 아니다.
- 캡처·녹화: 있다. `master01` `$HOME/markle_tmp/ev2/`: `rec-ev2.mp4`(5,609,007 B, sha256 `04c182c3…`), 단계 12장 + 30 s 주기 10장(`SHA256SUMS`, sha256 `3156ad70…`), 로그 5개, 해시 묶음 `packet-ev2.txt`(sha256 `9f7a3b68…`), 배치 목록 `deployment-inventory-20260920-094501.txt`(sha256 `881ad76c…`).

## 문제

| P | 내용 | 출처 | 고치는 쪽 | PR |
| --- | --- | --- | --- | --- |
| P28 | 보충이 실패하면 orchestrator 가 `ValueError: Logger severity cannot be changed between calls.` 로 죽는다(exit 1). 같은 줄(`orchestrator_node.py:540`)에서 로그 수준이 바뀌기 때문이다. 죽어도 웹은 200 을 주고 화면은 정상으로 보인다 | master01 실습13, 코드 확인 | 팔·orchestrator | **#342 머지. 실물 확인은 13e-a·13e-a2(생존) 대 13e-b(사망)** |
| P30 | 잡는 순간 약통이 홈에서 0.0487 m 밀려 부착이 거부됐다(`grasp miss`, 0.0875 > 0.08). 지워진 후보: 리셋·respawn, 서서히 흐름, 이웃 약통, 팔 계획 차이. 남는 후보는 이번 접근에서 그리퍼가 건드린 것이다(직전 틱 `right_inner_finger` `sep=0.0086`, 성공 회차 0.0987). 다만 그 구간 접촉 줄의 impulse 가 모두 0 이라 확정하지 못했다 | master01 실습13 | `sim`·팔 | 아직 없음. **13c 10바퀴에서 재현 0/21** |

## 다음 실습에서 확인할 것

- P28 수정 뒤 같은 대본 5바퀴(9/21 전에).
- P30 운영 대응(재범 결정 34, 9/20): 코드 수정은 시연 뒤다. 시연은 운영으로 막는다 — 본 시연 직전에 팔 노드·스테이지를 다시 띄우고, 샘플러·폴링을 끄고, 보충이 두 번 잇따라 실패하면 리셋한다. `--hold-distance` 는 완화하지 않는다. 지금은 진단용 로그 인자만 더한다.
- P30: 잡는 순간의 약통 이동을 다시 볼 것. `contact persist` 는 2초 간격 표본이라 밀린 순간의 힘을 놓쳤을 수 있다(해석). 그 구간만 `found` 줄이나 더 촘촘한 기록으로 본다.
- `down` exit 코드와 `aggregate_runs.py` 결과(보고 대기).
- **회차 디렉토리 이름과 실습 번호의 대응을 정해야 한다.** `master01` 오늘 산출물은 `p13`·`p13b`·`ev2`·`p13c`·`p13d`·`p13e-a`·`p13e-b`·`p13e-a2`·`p18`·`p14`·`p14p`·`p14p-part2` 12개인데 이 문서들의 번호는 15까지다. `p18` 이 무엇인지, `p14`·`p14p`·`p14p-part2` 가 실습14 의 무엇인지 확인 대기.
- `p14p-part2` 에는 `SHA256SUMS` 가 없다(실행 쪽에 요청).
