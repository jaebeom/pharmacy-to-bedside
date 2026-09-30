# 컨베이어↔팔 계약 시험 벡터 v1

v1.1.0 병원 한 바퀴의 실행 노드는 이 파일을 읽지 않는다. 시험만 쓴다: `rokey_p3_bringup/test/test_conveyor_contract_vectors.py`(L1 기준 판정기)와 `rokey_p3_orchestrator/test/test_contract_vectors_trip_fsm.py`(트립 FSM 러너).
한 바퀴의 벨트 관측 guard(`observation_guard`)는 기본 꺼짐이고 v1.1.0 `demo_v2.sh` 도 켜지 않는다.

[배송 계약 v1 11절](../../../../../docs/architecture/delivery-contract-v1.md)의 뜻을 입력 열과 기대값으로 적은 데이터다. 기준 commit 은 `dc172d1` 이다.
물리(정지 거리·흡착)를 대신하지 않는다. 벡터를 통과해도 L3 가 아니다.

| 파일 | 허가 경계 | 행위자 |
| --- | --- | --- |
| `dispense.json` | 배출 응답과 벨트 점유(11.1·11.2) | 벨트 backend |
| `pick.json` | `at_end` 정착 판정(11.1)과 피킹 허가(5절) | 벨트 backend(`at_end_vectors`), arm·orchestrator(`permit_cases`) |
| `next_dispense.json` | 다음 배출 허가(11.3) | orchestrator(`cases`) |

## 형식

- 파일 머리: `boundary`, `contract`(절과 commit), `actor`, `params`(시험용 값, 합격선 아님), `vectors`.
- 벡터: `id`, `clause`, `title`, 선택 `options`, `steps`.
- step: 시각 `t`(sim 초, 줄지 않음)와 입력 **하나**, 선택 `expect`.
  - 입력: `dispense`·`pouch`·`pick_notice`·`reset`.
  - `pouch.at` 은 기하 좌표가 아니라 `mid`(벨트 중간)·`end`(종단 구역)·`off`(벨트 부피 밖)·`lost`(frame 없음) 중 하나다. 러너가 자기 좌표로 옮긴다.
  - `pouch.speed` 가 `null` 이면 속도 미수신이다.
- `expect` 에 적은 키만 비교한다. 적지 않은 키는 보지 않는다.
- 표 형태 사례(`permit_cases`, `cases`)는 `input` 하나와 `expect.allowed` 다. `null` 은 unknown·stale·토픽 없음이고 허가가 아니다.
- `options` 는 계약의 (제안·미확정) opt-in 이다: `fail_closed`, `speed_missing_resets_settle`, `next_dispense_guard`. 없으면 계약의 "현재" 동작이다.
- 11.3 의 "현재"는 "벨트 비움(신선)"이다. 벡터는 트립 FSM 이 픽 결과 전에는 배출하지 않는 것(N05)까지 적는다.

## 쓰는 법

- 기준 판정기: `rokey_p3_bringup/conveyor_contract.py`.
  - 모든 벡터를 통과해야 한다(`rokey_p3_bringup/test/test_conveyor_contract_vectors.py`).
- 구현별 러너: 각 레인이 자기 시험에 둔다. 트립 FSM 러너는 `rokey_p3_orchestrator/test/test_contract_vectors_trip_fsm.py`.
  - 러너에 없는 opt-in 을 요구하는 사례는 skip 한다(이유에 opt-in 이름). opt-in 을 구현하는 PR 이 지원을 더한다.
  - 지금 못 맞추는 벡터는 러너에 `pytest.mark.xfail(strict=True, reason=...)` 로 표시한다.
    v1.1.0 트립 FSM 러너의 xfail 은 `N09` 하나다(칸 안착 관측, 계약 11.4 가 아직 없다).
  - 고치는 PR 에서 그 표시를 뗀다. strict 라서, 고쳐졌는데 표시가 남아 있으면 시험이 실패한다.
- 벡터를 바꾸는 것은 계약의 뜻을 바꾸는 것이다. 계약 문서와 같은 경로로 검토한다.
