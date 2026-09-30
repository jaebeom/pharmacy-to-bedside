# 실습22 — `master02` v0.3.0 기준선 (headless)

| 항목 | 값 |
| --- | --- |
| 번호 | 실습22 |
| 날짜·시각 | 2026-09-21 12:06:31-12:12:17 (KST, `up.console`·`down.console` 벽시계) |
| 실행 | `master02` 원격 실행과 관측 |
| 기계 | `master02` |
| 코드 | v0.3.0 `45d7fe3`(`45d7fe3b065d90617075a1c0b1260dc1664e9e7e`), 워크트리 `release/20260921-45d7fe3`, porcelain 전후 0, colcon 7 packages 11.8 s |
| 목적 | `master02` 에서 v0.3.0 시연 경로 기준선을 잡는다. 이 회차부터 `master02` 가 새 작업의 기준 기계다 |
| 조작 | `tools/demo_v2.sh up` 뒤 `curl`. 대본은 자동 긴급 → 1인 → 묶음 → 리셋 → 한 바퀴 더 → `down` |
| 판정선 | #240 issuecomment-5754812068(결과 전 게시). **이 문서는 원문과 대조하지 않았다**(`master02` 에 `gh` 없음). 판정선 문구는 `master02` `checklist.md` 에서 옮겼다 |

