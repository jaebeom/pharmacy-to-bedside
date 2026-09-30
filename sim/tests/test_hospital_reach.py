"""병원 집기·내려놓기 자세에서 합본 UR5 가 목표에 닿는가 — IK 로 본다. Isaac 을 띄우지 않는다.

`zones.hospital.yaml` 의 `load`(A1 끝 롤러)와 병상 열 곳의 협탁을, 그 구역의 정차 자세에서 푼다.
높이는 합본 실제 값이다: 팔 밑동 월드 z = `amr_base.arm_base_world_z()`, 흡착점은 손목에서 0.1555 m
(`amr_base.GRIPPER_TCP_OFFSET`), 접근 자세는 params 의 `approach_height_m` 만큼 위다.

A1 끝 롤러 윗면 0.3847 m 는 팔 밑동(0.4862)보다 **아래**다 — 빈월드 벨트 0.75 와 반대라 여기서 처음 본다.
"""

import importlib.util
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'sim/standalone'))
sys.path.insert(0, str(ROOT/'src/rokey_p3_manipulation'))

#: 팔꿈치가 펴질수록 0 에 가깝다. 빈월드 자세 고르기가 쓰는 통과선과 같은 값이다(amr_base 주석).
MIN_SIN_Q3 = 0.35


@unittest.skipUnless(importlib.util.find_spec('numpy') and importlib.util.find_spec('yaml'),
                     'requires numpy and pyyaml')
class HospitalReachTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import yaml
        from p3sim import amr_base
        from p3sim import hospital_nav as hn
        from rokey_p3_manipulation import ur5_kinematics as kin
        cls.kin, cls.amr, cls.nav = kin, amr_base, hn
        cls.params = yaml.safe_load(
            (ROOT/'src/rokey_p3_manipulation/config/ur5_arm.amr-combined.camera.yaml').read_text()
        )['/**']['ros__parameters']
        zones = yaml.safe_load((ROOT/'src/rokey_p3_description/config/zones.hospital.yaml').read_text())
        cls.zones, cls.belt_end = zones['zones'], zones['pharmacy']['belt_end']
        cls.limits = kin.intersect_limits(kin.UR5_JOINT_LIMITS)

    def solve(self, stand, target):
        """정차 자세 `stand`(x, y, yaw)에서 월드 점 `target` 을 흡착점으로 잡는 해."""
        import numpy as np
        kin, amr = self.kin, self.amr
        x, y, yaw = stand
        bx, by = x + amr.ARM_MOUNT_LOCAL[0]*math.cos(yaw), y + amr.ARM_MOUNT_LOCAL[0]*math.sin(yaw)
        base_yaw = yaw + amr.ARM_BASE_YAW      # 스테이지가 밑동을 이 yaw 로 저작한다(convention 'base')
        dx, dy, dz = target[0]-bx, target[1]-by, target[2]-amr.arm_base_world_z()
        cos, sin = math.cos(-base_yaw), math.sin(-base_yaw)
        suction = kin.top_down_pose((cos*dx - sin*dy, sin*dx + cos*dy, dz), 0.0)
        tool0 = suction @ kin.invert(kin.translate(np.eye(4), (0.0, 0.0, amr.GRIPPER_TCP_OFFSET[2])))
        home = self.params['home_joint_positions']
        return kin.solve_ik(tool0, home, home=home, limits=self.limits)

    def targets(self):
        """(이름, 정차 자세, 흡착점 월드) — 집기 하나와 내려놓기 열이다."""
        # 팔은 **검출된 봉투**를 노린다. 봉투는 `belt_end`(계약 프레임)가 아니라 그보다 0.12 m 안쪽,
        # 탐침 02 가 잰 자리에 선다(`hospital_nav.A1_SETTLED_XY`). 9/23 회차가 여기서 깨졌다.
        load, belt = self.zones['load'], self.belt_end
        settled = (*self.nav.A1_SETTLED_XY, belt['z'])
        yield ('load', (load['x'], load['y'], load['yaw']),
               (settled[0], settled[1], settled[2] + self.params['pouch_height_m']
                + self.params['grasp_z_offset_m']))
        for name, zone in sorted(self.zones.items()):
            if name.startswith('bed_') and zone.get('cabinet'):
                cabinet = zone['cabinet']
                yield (name, (zone['x'], zone['y'], zone['yaw']),
                       (cabinet['x'], cabinet['y'], cabinet['z'] + self.params['place_z_offset_m']))

    def test_every_pick_and_place_pose_has_an_ik_solution(self):
        for name, stand, target in self.targets():
            for label, lift in (('집기', 0.0), ('접근', self.params['approach_height_m'])):
                result = self.solve(stand, (target[0], target[1], target[2] + lift))
                self.assertTrue(result.ok, f'{name} {label}: IK 없음 (오차 {result.position_error:.4f} m)')
                elbow = math.sin(abs(result.joints[2]))
                self.assertGreaterEqual(elbow, MIN_SIN_Q3, f'{name} {label}: 팔꿈치가 너무 펴졌다 {elbow:.3f}')


if __name__ == '__main__':
    unittest.main()
