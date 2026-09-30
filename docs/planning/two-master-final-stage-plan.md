# P7 마스터 PC 2대 운영 계획 — 안정형 A / 고도화형 B

상태: **후속 계획 / 구현 미착수**. 2026-09-18 임재범 요청에 따라 마지막 단계에 배치한다.
검토 기준: main `7f5eada6a16cce2d55c84e4d4613fd699f89580f`.
이 문서는 현재 운영 설정이나 현장 검증 결과가 아니다. 옵션 A는 검증된 배치·유선 DDS를 유지하는 안정형, 옵션 B는 Master 02 = Isaac / Master 01 = ROS 제어·빌드·관제와 Zenoh·headless·Docker·복구 자동화를 적용하는 고도화형이다.
2026-09-19의 [기능 통합 후 리소스 최적화 계획](integration-resource-two-phase-plan.md)은 시연 전 동일 배치에서 장면·센서·물리 부하를 조정하는 별도 작업이다. 그 2차 O가 아래 P7-B의 배치·통신·컨테이너 전환을 시연 앞으로 당기는 뜻은 아니다.
2026-09-18 추가 요청에 따라 두 옵션을 병렬 선택지로 둔다. A를 선택한 뒤 반드시 B까지 진행하는 일정이 아니다.
세부 배포 설정과 아래 합격선 초안은 착수 시 pilot 후 별도 protocol/PR로 확정한다.

## 1. 일정에 넣는 위치와 시작 조건

[일정](schedule.md)의 P0-P6 뒤에 **P7 운영 환경 최적화**를 둔다.
기본 착수 시점은 **9/30 최종 발표 완료 이후**다. 이는 “마지막 단계”를 기존 일정에 적용한 계획상 해석이며 확정 착수일이 아니다.
9/21 조제실 시연, 9/29 최종 시연, 9/30 발표, 기존 acceptance 실행의 선행 조건으로 넣지 않는다.

착수 조건은 모두 충족해야 한다.

- P6 결과와 발표에 쓴 태그·씬·설정·run·원본 위치가 보존되어 있다.
- 승인된 시나리오가 기존 배치에서 정상 종료 → 리셋 → 재실행으로 3회 연속 완료된다.
  조제실 pilot의 HOLD_RETURN과 전체 배송의 성공 판정을 혼용하지 않는다.
- A1-A4 등 미해결 런타임 문제가 있으면 원인 수정 또는 재현 조건·운영 제한·롤백을 먼저 정리한다.
  분산화나 headless 전환을 원인 미확인 종료 현상의 해결책으로 간주하지 않는다.
- 마스터 2대의 후속 사용 기간, 현장 복구 담당, 공용 장비 사용 시간이 확보되어 있다.
  master02의 다른 사용자 프로세스 관측은 [장비 목록](../setup/host-inventory.md)에 있으므로 전용 사용을 가정하지 않는다.
- 동일 조건의 기준 실행과 복구 절차를 확보하고 P7 전용 작업 브랜치·이슈를 만든다.

P7 도중 앞 단계의 판정이 깨지면 그 변경만 되돌린다. 최종 시연 태그와 frozen protocol은 수정하지 않는다.
예상 집중 공수는 **옵션 A 1-2일 / 옵션 B 5-6일 + 리뷰·현장 슬롯 대기**다. 모두 환경 검증 전의 추정이며 공통 기준 확보를 포함한다. 두 옵션을 반드시 합산하지 않는다.

## 2. 두 가지 선택지

