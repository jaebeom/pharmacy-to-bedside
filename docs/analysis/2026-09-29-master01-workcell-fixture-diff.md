# master01 v1.0.0 리하 workcell.json 과 integrated-09 fixture 차이 (9/29)

장비: master01 = `IsaacSim14`.
상태: **unreviewed**. 검토자 없음. 파일 대조만 했다. Isaac 실행, 판정, 수정은 하지 않았다.

- 요청: M0609 자기 충돌 카드(9/29)의 오프라인 계획 표를 어느 파일로 돌릴지 정하려는 요청이었다.
- 적용 범위: master01 한 대, 회차 `m1-v1-rehearsal-a5d1107-r102502`(`v1.0.0` = `a5d1107`, 9/29 10:25 기동). master02 값은 **미확인**이다.

## 1. 관측

| 파일 | sha256 | 바이트 |
| --- | --- | --- |
| master01 회차 `~/markle_tmp/m1-v1-rehearsal-a5d1107-r102502/workcell/workcell.json` (10:25:02 생성) | `b11d37766df25ccc3c98dd0d7254543afd5702f94082f71de02d9b9754ac15c3` | 73536 |
| `experiments/fixtures/hospital-integrated-09/workcell.json` (`origin/main`, `v1.0.0` 같음) | `7fb6c613d332e3570443d09865a85ae473e51aed3233ab8ba47a2ad2fe210ff1` | 73494 |

- master01 `~/markle_tmp/*/workcell/workcell.json` 257개 가운데 256개는 회차 파일과 해시가 같다. 나머지 1개는 `51d1177d…6e56` 이다.
- `python3 -m json.tool --sort-keys` 로 정렬한 diff 는 623줄이다. 원문은 싣지 않고, 아래에 키 단위로 요약한다.

| 키 | fixture | master01 회차 |
| --- | --- | --- |
| `collision` | 없음 | `{"shelf":"boxes","shelf_board_margin":0.001,"shelf_post":0.03,"dispenser_body":"convexHull","dispenser_inlets":"none"}` |
| `pill_offset` | `[0.3, -0.1, 0.0]` | 없음 |
| `targets.round.center` | `[-7.75, 11.015, 0.98]` | `[-8.05, 11.115, 0.98]` |
| `obstacles` 개수 | 150 | 149. `PillIntegrationBracket`(center `[-7.75, 11.16, 0.83]`, size `[0.10, 0.22, 0.04]`)이 fixture 에만 있다 |
| `obstacles` center 이동 | — | 35개. 이름은 `RoundBinRim*` 32·`RoundBinSupport`·`RoundBinFloor`·`RoundBinMountPlate` 이다. 34개가 (−0.3, +0.1, 0) 이동했고, `RoundBinMountPlate` 만 (−0.3, 0, 0) 이동했다. size 는 1e−15 수준의 부동소수 차이뿐이다 |
| `contained_body_obstacles` | 키 165 | 키 165 로 같다. 값 137개가 다르다(어느 몸체에 포함되는지 매핑) |
| `source_sha256` | `2561206773f8d0496930dbe7d6525c79c9103efcaa18d485e7bf290d4b25116c` | `8c144b9b85b1967ee946eb827a117a96be8b8270e026463f1910f1e79744bba0` |

## 2. 해석 (검증 안 함)

- 두 파일은 서로 다른 원본 USD 에서 만들어졌다(`source_sha256` 가 다르다).
- round 목표와 RoundBin 장애물이 옮겨진 양은 `pill_offset` 과 크기가 같고 부호만 반대다. fixture 는 pill 통합 브래킷과 오프셋을 반영한 판이고, master01 회차는 그 전 판이거나 다른 판이라는 가설과 맞는다.
- 경쟁 가설: 같은 원본에서 준비기 옵션만 달리 줬을 수도 있다. 이 경우에도 `source_sha256` 가 다른 이유가 설명돼야 한다. 준비기 명령줄은 보지 않았다.
- 한계: 어느 쪽이 v1.0.0 시연 기준인지 판정하지 않았다. master02 파일은 보지 않았다. 원본 USD 두 개도 열어 보지 않았다.

## 3. 같은 날 master01 운영 메모 (관측)

- `v1.0.0` 리하 회차는 `boot_check` exit=5(stale)로 주문 전에 멈췄다. 원인은 관제 창 외에 GitHub Issue #771 Firefox 창이 하나 더 떠 있던 것이다. 이 대조 작업은 중복 기동하지 않았다.
- master02 용 카드(b3f3ba6 병원 한 바퀴)가 master01 로 잘못 왔다. 1단계 `hostname` 에서 멈췄고, 카드는 취소됐다. 체크아웃·빌드·기동은 하지 않았다.
