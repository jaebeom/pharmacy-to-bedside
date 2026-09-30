# 배포: <회차>

- 상태: planned | completed | rolled-back | aborted (하나 선택)
- 배포 담당자 / 리뷰어 / 승인 PR:
- 시작·종료 UTC / 실행 슬롯:
- 관련 issue / protocol:
- master01: 이전 SHA → 후보 SHA / 환경·config hash
- master02: 이전 SHA → 후보 SHA / 환경·config hash
- 추가 실행 호스트: 없음 또는 정확한 SHA·역할

## Preflight
작업 중인 실험 없음, 수집 경로, 마지막 승인 버전 보존, clean 코드, 실제 의존성·자산 식별,
clock/QoS/heartbeat/reset 확인 결과.

## 실행
정확한 명령·순서 / run ID / 성공·실패·미실행 검사 / 실제 차이.

## 롤백
원복 조건 / 원복할 호스트별 SHA 조합 / 결과 run / 남은 질문.