| 비교 | 옵션 A — 쉬운 안정형 (기본 권고) | 옵션 B — 기존 계획의 고도화형 |
| --- | --- | --- |
| 목표 | 적은 변경으로 반복 실행과 복구를 확실하게 한다 | 원격 ROS 연결·재현 가능한 배포·운영 자동화를 확대한다 |
| PC 배치 | 마지막으로 통합 검증된 실제 배치를 고정. 문서상의 번호에 맞추려고 옮기지 않는다 | Master 02 Isaac 전담 / Master 01 ROS 제어·빌드·관제 |
| ROS 통신 | 같은 유선 LAN에서 기존 Fast DDS 직접 통신 | 로컬 DDS + zenoh-bridge-ros2dds + Tailscale 명시적 유니캐스트 |
| 원격 접근 | Tailscale은 SSH·관리. ROS는 교육장 유선망에 남긴다 | Tailscale에 검증된 Zenoh ROS 경로를 추가한다 |
| Isaac 실행 | 검증된 네이티브 실행 모드·버전 유지. 창 모드가 기준이면 창 모드 유지 | 네이티브 분리 → headless 동등성 → Docker 순서로 변경 |
| 화면·디버깅 | 현장 GUI/유선 RViz, SSH CLI·로그. 기존 검증된 화면 접속만 사용 | WebRTC 1인 접속, CLI/관제, 필요 시 제한된 원격 RViz 경로 검증 |
| 다중 개발자 | 개인별 개발·빌드 공간, 통합 실행 동안 마스터의 빌드·학습 중지 | runtime/build slice 격리 후 제한된 동시 빌드 |
| 시작·중지·복구 | 지정 담당자가 tmux에서 절차대로 수동 실행·정지·태그 롤백 | readiness 확인과 제한 재시작을 갖춘 systemd 관리 |
| 저장소·에셋 | 기존 release worktree와 로컬 에셋·캐시 유지 | image digest·NVMe 마운트 고정. NFS는 실제 필요할 때만 |
| 집중 공수 | 1-2일 추정 | 5-6일 추정 |
| 주요 제약 | 외부 노트북의 ROS 직접 참여와 무인 복구를 제공하지 않음 | 브리지 상호운용·네트워크 단절·컨테이너·부팅 순서의 추가 검증 필요 |
| 선택 기준 | 쉬운 운영과 안정성이 최우선이면 선택 | 원격 ROS 참여·동시 개발·자동 복구가 실제 요구이고 검증 시간이 있을 때 선택 |

“안정성이 가장 높다”는 이 두 안 가운데 **추가 변경과 장애 원인을 최소화하는 설계 판단**이다.
A의 무장애가 실측으로 입증됐다는 뜻은 아니다. B의 기술 구성이 더 진보됐다고 해서 자동으로 더 안정적이거나 더 빠른 것도 아니다.
현재 요청은 선택지를 만드는 것이며 최종 선택은 아직 하지 않았다. 별도 선택이 없을 때의 계획상 기본값은 A다.
Ray/K3s, 분산 VRAM/NCCL, 무차별 정리 작업은 두 옵션 모두 범위 밖이다.

### 2.1 옵션 A — 실행 절차와 독립 완료 조건

1. **기준 고정 (0.5일):** 현재 성공한 run의 실제 호스트 배치·태그·Isaac/RMW/domain·DDS 설정·씬/에셋 hash와 실행 모드를 기록한다.
   2대의 역할이 이미 나뉘어 있으면 그대로 유지한다. 다른 배치만 검증됐으면 그 배치를 A 기준으로 삼고 새로운 역할 분리는 B에서 한다.
2. **운영 단순화 (0.5일):** 사용 슬롯과 한 명의 실행 담당을 정한다. 태그별 release, 사용자별 개발 공간, 명시적 tmux 세션을 사용한다.
   통합 실행 중 두 마스터의 빌드·학습을 중지하고, 코드 작업·가벼운 검증은 개인 개발 환경에서 한다.
   실행 인자·환경을 runbook으로 고정한다. 브리지·Docker·전역 GUI 설정·OOM 데몬은 새로 도입하지 않는다.
3. **반복·복구 확인 (0-1일):** 아래 판정을 확인하고 운영 runbook과 새 run 기록으로 닫는다. A가 통과하면 P7을 A로 완료할 수 있다.

