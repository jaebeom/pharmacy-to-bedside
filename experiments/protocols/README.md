# 실제 protocol

팀이 작성하고 리뷰한 protocol JSON만 여기에 둔다.
제안 단계에서는 수정할 수 있다. Freeze 이후에는 새 ID로 추가한다.

2026-09-30 기준 목록이다. sha256 은 파일 바이트의 앞 12자다. run 수는 `evidence/runs/` 에서 그 protocol 을 참조한 기록 수다.

| 파일 | phase | 상태 | frozen_at (UTC) | sha256 | run 수 |
| --- | --- | --- | --- | --- | --- |
| `pharmacy-lap-pilot-v1.json` | pilot | frozen | 2026-09-19T17:44:12Z | `7fcf25bd65ad` | 6 |
| `hospital-refill-integration-pilot-v1.json` | pilot | frozen | 2026-09-22T07:03:50Z | `6b7af9cf9967` | 1 |
| `hospital-full-acceptance-v1.json` | acceptance | frozen | 2026-09-24T23:14:44Z | `6cbd564a7338` | 67 |
| `hospital-full-acceptance-v2.json` | acceptance | frozen | 2026-09-27T02:56:34Z | `5d2d9478b707` | 4 |
| `hospital-full-acceptance-v3.json` | acceptance | frozen | 2026-09-27T09:56:06Z | `32e2b9c61af0` | 0 (v4 가 대체, #773) |
| `hospital-full-acceptance-v4.json` | acceptance | frozen | 2026-09-27T10:55:54Z | `a8d8a65b6455` | 17 |
| `ward-lap-b-acceptance-v1.json` | acceptance | proposed | — | `5e944fe6e757` | 0 |

- `v3`·`v4` 는 `requires_failure_classification` 이 참이다. 실패 run 에 `failure_class`·`failure_cause` 가 있어야 한다([schema](../../schemas/README.md)).
- `ward-lap-b-acceptance-v1` 은 검토용 제안이다. 승인·실행된 것이 아니다(파일 `purpose`).
작성 과정은 [실험 안내](../README.md), 정확한 필드는 [schema](../../schemas/README.md)를 참고한다.
