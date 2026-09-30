# 합본 AMR 대수별 부하 — 측정 규약과 비교표 (N = 1, 2, 3, 4)

## 결론

1. **대당 비용은 첫 한 대가 거의 전부다.** loop_hz 는 26.67(N=1) → 17.71(N=2)로 34% 떨어진다. 그 뒤로는 18.83·15.78 로 대당 약 1 Hz 다. N=4 까지 합쳐 대당 −3.6 Hz, GPU util +8%p, VRAM +0.19 GB, stage ready +2.7 s 다.
2. **무너지는 N 은 1 이다(rtf 선).** N=1 부터 rtf 0.450 으로 0.5 아래다. 다른 세 선(joint_states 공백 최대 0.34 s, VRAM 최대 7.45 GB, stage ready 최대 41 s)은 N=4 까지 안 걸렸다. 네 회차 모두 완주했다.
3. **80 W 전제 권고: 화면 속도가 우선이면 1대다.** 여러 대를 보여야 하면 2대와 4대의 차이는 작다(rtf 0.30 대 0.27). 그때는 4대까지 써도 된다. GPU 는 N=1 부터 전력 상한(0x4 89-93%)이라, 대수가 늘어도 W 는 거의 그대로다.

근거: master01 `~/markle_tmp/m1-hospital-n{1,2,3,4}-d379042-0{5,6,7,8}/` 의 `stop reason=` 줄. N 마다 한 회차라 N=2 와 N=3 의 뒤바뀜(0.299 < 0.318)은 회차 사이 변동 안이다.

