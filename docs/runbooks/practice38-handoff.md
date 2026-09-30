# 실습38 인계 — 동일 장면 복원과 ROS 통합을 구분한다
> **상태: 지난 기록 (2026-09-23 기준).** 지금은 [병원 한 바퀴 런카드](hospital-full.md)를 따른다.

## 바로 볼 결론

실습38의 공용 코드·실패 기록은 #500으로 main에 병합됐다(merge `308c2ae4bfc10c5f26ee1d3853d18694ffc39eb7`). 그러나 재현 입력은 로컬에 흩어졌고 다른 사람의 접근·재현을 확인하지 않았다. 이것이 이번 인계 보완 대상이다. 인계 누락이 현재 모든 실패의 원인이라고 단정하지 않는다.

이번 변경은 [실제 입력 전체](../../experiments/fixtures/practice38/README.md)를 Git에 보존한다. 이전 실행 기록은 수정하지 않고 이 문서를 추가한다. #500 병합은 받침대 배출·1350개 랜덤 파지·전체 루프 성공을 뜻하지 않는다.

## 현재 실행과의 차이 — 관측 스냅샷

9/23 17:46 KST 읽기 전용 확인: 실행 PID 751553, cwd `20260923-hf-bb3ac33`, SHA `bb3ac33bc371b9898c06ae1e404e162032b77b9b`. 실행 중인 다른 사람의 프로세스는 중단·변경하지 않았다.

| 항목 | 실습38 | 위 시점 실행 |
| --- | --- | --- |
| 진입점 | `hospital_workcell_demo.py --conveyor-probe` | `pharmacy_stage.py --preset hospital --workcell-layout ...` |
| 입력 | stock 1350개 | `m2-hospital-integrated-09/workcell.json`, 18개 |
| 입력 해시 | fixture manifest 참조 | `7fb6c613d332e3570443d09865a85ae473e51aed3233ab8ba47a2ad2fe210ff1` |
| ROS/팔/AMR | ROS OFF, 팔·AMR 고정 | ROS 통합 명령 인자가 켜진 실행; 동작 성공을 뜻하지 않음 |
| 병원 | 당시 #484 prepared root | 실행 release의 `hospital_navigationv1.usda` |

따라서 이 실행을 실습38의 재개로 취급하면 안 된다. 새 통합 코드 검증일 수는 있다. 현재 실패 원인은 해당 회차의 로그·판단과 별도로 대조해야 한다. 주행 문 갇힘·Nav2 무진전과 실습38의 벨트/선반 실패도 합치지 않는다.

## 위치와 단일 출처

| 대상 | 당시 값/출처 |
| --- | --- |
| 조제기 원점 | `workcell_preview.py`의 `DISPENSER_ORIGIN=(-8.78522324,11.7254655,0)`; 당시 코드 SHA 아래 참조 |
| 원통 입구 | `dispenser-placement.json`: (-8.05,11.115,0.98) |
| 모듈 입구 | 같은 파일: (-7.7,11.11546546,1.02) |
| 컨베이어 입구 | 같은 파일: (-9.8225,11.26546546,1.105) |
| 레일 | stock JSON `rail`: origin(-3.3,10.75,0), X stroke11.4, Y[-0.1,0.33], Z[0,1.1], carriage0.25 |
| 약품 1350개 | stock JSON `cells` 전체: surface·size·type·row·col·depth_index·front_accessible |
| 선반·벽·벨트 | 보존한 prepared USD와 외부 referenced assets; 현재 main 씬과 혼합하지 않는다 |
| AMR 한 대 | `amr-placement.json`: XY(-7.15,4.5), mount(-0.35,0,0.15). 현재 주행 목표로 승인된 값이 아님 |
| 봉투·경사판·벨트 | probe JSON의 spawn/end/graph_velocities/terminal_prim/outlet_chute. 값은 진단 후보 |

## 자산 확보와 검사

- fixture `manifest.json`의 모든 파일 해시가 일치해야 한다. 사본은 원본과 바이트 동일하다.
- 조제기: 저장소 `src/rokey_p3_description/models/dispenser/dispenser.usdc`, SHA-256 `cd2591a821d96e44e3a0a90ef66ee33e6fd1b432582618163094bb22242ddaf2`.
- M0609 및 Ridgeback+UR5, 병원 Props/Materials/texture는 외부 자산이다. `terminal-start.json` argv와 prepared USD의 참조 경로에서 찾는다. Git에 외부 모델 본체를 포함했다고 주장하지 않는다. AMR 루트 해시는 `amr-placement.json`에 있다.
- master02에서는 당시 자산 경로를 확인했다. 다른 PC로 의존 파일 전체 복사·접근 검증은 미실행이다. 루트 USD 해시 하나가 종속 자산 무결성을 보장하지 않는다.
- `prepare_hospital_scene.py`는 이 prepared #484 파일의 대체 생성기가 아니다. 다른 템플릿으로 새로 만들면 같은 장면이 아니다.

## 마스터에서 재개할 절차

#240 에서 슬롯을 조율한 뒤 실행한다. **이번 문서화에서는 새 Isaac/ROS를 실행하지 않았다.**