| A 합격 항목 | 판정과 증거 |
| --- | --- |
| 실제 기능 | 기존 승인 시나리오를 리셋 포함 3회 연속 완료. 새 성공 의미를 만들지 않음 |
| 통신·시간 | 기존 유선 경로에서 필수 토픽·서비스·액션 정상, /clock 단일 발행, TF·epoch·리셋 계약 유지 |
| 지속 실행 | 같은 기준 설정으로 120분 관측, crash/OOM 없음. 메모리 상한은 기존 고정 기준을 쓰거나 pilot 후 미리 고정 |
| 운영 재현 | SSH를 끊었다 붙여도 tmux 작업 유지, 정상 정지 후 로그 보존, 지정 담당자가 같은 태그로 재실행 |
| 수동 복구 | 별도 개발 태그 또는 설정 후보에서 기준 release로 복구 후 루프 1회 완료. 실패 원본도 보존 |
| 연결 장애 | 제어·시뮬레이션이 다른 호스트라면 유선 단절 시 기존 로컬 watchdog/명령 만료 계약 검증. 미구현이면 A도 운영 합격 처리하지 않고 별도 수정 |
| 부하 관리 | 통합 실행 중 마스터 빌드·학습 프로세스 없음. 동시 빌드 성능이나 새로운 15ms 목표는 A의 합격 조건으로 추가하지 않음 |

A는 현재 동작이 불안정한 상태를 그대로 “안정형 완료”로 부르는 안이 아니다.
기존 런타임 결함이 남아 있으면 원인 수정·검증이 먼저다.
화면 원격 접속이 미검증이면 현장 GUI와 SSH 관측만을 A의 제공 범위로 적는다.
새 WebRTC·원격 데스크톱 도입이 A의 숨은 전제가 되지 않게 한다.

### 2.2 옵션 B — 기존 계획 유지

아래 **3절부터 8절까지는 옵션 B의 상세 설계·실행 순서·합격 기준**이다.
B를 선택해도 검증된 기준 배치와 수동 복구는 먼저 확보한다. 이미 A의 기록이 있으면 재사용할 수 있다.
A를 별도 프로젝트로 먼저 완성해야만 B를 선택할 수 있는 것은 아니다.
B 전환 실패 시 검증된 A 프로필 또는 P7 직전 기준 배치로 복구하고, B는 보류 상태로 남긴다.
A/B 실행 프로필을 한 번에 띄우지 않는다. 두 /clock이나 직접 DDS와 Zenoh의 중복 경로를 만들지 않는다.

## 3. 옵션 B — 기존 운영과 목표 배치

| 항목 | 현재 저장소의 운영 기준 | P7 목표 |
| --- | --- | --- |
| master01 | Isaac Sim 주력 | ROS 2 고레벨 스택, 관제, 제한된 개발 빌드 |
| master02 | 비전·학습·오케스트레이터; 조제실 Isaac 개발 실행도 관측됨 | Isaac Sim 단일 장기 실행, PhysX·렌더·센서·시뮬레이터 내부 제어 |
| 호스트 간 ROS | 유선 10.10.0.x, Fast DDS | 로컬 DDS + 호스트 간 Zenoh 명시적 피어 연결 |
| Tailscale | SSH·관리; ROS 토픽 전송 금지 | P7에서 검증된 Zenoh 유니캐스트 경로를 허용하는 정책 변경 |
| 실행 환경 | 네이티브 Python 실행·태그별 release | 네이티브로 분리 검증 후 headless, 마지막으로 Docker를 별도 검증 |
| 코드 배포 | 개발 클론과 태그별 release 분리 | 유지. 사용자별 개발 공간 + 태그별 불변 배포 |
| 무인 복구 | 수동 관측·배포·롤백 | 제한된 서비스 복구 후 주문 비활성 대기 |

현재 [셋업](../setup/README.md), [장비 목록](../setup/host-inventory.md), [워크스페이스](../process/workspace-layout.md)가 운영 기준이다.
옵션 B 전환 PR에서 이 문서들과 [배송 계약](../architecture/delivery-contract-v1.md)의 배치 표를 함께 갱신한다.
장비 별칭과 기존 evidence는 바꾸지 않는다. 동일 master02라도 run별 배포 기록으로 역할을 구별한다.

현재 장비 기록상 master02는 Ubuntu 24.04.4, CPU “24 코어”(논리/물리 구분 재확인), RAM 62G,
NVMe 937G, RTX 5080 Laptop 16303 MiB, 드라이버 580.173.02,
Isaac 5.1.0-rc.19+release.26219, Jazzy/Fast DDS다.
master01의 CPU/RAM/드라이버는 미확인이다. 두 GPU의 VRAM을 하나로 합치는 계획이 아니다.

## 4. 옵션 B — 원안 검토와 수정

