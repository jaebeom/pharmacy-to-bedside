# 보충 실습 결과 대조 도구

> **상태: 지난 기록 (2026-09-22 기준, #489).** 도구 `summarize_workcell_trial.py` 는 main 에 있다. 9/22 원통 3회 실습용이다. 지금 병원 한 바퀴 절차는 [병원 전 구간 런카드](../../docs/runbooks/hospital-full.md)를 따른다.

`summarize_workcell_trial.py`는 이미 수집한 events JSONL, action results JSON, stage 로그를 읽고 새 JSON 보고서를 만든다. ROS나 Isaac을 시작하지 않으며 로봇·좌표·속도·알고리즘을 수정하지 않는다.

```bash
python3 sim/standalone/summarize_workcell_trial.py \
  --events <external-events.jsonl> --results <external-results.json> \
  --stage-log <external-stage.log> --output <new-external-summary.json>
```

입력은 동일 실행의 원통 3회 시험이며 셀당 최대 한 번이어야 한다. 각 action의 계획 feedback 셀과 stage의 attach/round release, 마지막 release 셀, 홈 복귀 관측을 대조한다. 이 조건의 일치가 시뮬 실습 관측 기준이고, 실물 파지/배송 합격 기준은 아니다. 로그를 다른 회차와 합치거나 같은 셀 재시도를 넣으면 안 된다.

설정값을 읽어서 실제 속도로 보고하지 않는다. JointState의 속도 최고값과 clock 역행 횟수를 별도로 출력한다. 데이터가 없으면 샘플 수 0이며 최고값 0은 정지 성능 검증이 아니다. 기존 결과 파일은 덮어쓰지 않는다. 현장 좌표·절대 경로·원본 로그는 이 변경에 포함하지 않는다.

검사: `python3 -m unittest discover -s sim/tests -p test_workcell_trial_report.py`. action 성공만 있고 attach/release/홈이 빠진 경우와 관측 속도 초과·clock 역행의 보존을 확인한다. 실제 로봇 실행 L3는 이 읽기 전용 도구의 검사 범위가 아니다.
