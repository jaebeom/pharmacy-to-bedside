"""GripperState / GripperCommand (contract 11.6) on the Isaac side behind --gripper-command-seq. No Isaac.

    python3 -m unittest discover -s sim/tests -p 'test_[mp]*.py'
"""

import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STANDALONE = ROOT / "sim" / "standalone"
sys.path.insert(0, str(STANDALONE))

from p3sim import bridge  # noqa: E402
from p3sim import observation as obs  # noqa: E402

MSGS = ROOT / "src" / "rokey_p3_interfaces" / "msg"
PRESETS = ("demo-ros", "demo-ros-refill", "demo-ros-refill-v2", "hospital-v2")


def load_stage():
    spec = importlib.util.spec_from_file_location("pharmacy_stage", STANDALONE / "pharmacy_stage.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


STAGE = load_stage()


def command(seq, close=True, epoch=1):
    return {"v": 1, "stamp": {"sec": 1, "nanosec": 0}, "epoch": epoch, "command_seq": seq, "close": close}


def msg_fields(name):
    text = (MSGS / name).read_text()
    constants = {k: int(v) for k, v in re.findall(r"^uint8 ([A-Z_]+)=(\d+)", text, re.MULTILINE)}
    fields = re.findall(r"^(?:bool|uint8|uint32|std_msgs/Header) ([a-z_]+)\s", text, re.MULTILINE)
    return constants, {"stamp" if f == "header" else f for f in fields}


class GateTests(unittest.TestCase):
    def test_idempotent_resend_and_order(self):
        gate = obs.GripperCommandGate()
        self.assertEqual(0, gate.last_applied)
        self.assertTrue(gate.accept(command(1), 1)[0])
        self.assertFalse(gate.accept(command(1), 1)[0])  # resend
        self.assertFalse(gate.accept(command(0, close=False), 1)[0])  # older
        self.assertTrue(gate.accept(command(3, close=False), 1)[0])  # gaps are fine
        self.assertEqual(3, gate.last_applied)

    def test_other_epoch_and_reset(self):
        gate = obs.GripperCommandGate()
        gate.accept(command(5), 1)
        applies, why = gate.accept(command(6, epoch=2), 1)
        self.assertFalse(applies)
        self.assertIn("epoch 2 is not current 1", why)
        gate.reset()  # RESET_DONE
        self.assertEqual(0, gate.last_applied)
        self.assertTrue(gate.accept(command(1, epoch=2), 2)[0])

    def test_state_fields(self):
        self.assertEqual({"epoch": 2, "seq": 9, "last_applied_command_seq": 4, "state": obs.STATE_HELD,
                          "mode": obs.GRIPPER_MODE_VIRTUAL}, obs.gripper_fields(2, 9, 4, True))
        self.assertEqual(obs.STATE_RELEASED, obs.gripper_fields(1, 0, 0, False)["state"])
        unknown = obs.gripper_fields(1, 0, 0, None)
        self.assertEqual((obs.STATE_UNKNOWN, obs.GRIPPER_MODE_UNKNOWN), (unknown["state"], unknown["mode"]))


class SchemaTests(unittest.TestCase):
    def test_state_and_command_match_the_interface_messages(self):
        constants, fields = msg_fields("GripperState.msg")
        self.assertEqual({"STATE_UNKNOWN": 0, "STATE_RELEASED": 1, "STATE_HELD": 2, "MODE_UNKNOWN": 0,
                          "MODE_VIRTUAL": 1, "MODE_PHYSICAL": 2}, constants)
        self.assertEqual((obs.STATE_UNKNOWN, obs.STATE_RELEASED, obs.STATE_HELD), (0, 1, 2))
        self.assertEqual((obs.GRIPPER_MODE_UNKNOWN, obs.GRIPPER_MODE_VIRTUAL, obs.GRIPPER_MODE_PHYSICAL), (0, 1, 2))
        self.assertEqual(fields, set(bridge.SCHEMAS[bridge.GRIPPER_STATE]) - {"v"})
        _constants, fields = msg_fields("GripperCommand.msg")
        self.assertEqual(fields, set(bridge.SCHEMAS[bridge.GRIPPER_COMMAND_SEQ]) - {"v"})

    def test_encode_and_reject(self):
        text = bridge.encode(bridge.GRIPPER_STATE, stamp=bridge.stamp(3.0), **obs.gripper_fields(1, 5, 2, True))
        self.assertEqual([], bridge.decode(bridge.GRIPPER_STATE, text)[1])
        self.assertEqual([], bridge.validate(bridge.GRIPPER_COMMAND_SEQ, command(1)))
        self.assertIn("close must be bool", bridge.validate(bridge.GRIPPER_COMMAND_SEQ, {**command(1), "close": 1}))
        self.assertIn("command_seq out of uint32 range",
                      bridge.validate(bridge.GRIPPER_COMMAND_SEQ, command(2 ** 32)))
        with self.assertRaises(ValueError):
            bridge.encode(bridge.GRIPPER_STATE, stamp=bridge.stamp(3.0), **{**obs.gripper_fields(1, 5, 2, True),
                                                                          "state": 3})


class StageTests(unittest.TestCase):
    def test_opt_in_needs_ur5_and_ros_and_presets_stay_off(self):
        self.assertFalse(STAGE.parse_args([]).gripper_command_seq)
        for name in PRESETS:
            with self.subTest(preset=name):
                self.assertFalse(STAGE.parse_args(["--preset", name]).gripper_command_seq)
        problem = "--gripper-command-seq needs --ur5 and --mode ros"
        self.assertTrue(any(p.startswith(problem) for p in STAGE.validate(STAGE.parse_args(["--gripper-command-seq"]))))
        ok = STAGE.parse_args(["--mode", "ros", "--ur5", "--gripper-command-seq"])
        self.assertFalse(any(p.startswith(problem) for p in STAGE.validate(ok)))

    def test_bool_ignored_from_the_start_and_seq_applied(self):
        source = (STANDALONE / "pharmacy_stage.py").read_text()
        block = source[source.index("if args.gripper_command_seq:  # only command_seq applies"):
                       source.index("if arm is not None and args.ros_refill_selfdemo:")]
        self.assertLess(block.index("closed = None"), block.index("if closed is not None and closed != cell.holding()"))
        self.assertIn("gripper_gate.accept(command, state[\"epoch\"])", block)
        self.assertIn("apply_suction(command[\"close\"])", block)
        reset = source[source.index("def do_reset_steps"):source.index("def handle_ros")]
        self.assertIn("gripper_gate.reset()", reset)
        publish = source[source.index("if args.gripper_command_seq and ros is not None and cell is not None"):]
        self.assertIn("physics_steps.seq, gripper_gate.last_applied", publish[:publish.index("next_gripper =")])


if __name__ == "__main__":
    unittest.main()