| 원안 | 판단 | 계획에 반영할 내용 |
| --- | --- | --- |
| Ray/K3s 가상 자원 풀 철회 | 채택 | 2대의 고정 배치에는 추가 운영 계층의 이익이 작다는 프로젝트 판단. “실시간 상호작용 지원 불가”라는 절대적 주장은 삭제. Ray에는 장기 실행 actor도 있다 [S1] |
| NCCL은 최소 10GbE 필수 | 수정 | 통신량·모델·NIC에 따라 달라지는 성능 문제다. 이번 범위에 분산 학습/NCCL을 넣지 않으며 10GbE 구매를 선행 조건으로 두지 않음 |
| 매번 Isaac 인스턴스 생성·폐기 | 제외 | 세션 내 장기 실행 + 계약상 리셋. 장시간 메모리 문제는 측정 후 정상 종료/재기동 주기로 관리 |
| zenoh-bridge-dds | 수정 | ROS 그래프·서비스·액션·CLI/RViz 지원을 위해 **zenoh-bridge-ros2dds**를 1차 후보로 검증. RMW 자체를 rmw_zenoh로 바꾸는 작업은 제외 [S2] |
| Zenoh가 센서 데이터를 자동 압축 | 수정 | 브리지 도입만으로 압축된다고 가정하지 않음. 토픽 선별·발행률·해상도부터 조절. image_transport 등 코덱과 복호화 소비자, 포인트클라우드 축소는 별도 측정 |
| nvidia-smi EXCLUSIVE_PROCESS로 VRAM 보호 | 제외 | CUDA compute mode이며 모든 그래픽 프로세스의 VRAM을 격리하는 장치가 아니다. 장비 지원도 확인 필요. 단일 서비스 소유·사용 슬롯·중복 실행 잠금으로 관리 [S3] |
| persistence mode 상시 강제 | 조건부 | 해당 GPU/드라이버 지원과 효과를 확인한 경우만 적용. 재부팅 후 유지되는 설정으로 오해하지 않음 [S3] |
| --headless --livestream 2 및 포트 8211/47995-48012 | 수정 | Isaac 5.1 공식 streaming 실행 경로와 **TCP 49100 / UDP 47998**를 기준으로 검증. 프로젝트 standalone 스크립트의 streaming 초기화는 별도 확인 [S4] |
| 브라우저/Omniverse 구형 클라이언트, 여러 명 동시 접속 | 수정 | **Isaac Sim WebRTC Streaming Client** 우선. 공식 5.1 안내는 인스턴스당 클라이언트 1개. 브라우저 뷰어는 별도 구현·검증 대상으로 보류 [S4] |
| NVMe cache 고정 | 채택 | 실제 5.1 이미지의 cache·ComputeCache·로그·config·data 마운트, UID/GID·쓰기 권한을 확인. warm/cold 시작 시간을 따로 측정 [S5] |
| 32GB swap + earlyoom 기본 설치 | 보류 | swap은 VRAM 부족을 해결하지 않으며 디스크 대기로 지연이 커질 수 있음. 먼저 메모리 계측·빌드 제한·정상 종료. OOM 종료 대상을 검증하기 전 데몬 자동 살해 정책 금지 |
| 사용자마다 CPU 70%·RAM 75% | 수정 | 빌드 전체의 부모 slice 예산과 사용자별 하위 한도를 함께 설정. CPUQuota=70%는 전체 CPU의 70%가 아니라 CPU 1개 기준 70%다 [S6] |
| X-server 즉시 비활성화 | 보류 | GUI 복구 경로를 보존한 채 headless 동등성부터 확인. 전용 운영 모드 전환은 그 다음 |
| USD를 NFS로 공유 | 선택 | 제어 노드가 대용량 USD를 실제 소비하는지 먼저 조사. 불필요하면 공유 안 함. 필요하면 읽기 전용, 승인 호스트 한정, 시뮬레이터는 로컬 NVMe에서 로드 |
| Git submodule + /opt/p3_workspace 강제 | 제외 | 현행 단일 저장소·release worktree 유지. 공용 build/install에 여러 사람이 쓰지 않음. 독립 외부 저장소가 생길 때만 submodule 검토 |
| 매일 05시 좀비/컨테이너/볼륨 정리 | 제외 | 실행 중인 세션·캐시·원본 증거 삭제 위험. 이름·소유권이 확인된 서비스 종료와 보존 기간 기반 로그 정리만. 자동 docker volume prune 금지 |
| 60 FPS·간섭 0·15ms 무조건 보장 | 수정 | 화면 FPS·물리 step·RTF를 분리. 기준 대비 성능·토픽별 지연 분포·손실·시계 오차를 protocol로 고정 |

