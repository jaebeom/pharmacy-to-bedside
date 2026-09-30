# 실습38 재현 입력 — 2026-09-23 인계 보완

**1350개 혼합 진열과 벨트 물리 진단의 당시 입력이다. 성공한 M0609 통합 실습 설정이 아니다.**
사용자가 9/23 위치값까지 Git에 보존하도록 명시하여 로컬 좌표·측정 입력을 처음 모았다.
공용 preset/default를 덮지 않는다. [재개 절차](../../../docs/runbooks/practice38-handoff.md)를 먼저 읽는다.

| 파일 | 용도 |
| --- | --- |
| `stock-mixed-1350.json` | 9선반×5층×30개, 모듈338·원통1012. 모든 물품 surface·size·층/열·접근 방향, 목표·레일·장애물·카메라·AMR 초기값 |
| `planning-inventory-1350.json` | 당시 순수 경로 사전 계산에 사용한 v2 inventory. 생산 ROS 토픽에 발행하는 입력이 아님 |
| `workcell-18-reference.json` | 비교용 이전 18칸 배치. 1350개 실습을 복원할 때 대신 사용하지 않는다 |
| `shelf-boards.json` | 선반별 높이·면적 측정 입력의 출처 |
| `probe-terminal.json` | 마지막 롤러 정착 진단. 받침대 배출 성공 아님 |
| `probe-receiver.json` | 짧은 경사판/받침대 배출 진단. 당시 결과 timeout |
| `terminal-start.json`, `receiver-start.json` | 실제 SHA·argv·기동 시각·입력 해시. 경로와 예전 출력 폴더는 기록용이며 그대로 재실행하지 않는다 |
| `dispenser-placement.json` | 원형/모듈/컨베이어 입구 world 좌표와 조제기 해시 |
| `amr-placement.json` | 합본 에셋 해시·시작 XY·팔 mount. 이 진단에서는 고정 |
| `hospital-pr484-resolved.usda` | 당시 실제 준비 병원 루트 레이어. 선반·문·벨트 등의 배치 보존. 외부 참조 자산은 별도 필요 |
| `review-display-20260923.json` | 9/23 화면 검토 때 본 카메라 시점·조명 설정. 당시 입력과 따로 둔 관측값이고 런타임이 읽지 않는다 |
| `manifest.json` | 모든 사본의 원본 경로·크기·SHA-256. 원본과 바이트 동일 |

JSON과 USD의 master02 절대 경로는 **당시 출처**다. 실행할 때 새 파일의 inventory 경로 및 외부 자산 위치만 변환한다. USD의 delete payload 목록을 전역 문자열 치환해 같은 값으로 합치면 파싱이 깨질 수 있으므로 무차별 치환하지 않는다. `stock-mixed-1350.json`의 `source_sha256`은 원래 18칸 입력의 계보이며 현재 파일 해시는 `manifest.json`이 기준이다.

단위: JSON world frame은 `hospital`, 위치/크기 m, 레일 각도는 관련 코드 정의를 따른다. 각 파일의 원래 값·키·precision을 유지했다. 선반 물품은 격자 진열이고 랜덤인 것은 파지 대상 선택이다.
