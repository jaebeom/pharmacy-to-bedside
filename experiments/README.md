# 사전 실험 설계

실행 전 측정 계약을 정하는 곳이다. 실제 실행 결과는 `evidence/runs/`, 외부 자료는 저장소 밖에,
프로젝트 운영 규칙은 `docs/`로 보낸다.

1. [pilot template](templates/pilot-smoke-v1.json)을 복사해 `protocols/<kebab-id>.json`을 만든다.
2. `proposed` 상태에서 초기화, 시드·반복 수, 시작/종료 사건, 분모, timeout, 누락·실패 처리,
   metric과 clock을 리뷰한다. 예시 문구와 날짜를 실제 설계로 바꾼다.
3. 리뷰 후 `status: frozen`, UTC `frozen_at`을 기록한다. **Pilot도 기록을 시작하기 전에 freeze한다.**
4. 마스터가 protocol의 SHA-256과 배포 commit을 확인한 뒤 정해진 시행을 실행한다.
5. 모든 outcome을 기록한다. 실패 후 재시도는 새 run이며, 원래 실패를 덮어쓰지 않는다.
6. Pilot으로 합격선을 정했다면 **새 acceptance protocol**의 freeze PR을 먼저 병합하고 새 데이터를 수집한다.
   Pilot 결과를 acceptance로 이름만 바꾸지 않는다.
   Acceptance 결과 PR의 기준 커밋에 이미 frozen protocol이 있어야 CI를 통과한다.

Frozen protocol은 공백 변경도 포함하여 수정·삭제하지 않는다. 새 설계는 `-v2` 같은 새 ID로
추가하고 이전 protocol과 변경 이유를 목적/관련 의사결정에 연결한다. 실행 기록은 protocol의
정확한 파일 hash를 참조하므로, proposed 문서를 측정 도중 계속 편집하는 방식은 허용하지 않는다.

`protocols/` 에는 protocol 7개가 있다(frozen 6, proposed 1). 목록과 run 수는 [protocols README](protocols/README.md) 에 있다.
`fixtures/` 에는 성공·진단 회차의 입력 사본이 있다([integrated-09](fixtures/hospital-integrated-09/README.md), [practice38](fixtures/practice38/README.md)). 공용 기본값이 아니다.
템플릿은 합의된 실험이나 측정값이 아니며 자동 검사 대상 생산 기록에도 포함하지 않는다. 전체 계약과 검사는 [schemas](../schemas/README.md),
[tools](../tools/README.md)를 따른다. 실제 장비·GPU를 사용하는 통합 테스트 코드는
`sim/tests/`에 둔다. 이 디렉터리는 ROS 패키지가 아니다.