## 5. 옵션 B — 통신과 실행 경계

### 목표 경로

Master 02의 Isaac/Fast DDS ↔ 로컬 ROS2DDS 브리지 ↔ Tailscale 유니캐스트 ↔
Master 01의 ROS2DDS 브리지 ↔ 로컬 ROS 제어·인식·관제.

- Master 02: USD·PhysX·렌더·센서·물리 스텝에 결합된 코드와 로컬 명령 만료/정지 경계.
- Master 01: 현행 orchestration·manipulation·navigation·perception·웹 백엔드. MoveIt 2는 현행 의존성이 필요로 할 때만 둔다.
  YOLO 추론이 필요한 경우 Master 01 자원 예산에 포함하며 학습은 통합 실행 중 배제한다.
- 개발자: SSH/tmux와 사용자별 빌드 공간. 웹 관제/Foxglove는 읽기 관측 위주. 조작권은 한 세션이 소유한다.
  로컬 RViz가 필요하면 해당 PC를 제한된 관측 브리지 참가자로 따로 검증한다.

통신망 “단일화”는 **호스트 간 ROS 경로가 하나**라는 뜻이다.
SSH·WebRTC와 로컬 DDS까지 하나의 프로토콜로 합치지 않는다.
유선 DDS 기준 실행 → 유선 Zenoh 비교 → Tailscale Zenoh 비교 순서로 운송 계층의 비용을 분리한다.
Tailscale에서 direct/relay 경로를 기록하고 [S7], 기존 2.5G 스위치 사양만으로 NIC 실효 속도를 추정하지 않는다.
목표 Tailscale 경로가 기준을 못 채우면 검증된 A 또는 유선 기준으로 복구하고 옵션 B 통신 전환을 보류한다. 우회망을 동시에 열지 않는다.

### 최소 연결 검증

1. 양측 브리지 버전·설정 digest를 고정하고 peer endpoint를 명시한다. ROS allowlist를 만든다.
2. 브리지는 Cyclone DDS 기반이므로 기존 Fast DDS와의 **호스트 내부 UDP 상호운용**부터 검증한다.
   공유 메모리 전용 전달을 기대하지 않으며 앱 전체 RMW를 동시에 교체하지 않는다 [S2].
3. 호스트별 DDS domain 분리와 인터페이스 제한을 설계한다.
   같은 호스트의 Isaac/ROS와 브리지는 같은 domain을 사용한다. 기존 통합/개발 domain과 충돌하지 않는 값은 현장 배정한다.
   Jazzy discovery 환경변수만으로 Isaac 내장 브리지 설정까지 적용됐다고 가정하지 않는다.
4. **DDS가 두 PC 사이를 직접 우회하지 않음**을 확인한다. 브리지를 끄면 호스트 간 테스트 토픽이 끊겨야 한다.
   중복 discovery/루프·이중 명령 경로가 있으면 진행하지 않는다.
5. /clock·/tf·/tf_static → 상태/명령 → 서비스/액션 → 카메라/라이다 순서로 연결한다.
   /clock 단일 발행, use_sim_time, TF 소유자와 transient-local late-join을 검사한다.
6. 서비스 응답, action goal/feedback/result/cancel, reset 요청/응답과 RESET_BEGIN을 검증한다.
   실제로 경계를 통과하지 않는 액션은 작은 양단 스텁으로 도구 호환성을 확인하되 제품 E2E 증거와 구분한다.
7. 통신 단절·재연결에서 goal token/epoch가 오래된 결과를 차단하는지 확인한다.
   컨트롤 호스트와 단절되어도 실행 호스트가 로컬에서 명령을 만료·정지시켜야 한다.
   이 경계가 없다면 별도 기능 PR과 L1/L2/L3가 먼저이며 배포 설정만으로 완료 처리하지 않는다.

