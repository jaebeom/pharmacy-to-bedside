# 증거 JSON 계약 v1

구조 계약은 [protocol.schema.json](protocol.schema.json), [run.schema.json](run.schema.json)에
JSON Schema 2020-12로 정의한다. [검사기](../tools/evidence.py)는 이 파일에 사용한 제한된
키워드를 직접 해석하므로 별도 패키지를 설치하지 않는다. 지원하지 않는 schema 키워드는 오류다.
추가 의미 검사는 아래 규칙을 따른다. 두 JSON 종류 모두 알 수 없는 필드와 중복 JSON 키를 거부한다.
단일 JSON은 256 KiB 이하여야 한다.

| 항목 | 규칙 |
| --- | --- |
| Run ID | `YYYYMMDDTHHMMSSZ-master01-<8자리 소문자 hex>` 또는 `master02`; 파일명·UTC 시각·host 일치 |
| 시각 | UTC `YYYY-MM-DDTHH:MM:SSZ`; `created_at`은 실행 ID 발급 시각, freeze 이후 |
| 코드 | 전체 40자리 Git commit SHA와 `dirty`; acceptance commit은 이 저장소에 실제 존재해야 함 |
| Dirty pilot | `code.dirty_patch_sha256` 필수, 해당 hash의 diff artifact 보존; untracked 코드도 diff/artifact에 포함 |
| 환경 버전 | `os`, `ros`, `isaac_sim`, `rmw`, `gpu_driver`, `cuda` 실제 정확한 버전 문자열 |
| 환경 fingerprint | `config`, `scene`, `model`, `dataset` 각각 `{ "sha256": "<64 hex>" }` |
| 해당 없음 | 버전/fingerprint만 `{ "not_applicable": "10자 이상의 구체적 이유" }` 허용; 모르는 값을 해당 없음으로 쓰지 않음 |
| Clock | `clocks.duration`: 주 duration clock (`simulation` 또는 `monotonic`); 각 metric의 실제 clock은 protocol에서 선언; watchdog timeout은 항상 `monotonic` |
| Protocol 참조 | `experiments/protocols/<protocol-id>.json`의 정확한 경로와 파일 바이트 SHA-256 |
| Phase | protocol과 run이 동일; 모든 run은 frozen protocol, acceptance는 clean commit 필요 |
| Acceptance freeze | `--base` 기준 커밋에서 protocol이 이미 frozen이어야 함; freeze와 결과는 별도 PR |
| Acceptance 환경 | `config`, `scene` fingerprint는 SHA-256 필수; N/A 불가 |
| Outcome | `succeeded`, `failed`, `aborted`, `timeout`; 종료 상태 자체는 합격 판정이 아님 |
| Artifact | 1개 이상; URI·SHA-256·바이트 크기 필수. 실패에도 진단 로그를 남김 |
| Metric | protocol의 이름·단위와 정확히 일치. 빠진 metric도 명시적으로 기록 |
| 측정값 | 유한 숫자이면 `sample_count > 0`; 미측정이면 `value: null`, `sample_count: 0`, `missing_count > 0` |
| 표본 수 | `sample_count + missing_count > 0`; 두 값의 정의는 protocol의 denominator를 따름 |
| Seed | protocol의 사전 seed 목록에 포함, `repetition_index`는 1부터 지정 반복 수까지 |
| 정정 | 새 run의 `supersedes`는 실제 존재하는 더 이른 run ID; 원본 삭제·변경 불가 |
| 실패 분류 | protocol의 `requires_failure_classification`이 참이면(`hospital-full-acceptance-v3`·`v4`) `failed` run에 `failure_class`(`robot`·`infra`·`operator`)와 `failure_cause` 필수, `failure_evidence`·`retry_run_id`는 선택; `failed`가 아닌 run에는 네 필드를 둘 수 없음 |

`environment.versions`에는 배포판 이름만으로 모호한 패키지는 패키지 버전 또는 이미지 식별자까지
기록한다. 여러 파일로 구성된 config/scene/model/dataset은 정렬된 파일 목록과 개별 SHA-256을 담은
inventory를 artifact로 보존하고 그 inventory의 hash를 fingerprint로 사용한다. USD의 외부 참조,
텍스처, 모델 가중치 등 실제 로딩 의존성도 포함한다. 실제 사용하는 항목에는 N/A를 쓰지 않는다.
두 마스터에 분산된 환경은 호스트별 inventory를 모은 deployment inventory로 연결한다.

Protocol은 목적·초기화·시작/종료 사건·리셋·제외 기준을 `purpose`에 명시한다.
각 metric은 분모, aggregation, clock, 누락 정책을 사전 정의한다. `missing_policy`는 항상
`record_missing`, timeout 정책은 항상 `record_timeout`이다. 실패·timeout을 분모에서 조용히
제거할 수 있다는 뜻이 아니다. threshold가 없는 관찰 metric은 허용하지만 acceptance protocol은
최소 하나의 threshold가 필요하다. threshold를 변경하려면 별도 protocol을 새로 만든다.

한 run에서 simulation cycle 시간과 monotonic wall elapsed 시간을 별도 metric으로 함께
기록할 수 있다. 각 metric의 clock은 protocol 정의를 따른다. 시간 metric이 있으면
`clocks.duration`에 선택한 주 clock을 사용하는 metric이 최소 하나 있어야 한다.
숫자가 실제로 그 시계에서 계산되었는지, 서로 다른 호스트의 시계가 섞이지 않았는지는
원본·수집기 코드·독립 검토로 확인한다.

검사기는 threshold를 평가하거나 합격 보고서를 만들지 않는다. 사람의 독립 검토는
`evidence/reviews/`에 추가하고, PR 승인·branch protection으로 권한을 통제한다.
`verified` 같은 자기 선언 필드는 run schema에 존재하지 않는다.

Run의 host_id는 대표 수집 마스터다. 분산된 한 시행은 canonical run 하나로 집계하며 참여 호스트별 SHA·환경은 deployment inventory artifact와 config fingerprint로 연결한다. 이 연결은 사람 리뷰 대상이다.
supersedes는 동일 시행의 기록 정정만 허용한다. code/host/environment/clocks/protocol/phase/seed/repetition_index와 원본 artifacts를 보존하고 correction_reason을 적는다. 새 실행 성공으로 과거 실패를 대체하지 않는다.