상태: 규약·판정선은 결과 전에 확정했다(9/23). 네 N 의 표를 채웠다. 판정선은 결과 뒤에 고치지 않았다.
카드: 재범, 합본 1→2→3→4대 과부하 측정. 9/23 이다. `--amr-count N` 이다. 커밋은 d379042 다. `demo_v2` 에서는 `P3_AMR_COUNT=N` 이다.
첫 대만 주문·Nav2 를 받는다. 2..N 번째는 `dock_2`-`dock_4` 에 서 있다. 내는 것은 센서와 TF 뿐이다. 라이다와 D455 는 그 구성을 줬을 때 난다.
여벌 대는 `Runtime` 이 없다. `joint_states` 를 내지 않는다. 그래서 공백은 `/m0609` 와 `/amr_1` 에서만 잰다.
회차: v0 완주 뒤 N=2·3·4 순으로 돈다. N=1 은 같은 SHA 의 v0 완주 회차를 기준으로 쓴다.
앞 문서: `hospital-perf-0923.md`(#587).

## 1. 조건 (N 사이에 바꾸지 않는다)

- 같은 트리 SHA 다. 같은 장비다. master02 이거나, 회차 기록에 적힌 장비 하나다. 창 모드는 `--window-half left` 다. 렌더 상한은 기본이다. `P3_RENDER_MAX` 를 두지 않는다.
- 카메라 설정(`P3_CAMERA_POUCHES`)은 N=1 과 같게 둔다. 라이다 설정도 같게 둔다. 대수가 늘면 라이다도 N 개가 된다. 그것도 대당 비용에 들어간다.
- 다른 GPU 프로세스가 없을 때 띄운다(`nvidia-smi --query-compute-apps=pid,process_name --format=csv` 를 기동 전 한 번 적는다).
- 회차마다 새로 띄운다. 이전 회차의 Isaac 이 남아 있지 않은지 본다.
- 표본 구간: stage ready 뒤 **600 s**, 또는 한 바퀴가 끝날 때까지 중 짧은 쪽. 주행이 없는 N(대기만)도 같은 600 s 로 잰다.

## 2. 재는 것과 방법

회차 폴더 `<회차>/` 아래에 둔다. 파일 이름은 고정이다.

| 항목 | 파일 | 방법 |
| --- | --- | --- |
| rtf, loop_hz | `stage.log` | `stop reason=` 줄의 `rtf=`·`loop_hz=`·`sim_s=`·`wall_s=` |
| GPU W·util·VRAM·클럭·스로틀 | `gpu.csv` | 아래 명령 A, 1 Hz |
| CPU | `top.txt` | 아래 명령 B, 5 s |
| joint_states 공백 | `gaps.csv` | 아래 스크립트 C. `/m0609/joint_states` 와 `/amr_1/joint_states` |
| 기동 시간 | `stage.log`, `demo_v2` 출력 | stage 시작 → `stage ready` 벽시계, `up` 완료 벽시계, 팔 `v2 계획 캐시 파일: 읽음 N/M` 줄 |
| py-spy(N=1·4 만) | `pyspy.txt` | ready 뒤 `py-spy record --native -r 50 -d 60 -f raw -o pyspy.txt -p <pid>` |

A. GPU

```bash
nvidia-smi --query-gpu=timestamp,power.draw,utilization.gpu,memory.used,clocks.sm,temperature.gpu,clocks_throttle_reasons.active \
  --format=csv -l 1 > <회차>/gpu.csv
```

B. CPU

```bash
top -b -d 5 > <회차>/top.txt
```

C. joint_states 공백. 받은 벽시계 시각과 헤더 stamp 를 적는다. 주제 이름은 인자로 준다.

```bash
python3 - /m0609/joint_states /amr_1/joint_states > <회차>/gaps.csv <<'EOF'
import sys, time, rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
rclpy.init(); node = rclpy.create_node("gap_probe")
print("topic,wall,stamp", flush=True)
for topic in sys.argv[1:]:
    node.create_subscription(JointState, topic, lambda m, t=topic: print(
        f"{t},{time.monotonic():.4f},{m.header.stamp.sec + m.header.stamp.nanosec * 1e-9:.4f}", flush=True),
        qos_profile_sensor_data)
rclpy.spin(node)
EOF
```

`ROS_DOMAIN_ID` 와 `use_sim_time` 은 그 회차 스택과 같게 둔다. 이 스크립트는 기록만 하고 아무것도 내지 않는다.

## 3. 집계와 판정선 (결과 전에 고정)

집계는 회차마다 같은 명령으로 한다.

- rtf·loop_hz: `stop reason=` 줄 그대로.
- GPU: 표본 구간의 `power.draw` 중앙·최대, `utilization.gpu` 중앙, `memory.used` 최대, 스로틀 `0x4` 초수 / 표본 초수.
- CPU: Isaac python 의 `%CPU` 중앙·최대.
- 공백: 주제별로 연속 두 `wall` 의 차. 최대, 99 백분위, 0.2 s 초과 횟수. stamp 차도 같이 본다(sim 시간 공백).
- 기동: stage ready 까지 초, `up` 완료까지 초.

**무너짐**은 아래 가운데 하나라도 맞는 첫 N 이다.

| 판정 | 선 | 이유 |
| --- | --- | --- |
| rtf | < 0.5 | 주행·집기 시한이 sim 시간이라 두 배 넘게 늘어진다 |
| joint_states 공백 | 최대 > 1.0 s 또는 0.2 s 초과가 분당 1회 넘음 | 35fb28a 전에는 팔 waypoint 시한이 새었다 |
| VRAM | 최대 > 15 GB(16 GB 중) | 넘으면 렌더 실패·강제 종료 위험 |
| 기동 | stage ready > 120 s | 회차 운영이 안 된다 |

대당 비용은 N=1 대비 차이를 (N−1)로 나눈다. 나눌 것은 Δloop_hz, ΔW, Δutil, ΔVRAM, Δ%CPU, Δ기동 s 다.
N 이 늘며 비용이 늘지 않으면(선형이 아니면) 그대로 적고 이유를 따로 본다.

## 4. 비교표

| N | SHA·회차 | rtf | loop_hz | GPU W 중앙/최대 | util 중앙 | VRAM 최대 GB | 0x4 비율 | Isaac %CPU 중앙/최대 | js 공백 최대 s | 0.2 s 초과/분 | stage ready s | up s | 판정 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | d379042 `m1-hospital-n1-d379042-05`(master01) | 0.450 | 26.67 | 72.0/77.4 | 45% | 6.87 | 0.89 | 826/960 | 0.29(`/amr_1`), 0.25(`/m0609`) | 0.71 | 33 | 38 | rtf 선에 걸린다. 0.450 은 0.5 보다 작다. joint_states 공백 선은 안 걸린다. VRAM 선은 안 걸린다. 기동 선은 안 걸린다 |
| 2 | 커밋은 d379042 다. 회차는 `m1-hospital-n2-d379042-06` 다. 장비는 master01 이다. 완주다 | 0.299 | 17.71 | 77.2/79.3 | 58% | 7.30 | 0.93 | 999/1143 | `/amr_1` 은 0.28 s 다. `/m0609` 은 0.27 s 다 | 0.47 | 33 | 39 | rtf 선에 걸린다. 0.299 다. joint_states 공백 선은 안 걸린다. VRAM 선은 안 걸린다. 기동 선은 안 걸린다 |
| 3 | 커밋은 d379042 다. 회차는 `m1-hospital-n3-d379042-07` 다. 장비는 master01 이다. 완주다 | 0.318 | 18.83 | 77.9/80.1 | 62% | 7.27 | 0.90 | 847/1061 | 둘 다 0.34 s 다 | 0.77 | 35 | 40 | rtf 선에 걸린다. 0.318 이다. joint_states 공백 선은 안 걸린다. VRAM 선은 안 걸린다. 기동 선은 안 걸린다 |
| 4 | 커밋은 d379042 다. 회차는 `m1-hospital-n4-d379042-08` 다. 장비는 master01 이다. 완주다 | 0.267 | 15.78 | 78.6/80.4 | 70% | 7.45 | 0.91 | 965/1120 | 둘 다 0.31 s 다 | 0.46 | 41 | 47 | rtf 선에 걸린다. 0.267 이다. joint_states 공백 선은 안 걸린다. VRAM 선은 안 걸린다. 기동 선은 안 걸린다 |

N=1 메모: 팔 계획 캐시 파일 `읽음 18/18`, stage ready 뒤 5 s 에 up 완료. py-spy 는 master01 에 미설치라 **미실행**. 장비는 master01 이다 — N=2·3·4 도 master01 에서 잰다.

대당 비용(N=1 대비, 대당):

| N | Δloop_hz | ΔW | Δutil | ΔVRAM GB | Δ%CPU | Δ기동 s |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | −8.96 | +5.2 다. 상한 80 W 근처다 | +13%p | +0.43 | +173 | up 이 +1 s 다 |
| 3 | −3.92 | +2.95 | +8.5%p | +0.20 | +10.5 | up 이 +1 s 다 |
| 4 | −3.63 | +2.2 | +8.3%p | +0.19 | +46 | stage ready 가 +2.7 s, up 이 +3 s 다 |

## 5. 한계

- GPU 는 80 W 에 묶여 있다(`hospital-perf-0923.md`(#587)). 전력이 이미 상한이면 W 는 대수와 무관하게 평평하다. 비용은 loop_hz 와 util 로만 보인다.
- 한 N 에 한 회차다. 같은 N 의 회차 사이 변동(실습40 에서 rtf 0.5 와 1.0 이 섞였다)은 이 표로 가를 수 없다. 판정 경계에 걸린 N 은 한 번 더 돈다.