## 6. 옵션 B — 실행 순서와 PR 단위

담당은 현행 역할 기준 제안이다. 신규 배정이나 현장 실행 완료를 뜻하지 않는다.

| 단계 | 예상 집중 공수 | 작업과 산출물 | 다음 단계 진입 조건 | 주 담당 제안 |
| --- | --- | --- | --- | --- |
| P7-0 기준 확보 | 0.5일 | 장비 inventory 갱신, 실제 process 배치·태그·자산 hash, direct/relay·NIC 실효 속도, 기준 run 3개·복구 절차 | 장비 사용 기간/슬롯 확보, 기존 시나리오 3회 완료 | 재범 + master01·master02 관측 |
| P7-1 역할 분리 | 1일 | 기존 네이티브 실행·유선 DDS 유지, Master 02 Isaac / Master 01 제어 배치 PR, 사용자별 build와 부모 slice 예산 | 무부하·동시 빌드 조건에서 반복 루프 유지 | 정비 + `sim/` |
| P7-2 Zenoh 전환 | 1-1.5일 | 버전 고정 브리지 설정, domain/allowlist/endpoint, 위 최소 연결 검증과 유선/Tailscale 비교 | 서비스·액션·리셋·센서·단절 검사 통과 | 정비 + 재범 계약 검토 |
| P7-3 headless·Docker | 1일 | 네이티브 headless 동등성 확인 후 Docker 별도 PR, 이미지 digest·streaming·NVMe 마운트·정상 종료 | 실제 P3 씬 로드, 1인 WebRTC 관측, Ctrl+C/서비스 중지 후 기록 보존 | `sim/` + 정비 |
| P7-4 복구 자동화 | 0.5-1일 | systemd 서비스와 준비 상태 검사, 제한 재시작, 운영 runbook | 브리지/Isaac 각각 장애와 재부팅 후 주문 비활성 대기 | 정비 + 재범 OS 적용 |
| P7-5 최종 비교 | 1일 | 부하/지연/메모리/복구 protocol과 run·리뷰, 현행 셋업·계약 갱신 | 고정 protocol 통과, reviewer 판정, 롤백 재현 | 재범 + 각 레인 |

각 단계는 브랜치·PR로 제출하고 앞 단계 증거가 있어야 다음 단계에 들어간다.
OS 권한이 필요한 설정은 기존 observer 규칙대로 재범이 적용하고 마스터에서는 지정 배포의 관측만 한다.
최종 배포 태그 번호는 검증 후 정한다. 계획 문서만으로 신규 릴리즈나 장비 설정을 만들지 않는다.

## 7. 옵션 B — 자원·자동 복구 설계

### 자원 예산

Master 01은 runtime slice와 build slice를 분리한다.
빌드 slice 전체에 CPU 총량·MemoryHigh·MemoryMax·TasksMax를 두고, 그 아래 사용자별 작업을 둔다.
CPU 예산은 온라인 논리 CPU 수 N에 대해 총 70%를 시험한다면 CPUQuota = 70 × N%라는 뜻이다.
실제 N, runtime 예약량, I/O 경합을 측정해 값을 정하며 네 사용자에게 각각 총 RAM 75%를 주지 않는다.
colcon 병렬도와 컴파일러 내부 병렬도를 함께 제한한다. 리소스 제한은 빌드 성공 보장이 아니다.

Master 02는 우리 서비스의 동시 인스턴스 1개를 보장한다.
다른 사용자 프로세스를 강제 종료하지 않는다. 서비스 소유권이 충돌하면 기동을 거부하고 슬롯을 조정한다.
RAM·VRAM·swap I/O·GPU 온도/클럭을 같이 기록한다.
기동 때의 셰이더 캐시 증가와 반복 실행 누수를 구분하며, 16GB급 VRAM에서 60 FPS를 사전 보장하지 않는다.

### 부팅·장애 복구

- BIOS 전원 복구는 장비 지원·사용 정책과 현장 복구 가능성을 확인한 뒤 계획된 정비 시간에 시험한다.
- 로컬 네트워크/시간 동기화 → Tailscale peer 확인과 Docker/GPU 준비 → 브리지 → Isaac 로드 →
  /clock·센서·TF·adapter 준비 → Master 01 제어의 **주문 비활성 대기** 순서다.
