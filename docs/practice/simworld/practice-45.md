# 2026-09-29 master02 카메라 배송 실습

탐색적 현장 실습 기록이다. frozen protocol에 따른 acceptance manifest가 아니다. 전체 병실 성능으로 일반화하지 않는다.

- 제품 코드: `05b8e2851a851ff9c2edebf2a5b39120a8121b41`, 후보 작업 트리 `candidate/hospital-dock-start-yaw`.
- 원본 및 실행 설정: `/home/rokey/markle_tmp/m2-near-tag-auth-fix-20260929`. 코드/환경 변경별 이전 실패 회차는 각 폴더에 별도 보존했다.
- 요청 `near-tag-auth-fix-20260929-01`, `ord-0001`, 환자2001, `bed_a1`.
- 파우치/태그 카메라 기본 사용. 실제 Isaac Sim GUI, 관제 웹, 화면 녹화.

## 관측

요청45.850 → 파우치 배출45.883 → 적재 위치 도착60.817(sim s). 첫 조제와 AMR 이동을 함께 시작했다.
탁자 정착64.250, 흡착거리0.0052m, 적재완료88.050. 환자 태그 카메라 판독2001 → AUTH_OK147.483.
ORDER_DONE182.950, DELIVERED. 별도 보관함 관측도 `bed_a1/cabinet`, `ord-0001`, present=true.
DOCKED248.750 뒤 trip 없음·idle 확인. 현재 시뮬/UI는 도크 대기 상태로 유지했다.

## 변경 및 한계

- 병실 태그를 로봇 가까운 가장자리로 옮겼다. 실제 QR 면과 TF를 일치시켰다. A1은 (22.82,7.625,0.6355).
- 계약대로 접두를 뺀 카메라 ID와 기존 sim QR 전체 ID를 같은 정거장 ID일 때만 인증한다.
- 동시 시작은 첫 파우치에 적용. 파지는 AMR 도착과 봉투 정착 후에만 허용한다.
- load 위치·receiver 판정·파지 추가하강0.05m·동시 조제 활성화는 위 env.sh 및 외부 YAML 실행 설정이다.
- 5cm 추가 하강은 실측 보정이다. odom/base 높이 차이의 근본 수정은 아직 하지 않았다.
- 병실10개 태그 배치를 바꿨으나 L3는 A1 한 건. 다른 병실·다른 도크·반복 신뢰성은 미실행.
- PR/push/main 병합 미실행.

## 검증

손목/파지 L1 91 passed, 정착18 passed, 태그37 passed, 최종 FSM76 passed. 관련 colcon build 성공.
Ruff 전체, check_repository, evidence validate 성공. 전체 unittest·전체 colcon test는 미실행.

## 실패 보존

`/home/rokey/markle_tmp/` 아래 같은 날짜의 `m2-receiver-mobile-pick`, `m2-receiver-locked-wrist`,
`m2-receiver-drop5cm`, `m2-table-settle-drop5cm`, `m2-near-tag-concurrent` 폴더에 원본을 보존했다.
높이 오차로 흡착 실패, 정착 조건으로 파지 미진입, 병실 관측 IK 실패, 태그 판독 후 ID 형식 불일치를 구분했다.
직전 회차는 판독 성공했지만 auth_mismatch였으며 이번 성공으로 대체하지 않는다.

원본 파일별 hash는 `artifact-hashes.json`, 자세한 단계/한계는 `summary.md`, 영상은 `delivery-success.mp4`다.
조제기 재개 대기 분석은 `m2-receiver-locked-wrist-20260929/resume-wait-analysis.md`에 별도 보존했다.
