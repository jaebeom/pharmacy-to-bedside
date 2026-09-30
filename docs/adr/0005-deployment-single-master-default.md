# ADR 0005 — 배치: 단일 마스터가 기본, `P3_ROLES` 로 두 대 분리

- 상태: proposed
- 날짜: 2026-09-25
- 결정자: 재범. 호스트 배치 결정 ⑤ #576 5797408402(시나리오 284행). ⑤ 확정은 9/24 14:2x 에 전달됐다([촬영 샷리스트](../presentation/hospital-demo-shotlist.md) 51·55행). 그 확정의 댓글 URL 은 없다. PR #602 는 재범 요청(9/23)이다
- 승인 PR: 없음(이 ADR 의 PR 에서 검토)
- 관련 issue / RFC / evidence review: PR #602(bfeb4af), [계약 v1 1.1](../architecture/delivery-contract-v1.md#11-실제-배치-924), [시스템 그림](../architecture/system-overview.md), [병원 시연 런북 10절](../runbooks/hospital-demo.md), [리하 05](../reha/reha-05.md), [rtf 레버](../presentation/challenge-rtf-levers.md), [유선망 설정](../setup/ros2-wired-network.md)
- 대체 관계: 계약 v1 0–1절의 계획 배치(Isaac = master1, YOLO·QR·오케스트레이터·GUI = master2, 노트북)를 대신한다. 계획은 9/18 부하 측정 뒤 `rokey_p3_bringup/config/hosts.yaml` 에 적기로 했다. 그 파일은 main 에 없다. 9/18 측정 기록도 찾지 못했다(미확인)

## 맥락

- 노트북은 쓰지 않았다(계약 1.1).
- 두 대로 나눈 회차는 회차19 하나뿐이다([리하 05](../reha/reha-05.md) 50–70행, [회차표](../reha/rounds-240.md) 36–37행). 한 시나리오를 두 PC 에 나눈 첫 회차다.
  - 빌드 4d01333, 도메인 131. master01 = stage(`/clock` 발행자 1), master02 = arm·nav·stack·web.
  - #240 5797973069(master01)·5797973429(master02)·5798100488(녹화).
  - 결과 5/5, `/orders/status` 0→1→1→2 DELIVERED, 접촉 0.
  - rtf 0.711 이다. 한 대 회차18(bfc8c38)은 0.686 이다. 차이는 **+0.025** 다. N=1 이다.
- 결정 ⑤의 채택선은 +0.1 이다. +0.025 는 못 미친다([rtf 레버](../presentation/challenge-rtf-levers.md) 19행).
- 전체 노드를 한 번에 띄운 부하는 검증하지 않았다([노드 구성](../analysis/node-topology-v1.md) 45·56행). 병원 부하 측정은 [9/23 부하](../analysis/2026-09-23-hospital-sim-load.md)·[N대 부하](../analysis/hospital-amr-count-load.md)에 있다.
- 망 제약: 방화벽이 UDP 를 막으면 토픽이 조용히 안 온다([유선망](../setup/ros2-wired-network.md) 3절 72–83행). 두 PC 는 같은 도메인과 같은 DDS 프로필이어야 한다.

## 대안

| 안 | 내용 | 한계·반증 |
| --- | --- | --- |
| A | 계획 배치(Isaac 1대 + 나머지 1대 + 노트북) 고정 | 노트북 미사용. 이득이 +0.025(N=1)라 두 대를 기본으로 할 근거가 없다 |
| B | **한 대가 기본. `P3_ROLES`·`P3_PEER` 로 두 대 분리를 선택지로 둔다** | 두 대 경로는 기본 회차에서 돌지 않아 회귀를 늦게 안다. 반증: 두 대가 같은 기계 비교에서 +0.1 이상이면 기본을 바꾼다 |
| C | 한 대만, 분리 기능 없음 | 한 대 부하가 넘치는 구성(N대 AMR 등)에서 대안이 없다 |

## 결정과 이유

**B안.**

- 기본은 `P3_ROLES`·`P3_PEER` 를 비운 한 대다. 월드의 모든 역할을 순서대로 띄운다: stage → arm → nav → stack → web(`tools/demo_v2.sh` 231–242행, [시스템 그림](../architecture/system-overview.md) 14·18–22행).
- 두 대(PR #602, bfeb4af, 0e2c5e7):
  - 스테이지 PC 는 `P3_ROLES="stage"` 로 먼저 띄운다. 다른 PC 는 `P3_ROLES="arm nav stack web"` 로 스테이지가 준비된 뒤 띄운다. 둘 다 `P3_PEER=<상대 IP>` 를 준다(`demo_v2.sh` 20–22행).
  - `P3_PEER` 는 모든 역할에 `FASTRTPS_DEFAULT_PROFILES_FILE` 과 `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET` 을 넘긴다.
  - 띄우기 전 확인: 상대 ping, 프로필 안의 두 주소와 127.0.0.1, LOCALHOST 제한. 실패하면 exit 2 다.
  - 스테이지가 없는 PC 는 `/clock` 발행자가 정확히 1 이어야 한다(아니면 exit 3). 2 s 안에 sim 시간이 흘러야 한다(아니면 exit 4).
  - 시험: `tests/test_demo_v2.py` 179–296행.
- 촬영과 기본 회차는 한 대로 돈다(결정 ⑤).

## 결과

- 두 대 경로는 회차19 한 번(N=1)으로만 섰다.
- #602 본문은 PR 시점에 실물 두 대(L3) 회차가 없었고 PC 사이 방화벽도 확인하지 않았다고 적는다. 회차19 가 그 뒤의 L3 다.
- 9/24 밤 다중 PC 회차(빌드 fcec7a8, #240 5816379015·5816418529)는 **main 문서에 기록이 없다.**
  - main 에 없는 브랜치 문서만 "N=4 다중 PC PASS" 를 적는다(docs/tutor-response-deck 의 `tutor-response.md`).
  - 같은 밤의 10건·N=2 결과는 그 문서에서도 대기로 남았다.
  - fcec7a8 자체는 트레이 클립 커밋이다. main 에 없다(exp 브랜치들).
  - [9/25 밤 기록](../reha/night-0925.md)은 빈 양식이다.
  - 그래서 이 ADR 의 근거로 세지 않는다. 기록되면 이 절에 더한다.
- 재검토 조건: 같은 기계 비교에서 두 대가 +0.1 이상이면 기본을 바꾼다. 또는 한 대 rtf 가 합격선 0.35 아래로 떨어지는 구성을 기본으로 쓰게 되면 다시 본다.

## 롤백

- 두 대로 띄운 뒤 문제가 나면 `P3_ROLES`·`P3_PEER` 를 비우고 한 대로 띄운다. 코드 변경은 없다.
- 기본을 두 대로 바꾸는 것은 이 ADR 을 대체하는 새 ADR 이다.