- systemd After=는 시작 순서일 뿐 원격 peer/씬 준비 완료가 아니다. 각 readiness 검사와 제한 시간을 둔다.
- Docker restart 정책과 systemd 중 하나만 재시작 소유자로 정한다. 무한 재시작을 금지하고 횟수 제한 뒤 실패 상태로 남긴다.
- 중지 시 주문 수락 차단 → 동작 취소/로컬 정지 확인 → 로그 flush → 정상 SIGINT → 제한 시간 뒤 해당 서비스만 정리한다.
- 재부팅·Isaac 재시작은 과거 주문 자동 재생을 뜻하지 않는다. /clock 재시작과 새 세션·epoch 정합을 확인하고
  이전 명령·goal 결과를 거부한 뒤 운영자가 새 실행을 시작한다.
- 자동 정리는 보존 기간이 지난 로그 등 확인된 대상만 한다. 실행 중 worktree, USD·shader cache, evidence 원본,
  컨테이너 볼륨, 타인 프로세스는 일괄 정리하지 않는다.

## 8. 옵션 B — 합격 기준 초안과 측정 방법

아래 수치는 **새 protocol에 넣을 제안**이며 기존 acceptance 기준을 바꾸지 않는다.
P7-0 pilot에서 타당성을 확인하고 비교 실행 전에 동결한다. 결과를 본 뒤 합격선을 완화하지 않는다.

| 항목 | 제안 판정 | 측정 조건 |
| --- | --- | --- |
| 기능 | 승인된 전체 루프 3회 연속 완료, 매 회 리셋 포함; 중복 실행·오래된 결과 수락 0 | 동일 태그·씬·seed/주문 풀, 기준/분리/브리지 조건별 실행 |
| 인터랙티브 관측 | ROS CLI 그래프/토픽 관측·action 취소·원격 정지 작동, WebRTC 1인 접속, SSH 재접속 후 세션 유지 | 관측자가 바뀌어도 제어 소유자는 1명 |
| 시간·TF | /clock 발행자 1개, late-join tf_static 정상, 계약상 epoch/reset 규칙 준수 | 물리 시간과 전송 시간 측정을 분리 |
| 빌드 간섭 | 허용된 동시 빌드 부하에서 Master 02 RTF 중앙값 저하 5% 이내, step 처리시간 p95 증가 10% 이내; 기능 회귀 0 | 동일 최종 구성의 무빌드 조건과 30분씩 비교. 개발자 최대 4명 부하, 실제 동시 빌드 수/병렬도 기록 |
| 전체 성능 | 분리 구성 RTF 중앙값이 기존 기준의 95% 이상, 기존 시나리오 시간 제한 충족 | 렌더 FPS·physics step rate·RTF 각각 기록. 60 FPS는 고정 렌더 조건의 추가 목표 |
| 명령·상태 전송 | 지정 소형 토픽 단방향 지연 p95 ≤ 15ms, p99도 보고 | OS wall clock 동기화 오차 상한 ≤ 1ms 확인. sender/receiver 계측. 최소 10,000표본 또는 30분 중 긴 쪽 |
| 센서 전송 | 토픽별 전달률 ≥ 99%, 수신 age p95 ≤ 발행 주기 2배를 초안으로 검토 | 해상도·바이트/메시지·Hz·QoS·CPU 코덱 부하 기록. 센서 15ms는 별도 도전 목표이며 일괄 합격선 아님 |
| 장기 안정성 | warm-up 뒤 120분, crash/OOM/드라이버 Xid 0; VRAM은 사전 고정 상한 이내, 동일 주기 말 점유 증가가 전체 VRAM의 5% 이내 | warm-up 종료 규칙·해당 씬 VRAM 상한은 pilot에서 결정. 주기별 RAM/VRAM 추세도 리뷰 |
| 단절·재접속 | 연결 단절 10초 주입 3회, 로컬 watchdog의 계약 기한 내 정지·명령 만료, 재연결 뒤 이전 명령 실행 0 | watchdog 기한이 미정이면 protocol 동결 불가. 임무 재개 전 상태 재동기화 |
| 재시작·복구 | 브리지 재시작·Isaac 재시작·호스트 재부팅 각 1회, 각 readiness 제한 내 비활성 대기 복구, 주문 자동 재생 0 | warm/cold 기동 제한은 P7-0에서 기록 후 고정. 로그/태그/자산 hash 보존 |

