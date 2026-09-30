# ADR 0006 — 병원 씬 채택과 성능 기본값

- 상태: proposed
- 날짜: 2026-09-25
- 결정자: 재범.
  - 씬 컨베이어로 바꾼 결정: #527 5790278911 ③(9/23). #215 의 결정 5728694347 을 대체한다.
  - 빈 월드 조제실로 돌아가는 길은 없다(재범 9/23, [hospital-full](../runbooks/hospital-full.md) 143행).
  - 합격선 rtf ≥ 0.35 는 #576 5795950859 ①이다(9/24 00:11 승인, hospital-full 262–267행).
  - 이 댓글들의 원문은 이 초안 작성 때 다시 열어 보지 않았다.
- 승인 PR: 없음(이 ADR 의 PR 에서 검토)
- 관련 issue / RFC / evidence review: PR #215(80cd538), PR #553(afe69a7), PR #642·#643, PR #693(e9fa2e8), [스테이지 인자·기본값](../architecture/stage-arguments.md), [병원 전 구간 성능](../analysis/hospital-perf-0923.md), [rtf 레버](../presentation/challenge-rtf-levers.md), [hospital-full 런북](../runbooks/hospital-full.md), [시나리오](../planning/scenario.md) 280·287행
- 대체 관계: #215 의 "자체 벨트" 결정(5728694347)을 대체한다

## 맥락

- #215(9/19): 병원 씬 위에 조제실을 얹었다. `--base-usd`·`--pharmacy-origin`·`--base-deactivate`, preset hospital-v2 를 넣었다. 이때는 우리 벨트를 쓰고 씬 벨트를 껐다(944e80d).
- #553(9/23, 60 커밋): preset `hospital`·`hospital-full` 을 넣었다.
  - 씬 컨베이어 driver 는 45d4dc5, A1 롤러 끝까지는 6f46135 다.
  - 실습37 M0609 workcell 은 d448530, `P3_WORLD=hospital` 은 8b7ccb8 이다.
  - 접촉 문턱 5 N(396958e), `slots_in_world` 성능 수정(3ad7c5e)도 여기서 들어왔다.
- 성능:
  - tick 은 omni.graph 35 %, physx 17 %, `slots_in_world` 16 % 다([성능](../analysis/hospital-perf-0923.md) 6행).
  - GPU 는 80 W 상한 노트북 부품이다. 그래서 rtf 목표는 0.7 이다(9/24). 같은 기계끼리만 비교한다(master01 0.69, master02 0.45–0.50).
  - 10건 회차에서는 rtf 가 0.34–0.35 로 내려간다([rtf 레버](../presentation/challenge-rtf-levers.md) 37행).

## 대안

