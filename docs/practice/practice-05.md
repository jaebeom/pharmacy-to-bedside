# 실습5 — master02, 4-B 구성을 main 에서 처음 실행

| 항목 | 값 |
| --- | --- |
| 번호 | 실습5 |
| 날짜·시각 | 2026-09-18 13:30:48-14:31:18 무렵(KST). 14:31:12 ROS 쪽 C-c, 6 s 뒤 스테이지 C-c |
| 장소 | `master02` 개발 클론 |
| 돌린 사람 | 재범(지시). 기동·웹 명령은 `master02` 원격 셸 |
| 기동·로그 | `master02` tmux |
| 출처 | master02 종료 보고. 이 기록은 `master02` 화면을 직접 보지 않고 썼다 |

## 목적

[실습4](practice-04.md) 의 4-B 구성을 로컬 merge 트리가 아니라 `main` 에서 처음 돌린다.

## 구성

| 부분 | 값 |
| --- | --- |
| 트리 | `master02` 개발 클론, `main` `7453b3d`(#165 머지 커밋). 실행 코드는 실습4 트리 `0f5b090` 과 같다. 4-B 구성, 도메인 117, 팔 `rail_enabled`·속도 기본 80% |
| 명령 | 저장소 밖 스크립트 `start_main.sh`. 원문은 받지 못했다 |

## 관측

### 사람이 본 것

재범의 화면 관측은 보고에 없다. 재범 지시: "못봤다 다시 실행"(→ 웹 리셋), 끝에 "로컬 최신화 및 실습 진행"(→ [실습6](practice-06.md)).

### 로그로 본 것

| 항목 | 값 |
| --- | --- |
| 기동 | 13:30:48 기동 전 확인 `others:[]` → 스테이지(`demo-ros-refill`) → 팔 → 스택 → 웹 READY |
| 끝 | 14:31:12 `m2-web`·`m2-stack`·`m2-arm` tmux C-c, 6 s 뒤 `m2-stage` C-c. `stop reason=sigint updates=209103 wall_s=3620.329 loop_hz=57.76 sim_s=3485.050 rtf=0.963`, **`exit=0`**. 네 프로세스가 내려간 것을 `pgrep` 으로 확인한 뒤 kill-session |
| 안정성 | `app_stopped` 0. 타임라인 STOP 은 종료 때의 `STOP sim_time_last=3485.250 (closing)` 1줄뿐 |
| 트립 | 2개. 발행기 `r001-0001`, 웹 리셋 뒤 `r002-0001`. 둘 다 `ord-0002` `HOLD_RETURN`(`pharmacy_only`) |
| 웹 명령 | `POST /api/reset` 1회(13:34:48, 재범 "못봤다 다시 실행"에 따라 넣음), `POST /api/requests` 0 |
| 보충 | 2회 모두 성공(grasp attached → released `inlet=a`). grasp→released sim s 15.550→32.600, 244.383→263.000. released 때 canister y 0.5806·0.5795 |
| 팔 로그 | 수신 공백 456줄, 최대 0.33 s(wall). 실패·"레일이 밀려" 0줄 |
| 조제기 접촉 | `m0609`↔`DispenserBody` 62줄 모두 near, touch 0, sep 최소 0.0635 |
| P6 경고 | `non-existent path …/link_2/visuals/MF0609_2_1/Scene` 2줄 남음. `7453b3d` 에는 #167(link_2 visuals 수정, 이후 머지)이 없다. 재범 화면 확인 없음 |
| 로그 파일 | `$HOME/markle_tmp/` 의 `main_stage.log`, `main_arm.log`, `main_stack.log`, `main_web.log`, `kit-main-133046.log`, 빌드 `main_7453b3d_build.log`(저장소 밖) |

## 문제

새 문제 보고는 없다. 실습3 의 P6 은 이 트리에 수정(#167)이 없어 경고가 남았다.

## 다음 실습에서 확인할 것

- P6: #167 이 들어간 트리에서 경고가 사라지는지, 재범이 화면에서 로봇 가운데를 보는지.
- 웹 "대기 중" 표시(#163)를 화면에서 본다.