1. 이 PR의 fixture를 확보한다. 과거 물리 코드 재현은 별도 worktree `1e6e1d87db47949a7123d1640d7d53703b908c94`(terminal/SIGINT) 또는 `84742dec6454115d07dc5229ece76ba459e75f6b`(receiver)를 사용한다. 새 코드로 돌리면 새 SHA의 회차로 기록한다.
2. 아래 준비 명령은 master02 자산 경로를 이용한다. 새 출력 경로만 사용하고 원본 JSON은 덮지 않는다. 같은 코드·씬·입력의 재현과 새 통합 실행을 분리한다.

```bash
# fixture를 포함한 checkout에서 실행. 준비만 하며 Isaac을 시작하지 않는다.
python3 - <<'PYCODE'
from pathlib import Path
import hashlib, json, shlex
fixture = Path('experiments/fixtures/practice38').resolve()
manifest = json.loads((fixture/'manifest.json').read_text())
for name, item in manifest['files'].items():
    assert hashlib.sha256((fixture/name).read_bytes()).hexdigest() == item['sha256'], name
prepared = Path('/tmp/practice38-handoff-inputs')
prepared.mkdir(exist_ok=False)
for mode in ('terminal', 'receiver'):
    source = json.loads((fixture/f'probe-{mode}.json').read_text())
    source['inventory'] = str(fixture/'stock-mixed-1350.json')
    config = prepared/f'{mode}.json'
    config.write_text(json.dumps(source, indent=2)+'\n')
    argv = json.loads((fixture/f'{mode}-start.json').read_text())['command']
    argv[argv.index('--base-usd')+1] = str(fixture/'hospital-pr484-resolved.usda')
    argv[argv.index('--conveyor-probe')+1] = str(config)
    argv[argv.index('--output')+1] = str(prepared/f'{mode}-new-run')
    for flag in ('--robot-usd', '--amr-combined'):
        assert Path(argv[argv.index(flag)+1]).is_file(), flag
    (prepared/f'{mode}-command.txt').write_text(shlex.join(argv)+'\n')
    print(mode, 'prepared command:', prepared/f'{mode}-command.txt')
PYCODE
```

3. 지정한 실행 코드의 worktree로 이동한다. 생성된 `*-command.txt`를 확인하고 ROS를 source하지 않은 Isaac 환경에서 실행한다. master02 표시 환경은 `DISPLAY=:0`, `XAUTHORITY=/run/user/1000/gdm/Xauthority`, `XDG_RUNTIME_DIR=/run/user/1000`이다. 외부 참조가 없으면 누락을 기록하고 다른 모델로 조용히 바꾸지 않는다.
4. 시작 전에 1350개(모듈338/원통1012), 9선반×5층, 기준 투입구, AMR1대를 확인한다. placement JSON과 probe prepared 이벤트를 보존한다.
5. 녹화의 처음·중간·끝 실제 프레임을 확인한다. 새 run에 코드 SHA·입력 해시·시각·결과 JSON·영상 해시를 남긴다.
6. SIGINT로 종료하고 결과 저장을 확인한다. 받는 사람의 재현 회신 전에는 인계 완료로 표시하지 않는다.

## 알려진 결과와 다음 작업

| 조건 | 당시 결과 | 다음 작업 |
| --- | --- | --- |
| terminal | 약34.616668 sim s, 롤러 끝 정착 | 정상 진단 기준. 받침대 배출 성공 아님 |
| receiver | 90 sim s timeout, supported_xy=false, flat=false | 접촉·충돌/재질과 배출 구조 검토. 판정 완화로 성공 처리하지 않음 |
| 1350개 중 랜덤 원통3개 | 사전 경로 계획3개 실패, 실제 동작0 | 전체 물품 장애물·레일 도달·18칸 전제와 연결을 검토 |
| 내부 흡입 | 별도 키네마틱 시각 데모만 존재 | 그리퍼 해제·재고·ROS 통합 미완료 |
| 조제→적재→Nav2→복귀 | 실습38에서 미실행 | 선행 단계 검증 뒤 구간별 통합 |

계획만 재현하는 명령은 다음과 같다. 이전 관측은 [실습38](../practice/simworld/practice-38.md)을 참조한다. 무거운 사전 계산이므로 진행 중인 다른 실습과 자원을 조율한다.

```bash
PYTHONPATH=sim/standalone:src/rokey_p3_manipulation python3 sim/standalone/check_stock_refill.py \
  --inventory /path/to/fixture/planning-inventory-1350.json \
  --output /path/to/new-plan-results.jsonl --seed 835258728 --rail-select first_feasible
```

## 이번 확인과 남은 확인

원본과 Git 입력의 해시 일치, 1350개 내역, 18칸 비교, JSON 파싱, 문서/저장소 검사를 실시한다. 결과는 PR에 기록한다. 새 물리 L3, 다른 PC의 외부 자산 확보, 다른 사람의 수신·재현은 아직 미확인이다. 이번 인계 보완을 실습 성공으로 읽지 않는다.

## 이미지 인계

[실습38 이미지 전수 대조와 현재 카메라 문제](../analysis/practice38-image-audit.md)에 검색 범위·17개 캡처·현재 사용자 화면1개와 각각의 해시를 남겼다.

9/23 라이브 화면 조정 후속: Default 조명·16:9·10mm는 별도 `review-display-20260923.json`에 보존했다. 실제 적용 화면과 현재603dfc1 실행의 조제기 payload 누락은 이미지 감사19절에 있다. 재기동 자동 적용은 아직 연결하지 않았다.
