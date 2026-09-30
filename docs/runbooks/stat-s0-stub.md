# STAT S0 stub 재현 runbook

- 대상: [STAT S0 계약](../architecture/stat-delivery-contract-v1.md)(proposed)의 정상 한 바퀴와 장애·재시작 복구를 손으로 재현한다. 추적 이슈 #299.
- 상태: **L1**. ROS·Isaac·마스터를 쓰지 않는다. stub 세계의 "관측"은 파일 속 가짜 물리 상태이며 센서·물리 성공의 근거가 아니다. L2·L3 는 미실행이다.
- 필요한 것: Python 3.10 이상(표준 라이브러리만). 개발 기계에서 돈다. 공유 ROS 그래프·마스터 자원을 쓰지 않는다.

## 규칙

- 원장(`stat.db`)과 stub 세계(`world.json`)는 `--dir` 폴더에 생긴다. **저장소 밖** 임시 폴더를 쓴다(`evidence/`·`src/` 아래 금지).
- 결과를 증거로 남기려면 `evidence/runs/` 규칙을 따른다. 이 runbook 의 출력은 run 기록이 아니다.

## 준비

```bash
cd <저장소>/src/rokey_p3_orchestrator
export PYTHONPATH=$PWD
D=$(mktemp -d -t stat-s0-XXXX)
s0() { python3 -m rokey_p3_orchestrator.stat_cli --dir "$D" "$@"; }
s0 init          # Pod 2개(SIM-KIT-A), 스테이션 STN-3F-A·B. 다시 해도 재고를 덮지 않는다(seeded=false)
s0 demo          # 합성 관측 → 합성 승인 → 접수. 같은 요청을 한 번 더 보내 REPLAY·같은 ticket 을 확인한다
```

## 1. 정상 한 바퀴

```bash
s0 run
```

기대: `orders` 에 `STAT-0001` 이 `DELIVERED`·임무 `CLOSED`, `world_applied` 가 다섯 kind 모두 1, `pods` 의 `POD-1` 이 `RECEIVER`.
`events` 에서 `STAT_ORDER_DELIVERED` 가 복귀 op commit 보다 먼저다(인계 확정과 임무 종료는 따로 기록).

## 2. 인계 결과 소실

```bash
D=$(mktemp -d -t stat-s0-XXXX); s0 init; s0 demo
s0 inject drop_result:RELEASE --times -1       # 해제는 적용되지만 결과 응답이 계속 사라진다
s0 run --result-timeout 0.5
```

기대: `STAT_OP_RECONCILE` 뒤 관측으로 `STAT_OP_COMMITTED`, `STAT_ORDER_DELIVERED` 1건, `world_applied.RELEASE` 1.

## 3. 프로세스 crash 와 재시작

```bash
D=$(mktemp -d -t stat-s0-XXXX); s0 init; s0 demo
s0 run --crash-at after_send:DISPENSE; echo "exit=$?"   # 출고 적용 직후, 원장에 SENT 를 쓰기 전에 os._exit(70)
s0 status                                               # current_op 가 STAT-0001/DISPENSE 로 남아 있다
s0 run                                                  # 새 프로세스: generation 2, 대조 후 이어서 진행
```

기대: 첫 `run` 은 `exit=70`. 두 번째 `run` 에서 `generation` 2, `DELIVERED`, `world_applied.DISPENSE` 1(두 번째 출고 없음).
crash 지점은 `after_intent`·`after_send`·`before_commit` 과 kind(`DISPENSE`·`LOAD`·`FLY`·`RELEASE`·`RETURN`)를 조합한다.

## 주입할 수 있는 고장

`s0 inject <이름> [--times N]`(N=-1 은 계속, 0 은 해제).

| 이름 | 뜻 |
| --- | --- |
| `drop_ack:<KIND>` | 적용은 하고 ACK 가 사라진다 |
| `drop_result:<KIND>` | 적용은 하고 결과 조회 응답이 사라진다 |
| `hold:<KIND>` | 수락만 하고 적용을 미룬다(늦은 적용은 시험 코드의 `apply_pending`) |
| `fail:<KIND>` | 장치가 실패를 낸다 |
| `wrong_pod` · `wrong_station` | 다른 Pod 를 내보낸다 · 다른 스테이션에 내린다 |
| `stale_obs` · `no_obs` | 같은 표본 반복(한 `run` 프로세스 안에서만. 반복할 표본을 메모리에 둔다) · 관측 없음 |

취소는 `s0 cancel STAT-0001`, 상태는 `s0 status`.

## 자동 시험

```bash
cd <저장소>/src/rokey_p3_orchestrator
python3 -m pytest -q test/test_stat_intake.py test/test_stat_dispatch.py test/test_stat_cli.py
```

CI 에서는 colcon 이 같은 시험을 orchestrator 패키지 시험으로 돌린다.