| 안 | 내용 | 한계·반증 |
| --- | --- | --- |
| A | 빈 월드 조제실만(병원 없음) | 병동 주행·인증 장면이 없다. 재범 9/23: 돌아가는 길 없음 |
| B | 병원 씬 + 자체 벨트(#215 시점) | #527 ③ 으로 대체됐다 |
| C | **병원 씬 + 씬 컨베이어 + 아래 성능 기본값** | 기본값 대부분이 N=1 회차나 고른 값이다(아래) |

성능 레버 중 버린 것:

- `--render-dt 1/30`: rtf 0.367 → 0.273 으로 나빠졌다(master02 5cb6542). 물리 1/30 은 금지다.
- 해상도 640×720: rtf 0.42 그대로였다. 효과가 없다.
- 다중 PC: +0.025, N=1 로 채택선 +0.1 에 못 미친다([ADR 0005](0005-deployment-single-master-default.md)).
- 솔버 반복 4 → 16(bd4a78a, exp/pouch-solver): 병합하지 않은 후보로 남았다.

## 결정과 이유

**C안.** 값은 `sim/standalone/pharmacy_stage.py` 의 hospital preset(183–191행)과 `tools/demo_v2.sh` 에 있다. preset 값은 `P3_STAGE_ARGS` 로 바꾼다(예 `--render-every 1`).

| 값 | 기본값 | 어디 | 근거(빌드 · #240 댓글) |
| --- | --- | --- | --- |
| 씬 컨베이어 | 켬(A1 롤러 끝) | preset, #553 | #527 ③. 운반 34.58 s 실측(8b7ccb8) → `P3_BELT_TIMEOUT_S` 60(`demo_v2.sh` 126행) |
| `render_every` | 2(preset 밖 기본 1) | preset 186행(37e7ff4, 골든 42d73f8 에서) | 5a10c79 회차11·12 · 5796069792: rtf 0.418 → 0.690, loop 24.8 → 40.9 Hz, 5장면 통과 |
| `rail_drive` | `VERIFIED_RAIL_DRIVE` [1e5, 1e4, 5e4](기본 [1e7, 1e5, 1e8]) | preset 184행·107행(2c1699e) | 94f19fb · 5795175482: 1e7 에서 0.6–0.8 s loop stall 5회 → 0회, rtf 0.354 → 0.386 |
| `pouch_pool` | 12(preset 밖 기본 8) | preset 191행·83행(a0b3f16), PR #643 | 8 에서 ord-0009·0010 `pool_exhausted`(50b658a · 5802751527) → 12 에서 0(b40e133 · 5804528593). 12 = 주문 풀 10 + 여분 2 |
| seed | 7(`P3_V2_SEED`, preset 밖 0) | `demo_v2.sh` 176·351행, PR #642 | 68dd351 · 5802558111 5/5 |
| 트레이 매트 | 정지 마찰 1.0·동 마찰 0.9, combine=max | #693(be60b12) | RC-1 회차55·56 봉투 11–13 cm 밀림 → not_detected(PhysX 기본 0.5). 회차57 최대 8.2 cm(칸 한계 9 cm) |
| 트레이 클립 | **main 에 없다** | origin/fix/rc2-clip 9232cc7(`--tray-clip`, hospital preset 에서 켬) | 재범 9/24 20:5x "밀림 확실히 끝내기". 매트 빌드도 1.0 m/s 곡선에서 3.4 cm 밀렸다. L3 미실행 |

## 결과

- 고른 값이라 실측 근거가 약한 것:
  - 접촉 문턱 5 N(396958e).
  - 매트 마찰 1.0/0.9(be60b12). `tray drift` 진단 줄(85acb00)은 L3 미실행이다.
- `render_every` 2 와 `rail_drive` 는 한 기계의 한 쌍 비교다. 다른 기계에서 다시 잰 기록은 없다.
- 트레이 클립은 병합되면 이 표의 칸을 채운다. 병합 전에는 기본값이 아니다.
- 문서 부채:
  - [스테이지 인자](../architecture/stage-arguments.md) 20행은 바닥 장식 인자가 main 에 없다고 적는다. 그런데 #669(905751d·5e33402)가 넣었다(`pharmacy_stage.py` 171·185행 `hospital_decor: True`). 낡은 줄이다.
  - render-dt 1/30 의 기준값이 두 문서에서 다르다: [스테이지 인자](../architecture/stage-arguments.md) 24행은 기준 없이 0.273 이고, [rtf 레버](../presentation/challenge-rtf-levers.md) 17행은 0.367 → 0.273 이다.
  - [rtf 레버](../presentation/challenge-rtf-levers.md) 64행 "master01 1대는 0.45" 는 같은 문서 51행(0.690)과 맞지 않는다.
- 재검토 조건: 10건 회차 rtf 가 합격선 0.35 아래로 떨어질 때. 또는 봉투 밀림이 클립 뒤에도 칸 한계(9 cm)에 닿을 때.

## 롤백

- 성능 값은 `P3_STAGE_ARGS` 로 preset 밖 기본값으로 되돌린다(`--render-every 1` 등). 코드 변경은 없다.
- 씬 컨베이어를 자체 벨트로 되돌리는 것은 #527 ③ 을 뒤집는 재범 결정이다. 그렇게 되면 새 ADR 을 쓴다.
