# ROS 2 유선 폐쇄망 구성 (스위치 + FastDDS 화이트리스트)

교육 자료 "GPU-개인PC—ROS 네트워크 구성 및 설정"을 실제 환경에 맞게 정정한 버전.
왜 이렇게 하는지는 [부록](#부록-이-설정을-왜-하는가)에, 전체 그림은 [우리 셋업](README.md)에 있다.

## 전제

| 항목 | 값 |
| --- | --- |
| OS / ROS 2 | Ubuntu 24.04 / Jazzy (Isaac Sim 5.1.0 이 요구하는 조합. Humble 아님) |
| RMW | `rmw_fastrtps_cpp` (Jazzy 기본) |
| ROS_DOMAIN_ID | 우리 조 배정 `115`-`121` 중 **115** (팀 전원 동일). 처음 값이다. 마스터 회차는 `P3_DOMAIN` 으로 따로 준다([도메인 규칙](#도메인-규칙)) |
| 유선 대역 | `10.10.0.0/24` (= 넷마스크 `255.255.255.0`). 스위치 폐쇄망 |
| 무선 | rokey3 AP. 인터넷 전용, ROS 트래픽 없음 |
| 스위치 | TP-Link TL-SG105S-M2 (5포트 2.5G), 케이블 4개 |

원본 자료의 `WSL2 humble` 표기는 오기다. WSL2 는 NAT 뒤라 고정 IP 를 못 받고, Humble 은 Isaac 5.1 과 맞지 않는다.

## IP 배정

**사람마다 자기 주소가 있다.** 케이블은 4개라 개인 노트북은 동시에 2대만 붙지만, 주소는 나눠 쓰지 않는다.

| 장비 | IP | 누구 |
| --- | --- | --- |
| 마스터 1 (`master01`) | `10.10.0.1` | 공용 |
| 마스터 2 (`master02`) | `10.10.0.2` | 공용 |
| `dev01` | `10.10.0.11` | 임재범 |
| `dev02` | `10.10.0.12` | 전제환 |
| `dev03` | `10.10.0.13` | 이태규 |
| `dev04` | `10.10.0.14` | 박세준 |

배정표의 기준 위치는 [장비 목록](host-inventory.md)이다. 바뀌면 거기를 고친다.

같은 IP 가 둘이면 ARP 충돌로 **양쪽 다 끊긴다.** IP 는 노트북 설정에 들어가는 값이지 케이블에 붙어 있지 않아서,
케이블을 나눠 쓰는 것만으로는 충돌이 막히지 않는다. 그래서 한 사람에 한 주소다.
(9/14 까지는 `.3`/`.4` 를 둘씩 나눠 썼다. 아직 `.3`/`.4` 인 사람은 위 표대로 바꾼다.)

Netmask 는 전부 `255.255.255.0`, Gateway 는 **비워둔다**. 인터넷은 무선으로 나간다.

## 1. 고정 IP 설정

1. LAN 케이블을 PC 와 스위치에 연결한다.
2. Settings → Network → Wired 의 톱니바퀴 아이콘 클릭.
3. IPv4 탭에서 **Manual** 선택.
4. Address 에 자기 주소, Netmask 에 `255.255.255.0`. Gateway 와 DNS 는 비워둔다.
5. **"Use this connection only for resources on its network" 를 체크한다.**
   체크하지 않으면 유선이 기본 경로를 잡아채 무선 인터넷이 끊긴다.
6. Apply 후, 유선 연결 토글을 OFF → ON 하여 재적용한다.

확인:

```bash
ip -br addr             # enp*  UP  10.10.0.xx/24 가 보여야 한다
ip route                # default 가 wlo* (무선) 쪽이어야 한다
```

## 2. 유·무선 분리 검증

둘 다 성공해야 한다.

```bash
# (a) 폐쇄망 — 마스터 1 로 ping
ping -c 3 10.10.0.1

# (b) 인터넷 — 무선으로 나가는지
ping -c 3 8.8.8.8
curl -I https://github.com
```

(a) 가 무응답이면 케이블·주소·상대 PC 전원 중 하나다. (b) 가 안 되면 1번의 5단계를 다시 본다.

## 3. 방화벽

ping 이 되어도 방화벽이 DDS 의 UDP 를 막으면 토픽만 안 온다.

```bash
sudo ufw status
```

`Status: inactive` 면 끝. `active` 면 유선 NIC 와 우리 대역만 열어준다 (`ufw disable` 로 통째로 끄지 않는다).

```bash
sudo ufw allow in on enp4s0 from 10.10.0.0/24 proto udp   # enp4s0 은 ip -br addr 에서 본 자기 유선 NIC 이름
sudo ufw status numbered
```

## 4. ephemeral 포트 범위 조정

Linux 기본 ephemeral 포트 범위는 `32768–60999` 다. DDS 는 도메인 ID `D` 에 대해 `7400 + 250×D` 부터 포트를 쓰므로
도메인 115 는 `36150`부터, 121 은 `37650`부터이고 전부 이 구간과 겹친다.
다른 프로그램이 그 포트를 먼저 잡으면 **그 PC 만 간헐적으로** 디스커버리에 실패한다.

| 용도 | 계산식 | D=115, P=0 |
| --- | --- | --- |
| discovery multicast | `7400 + 250×D` | `36150` |
| user multicast | `7401 + 250×D` | `36151` |
| discovery unicast | `7410 + 250×D + 2×P` | `36160` |
| user unicast | `7411 + 250×D + 2×P` | `36161` |

`P` 는 같은 PC 의 참가자(프로세스) 번호다. 도메인 121 의 P=119 까지 써도 `37899` 이므로 하한 40000 이면 충분하다.

```bash
echo 'net.ipv4.ip_local_port_range = 40000 60999' | sudo tee /etc/sysctl.d/99-ros-domain.conf
sudo sysctl --system
sysctl net.ipv4.ip_local_port_range   # 40000  60999
```

**스위치에 붙는 전 PC 에 동일하게 적용한다.**
([ROS 2 Domain ID 문서](https://docs.ros.org/en/jazzy/Concepts/Intermediate/About-Domain-ID.html))

## 5. FastDDS 유선 전용 설정

ROS 2 토픽이 무선이나 가상 인터페이스(Tailscale, Docker)로 새지 않게 인터페이스를 제한한다.
`ip -br addr` 에 `tailscale0`, `docker0` 가 보인다면 이 설정이 특히 중요하다 —
화이트리스트가 없으면 참가자가 그 주소들까지 광고해서 상대가 닿지 않는 경로로 연결을 시도한다.

화이트리스트는 **자기 PC 의 로컬 인터페이스** 주소만 매칭한다. 없는 주소는 무시되므로
아래 파일을 **전 PC 에 그대로 복사**해 쓰면 된다.

```bash
mkdir -p ~/.ros
cat > ~/.ros/fastdds_whitelist.xml << 'EOF_XML'
<?xml version="1.0" encoding="UTF-8" ?>
<dds xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
    <profiles>
        <transport_descriptors>
            <transport_descriptor>
                <transport_id>wired_udp</transport_id>
                <type>UDPv4</type>
                <interfaceWhiteList>
                    <address>127.0.0.1</address>
                    <address>10.10.0.1</address>
                    <address>10.10.0.2</address>
                    <address>10.10.0.11</address>
                    <address>10.10.0.12</address>
                    <address>10.10.0.13</address>
                    <address>10.10.0.14</address>
                </interfaceWhiteList>
            </transport_descriptor>
        </transport_descriptors>
        <participant profile_name="wired_only" is_default_profile="true">
            <rtps>
                <userTransports>
                    <transport_id>wired_udp</transport_id>
                </userTransports>
                <useBuiltinTransports>false</useBuiltinTransports>
            </rtps>
        </participant>
    </profiles>
</dds>
EOF_XML
ls -l ~/.ros/fastdds_whitelist.xml
```

`127.0.0.1` 은 반드시 포함한다. `useBuiltinTransports=false` 로 공유메모리 전송이 꺼지므로
같은 PC 안의 노드 간 통신이 localhost UDP 로 이루어진다.

> `interfaceWhiteList` 는 Fast DDS 2.14(Jazzy)에서 동작하지만 deprecated 이며,
> 향후 `<interfaces><allowlist>` 형식으로 옮겨야 한다.
> ([Fast DDS 2.14 문서](https://fast-dds.docs.eprosima.com/en/v2.14.5/fastdds/transport/whitelist.html))

## 6. 환경 변수 등록

`~/.bashrc` 에 직접 기록한다. 현재 셸에만 `export` 하면 새 터미널에서 전부 사라진다.

```bash
cat >> ~/.bashrc << 'EOF_RC'
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=115
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE=$HOME/.ros/fastdds_whitelist.xml
EOF_RC
source ~/.bashrc
```

확인 후 데몬 재시작:

```bash
printenv ROS_DISTRO ROS_DOMAIN_ID RMW_IMPLEMENTATION FASTRTPS_DEFAULT_PROFILES_FILE
ros2 daemon stop && ros2 daemon start
```

`export ROS_DISTRO=...` 는 넣지 않는다. `setup.bash` 가 알아서 넣는 값이라 수동 지정하면 소싱 순서에 따라 꼬인다.

**Isaac Sim 은 이 `~/.bashrc` 가 적용된 터미널에서 띄우지 않는다.** Isaac 5.1 은 내부 Python 3.11 을 쓰고
Jazzy 는 3.12 라서 섞이면 죽는다. Isaac 용 터미널은 [`sim/README.md`](../../sim/README.md) 대로 따로 연다.

마스터 회차를 `tools/demo_v2.sh` 로 띄우면 도메인은 `P3_DOMAIN` 값을 쓴다. 위 115 가 아니다([도메인 규칙](#도메인-규칙)).
프로필 파일은 `P3_FASTDDS_PROFILE`(기본 `~/.ros/fastdds_whitelist.xml`)이다.
스테이지에는 그 파일이 있으면 늘 넘긴다. 나머지 역할에는 두 PC 모드(`P3_PEER`)일 때만 넘긴다.

## 7. 통신 테스트

같은 PC 안에서 먼저 확인한다.

```bash
# 터미널 A
ros2 run demo_nodes_py talker

# 터미널 B
ros2 run demo_nodes_py listener
```

그다음 PC 간 확인 — 한 대에서 talker, 나머지에서 listener 를 띄운다.
`[INFO] I heard: [Hello World: N]` 이 출력되면 성공. (9/14 에 도메인 105 로 마스터 간 확인. 9/17 에 115 로 양방향 확인: [9/17 실측](#917-실측).)

노드가 보이는지 확인:

```bash
ros2 node list
ros2 topic list
ros2 topic echo /chatter
```

토픽이 되면 실제로 쓸 서비스·액션과 Isaac 의 `/clock` 수신도 같은 방식으로 확인한다.
토픽 성공이 DDS 전체의 성공은 아니다.

## 9/17 실측

마스터 두 대(`master01`, `master02`)에서 9/17 에 확인한 것이다.
이 문서를 쓸 때 마스터에서 직접 돌리지 않았다. 장비 사양은 [장비 목록](host-inventory.md#마스터-917-실측).

### 양방향 토픽

| 항목 | 값 |
| --- | --- |
| 도메인 | `115` |
| 시각 | 14:30-14:35 KST |
| `master01` → `master02` | `/chatter_m1` 7개 연속 수신(첫 수신 14:30:37) |
| `master02` → `master01` | `/chatter_m2` 5/5 수신 |
| 화이트리스트 유무 | 있을 때와 뺐을 때 결과 차이 없음 |
| `master02` 의 UDP bind | `10.10.0.2`, `127.0.0.1`, `239.255.0.1:36150` 뿐 |
| ping | 0.3-1.0 ms |

도메인 115 의 멀티캐스트 포트는 `7400 + 250 × 115 = 36150` 이다. 위 bind 목록의 `36150` 이 그것이다.

확인에는 한쪽에서 발행하고 다른 쪽에서 `ros2 topic echo` 로 받는 짝을 썼다.
`ros2 multicast send`·`receive` 는 기본 경로(무선)로 나가서 유선 확인이 되지 않는다.
토픽 이름은 PC 마다 다르게(`/chatter_m1`, `/chatter_m2`) 해서 어느 쪽이 보낸 것인지 구분한다. 9/17 에 쓴 발행 명령의 정확한 형태는 미확인이다. 예:

```bash
# 보내는 PC
ros2 topic pub -r 1 /chatter_m1 std_msgs/msg/String "{data: m1}"
# 받는 PC
ros2 topic echo /chatter_m1
```

### 마스터에 깔린 화이트리스트 파일

9/17 에 마스터에서 본 파일은 위 5번 파일과 주소가 다르다.

| 항목 | 마스터의 파일 |
| --- | --- |
| transport | `UDPv4`, `transport_id` `wired_udp` |
| `interfaceWhiteList` | `127.0.0.1`, `10.10.0.1`, `10.10.0.2`, `10.10.0.3`, `10.10.0.4` |
| `useBuiltinTransports` | `false` |

- `.3`·`.4` 는 9/14 까지 쓰던 옛 주소다.
- 노트북 주소 `10.10.0.11`-`10.10.0.14` 가 없다.
- 위 양방향 확인은 이 파일이 깔린 상태에서 됐다. 노트북이 붙었을 때의 영향은 확인하지 않았다.
- 5번 파일로 맞출지, 언제 맞출지는 **미결정**이다(9/18 스크럼 안건).

### 도메인 규칙

- **마스터에서 돌리는 실습·시연: `master01` 은 117, `master02` 는 118 이다(재범 결정 33, 9/20).**
  - 두 마스터가 같은 유선망에 있어 같은 값을 쓰면 서로 보인다. 9/20 09:27 에 `master01` 의 기동 전 확인이 "도메인 117 에 `/clock` 발행자 1" 로 멈췄다. `master02` 의 스테이지가 보인 것이다.
  - `selfdemo` 스테이지도 `/clock` 을 낸다. 씬만 띄운 것도 남의 실행에 보인다.
  - [9/21 시연 runbook](../runbooks/demo-0921-v2.md)의 실습 명령에 적힌 117 은 **그대로 둔다**(재범 지시). 그 문서는 실습 원문을 옮긴 것이다. 이 규칙대로면 `master02` 에서 돌릴 때는 118 이다.
- **웹 PC 는 119, 개인 실험은 120 이다(재범 결정 43, 9/21).**
  - 이것으로 실습·시연에 쓰는 네 자리가 다 정해졌다: `master01` 117 · `master02` 118 · 웹 PC 119 · 개인 120.
  - 그 전의 `115`(통합 실행 전용) 제안은 이 결정으로 대체한다.
- 9/17 에 `master01` 이 `116` 이었다가 `115` 로 바뀌었다.
- 마스터 실습·시연 값과 웹 PC·개인 실험 값은 정해졌다(위). **이 문서의 전제 표는 아직이다.**
- **9/21 이후 기록에 남은 값(관측).** 위 결정 33·43 을 바꾼다는 결정 원문은 찾지 못했다(미확인).
  - 9/21: master02 회차를 임시 도메인 121 로 돌렸다. 118 에 다른 사람의 Nav2 가 떠 있었다(#240 5755534953).
  - 9/23 오전: master02 병원 Nav2 회차가 121 이었다(#240 5787005979).
  - 9/23 저녁: master01 리하 회차1 이 131 이었다(#240 5794286637).
    두 PC 회차19 도 131 이었다(#240 5797973069).
  - 9/24: 리하 실습 계획이 두 마스터의 도메인을 131 로 적었다. 재범은 "계획 수립해서 바로 진행" 이라고 했다(#576 5808255601).
  - 9/27: acceptance 회차의 기동 줄에 `P3_DOMAIN=131` 이 있다(#240 5852183688).
  - 131 은 [전제](#전제) 표의 조 배정 범위(`115`-`121`) 밖이다.
- `tools/demo_v2.sh` 는 도메인을 필수 변수 `P3_DOMAIN` 으로 받는다. 기본값은 없다.
  머리 주석은 어느 값을 쓸지가 재범 결정이라고 적는다.
  스크립트는 역할마다 `ROS_DOMAIN_ID` 를 그 값으로 준다. 위 6번의 `.bashrc` 값 115 는 그 역할들에 쓰이지 않는다.

### Isaac 과 `/clock`

스텁을 띄우기 전에 `/clock` 발행자가 이미 있는지 본다.

```bash
ros2 topic info /clock -v
```

발행자가 있으면 스텁은 `publish_clock:=false` 로 띄운다. `/clock` 작성자는 하나여야 한다.

```bash
ros2 launch rokey_p3_bringup stub_loop.launch.py publish_clock:=false
```

Isaac 프로세스가 ROS 참가자인지는 그 프로세스의 UDP 소켓으로 본다. `<kit PID>` 는 Isaac(kit) 프로세스 번호다. 뒤의 쉼표는 다른 PID 가 앞자리로 걸리지 않게 붙인다.

```bash
ss -uanp | grep 'pid=<kit PID>,'
```

- 9/17 14:29 `master01` 에서는 0개였다(`master01` 관측). 그 시각 Isaac 은 ROS 참가자가 아니었다.
- 소켓이 없으면 Play 상태, ROS 2 bridge 확장이 켜졌는지, 저장된 그래프에 `/clock` 발행 노드가 있는지를 본다.
- PC 간에 Isaac `/clock` 이 안정적으로 오는지는 아직 **미확인**이다.

## 트러블슈팅

| 증상 | 원인 |
| --- | --- |
| ping 은 되는데 토픽이 안 옴 | `ROS_DOMAIN_ID` 불일치 / ufw 활성 / 화이트리스트 파일이 로드 안 됨 |
| 갑자기 양쪽 다 통신 끊김 | 같은 IP 를 두 대가 쓰고 있다 (IP 충돌). `.3`/`.4` 옛 설정이 남은 PC 가 있는지 확인 |
| Tailscale·Docker 켠 뒤로 안 됨 | 가상 인터페이스가 잡힌 상태. `echo $FASTRTPS_DEFAULT_PROFILES_FILE` 로 XML 이 실제로 로드됐는지 확인 |
| 아까는 됐는데 새 터미널에서 안 됨 | 환경 변수를 `~/.bashrc` 에 넣지 않음 |
| 간헐적으로 노드가 안 보임 | ephemeral 포트 충돌 (4번 적용) 또는 오래된 `ros2 daemon` (재시작) |
| 유선 연결 후 인터넷 끊김 | IPv4 에 Gateway 입력했거나 "only for resources on its network" 미체크 |
| Isaac 을 띄우면 이상하게 죽음 | ROS 를 source 한 터미널에서 띄웠다. 6번 마지막 문단 |
| `/opt/ros/jazzy/setup.bash: No such file` | 해당 PC 의 ROS 2 배포판이 다름. 전 PC Jazzy 여야 한다 |

---

## 부록: 이 설정을 왜 하는가

### 목적

여러 대의 PC 를 **하나의 ROS 2 시스템처럼** 동작하게 만드는 것이다.
Isaac Sim 을 돌리는 GPU PC 와 개인 노트북에서 띄운 노드가 같은 토픽을 주고받아야 하는데,
그러려면 모든 장비가 같은 네트워크 위에서 서로를 발견할 수 있어야 한다.
위 1-7번은 그 조건을 만드는 절차다.

### ROS 2 에는 마스터가 없다

ROS 1 은 `roscore` 가 중앙 등록소 역할을 해서, 모든 노드가 `ROS_MASTER_URI` 로 한 곳을 바라봤다.
ROS 2 는 그게 없다. 대신 DDS 가 **분산 디스커버리**를 한다 —
노드가 뜨면 네트워크에 "나 여기 있다"를 멀티캐스트로 뿌리고, 그걸 받은 다른 노드가 직접 연결을 맺는다.
(우리가 "마스터 PC" 라고 부르는 건 공용 GPU PC 라는 뜻이지 ROS 의 마스터가 아니다.)

여기서 두 가지가 따라 나온다.

- 설정 파일에 상대 PC 의 주소를 적을 곳이 없다. **같은 네트워크에 있고 도메인 ID 가 같으면 자동으로 붙는다.**
- 반대로, 격리해 주는 장치도 없다. 옆 조가 같은 망에 같은 도메인 ID 로 들어오면 그쪽 토픽이 그대로 섞인다.

`ROS_DOMAIN_ID` 가 조별로 배정되는 이유가 이것이다. 도메인 ID 는 DDS 가 쓰는 UDP 포트 번호를 결정하고
(`7400 + 250 × 도메인 ID` 부터), 번호가 다르면 애초에 서로의 패킷을 듣지 않는다.
**팀 내에서 한 명이라도 값이 다르면 그 사람만 아무것도 안 보인다.**

### 왜 굳이 유선인가

무선으로도 원리상 되지만, 실제로는 잘 깨진다.

- DDS 디스커버리는 멀티캐스트에 의존하는데, Wi-Fi 에서 멀티캐스트는 가장 낮은 전송률로 나가고 재전송이 없다.
  패킷이 조용히 사라져서 "노드가 떴다 사라졌다" 하는 증상이 나온다.
- 교육장 AP 는 클라이언트 간 통신을 막아두는 경우가 많다. 그러면 ping 도 안 된다.
- Isaac Sim 의 카메라·포인트클라우드 토픽은 수십에서 수백 Mbps 를 쉽게 넘긴다. 공용 AP 로는 감당이 안 되고,
  같은 AP 를 쓰는 다른 조까지 느려진다.

그래서 **ROS 트래픽은 유선 스위치, 인터넷은 무선**으로 역할을 나눈다.
스위치는 외부와 연결되지 않은 폐쇄망이라 다른 조 트래픽이 섞일 일도 없다.

### 각 단계가 막는 것

| 단계 | 없으면 생기는 일 |
| --- | --- |
| 고정 IP (`10.10.0.X/24`) | DHCP 서버가 없는 폐쇄망이라 주소를 못 받는다. 링크로컬(`169.254.x.x`)로 떨어져 서로 다른 대역이 된다 |
| Gateway 비우기 + "only for resources on its network" | 유선이 기본 경로를 가져가는데 그 너머에 인터넷이 없어서 웹·apt 가 전부 죽는다 |
| 사람마다 고유 IP | 같은 주소 두 대가 동시에 붙으면 ARP 충돌로 둘 다 끊긴다 |
| 방화벽 확인 | DDS 는 동적 UDP 포트를 쓴다. 방화벽이 인바운드를 막으면 ping 은 되는데 토픽만 안 온다 |
| ephemeral 포트 조정 | 도메인 115 의 포트(36150부터)를 다른 프로그램이 먼저 점유하면 그 PC 만 간헐적으로 디스커버리에 실패한다 |
| FastDDS 화이트리스트 | 참가자가 유선·무선 주소를 **둘 다** 광고한다. 상대가 닿지 않는 무선 주소로 연결을 시도하다 타임아웃을 기다려 디스커버리가 느려지거나 실패한다 |
| `~/.bashrc` 에 기록 | 터미널을 새로 열 때마다 설정이 사라진다. `ros2 launch` 를 여러 터미널에서 띄우는 순간 일부만 통신된다 |
| 전 PC 동일 배포판 | Humble 과 Jazzy 는 DDS 버전과 메시지 정의가 달라 서로 붙지 않는다 |

### 이걸 알아야 하는 이유

프로젝트 중 가장 자주 만나는 장애가 **"노드는 떴는데 토픽이 안 온다"** 이고,
그 원인의 대부분은 코드가 아니라 이 문서의 네트워크 계층에 있다.
원인을 모르면 멀쩡한 콜백 함수를 몇 시간씩 들여다보게 된다.

증상을 계층으로 나눠서 접근하면 빠르다.

1. **케이블·IP 계층** — `ip -br addr` 로 내 주소 확인 → 상대에게 `ping`.
   여기서 막히면 ROS 문제가 아니다.
2. **도메인·방화벽 계층** — `echo $ROS_DOMAIN_ID` 로 팀원과 값 대조, `sudo ufw status` 확인.
   ping 은 되는데 `ros2 node list` 에 상대가 안 보이면 대개 여기다.
3. **DDS 설정 계층** — `echo $FASTRTPS_DEFAULT_PROFILES_FILE` 로 프로파일이 실제로 적용됐는지 확인.
4. **ROS 계층** — 여기까지 통과했는데 안 되면 그제야 토픽 이름, QoS, 메시지 타입을 본다.

1-3 을 건너뛰고 4 부터 보는 것이 시간을 가장 많이 잡아먹는다.

### 시연 전 체크리스트

각자 자기 PC 에서 아래를 실행하고 결과를 맞춰본다.

```bash
ip -br addr | grep 10.10.0      # 내 IP 가 배정표와 같은가
ping -c 3 10.10.0.1             # 마스터 1 에 닿는가
sudo ufw status                 # inactive 이거나 유선 UDP 허용 규칙이 있는가
echo $ROS_DOMAIN_ID             # 팀 전원 115 인가
echo $FASTRTPS_DEFAULT_PROFILES_FILE
sysctl net.ipv4.ip_local_port_range   # 40000 60999
ros2 node list                  # 팀원 노드가 보이는가
```

마지막 줄에서 팀원 노드가 보이면 준비 완료다.
