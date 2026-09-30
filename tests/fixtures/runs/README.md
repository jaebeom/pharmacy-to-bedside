# 합성 run 디렉토리

`tools/aggregate_runs.py`·`tools/hospital_full_metrics.py` 테스트 전용이다. 실제 실행이나 측정이 아니다.
2000년 날짜, `master02`, stamp 값은 모두 지어낸 것이다. `evidence/runs/` 에 옮기지 않는다.

한 줄 형식은 `event_logger_node.py` 가 쓰는 그대로다. 파일은 `run_log.jsonl`·`run_log.judge` 로 만들었다.

| 디렉토리 | 내용 |
| --- | --- |
| `20000101T000000Z-master02-00000001` | 기동 직후 epoch 1 의 조제실 한 바퀴. protocol 의 시행이 아니다 |
| `20000101T000100Z-master02-00000002` | epoch 2, 리셋 뒤 한 바퀴. 픽 재시도 1회, 보충 요청과 보충 완료 |
| `20000101T000300Z-master02-00000003` | epoch 3, 배출 직후 리셋으로 끊긴 트립 |
| `hospital-full-a01` | 병원 attempt 폴더 하나. master01 campaign 1 attempt 1(`64e5ab7`)의 줄 형식을 두고 값은 규칙이 모두 걸리게 고쳤다. `test_aggregate_hospital_full.py` 가 쓴다 |

`pharmacy-lap-pilot-v1.json` 은 테스트용 protocol 이다. `metrics` 는 `experiments/protocols/pharmacy-lap-pilot-v1.json`(frozen 2026-09-19)의 것을 복사했다.
두 `metrics` 가 같은지 테스트가 확인한다.
