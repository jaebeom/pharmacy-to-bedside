# 실습10 — master01, L3-1 시연 경로 회귀(`demo_v2.sh`, headless 1회차·창 모드 2회차)

| 항목 | 값 |
| --- | --- |
| 번호 | 실습10 |
| 날짜·시각 | 2026-09-20(KST). 1회차 02:17:46-02:27:29, 2회차 02:31:04-02:36:00 |
| 장소 | `master01`(IsaacSim14), 도메인 117. 1회차 **headless**, 2회차 **창 모드** |
| 돌린 사람 | `master01` 원격 실행(재범 원격 승인) |
| 출처 | master01 보고와 #240 댓글(1회차, 보충 시간 해석, 2회차). 수치가 다르면 #240 이 맞다 |
| 원본 | `master01` `$HOME/markle_tmp/l31/`·`l32/`(저장소 밖) |
| 기록 | 이 기록은 `master01` 화면을 직접 보지 않고 썼다 |

## 목적

`master01` 에서 9/21 시연 경로(`tools/demo_v2.sh`)가 그대로 도는지 본다(L3-1 회귀). 판정 항목은 "3회 연속 + 보충 + 리셋 뒤 1회" 이고, 합격선은 새로 정하지 않았다(#240). 실습9 는 runbook 의 리허설용으로 예약돼 있어 이번이 실습10 이다.

## 구성

| 부분 | 값 |
| --- | --- |
| 관측 첫 줄 | 트리 `419b20b453c6`(`release/20260920-419b20b`, 커밋 안 한 변경 0, install 02:10:56), 기동 02:17:46, 계획 캐시 새로 풂(16/16, 58.2 s), headless |
| `main` 포함 확인 | `419b20b` 는 `main` 에 있다(#288 머지 커밋, 2026-09-19 17:08:32 UTC) |
| 기동 전 | 남의 Isaac·GPU 프로세스 없음, `/clock` 0, 시계 동기화 yes |
| 명령 | `tools/demo_v2.sh up`(1회차: stage PLAY 50 s, 캐시 58.2 s, stack 1 s, web 2 s) |
| 환경 | `P3_DOMAIN=117`, `P3_M0609=$HOME/cobot3_ws/isaacpjt/M0609`, `P3_DISPENSER_FILE=$HOME/markle_tmp/dispenser_refill.yaml`(sha256 `b12bd67f…`, 9/17 파일과 같음), `P3_STAGE_ARGS=--headless`, `P3_RUN_HOST=master01`, `P3_SESSION_PREFIX=p3v2-l31`, `P3_LOG_DIR=$HOME/markle_tmp/l31` |
| 웹 venv | release 폴더 안, `--system-site-packages` |
| run | `20260919T171937Z-master01-60bbdb40`(epoch 1), `20260919T172450Z-master01-f6d064c9`(epoch 2). 원본 sha256 목록은 `$HOME/markle_tmp/l31/runs.sha256` |

## 관측

### 사람이 본 것

없음(headless, 캡처 없음).

### 로그로 본 것

트립(sim s). 모두 `HOLD_RETURN`(`pharmacy_only`)이고 pick 은 1회씩이었다.

| 순서 | 요청 | 한 바퀴 |
| --- | --- | --- |
| 1 | `r001-0001` ibu 긴급(발행기) | 12.43 |
| 2 | `web-l31-0002` amox 1인 | 12.53 |
| 3 | `web-l31-0003` ibu 1인 | 12.35 |
| — | 리셋 | |
| 4 | `r002-0001` ibu 긴급(발행기) | 12.52 |

| 보충 | `REFILL_REQUESTED` → `REFILL_DONE` | 재개까지 더 |
| --- | --- | --- |
| ibu | 19.95 s | 3.81 s |
| amox | 18.69 s | 2.85 s |
| ibu | 21.27 s | 3.84 s |

- 리셋: 웹 `POST /api/reset`, `RESET_BEGIN` → `RESET_DONE` 0.01 sim s, 요청 수락까지 wall 4 s. 벨트 `speed_measured 0.1500`(요청 0.15, 4회 모두 mismatch False).
- `aggregate_runs.py`(epoch 2): `lap_success` 1, `lap_s` 12.517, `dispense_to_end_s` 9.117, `refill_s` 21.267. epoch 1 은 not a trial.
- Isaac: `stop reason=sigint wall_s=529.819 loop_hz=59.42 rtf=0.990`, STOP 0, PAUSE 0, `app_stopped` 0, rtf 0.990, loop_hz 59.42, 벨트 ratio 1.000(4회), VRAM 2319 → 2354 MiB. RSS 는 기동 1분 뒤(02:18:47)부터 끝까지 10.06 GiB(= 10.55 GB) 그대로였다(1분 간격 샘플 10개로 보정). `down` 은 모두 `exit 0`.
- WARN: 팔 2줄(`joint_states` 공백 0.22 s), 그 밖 0.

### 2회차 — 창 모드

| 항목 | 값 |
| --- | --- |
| 관측 첫 줄 | 트리 `419b20b453c6`(1회차와 같음, 커밋 안 한 변경 0), 기동 02:31:04, 계획 캐시 새로 풂(16/16), 창 모드(`DISPLAY=:1`, 1920×1080, 왼쪽 Isaac·오른쪽 firefox `?demo=1`). 종료 02:36:00 |
| 1회차와 다른 환경 | `P3_STAGE_ARGS` 없음, `P3_SESSION_PREFIX=p3v2-l32`, `P3_LOG_DIR=$HOME/markle_tmp/l32`, `P3_SCREEN_SIZE="1920 1080"`, `P3_BROWSER=firefox`, `DISPLAY=:1`, `XAUTHORITY=/run/user/1000/gdm/Xauthority` |
| run | `20260919T173221Z-master01-56c83728`(epoch 1), `20260919T173352Z-master01-e8d0a920`(epoch 2) |
| 기동 | 02:31:04 → 02:32:23(up exit 0). stage PLAY 11 s(1회차 50 s) |
| 사람 조작 | 원격 잠금 해제는 재범이 `loginctl unlock-session 2` 로 직접 했다(원격 실행 권한에서는 막힘). firefox 가 x=116 에 떠서 Isaac 을 가렸고, 새 프로필이라 번역 팝업과 Privacy Notice 탭이 떴다. 시스템 python3 `gi` Wnck 로 창 위치만 옮기고(Isaac 66,32 894×1048, firefox 1026,32 894×1048), XTest 로 Escape 를 한 번 눌러 팝업을 닫았다 |
| 녹화 | `$HOME/markle_tmp/l32/rec-023036.mp4`, 248.8 s, 13,708,997 B, 1920×1080 15 fps x264(ffmpeg x11grab). gst 는 `h264parse` 가 없어 쓰지 못했다. 캡처 PNG 14장. 깃에 넣지 않는다. `gnome-session-inhibit` 은 동작했고 끝난 뒤 풀렸다 |

트립(sim s, 모두 `HOLD_RETURN`/`pharmacy_only`, pick 1회):

| 순서 | 요청 | 한 바퀴 |
| --- | --- | --- |
| 1 | `r001-0001`(발행기, `ord-0002` ibu 긴급) | 12.72 |
| 2 | `web-l32-0002` `ord-0001` amox | 12.47 |
| 3 | `web-l32-0003` `ord-0004` ibu | 12.83 |
| — | 리셋 02:33:52(수락까지 3 s) | |
| 4 | `r002-0001`(발행기, 또 `ord-0002`) | 12.52 |
| 5 | `web-l32-0005` `ord-0003` amox **수락** | 13.15 |

| 보충 | `REFILL_REQUESTED` → `REFILL_DONE` | 재개까지 더 | 팔 단계 합 |
| --- | --- | --- | --- |
| ibu | 19.92 s | 3.80 s | 23.67 s |
| amox | 18.60 s | 2.85 s | 21.38 s |
| ibu | 21.27 s | 3.80 s | 25.00 s |
| amox | 29.70 s(앞 ibu 보충이 끝나길 기다린 시간 포함) | 2.88 s | 21.72 s |

- grasp miss 없음.
- `aggregate_runs.py`: epoch 1 은 not a trial, epoch 2 는 트립이 2개라 "2 counted trips in one run directory" 로 지표를 내지 않았다.
- Isaac: `stop reason=sigint wall_s=283.160 loop_hz=59.57 sim_s=281.150 rtf=0.993 dispensed=2 render_products=0`, `exit 0`. STOP 1(내릴 때 closing), PAUSE 0, `app_stopped` 0. rtf 는 녹화 켬 0.990, 끔 0.993. VRAM 최대 2598 MiB. RSS(kit python3 1개) 5.28 GiB 는 멈춘 값이고, 1회차와 세는 방식이 달라 절대값을 비교하지 않는다.
- WARN: 팔 8줄(4쌍, `joint_states` 공백 0.20-0.23 s), 스택 1줄(종료 ctrl-c 줄), 그 밖 0. `down` 은 모두 `exit 0`(browser 130 = C-c).

보충 단계가 빠지지 않았다는 직접 증거(1·2회차 원본에서 추출, #240):

- 팔 "단계 시간" 합(sim s): 1회차 ibu 23.68(15단계)·amox 21.47(16단계)·ibu 25.02, 2회차 위 표. 모두 ok.
- 스테이지: 보충마다 `refill_ros grasp attached distance=0.0376-0.0404`, `refill_ros released … type=… target=…`, `respawn cell=…` 이 있다. `grasp miss` 0건.
- 이벤트 `REFILL_REQUESTED → REFILL_DONE → DISPENSER_RESUMED` 가 모두 있다. 웹에서 ibu 재고 0 → 5 를 봤다(amox 는 미확인).
- `guarded module: motion=…` 줄은 0건이다. `demo_v2.sh` 의 `P3_V2_GUARDED_MODULE_PATH` 기본값이 `false` 다(`419b20b` 에서 확인).

### 해석 (#240)

- 보충이 실습8·9 의 절반인 것은 #228 효과로 본다. 단계 누락은 없었다(위 직접 증거).
- 실습8 트리 `a94f06e` 는 #228 전이다. #228 은 `419b20b` 의 조상이다.
- #228 은 궤적 점마다 2틱이 들어 모든 궤적이 설계의 1.67배 걸리던 것을 고쳤다. #228 본문의 이론값(원통 16-18 s, 모듈 19-22 s) 안에 실측(원통 18.69, 모듈 19.95·21.27)이 든다.
- 계획 캐시는 원인이 아니다(실습8 도 기동 때 16/16 을 풀었다).
- guarded 모듈 경로(#229·#230)는 이 실행에서 꺼져 있었으므로 보충 시간에 관여하지 않았다.
- 관측값 둘: 1회차 첫 ibu 보충의 팔 "단계 시간" 합 23.68 s 와 `REFILL_REQUESTED` → `REFILL_DONE` 19.95 s. 차이는 3.73 s 다. 해석(코드 정적 확인): 이 차이는 `REFILL_DONE` 뒤 홈 복귀다. `419b20b` 의 `m0609_arm_node.py` 에서 `REFILL_DONE` 은 `_run_refill` 안(1219행)에서 나가고, `_execute_refill` 은 결과를 내기 전에 `_return_home`(1115행)으로 홈까지 간다. 단계 시간 로그 문구도 "마지막은 결과 전 복귀 포함" 이다(1178행). 줄 번호는 `419b20b` 에서 확인했다.

### 기록 방식과 정정

- 이 두 실행은 `evidence/runs/` 의 공식 기록이 아니다. protocol `pharmacy-lap-pilot-v1` 동결(#301) 전이다.
- `frozen_at` 2026-09-19T17:44:12Z(9/20 02:44 KST)는 이 run 들의 `created_at` 17:19Z·17:32Z 보다 뒤다(실습11 에서 바로잡음).
- protocol 은 epoch 당 트립 1개만 센다. 그래서 2회차 epoch 2(트립 2개)는 지표가 나오지 않았다.
- 정정: 1회차 뒤 "Isaac RSS 가 계속 는다"(3.28 → 10.55 GB)고 먼저 올렸다가, 1분 간격 시계열(02:18:47-02:27:17 10개 모두 10.06 GiB)로 철회했다. 3.28 은 기동 직후 첫 샘플이었다.

캡처: 2회차 창 모드에 22개와 녹화 1개가 있다. 1회차는 headless 라 화면이 없다. 전부 `master01` `$HOME/markle_tmp/l32/`(저장소 밖)이고, 목록과 sha256 은 보고된 값을 master01 파일에서 읽기 전용으로 다시 계산해 대조했다.

| 묶음 | 수 | 내용 |
| --- | --- | --- |
| 전달용 webp | 4 | `p10-layout-halves-023258`(22,822 B, 960×540, sha256 앞 `61f0167e041b1db9`), `p10-refill-isaac-023320`(5,828 B, 490×532, `d24428ee1da1417d`), `p10-web-refilling-023320`(14,488 B, 520×534, `1de58b942c024c14`), `p10-pick-after-reset-isaac-023421`(5,896 B, 490×532, `a35eaf467754a33d`). 합 49,034 B |
| 원본 PNG | 14 | 모두 1920×1080, 합 7.6 MB. `pre-023056`·`stage-play-023116`·`ready-023230`·`layout-023258`·`t2-belt-023315`·`t2-pick-023321`·`t3-belt-023328`·`t3-pick-023333`·`refill-a-023343`·`reset-023353`·`t5-belt-023416`·`t5-pick-023421`·`refill-amox-023430`·`end-ep2-023445`(이름 끝 숫자는 찍힌 시각 HHMMSS) |
| 녹화에서 뽑은 프레임 | 4 | `vid-refill-158/164/170/176.png`, 각 525-531 KB, 1920×1080 |
| 녹화 원본 | 1 | `rec-023036.mp4`, 13,708,997 B, 248.8 s, 1920×1080 15 fps, sha256 앞 `d0bee8f5123c12fc` |

**왜 문서에 이미지가 없는가**: 재범 결정 35(9/20)로 **대표 네 장은 재범에게 파일로 직접 전달**하는 것으로 정리됐다. 그래서 저장소에는 목록·해시만 남긴다. 그 전까지는 전달 방식이 막혀 있었다(`master01` 쪽의 "base64 를 화면에 출력하지 말라" 지시와 겹쳤다). 원본 PNG 와 녹화는 크기 때문에 올리지 않는다.

## 문제

| P | 내용 | 출처 | 고치는 쪽 | PR |
| --- | --- | --- | --- | --- |
| P24 | 발행기(`order_generator`)가 epoch 마다 주문 풀의 요청을 자동으로 보낸다(두 회차 모두 `ord-0002`). 그래서 리셋 뒤 웹이 같은 주문을 보내면 `unknown_or_used_order` 로 거부된다. 발행기가 쓰지 않는 주문(2회차 `ord-0003`)은 리셋 뒤에도 받아졌다. runbook 대본에 이 동작이 없다 | master01 실습10 1·2회차 | runbook | #297(머지, runbook 에 자동 요청과 409 를 적음) |
| P25 | 창 모드에서 firefox 가 Isaac 을 가리는 자리(x=116)에 뜨고, 새 프로필의 첫 실행 팝업(번역, Privacy Notice)이 뜬다. `demo_v2.sh` 는 창 위치를 못 정한다(스크립트 주석). 2회차는 시스템 python3 `gi` Wnck 와 XTest 로 손으로 옮기고 닫았다 | master01 실습10 2회차 | 미정(`demo_v2.sh` 또는 운영 절차) | 아직 없음 |

코드에서 본 것: `stub_loop.launch.py` 의 `max_requests` 기본값은 1 이고("스텁 한 바퀴는 1건이다. 0 이면 주문 풀 전부"), 발행기는 epoch 마다 그만큼 보낸다(`order_generator_node.py`). 발행기를 끄는 launch 인자는 없다.

참고(문제 아님):

- RSS 는 기동 직후 올라간 뒤 실행 중에는 늘지 않았다(10분, 샘플 10개).

## 다음 실습에서 확인할 것

- amox 보충 뒤 재고 증가(웹에서 미확인).
- v0.3.0 후보 SHA 에서 protocol 순서(epoch 당 트립 1개)로 L3-1 을 한 번 더(런카드).
- 더 긴 실행에서도 RSS 가 평평한지.
