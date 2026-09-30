#!/usr/bin/env python3
"""병원 컨베이어가 **참조로 불러온 씬 아래서도** 봉투를 A1 롤러 끝까지 보내는가(#527 H1 의 첫 위험).

    ~/isaacsim/python.sh sim/standalone/conveyor_reference_probe.py \
        --base-usd sim/scenes/hospital_navigationv1.usda --config <probe06 설정 json> --output <새 디렉터리>

pharmacy_stage 는 병원 씬을 `/World/P3Base/Scene` 에 reference 한다(p3sim/base_scene.add_base_scene). 실습38 의 탐침은
씬을 루트 스테이지로 열었다(hospital_workcell_demo.py). 씬 컨베이어의 OmniGraph 가 reference 아래에서도 돌고
`inputs:conveyorPrim` 이 다시 매핑되는지 아무도 보지 않았다 — 이 실행기가 그것만 본다. 로봇은 만들지 않는다.
설정 json 은 hospital_workcell_demo.py --conveyor-probe 와 같다(경로는 씬 루트 기준 /World/Conveyor/... 그대로 두면
여기서 참조 경로로 옮긴다). 결과는 --output 의 conveyor-result.json 과 CONVEYOR_PROBE 줄이다.
"""
import argparse
import json
import sys
import threading
from pathlib import Path

STANDALONE = Path(__file__).resolve().parent
sys.path.insert(0, str(STANDALONE))

CONVEYOR_UNDER_REFERENCE = '/World/P3Base/Scene/Conveyor'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--base-usd', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True, help='workcell --conveyor-probe 설정 json')
    parser.add_argument('--output', type=Path, required=True, help='새 디렉터리(있으면 거부)')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--surface-velocities', type=Path, default=None,
                        help='그래프 대신 표면 속도를 직접 쓴다(예: p3sim/hospital_conveyor_surfaces.json)')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('--output must not exist; preserve earlier trials')
    from isaacsim import SimulationApp

    app = SimulationApp({'headless': args.headless})
    import omni.usd
    from pxr import UsdGeom

    from minimal_clock import install_sigint_handler
    from p3sim import base_scene
    from p3sim.hospital_conveyor_probe import HospitalConveyorProbe

    context = omni.usd.get_context()
    context.new_stage()
    stage = context.get_stage()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, '/World').GetPrim())
    info = base_scene.add_base_scene(stage, str(args.base_usd.resolve()), (0.0, 0.0, 0.0, 0.0))
    print('CONVEYOR_REFERENCE_PROBE base ' + str(info), flush=True)
    while context.get_stage_loading_status()[2] > 0 and app.is_running():
        app.update()
    for _ in range(10):
        app.update()
    args.output.mkdir(parents=True)
    config = json.loads(args.config.read_text())
    if args.surface_velocities:
        config['surface_velocities'] = json.loads(args.surface_velocities.read_text())['surface_velocities']
    used = args.output / 'config-used.json'
    used.write_text(json.dumps(config, indent=1) + '\n')
    probe = HospitalConveyorProbe(stage, used, args.output, conveyor_root=CONVEYOR_UNDER_REFERENCE)
    stop = threading.Event()
    install_sigint_handler(stop)
    try:
        while not stop.is_set() and app.is_running() and not probe.finished:
            probe.step()
    finally:
        try:
            probe.abort()
        finally:
            probe.log.close()
            app.close()


if __name__ == '__main__':
    main()
