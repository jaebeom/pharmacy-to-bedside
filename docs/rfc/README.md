# RFC — 제안

결정 전에 논의할 변경을 NNNN-kebab-title.md로 쓴다.
상태(proposed/rejected/promoted), 작성자, 질문, 근거/가설, 대안, 검증 계획,
담당·기한, 관련 issue를 포함한다. 승인 문서가 아니다.
비용이 큰 결정을 채택하면 [ADR](../adr/README.md)로 연결하고 promoted와 목적지를 남긴다.

## 목록

2026-09-30 파일 목록과 대조했다. 상태는 각 문서 머리의 `상태` 칸을 옮겼다.

| 번호 | 제목 | 상태 | 기준 |
| --- | --- | --- | --- |
| [0001](0001-navigation-ward-routing-and-reset.md) | 병동 주행(F3): 계층 경로 연결과 리셋 뒤 costmap 초기화 | proposed | main `e271081` |

병동 주행의 지금 구성(odom TF, Nav2 는 접근점까지, 마지막 구간은 직접 추종기)은 [ADR 0003](../adr/0003-ward-driving-approach-point.md)에 있다.
그 ADR 도 `proposed` 다. 저장소에는 이 RFC 를 promoted 로 바꾼 기록이 없다.