**결과 한 줄: 판정은 통과(headless 기준선)다**(#240 issuecomment-5754948948, 원문 미대조). **`PAUSED` 한 건(21.483 s)은 하한 22 s 아래라 기준선 불일치 1건으로 따로 적는다.**

## 구성

| 항목 | 값 |
| --- | --- |
| 도메인 | 118 |
| 명령 | `tools/demo_v2.sh up` / `down` |
| 환경 | `P3_DOMAIN=118` `P3_M0609=/home/rokey/cobot3_ws/isaacpjt/M0609` `P3_DISPENSER_FILE=$HOME/markle_tmp/dispenser_refill.yaml` `P3_WEB_PY=…/candidate/practice-02/web/backend/.venv/bin/python`(requirements 일치 확인) `P3_RUN_HOST=master02` `P3_SCREEN_SIZE="1920 1080"` **`P3_STAGE_ARGS=--headless`** `P3_LOG_DIR=~/markle_tmp/m2-p22/logs` |
| 표시 | `DISPLAY` 안 줌, `P3_BROWSER` 없음, `P3_CAPTURE_EVERY` 0 |

런카드와 다른 것 셋:

1. **`--headless`**. 기동 직전 캡처(`shots/p22-00-preflight-120440.png`, 12:04:40)에 **콘솔에서 사람이 작업 중**이었다(`IdleHint=no`). 창 모드 대신 headless 로 정했다(결정 (c)). 콘솔은 건드리지 않았다.
2. `P3_SCREEN_SIZE="1920 1080"`(기본 `2048 1152`). 1920×1080 두 대 미러링 값이다. headless 라 실제로는 쓰이지 않았다.
3. 웹 venv 는 `candidate/practice-02` 의 것이다.

## 기동 전 확인 (12:04:38, `preflight.txt`)

| 항목 | 값 |
| --- | --- |
| 도메인 118 노드 | 0 |
| `/clock` | `Unknown topic '/clock'` |
| 다른 Isaac | 0 |
| `compute-apps` | 0 |
| `LockedHint` | no |
| `P3_ARM_CMD` | 없음 |
| GPU | 165 MiB, 0 %, 41 °C, load 0.11 |

## 기동·종료 (`up.console`·`down.console`)

```text
[demo_v2 12:06:31] stage 시작
[demo_v2 12:06:45] stage 준비: [pharmacy_stage] timeline_event type=PLAY sim_time=0.000
[demo_v2 12:07:46] arm 준비: … v2 계획 캐시: 16/16칸 풀림, 전체 58.9 s, 칸당 2.1-6.9 s. 못 푼 칸 {}
[demo_v2 12:07:47] stack 준비: … orchestrator up. 주문 풀 4건, epoch=1, pharmacy_only=True
[demo_v2 12:07:48] 준비 완료
real 1m18.325s
[demo_v2 12:12:10] web 내려감: exit=0
[demo_v2 12:12:11] stack 내려감: exit=0
[demo_v2 12:12:12] arm 내려감: exit=0
[demo_v2 12:12:17] stage 내려감: exit=0
real 0m7.080s
```

`12:06:45` 는 `demo_v2` 가 PLAY 줄을 **알아챈** 시각이다. Kit 로그의 PLAY 는 `03:06:40Z [9,246ms]` 로 약 5 s 앞선다(아래 정정 3).

## 결과 수치

원본에서 다시 셌다. `master02` `checklist.md` 와 전부 일치한다.

| 항목 | 값 | 근거 |
| --- | --- | --- |
| up | 78.3 s | `up.console` `real 1m18.325s` |
| 계획 캐시 | 16/16, 58.9 s | arm.log `v2 계획 캐시: 16/16칸 풀림, 전체 58.9 s` |
| 트립 `REQUEST_ACCEPTED`→`DOCKED` (epoch1, 긴급·1인·묶음) | 12.733 / 12.583 / 22.900 | `events.jsonl` |
| 트립 (epoch2) | 12.733 / 12.900 / 23.067 | `events.jsonl` |
| `DOCKED` | 6/6 | `events.jsonl`(stack.log 에는 이 이름이 없다) |
| `PAUSED` 대기 `DISPENSER_PAUSED`→`DISPENSER_RESUMED` | e1 23.716 / **21.483** · e2 25.183 / **22.000** | `events.jsonl` |
| 보충 | 4/4 (`REFILL_REQUESTED` 4, `REFILL_DONE` 4) | `events.jsonl` |
| 주문 | 8/8 `HOLD_RETURN` reason=`pharmacy_only` | `order_status.jsonl` 최종 상태 |
| 리셋 | `RESET_BEGIN` 224.083 → `RESET_DONE` 224.100, 첫 요청 228.000 | epoch2 `events.jsonl` |
| `rtf` | **0.995 [headless]** | stage.log:10984 `stop reason=sigint updates=19992 wall_s=334.942 loop_hz=59.69 sim_s=333.200 rtf=0.995 dispensed=4 render_products=0 ur5=off … contact_watch=on` |
| VRAM | Isaac 2606 MiB / 전체 2813 MiB [headless] | `master02` 측정. 다시 재지 않았다 |
| `[ERROR]` | stage 0 · arm 0 · stack 0 · web 0 | `grep -c '\[ERROR\]'` 로그 4개 |
| WARN | arm 4(`joint_states` 수신 공백 2, `rail/joint_states` 수신 공백 2, 0.21-0.22 s) · stack 1(`[launch]: user interrupted with ctrl-c (SIGINT)`, `down`) · web 0 | `grep '\[WARN'` |
| 낙하 | 0/4 | stage.log 에서 `groundplane`(대소문자 무시) 0줄 |
| web 응답 | 90줄(200 ×89, 202 ×1), 4xx 0 | `web.log` 응답줄 **전부**(정적 파일 포함)를 셌다 |
| 회차 중 118 남의 노드 | 0 (1분 간격 4회, 기준 13노드 = 이 스택) | `watch118.tsv`, `nodes_baseline.txt` |
| 종료 | 네 프로세스 `exit=0`, 7.1 s, 잔여 0, tmux 없음, `compute-apps` 0, porcelain 0 | `down.console` |

run 디렉토리(`master02` `~/.ros/rokey_p3/runs/`):

- epoch1 `20260921T030746Z-master02-c445420a` — events 51, late 0, stale 0, `closed_by_reset_epoch` 2
- epoch2 `20260921T031025Z-master02-10e49f6b` — events 53, late 0, stale 0

`watch118.tsv` 의 12:11:31 표본은 `/clock` 발행자 0 이다. 앞뒤 표본은 1 이다. 표본을 찍은 순간의 값으로 보인다(해석).

## 판정선

| # | 판정선 | 결과 |
| --- | --- | --- |
| 1 | up·캐시 | up 78.3 s, 캐시 16/16 58.9 s. `master01` 범위(78-87 s / 57.5-64.9 s) 안 |
| 2 | 두 바퀴 | 트립 6/6 `DOCKED`, 주문 8/8 `HOLD_RETURN`, 보충 4/4, 거부 0, `[ERROR]` 0, WARN 은 기준 목록 안(아래 정정 1) |
| 3 | 트립 시간 | 트립 여섯 개 모두 범위 안. **`PAUSED` 21.483 s 는 22-35 s 하한 아래**(기준선 불일치 1건). 22.000 s 는 하한과 같다(아래 정정 2) |
| 4 | 낙하 #397 | 0/4 |
| 5 | rtf·VRAM | 0.995, 2606/2813 MiB. **headless 꼬리표. `master01` 창 모드 기준선과 직접 비교하지 않는다** |
| 6 | down | `exit=0` ×4, 잔여 0 |
| 7 | 산출물 | 로그·캡처·`SHA256SUMS` 있음. **클립·회차 중 캡처는 미실행**(아래) |
| 8 | 수치 | `grep -c` 와 원문 기준 |

## 정정 경위

결과가 나온 뒤 판정 문구 세 곳을 바로잡았다. **덧붙인 것과 결과 전에 고정한 것은 다르다.** 그래서 따로 적는다.

1. **WARN 판정이 arm 기준이었다.** `checklist.md` 는 "WARN 은 기준 두 종류뿐"(arm 의 `joint_states`·`rail/joint_states` 수신 공백)이라고 썼다. stack.log 의 `[launch]: user interrupted with ctrl-c (SIGINT)` 1건은 그 셈 밖에 있었다. `master01` stack 로그 11개와 대조했다. 11개 모두에 이 줄이 1건씩 있었다. 그래서 **새 종류가 아니라 `down` 의 정상 종료 줄**로 확정했다(#240 issuecomment-5754948948, 원문 미대조).
2. **`PAUSED` 하한을 포함하는지 결과 전에 적지 않았다.** 22.000 s 는 하한 22 s 와 정확히 같다. 판정선에 `≥`·`>` 가 없어 경계값의 판정이 문구로 정해지지 않는다. 21.483 s 는 어느 쪽으로 읽어도 하한 아래다. 그래서 **경계 1건(22.000)과 불일치 1건(21.483)을 따로 기록한다.**
   - 두 값은 둘 다 epoch 의 **두 번째 요청(1인, `ord-0001`)** 에서 나왔다. 첫 요청(`ord-0002`)은 23.716·25.183 s 다. 표본이 둘뿐이라 경향이라고 하지 않는다(해석 보류). [실습19](practice-19.md) 는 1인을 넣는 시점이 이 대기를 22 s 와 35 s 로 가른다고 적었다.
3. **"stage warn 은 전부 PLAY 이전" 이 틀렸다.** 처음에는 PLAY 시각을 `demo_v2` 의 `stage 준비` 줄(12:06:45)로 잡았다. 그러면 stage warn 124줄이 전부 그 앞이다. Kit 로그의 PLAY 줄(`[py stdout]: [pharmacy_stage] timeline_event type=PLAY`)의 ms 카운터로 다시 잰 값은 `03:06:40Z [9,246ms]` 다. 그 기준으로 **123줄은 PLAY 이전이고, 1줄은 PLAY 2 ms 뒤**다:
   ```text
   2026-09-21T03:06:40Z [9,248ms] [Warning] [omni.timeline.plugin] Deprecated: direct use of ITimeline callbacks is deprecated. …
   ```
   `[pharmacy_stage]` 가 낸 WARN 은 0 이다. 이 줄은 실습23 에서 기준 목록 ⑤로 들어갔다(12:22 확정 문구 덧붙임, #240 issuecomment-5754948948, 원문 미대조).

## 이 회차에서 나온 읽기 함정

1. **stage 로그는 줄 순서와 시각 순서가 다르다.** stderr·stdout 이 섞여 기록된다. 실습22 stage.log 는 PLAY 줄이 558행이다. 그 뒤인 654-661행에 Kit warn 6줄이 있다. 시각으로 보면 5줄은 PLAY 앞이고, 661행 1줄만 PLAY 뒤다. **"PLAY 뒤" 는 줄 번호가 아니라 선두 UTC 타임스탬프로 자른다.**
2. **PLAY 시각은 Kit 로그의 ms 카운터로 잰다.** `demo_v2` 의 `stage 준비` 줄은 PLAY 를 알아챈 시각이라 약 5 s 늦다.
3. **"WARN 새 종류 0" 이라고 쓸 때는 어느 로그를 셌는지 밝힌다.** arm 만 세면 stack 의 SIGINT 줄을 놓친다([README 함정](README.md#로그-읽기-함정-920-정리)과 같은 자리).

## 미실행

- **판정선 7 의 클립·회차 중 캡처**: 미실행. 콘솔에서 사람이 작업 중이라 headless 로 돌렸다(12:04 캡처). 기동 직전 캡처 1장(`p22-00-preflight-120440.png`, 1,189,430 B)만 있다.
- **창 모드 기준선**: 미실행. 이 회차의 `rtf`·VRAM 은 headless 값이다.
- **#240 원문 대조**: 미실행. 판정선·판정·정정은 메시지로 받은 내용이다.

## 산출물

`master02` `~/markle_tmp/m2-p22/`. `SHA256SUMS` 가 두 번 바뀌었다. 바뀔 때마다 이전 목록을 대체했다.

| 판 | 줄 | 크기 | sha256 | 바뀐 이유 |
| --- | --- | --- | --- | --- |
| 1 | 18 | 1,567 B | `c0a672cd9e4839f99754443b93906f64f6511090931ac9636298ebb171e38567` | 회차 직후 |
| 2 | 19 | 1,654 B | `5b49a8fe64992836a45eb73476b4a645e746ddd020cbc69887b51914361ddf6f` | 요청으로 `stage_warn_kinds.txt`(104 종류, 합계 124) 추가 |
| 3 | 20 | 1,744 B | `d600611f9244a3349618ba64c184a67bc6557da6b10b54a0bd8b276cb0c9765a` | 정정 3 으로 `stage_warn_kinds.v2.txt`(머리 주석 정정, 종류 목록은 v1 과 같음) 추가 |

3판은 `sha256sum -c` 를 다시 돌려 실패 0 을 확인했다. 주요 파일: `logs/20260921-120631-{stage,kit,arm,stack,web}.log`, `checklist.md`, `preflight.txt`, `up.console`, `down.console`, `requests.log`, `watch118.tsv`, `nodes_baseline.txt`, `shots/p22-00-preflight-120440.png`.

## 에셋 복사 (회차 뒤)

회차가 끝난 뒤 `master01` `~/hospital_custome/`(09:56 판)을 `master02` `~/assets-from-master01/hospital_custome-20260921/` 로 복사했다.

| 항목 | 값 |
| --- | --- |
| 경로 | rsync over Tailscale SSH(`isaacsim14`, direct) |
| 시각 | 12:13:59 `~/.ssh/known_hosts` 생성(1줄) → rsync 12:14:27-12:14:58 |
| rsync | 1차 1,834 파일 1,312,007,788 B 7.1 s / 2차 776 파일 2,398,885,824 B 12.7 s |
| 원본 목록 | `hospital_custome_master01.sha256` 2,611줄(`efe82f0bf4223bed…`) |
| 제외 | `hopital_custome/Collected_hopital_custome.zip` 1개(2,236,357,058 B). `master02` `~/Downloads/` 의 같은 파일과 sha256 동일이라 보내지 않았다 |
| 대조 | `sha256sum -c` **2,610/2,610 OK**, 불일치 0(다시 돌림) |

## 다음 실습에서 확인할 것

- `PAUSED` 하한을 `≥ 22` 로 읽을지 `> 22` 로 읽을지 판정선에 적는다.
- 1인 요청의 `PAUSED` 가 하한 근처로 떨어지는지 표본을 더 모은다. 지금은 둘뿐이다.
- 콘솔이 비어 있을 때 창 모드로 한 번 돌려 `master02` 창 모드 기준선을 잡는다.
