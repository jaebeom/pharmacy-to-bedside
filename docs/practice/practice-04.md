# 실습4 — master02, 실습3 문제 수정판(#162·#165)

| 항목 | 값 |
| --- | --- |
| 번호 | 실습4 |
| 날짜·시각 | 2026-09-18 12:22:01-13:30(KST). 기동 전 확인·스테이지 12:22:01, 웹 READY 12:22:20, 내림 13:29-13:30 |
| 장소 | `master02` |
| 돌린 사람 | 재범(지시·화면). 기동·웹 명령은 `master02` 원격 셸 |
| 기동·로그 | `master02` tmux |
| 출처 | master02 종료 보고. 이 기록은 `master02` 화면을 직접 보지 않고 썼다 |

## 목적

[실습3](practice-03.md) 의 P6·P7·P8 을 고친 판(#162, #165)을 본다.

- **4-A: 실행하지 않았다.** 재범이 "실습4-B 시작" 이라고 해서 건너뛰었다.
- 4-B: 실습3 3-B 와 같은 구성(`demo-ros-refill` + 팔 `rail_enabled` + 어댑터 스택 + 웹)을 수정판으로 돌린다.

## 구성

| 부분 | 값 |
| --- | --- |
| 트리 | `candidate/practice-04` = `origin/main` `52a13fc` + `fix/sim-practice3-fixes` `4e467f4`(#162) + `feat/manipulation-m0609-rail-speed` `0a35619`(#165) → `0f5b090`. 로컬 merge, push 안 함. 빌드 `Summary: 7 packages finished [17.8s]`. 웹은 practice-02 venv 재사용 |
| 팔 | `rail_enabled`, `max_joint_speed` 기본값(= 80%) |
| 커밋 확인 | `52a13fc`·`4e467f4`·`0a35619` 는 모두 `main` 에 있다(#162·#165 는 그 뒤 머지). `0f5b090` 은 원격에 없어 확인할 수 없다 |
| 명령 | 저장소 밖 스크립트 `start_practice4B.sh`. 원문은 받지 못했다 |

## 관측

### 사람이 본 것

재범의 화면 관측은 보고에 없다. 재범 지시: "실습4-B 시작", 끝에 "로컬 최신화하고 돌려보자"(→ [실습5](practice-05.md)).

### 로그로 본 것

| 항목 | 값 |
| --- | --- |
| 기동 | 12:20:28 실습3 3-B 를 이름으로 내림 → 12:22:01 기동 전 확인 `others:[]`, 117 `/clock` 0 → 스테이지 12:22:01, PLAY 직후 팔 → 스택 → 웹 12:22:20 READY, firefox 새 탭 |
| 끝 | 13:29-13:30 `m2-stack`·`m2-web`·`m2-arm` → `m2-stage` 순서로 tmux C-c. 생존 wall 4054 s(약 68분). `stop reason=sigint updates=234737 loop_hz=57.90 sim_s=3912.284 rtf=0.965`, **`exit=0`** |
| 안정성 | `app_stopped` 0, 타임라인 STOP 0 |
| 트립 | 3개(발행기 `r001`, 웹 리셋 뒤 `r002`·`r003`), 모두 `HOLD_RETURN` `pharmacy_only` |
| 웹 명령 | `POST /api/reset` 2회(12:24:41, 12:25:56, 재범 요청으로 넣음), `POST /api/requests` 0 |
| 보충 | 3회 모두 성공(grasp attached → released `inlet=a` → `REFILL_DONE`). `REFILL_REQUESTED`→`REFILL_DONE` **26.43·30.40·30.47 sim s**(실습3 3-B 는 35.9·37.6). released 때 canister y 0.5797-0.5806(3-B 0.646) |
| 팔 로그 | `수신 공백` 473줄, 최대 0.44 s(wall), 모두 stale 1.0 s 미만. 예: "joint_states 수신 공백 0.23 s(wall). stale 은 1.0 s, 유예 3.0 s." 실패 0, "레일이 밀려" 0 |
| 조제기 접촉 | `m0609`↔`DispenserBody` 86줄 모두 `near`(impulse 0, sep 최소 0.0619 m). **touch 0**(3-B 는 `link_4` impulse 10). 힘은 그리퍼 손가락↔투입구 벽에서만 났다(`left_inner_finger`↔`InletBWallXMinus` touch impulse 10.93, ↔`InletAWallXPlus` 0.066) |
| P6 경고 | `getAttributeCount/getTypes called on non-existent path …/m0609/link_2/visuals/MF0609_2_1/Scene` 가 여전히 2줄(스테이지·kit 로그 각각, 03:22:10Z). 화면에서 가운데가 보였는지는 재범 확인이 없다 |
| 웹 "대기 중" 표시(#163) | 웹 서버 로그에 관련 줄 0. 화면 표시는 관측하지 못했다 |
| 스택 로그 | `stale`·`unknown`·`기다린다`·`WAIT`·`신선` 을 grep 한 결과: 발행기 "RESET_DONE 뒤 3.5 s 를 기다린다" 7줄, `event_logger` run 끝 줄(`'stale': 0`) 2줄. orchestrator 의 stale/unknown 판정 0줄 |
| run | `20260918T032213Z-master02-4cb468f6`, `20260918T032441Z-master02-7a664ecd`, `20260918T032556Z-master02-673d4e8b` |
| 로그 파일 | `$HOME/markle_tmp/` 의 `p4b_stage.log`, `kit-practice4B-122158.log`, `p4b_arm.log`, `p4b_stack.log`, `p4b_web.log`(저장소 밖) |

## 실습3 문제의 해소/남음

| 실습3 | 결과(로그 기준) |
| --- | --- |
| P6 로봇 가운데 | 경고 2줄이 남았다. 화면 확인 없음 → 미확인 |
| P7 조제기 앞면 충돌 | `DispenserBody` touch 0(near 만) → 로그상 해소 |
| P8 `above_inlet` 도달 | 보충 3/3 성공, TIMEOUT 보고 없음 → 로그상 해소 |
| 대기 표시(#163) | 화면 관측 없음 → 미확인 |

## 다음 실습에서 확인할 것

- P6: 재범이 화면에서 로봇 가운데가 보이는지 확인한다. 경고 2줄이 남는 이유.
- 웹 "대기 중" 표시를 화면에서 본다.
- 4-A(selfdemo) 는 실행하지 않았다.
- [실습5](practice-05.md) 는 같은 구성을 `main` `7453b3d` 에서 돌린다(실행 코드는 실습4 트리와 같다).
