# 증거 저장과 검토

## 지금 들어 있는 것 (2026-09-30, main `3b0b40b` = `v1.1.0` + 문서)

`runs/` 에 run manifest 95개가 있다. 2026-09-19 부터 09-28 까지 master01(`IsaacSim14`)·master02(`IsaacSim07`)가 발급했다.
아래 수는 `runs/*.json` 의 `protocol.path`·`host_id`·`outcome` 을 센 값이다. 판정은 아니다.

| protocol | phase | master01 성공/실패 | master02 성공/실패 | 합계 |
| --- | --- | --- | --- | --- |
| `pharmacy-lap-pilot-v1` | pilot | 6 / 0 | — | 6 |
| `hospital-refill-integration-pilot-v1` | pilot | — | 0 / 1 | 1 |
| `hospital-full-acceptance-v1` | acceptance | 41 / 3 | 18 / 5 | 67 |
| `hospital-full-acceptance-v2` | acceptance | 2 / 0 | 0 / 2 | 4 |
| `hospital-full-acceptance-v4` | acceptance | 14 / 3 | — | 17 |

- `v4` 의 실패 3건은 중단된 회전 6 의 attempt 1–3 이다(run `notes`). 성공 14건은 회전 7 이다.
- 회전별 판정과 릴리스는 배포 기록과 GitHub 릴리스에 있다: `v0.5.0`(회전 1–4), `v1.0.0`(회전 7, 14/14, attempt 12·13 미실행).
- `v1.1.0`(`f316197`) 코드로 돌린 acceptance run 은 없다. `v1.1.0` 배포 기록도 없다.
- `supersedes` 로 정정한 run 은 없다.
- 테스트 fixture(`tests/fixtures/`)는 합성 데이터다. 프로젝트 성능으로 인용하지 않는다.

`deployments/` 에는 배포 기록 셋이 있다: [`v0.5.0-rc.1`](deployments/2026-09-27-jaebeom-v0-5-0-rc-1.md), [`v0.5.0`](deployments/2026-09-27-jaebeom-v0-5-0.md), [`v1.0.0`](deployments/2026-09-28-jaebeom-v1-0-0.md).
`reviews/` 에는 검토 기록 둘이 있다(`2026-09-27-jaebeom-c4-artifact-loss.md`, `2026-09-27-jaebeom-c4r-host-split.md`).
기록 파일은 커밋 뒤 고치지 않는다. 정정은 새 파일로 한다.

## 층

| 층 | 저장 위치 | 의미 |
| --- | --- | --- |
| raw | 팀의 접근 제한 artifact 저장소 | 원본 로그·rosbag·영상·설정 snapshot |
| run | runs/*.json | 누가 어떤 코드/환경/규격으로 무엇을 관측했는지 |
| review | reviews/*.md | 원본·모집단·재현을 확인한 별도 판단 |
| analysis | docs/analysis/ | 해석, 경쟁 가설·반증·적용 범위 |
| decision | docs/adr/ | 팀이 선택한 설계와 이유 |
| deployment | deployments/*.md | master별 배포 SHA 조합·승인·rollback |

파일을 Git에 넣었다는 사실과 검증 완료는 다르다.
hash는 바이트 동일성을 확인하며 관측의 정확성·무누락·원인 판단을 보증하지 않는다.

## 수집 순서
1. experiments의 proposed 규격을 검토하고 frozen pilot 또는 acceptance protocol을 커밋한다.
2. 배포 기록으로 두 마스터의 코드 SHA 조합·설정·실행 슬롯을 고정한다.
3. 실행 전에 run ID와 예정 seed/repetition을 배정하고 수집을 시작한다.
4. 원본을 닫은 뒤 SHA-256·크기를 계산하고
   `sha256/<전체 hash>/<filename>` 같은 content-addressed 키에 복사한다.
5. run manifest에 protocol path/hash, 코드·환경, 결과(outcome), artifacts, 모든 지표를 기록한다.
6. 실패·abort·timeout도 저장한다. 수집기가 죽으면 운영자의 회차 기록과 대조해 복구한다.
7. [도구 사용법](../tools/README.md)대로 manifest·원본 hash를 검증한다.
8. 작성자 외 팀원이 [검토 틀](../docs/templates/evidence-review.md)로 모집단·재현·해석을 확인한다.

원본은 주 저장소와 두 번째 보존 위치에 복사하고 hash를 대조한다.
최소 보존 기간은 프로젝트 종료와 평가 이의 확인이 끝날 때까지로 제안한다.
삭제·장기 보관 기한은 팀이 저장 용량·자료 권한에 맞춰 결정하고 기록한다.
보존 위치·담당·용량·복구 확인 전에는 acceptance를 시작하지 않는다.
run 기록의 artifact 는 `sha256/<hash>/<파일>` 키·hash·크기만 담는다. 원본 파일은 이 저장소에 없다.
팀 공용 외부 저장소와 접근 권한을 정한 기록은 이 저장소에서 찾지 못했다(미확인).

## 내용 규칙
- raw를 Git에 넣지 않는다. URL에는 인증정보·서명 query를 넣지 않는다.
- code.commit은 제품 코드 SHA다. manifest 추가로 생긴 커밋과 다르다.
- 환경 versions와 fingerprints는 실제값, 적용 안 되는 항목은 이유를 남긴다.
  모르는 값을 not_applicable로 위장하지 않는다.
- 한 실제 시행에는 대표 수집 마스터(master01 또는 master02)가 발급한 canonical run 하나만 둔다.
  host_id는 수집 마스터이며 모든 실행 장비를 뜻하지 않는다. dev PC를 포함한 참여 호스트별
  SHA·환경·설정의 deployment inventory를 artifact로 보존하고 config fingerprint로 연결한다.
  같은 사이클의 두 마스터 로그는 이 run의 artifacts로 모으며 두 개의 성공 표본으로 세지 않는다.
  이 연결과 시행 중복 여부는 독립 리뷰에서 확인한다.
- 수치가 없으면 null, sample_count와 missing_count로 누락을 표현한다.
- 기록된 run·review 및 frozen protocol은 변경·삭제하지 않는다.
  정정은 새 기록에서 supersedes로 이전 것을 참조한다.
  supersedes는 같은 실제 시행의 기록 정정 전용이다. 코드·환경·host·protocol·seed·반복 번호를
  유지하고 원본 artifact와 correction_reason을 남긴다. 재실행·retry로 이전 실패를 대체할 수 없다.
  잘못된 시행 식별자는 기존 run을 rejected로 리뷰하고 새 측정으로 다룬다.
  정정 관계는 중복 측정이 아니다. 집계 때 원본과 정정을 둘 다 표본으로 세지 않는다.

## CI와 사람의 경계
CI는 schema, protocol hash, phase, finite 수치, 명명, 기존 기록 변경을 검사한다.
private artifact를 다운로드하거나 측정 진실·독립 승인·모집단 완전성을 증명하지 않는다.
검토자는 raw 접근·hash·실패 누락·환경·재현 run을 확인하고 verified/rejected를 결정한다.
검토 뒤 새 증거가 나오면 새 review와 analysis로 정정한다.