센서 age는 시뮬레이션 stamp와 OS wall clock을 그대로 빼서 구하지 않는다.
전송 구간용 별도 송수신 timestamp와 시계 오차를 기록한다. 동기화가 불충분하면 RTT만 보고하며 RTT/2를 실측 단방향 지연으로 표시하지 않는다.
ros2 topic hz·bw만으로 전송 지연이나 손실을 입증하지 않는다. sender 발행 수/식별자와 수신 수를 함께 기록한다.
best-effort 센서의 손실과 주문 명령의 멱등성·유일 종료 판정은 별개다.

고정할 정보: 태그/SHA, OS·드라이버·Isaac build/image digest, 브리지 버전·설정 hash, DDS/RMW/domain,
실제 route/direct/relay, 씬·에셋·모델 hash, 해상도·rate·QoS, 빌드 부하, 원본 위치·hash.
원본은 외부에 보존하고 protocol/run/review는 저장소 evidence 규칙을 따른다. 실패·중단도 분모에 포함한다.

## 9. 공통 롤백과 남은 확인

실패 시 주문 수락 차단과 로컬 정지를 먼저 확인한다.
해당 단계의 서비스만 중지하고 **P7 직전 배포 기록에 적힌 실제 호스트 배치·태그·DDS 설정**으로 돌아간다.
기존 표가 master01=Isaac이라고 해서 실제 검증된 master02 개발 실행을 덮어쓰지 않는다.
프로필 전환 때 두 DDS 경로나 두 /clock 발행자가 동시에 활성화되지 않도록 확인한다.
복구 후 기준 루프 1회와 run 저장을 확인한다.

옵션 A는 실제 기준 배치·반복 실행·수동 복구의 증거를 확인해야 한다.
옵션 B에서 추가로 모르는 것: Master 01 자원 여유, 두 NIC 협상 속도, 후속 장비 사용 기간,
Tailscale direct 경로의 안정성, 선정 브리지 버전의 Fast DDS/Isaac 5.1 상호운용,
현재 standalone streaming 초기화, 실제 씬의 VRAM/RTF, 로컬 watchdog의 구현·검증 상태.
B의 추가 항목은 P7-0/2에서 증거로 닫는다. A 완료 판정에 B 전용 미확인 항목을 끼워 넣지 않는다. 현재 문서 작업에서는 장비 실행·설정 변경·성능 검증을 하지 않았다.

## 10. 공식 근거

확인일: 2026-09-18. Isaac은 프로젝트 버전 5.1 문서 기준이다.
그 외 현재 문서는 설계 근거이며 설치할 정확한 버전의 검증을 대신하지 않는다.

- [S1 Ray Actors](https://docs.ray.io/en/latest/ray-core/actors.html): stateful actor 실행 모델.
- [S2 Eclipse Zenoh ROS2DDS](https://github.com/eclipse-zenoh/zenoh-plugin-ros2dds): ROS 그래프·서비스·액션 지원, Cyclone DDS 기반과 중복 DDS 경로 방지.
- [S3 NVIDIA nvidia-smi](https://docs.nvidia.com/deploy/nvidia-smi/index.html): compute/persistence mode 의미와 지원 제약.
- [S4 Isaac Sim 5.1 Livestream Clients](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/manual_livestream_clients.html): 실행 방식·클라이언트·접속 수·포트.
- [S5 Isaac Sim 5.1 Container Installation](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_container.html): 이미지·캐시·data 마운트와 준비 로그.
- [S6 systemd resource control](https://manpages.ubuntu.com/manpages/noble/man5/systemd.resource-control.5.html): CPUQuota·MemoryHigh·MemoryMax 의미. Ubuntu 24.04 문서 기준이며 실제 설치 버전도 기록한다.
- [S7 Tailscale connection types](https://tailscale.com/docs/reference/connection-types): direct와 relay 경로.
