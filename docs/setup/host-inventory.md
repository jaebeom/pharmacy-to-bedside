# 장비 목록과 IP 배정

누가 어느 PC 를 쓰고 어느 주소인지의 **기준 표**. 다른 문서는 이 표를 가리킨다. 바뀌면 여기부터 고친다.

## 장비 6대, 케이블 4개

| 별칭 | 누구 | GitHub | 유선 IP | 유선 슬롯 | 하는 일 |
| --- | --- | --- | --- | --- | --- |
| `master01` (마스터 1, `IsaacSim14`) | 공용 | 없음 | `10.10.0.1` | 포트 1 상시 | Isaac Sim 과 스택 전부(한 대 기본) |
| `master02` (마스터 2, `IsaacSim07`) | 공용 | 없음 | `10.10.0.2` | 포트 2 상시 | Isaac Sim 과 스택 전부(한 대 기본) |
| `dev01` | 임재범 | [@jaebeom](https://github.com/jaebeom) | `10.10.0.11` | 포트 3·4 교대 | 개발 |
| `dev02` | 전제환 | [@JeonJehwan](https://github.com/JeonJehwan) | `10.10.0.12` | 포트 3·4 교대 | 개발 |
| `dev03` | 이태규 | [@Taegyu-Lee1117](https://github.com/Taegyu-Lee1117) | `10.10.0.13` | 포트 3·4 교대 | 개발 |
| `dev04` | 박세준 | [@parksejun12](https://github.com/parksejun12) | `10.10.0.14` | 포트 3·4 교대 | 개발 |

<img width="672" height="422" alt="image" src="https://github.com/user-attachments/assets/bc517f1a-0bfd-46ae-a2b8-e24af85ad3be" />

- 스위치: TP-Link TL-SG105S-M2 (5포트, 2.5G). 케이블 4개. 마스터가 2개를 상시 점유하므로 **개인 노트북은 동시에 2대**.
- Tailscale: 6대 모두 연결. 주소는 `100.x.x.x` 로 자동 배정되며 유선 IP 와 무관하다. `tailscale status` 로 확인.
- 별칭(`master01`, `dev01`)은 실행 기록(`evidence/runs/`)에서 장비를 가리키는 ID 다. 사람 이름 대신 쓴다.
- GitHub handle 은 PR 리뷰 요청과 이슈 배정에 쓴다.
- 전화번호와 개인 이메일은 저장소에 두지 않는다. 팀 Notion 페이지에 있다.

## 주소는 케이블이 아니라 PC 에 붙는다

케이블은 4개지만 주소는 6개를 다 예약한다. 두 대가 같은 IP 로 동시에 붙으면 ARP 충돌로 둘 다 끊기기 때문에
주소를 나눠 쓰지 않는다. 케이블만 교대한다.

9/14 까지는 개인 노트북이 `.3`(이태규/박세준), `.4`(임재범/전제환)를 둘씩 나눠 썼다.
**아직 `.3`/`.4` 로 설정된 PC 는 위 표의 자기 주소로 바꾼다.** 절차는 [유선망 문서 1번](ros2-wired-network.md#1-고정-ip-설정).

## 마스터 두 대 요약 (2026-09-30)

값마다 근거가 따로 있다. 근거가 없는 칸은 "미확인"이다.

| 항목 | `master01` | `master02` | 근거 |
| --- | --- | --- | --- |
| 호스트 이름 | `IsaacSim14` | `IsaacSim07` | 아래 사양 표 |
| GPU | RTX 5080 Laptop, 16303 MiB | RTX 5080 Laptop, 16303 MiB | 아래 사양 표 |
| GPU 전력 상한 | 80 W | 80 W | 다음 줄 |
| 전력 상한 관측 | 9/27 13:43 KST 댓글은 Current Power Limit 15 W(Default 80 W)를 적었다. 1분 뒤 댓글의 조회는 80 W 였다. 왜 15 W 였는지, 언제 돌아왔는지는 모른다 | `nvidia-smi -pl 175` 는 노트북 GPU 라 지원되지 않는다 | master01: #240 5852701923·5852708824. master02: [병원 전 구간 성능](../analysis/hospital-perf-0923.md) |
| Isaac Sim | 5.1.0(`5.1.0-rc.19+release.26219`) | 5.1.0(`5.1.0-rc.19+release.26219`) | 아래 사양 표 |
| 하는 일 | stage·arm·nav·stack·web 을 한 대에서 띄운다 | stage·arm·nav·stack·web 을 한 대에서 띄운다 | [ADR 0005](../adr/0005-deployment-single-master-default.md)(proposed), `tools/demo_v2.sh` |
| 관측 | 관측 에이전트 하나. 9/25 에는 다른 코딩 도구의 observer 도 있었다 | 관측 에이전트 하나. 9/25 에는 다른 코딩 도구의 observer 도 있었다 | #240 5833150211·5833230900 |
| `ROS_DOMAIN_ID` | 회차마다 `P3_DOMAIN` 으로 준다 | 회차마다 `P3_DOMAIN` 으로 준다 | [도메인 규칙](ros2-wired-network.md#도메인-규칙) |
| OS·드라이버 재확인 | 9/20 뒤 미확인 | 9/17 뒤 미확인 | 아래 사양 표의 확인일 |

## 첫날에 채울 것

각 PC 에서 아래를 실행해 결과를 이 표 아래에 붙인다. 실측하지 않은 칸은 "미확인"으로 둔다.

| 별칭 | OS / 커널 | CPU / RAM | GPU / VRAM / 드라이버 | Isaac | ROS·RMW | 확인일 |
| --- | --- | --- | --- | --- | --- | --- |
| `master01` (`IsaacSim14`) | Ubuntu 24.04.4 / 6.14.0-27-generic | 24 코어 / 62G | RTX 5080 Laptop / 16303 MiB / 580.173.02 | 5.1.0-rc.19+release.26219.9c81211b | Jazzy(`/opt/ros/jazzy`) / `rmw_fastrtps_cpp` | 2026-09-20 |
| `master02` (`IsaacSim07`) | Ubuntu 24.04.4 / 6.14.0-27 | 24 코어 / 62G / NVMe 937G | RTX 5080 Laptop / 16303 MiB / 580.173.02 | 5.1.0-rc.19+release.26219 (홈 디렉토리 `isaacsim/VERSION`) | Jazzy / `rmw_fastrtps_cpp` | 2026-09-17 |
| `dev01` (`romanty-LOQ-15AHP10`, Lenovo LOQ 15AHP10) | Ubuntu 26.04.1 LTS / 커널 미확인 | AMD Ryzen 7 250 / 16 GiB / 512 GB | Radeon 780M 내장 (NVIDIA 없음) | 해당 없음 | 미확인 — **26.04 라 Jazzy 설치 가능 여부 확인 필요** | 2026-09-15 |
| `dev02` | 미확인 | 미확인 | 미확인 | 미확인 | 미확인 | 미확인 |
| `dev03` | 미확인 | 미확인 | 미확인 | 미확인 | 미확인 | 미확인 |
| `dev04` | 미확인 | 미확인 | 미확인 | 미확인 | 미확인 | 미확인 |

```bash
hostnamectl; uname -r
lscpu | grep 'Model name'; free -h | head -2
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
ip -br addr; sysctl net.ipv4.ip_local_port_range
printenv ROS_DISTRO RMW_IMPLEMENTATION ROS_DOMAIN_ID
tailscale version
```

GPU 가 없는 노트북은 `nvidia-smi` 가 실패하는 게 정상이다. 그대로 "없음"이라고 적는다.
`dev01` 은 설정 → 정보 화면 기준이며 커널·ROS 는 위 명령으로 다시 채운다.
마스터는 Ubuntu 24.04 인데 노트북이 26.04 면 ROS 2 Jazzy 공식 패키지(24.04 용)가 안 잡힐 수 있다. `ls /opt/ros` 로 확인하고 없으면 24.04 Docker 또는 듀얼부팅을 검토한다.
로그인 이메일, 키, 토큰은 표에 넣지 않는다.

아래 절들은 그날의 관측 기록이다. 지금 값과 다를 수 있다. 지금 요약은 [마스터 두 대 요약](#마스터-두-대-요약-2026-09-30)이다.

## 마스터 9/17 실측

위 표의 `master02` 줄과, 아래 `master01` 9/17 칸은 그날 각 마스터에서 확인한 값이다.
`master01` 표 줄의 지금 값은 9/20 재확인이다(아래 「`master01` 9/20 재확인」).
이 문서를 쓸 때 마스터에서 직접 확인하지 않았다. "미확인" 칸은 그날 명령을 돌리지 않은 것이다.

두 대 공통:

| 항목 | 값 |
| --- | --- |
| `ROS_DOMAIN_ID` | `115` |
| `RMW_IMPLEMENTATION` | `rmw_fastrtps_cpp` |
| `FASTRTPS_DEFAULT_PROFILES_FILE` | 홈 디렉토리 `.ros/fastdds_whitelist.xml`, `.bashrc` 에서 설정 |
| 방화벽 | ufw `ENABLED=no` |

`master01`:

| 항목 | 값 |
| --- | --- |
| 유선 | `10.10.0.1`, 인터페이스 `enp131s0` |
| Isaac (9/17) | 빌드 번호는 그날 미확인. GUI 창 제목은 Isaac Sim Full 5.1.0 |

`master02`:

| 항목 | 값 |
| --- | --- |
| 유선 | `10.10.0.2` |
| tmux | 3.4. 9/17 재범 설치 |
| ultralytics·`nvcc` | 둘 다 없음(9/17). 설치 요청은 9/18 스크럼 안건 |
| unattended-upgrades | 활성. `Automatic-Reboot` 줄은 모두 주석이다 |

`dev02`-`dev04` 는 아직 비어 있다.

## `master01` 9/20 재확인

이 문서를 쓸 때 master01 에서 직접 확인하지 않았다.
값은 master01 에서 읽기·조회 명령으로 얻은 결과다.
출처는 슬롯 이슈 #240 댓글과 전달받은 master01 보고다. 08:53 값은 master01 에서 읽기 명령으로 보냈다.

| 항목 | 값 |
| --- | --- |
| 커널 | `6.14.0-27-generic` |
| CPU / RAM | 24 코어 / 62G |
| GPU / VRAM / 드라이버 | RTX 5080 Laptop / 16303 MiB / 580.173.02 |
| Isaac | 5.1.0-rc.19+release.26219.9c81211b |
| ROS 2 | Jazzy, `/opt/ros/jazzy` |
| tmux | **없음**(9/20 02시). 설치는 재범 결정 대기. 뒤 관측: 같은 날 03:11 에 `demo_v2 up` 이 돌았다(#240 5744270086). 설치 원문은 #240 에서 찾지 못했다 |
| `tools/demo_v2.sh up` | 9/20 02시에는 tmux 가 없어 이 스크립트로 띄우지 못했다. 03:11 부터 띄웠다(위 줄) |
| release 워크트리 | 08:53 에 셋이다: `419b20b`, `2c68b73`, `13a2dfd` |
| 9/20 02시 워크트리 | 없었다. 그날 처음 만들었다([배포 runbook](../runbooks/deployment.md)) |
| 유선 밖 인터페이스 | `wlp128s20f3` `172.18.0.61/24`, `tailscale0` `100.x.x.x`. Tailscale 1.102.4 |
| `net.ipv4.ip_local_port_range` | `32768 60999` |
| `ROS_DISTRO` | 비대화형 셸에서 비어 있다. `/opt/ros/jazzy` 는 있다. 실행 영향은 미확인 |
| ufw | 미확인. `sudo -n ufw status` 가 비밀번호를 요구해 돌리지 않았다(sudo 는 재범). 위 두 대 공통 표의 `ENABLED=no` 는 9/17 값이다 |
| 개발 클론 | **이 클론에서 빌드·실행하면 옛 코드다.** `main` `462b143`, `origin/main` 보다 210 커밋 뒤. fetch 만 했다 |
| 개발 클론 경로 | `/home/rokey/Dev/cobot3_ws/ROKEY_P3_A3` |
| 저장소에 없는 파일 | 개발 클론에 untracked 병원 씬 파일과 `src/m0609/` 가 있다(아래 목록). 처리 방침은 해당 레인(세준·Simu) 결정 |

untracked 목록(08:53): `sim/Collected_hospital_custome/`, `sim/standalone/hospital_main.py`·`README_hospital.md`·`conveyor_config.example.json`·`test_conveyor_routes.py`, `sim/standalone/p3sim/hospital_assets.py`·`hospital_scene.py`·`sorter.py`, `src/m0609/`.

가설(master01 관측): 병원 씬 작업의 잔여물이다. 확인하지 않았다.

## 삼성 PC (웹, 9/17)

프론트·백엔드 작업에 쓰는 PC 다. 값은 전달받은 보고이고, 이 문서를 쓸 때 확인하지 않았다.
위 장비 표의 별칭·유선 IP 는 아직 없다.

| 항목 | 값 |
| --- | --- |
| 호스트명 | `rokey-550XBE-350XBE` |
| Python | 3.12.3 |
| ROS 2 | Jazzy 있음 |
| GitHub | 이 PC 의 키가 등록되지 않았다. 재범 등록 대기 |

## `master02` 공유 사용 관측 (9/17)

- 관측(전달받음, 문서 미확인): 16:11-16:29 에 우리 팀이 띄우지 않은 M0617 Isaac 프로세스가 몇 분 간격으로 다시 떴다.
- 추정: 같은 PC 를 쓰는 다른 사용자다. 누구인지는 확인하지 않았다.
- 판단: 우리 스택을 띄우기 전에 다른 Isaac 이 떠 있는지 본다. 떠 있으면 띄우지 않는다([보충 장면 runbook](../runbooks/master02-m0609-refill-stage.md)). 시간 창을 나눌지는 재범 결정 대기다.

## `master02` 9/20 인수인계

9/20 에 한 번씩 헛디딘 뒤 확정한 값들이다. 다시 쓰는 사람이 같은 함정을 반복하지 않도록 남긴다. 모두 그날 관측이고, 바뀔 수 있는 값이다.

**전원 일정 — 22:00 종료 / 03:00 기상.** root crontab 한 줄(`/usr/sbin/rtcwake -m off -s 18000`, 매일 22:00:01)이 원인이다. RTC 알람을 5시간 뒤로 걸고 끄므로 **종료와 기상이 같은 한 줄에서 나온다. BIOS wake 가 아니다.**

**이미 찾아본 곳**: `/etc/crontab`·`/etc/cron.d/*`·사용자 crontab·systemd timer 에는 **없다**. `/var/spool/cron/crontabs/` 는 권한이 없어 못 읽는다. 그래서 확인은 `journalctl | grep "CMD (/usr/sbin/rtcwake"` 로 한다.

끄는 것은 재범 몫이다(sudo). 9/20 21:30 시점 아직 안 꺼졌다. 그 뒤 상태는 미확인이다.

**자동 로그인 — 켜져 있고 값이 `master01` 과 다르다.** `/etc/gdm3/custom.conf` 의 **`[daemon]` 절 6·7행**에 있다(sha256 `8e1ebbe7…5bda`, 600 B, 10:23:42).

- `>>` 로 파일 끝에 덧붙이면 마지막 절이 `[debug]` 라 **거기 소속으로 읽혀 무효다.** 9/20 에 이것으로 두 번 실패했다.
- 창 모드로 Isaac 을 돌릴 때 쓰는 값은 `DISPLAY=:0`, `XAUTHORITY=/run/user/1000/gdm/Xauthority` 다. **`$HOME/.Xauthority` 는 생기지 않는다.**
- **`master01` 은 `:1` 이고 자동 로그인이 아니라 사람이 로그인한 세션이 남아 있는 것이다.** runbook 값을 기계 간에 돌려 쓰지 않는다.
- 데스크톱이 올라온 뒤 유휴 GPU 부하가 0 % → 25-30 %(VRAM 약 190 MiB)로 상시 올라간다. **10:23 이전 회차와 이후 회차의 자원 표는 기준선이 다르다.**

**창 모드 녹화 — `ximagesrc` 에 `remote=true` 가 필수다.** 없으면 MIT-SHM(`X_ShmGetImage BadMatch`)으로 실패하고 **0 바이트 mp4 가 만들어진다**(`use-damage=0` 만으로는 안 된다).

**파이프라인이 죽어도 파일은 생기므로 파일 존재로 성공을 판단하지 않는다.** 9/20 12d-v 가 이 함정에 빠져 그날 `master02` 회차 영상이 0개가 됐다([실습12](../practice/practice-12.md)).

확인은 녹화 5초 뒤 `[ -s "$OUT" ]`, 종료 뒤 `cv2.CAP_PROP_FRAME_COUNT` 와 `gst.log` 의 `X Error|BadMatch|ERROR` 로 한다. **`ffprobe` 는 없고 `cv2` 4.6.0 은 있다.** 예비로 `simplescreenrecorder` 가 있다(GUI 앱이라 무인 실행에는 설정이 필요하다).

**워크트리·산출물.** 실행은 개발 클론이 아니라 `$HOME/Dev/cobot3_ws/release/<날짜>-<sha>/` 에서 한다(9/20 에 `20260920-644ec0a`·`20260920-eba5351`·`20260920-1585a91` 셋). 회차 산출물은 `$HOME/markle_tmp/m2-*/`, sha256 인벤토리는 `$HOME/markle_tmp/inventory-20260920.txt` 다. **`$HOME/test_amr/` 는 다른 사람의 Nav2 작업이고 저장소 밖이다(9/20 기준 미커밋). 건드리지 않는다.**

**도메인.** `master01`=117 / `master02`=118 은 **재범 결정 33**이다(9/20. [도메인 규칙](ros2-wired-network.md#도메인-규칙)). 9/21 이후 쓰인 값도 그 절에 있다.

기동 전 `ROS_DOMAIN_ID=118 ros2 topic info /clock` 의 발행자가 0 이어야 한다. Isaac 없이 남은 ROS 노드는 `/clock` 으로 못 잡으니 **`ros2 node list` 로 118 의 남의 노드도 본다.**

**주의**: `$HOME/test_amr/tools/start_isaac_domain118.sh` 도 118 을 쓴다. **네임스페이스가 없어**(`/scan`·`/odom`·`/cmd_vel` 전역) 같이 돌면 토픽이 섞인다.

**118 을 함께 쓰는 곳들을 어떻게 가를지는 결정 43 대기다.**

(**이 값을 "배정" 이라고 적은 옛 표현은 틀렸다.** 지시문들이 결정 번호 없이 "118 로" 라고만 말해 그렇게 옮겨 적혔다. **같은 저장소의 두 문서가 어긋나면 안 되므로** 결정 번호로 바로잡는다.)

**관측 에이전트는 자동 복귀하지 않는다.** `$HOME/.config/autostart/markle2.desktop` 이 9/20 에 제거됐다. 부팅해도 에이전트가 뜨지 않으므로 **필요하면 사람이 띄운다.** 남은 `screen-off.desktop` 은 `DISPLAY=:1` 을 써서 이미 동작하지 않는다(실제는 `:0`).
