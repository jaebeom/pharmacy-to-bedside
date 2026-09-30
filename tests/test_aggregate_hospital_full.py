"""hospital-full-acceptance-v1 rules against a reduced attempt folder; the fixture is not a measurement.

tests/fixtures/runs/hospital-full-a01 keeps the line formats of master01 campaign 1 attempt 1 (64e5ab7) with values
edited so that every rule fires. Expected values are worked out by hand in the comments.
"""

import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("aggregate_runs", SOURCE / "tools/aggregate_runs.py")
aggregate_runs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aggregate_runs)

PROTOCOL = SOURCE / "experiments/protocols/hospital-full-acceptance-v1.json"
PROTOCOL_V2 = SOURCE / "experiments/protocols/hospital-full-acceptance-v2.json"
PROTOCOL_V4 = SOURCE / "experiments/protocols/hospital-full-acceptance-v4.json"
FIXTURE = SOURCE / "tests/fixtures/runs/hospital-full-a01"


def materialize(target):
    """Copy the fixture and drop the `.fixture` suffix (`*.log`, `STEPS.md`) as an attempt folder has them."""
    shutil.copytree(FIXTURE, target)
    for path in list(target.rglob("*.fixture")):
        path.rename(path.with_suffix(""))
    return target


def values(result):
    return {metric["name"]: metric["value"] for metric in result["metrics"]}


#: attempt 1 값(주석은 test_attempt_one_folder 참고) — 단일 root 와 phase E 분할 root 시험이 같이 쓴다.
ATTEMPT_1_VALUES = {
    "attempt_success": 1, "scene_workcell_ready": 1, "scene_refill_both": 1, "scene_container_qr": 1,
    "pouch_to_end_s": 34.58, "scene_pouch_at_end": 1, "scene_pick_in_slot": 1, "scene_delivered_docked": 1,
    "amr_touch_count": 0, "governor_margin_lines": 4, "governor_full_speed_lines": 1, "governor_unknown_lines": 1,
    "boot_check_pass": 1, "orders10_delivered": None, "orders_beds_all_delivered": None,
    "orders10_multipc_delivered": None, "record_fps_min": 29.5, "record_drop_ratio_max": 0.010003,
    "record_corrupt_sum": 0, "unplanned_intervention_count": 1, "avoidance_encounters": 2,
    "governor_limit_lines_during_encounters": 2, "vision_detect_rate": 0.0, "vision_latency_ms": 1000.0,
    "fresh_clone_step_wall_s": None, "fresh_clone_asset_sha_ok": None, "rtf": 0.627, "attempt_wall_s": 497.0,
    "reset_dock_pose_error_m": None, "reset_arm_park_error_rad": None, "pouch_spawn_records": 1,
}


class HospitalFullTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.attempt = materialize(self.root / "a01")

    def run_on(self, folder, attempt=1):
        return aggregate_runs.aggregate(folder, PROTOCOL, attempt=attempt)

    def test_attempt_one_folder(self):
        got = values(self.run_on(self.attempt))
        self.assertEqual(len(got), 31)   # every protocol metric has a row
        # ped_1 sim 167.95-175.00 → wall W0+268.7…280.0 holds the 50% line at W0+270; dummy_2 has no end, so it runs
        # to the last speed.csv row and holds the 53% line (governor_limit_lines_during_encounters). up.log 08:18:42
        # (+9 h from the 08:19:18 ↔ ROS 1790291957.7 pair) = 1790291922; DOCKED sim 290 → W0+464 (attempt_wall_s).
        self.assertEqual(ATTEMPT_1_VALUES, got)

    def test_missing_line_fails_the_scene_and_the_attempt(self):
        folder = self.attempt
        stage = next((folder / "logs").glob("*-stage.log"))
        lines = [line for line in stage.read_text().splitlines() if "target=round" not in line]
        stage.write_text("\n".join(lines) + "\n")
        (folder / "demo_v2-env.txt").write_text("P3_DECK_VISION       0\n")
        result = self.run_on(folder)
        got = values(result)
        self.assertEqual((0, 0), (got["scene_refill_both"], got["attempt_success"]))
        self.assertIsNone(got["vision_detect_rate"])
        self.assertTrue(any("P3_DECK_VISION=0" in note for note in result["notes"]))

    def test_a_short_stock_line_or_an_unmatched_arrival_fails(self):
        stage = next((self.attempt / "logs").glob("*-stage.log"))
        stage.write_text(stage.read_text().replace("present=14 empty=['shelf_68/r0c1', ", "present=14 empty=["))
        events = self.attempt / "event_run/events.jsonl"
        events.write_text(events.read_text().replace('"request_id": "web-m1-9501", "robot_id": "x", "stale": false, '
                                                     '"stamp": 215.0', '"request_id": "", "robot_id": "x", '
                                                     '"stale": false, "stamp": 215.0'))
        got = values(self.run_on(self.attempt))
        self.assertEqual((0, 0), (got["scene_workcell_ready"], got["scene_delivered_docked"]))

    def test_fresh_clone_from_steps(self):
        got = values(self.run_on(self.attempt, attempt=16))
        # STEPS.md clone 4 + build 18 + venv 4 + assets 2 + prep 10 = 38 s, then up 1790291922 → ORDER_DONE sim 224
        # (W0 + 1.6 × 224 = 1790292313.4) = 391.4 s
        self.assertEqual((429.4, 1), (got["fresh_clone_step_wall_s"], got["fresh_clone_asset_sha_ok"]))

    def test_fresh_clone_asset_check_failure_is_zero(self):
        steps = self.attempt / "STEPS.md"
        steps.write_text(steps.read_text().replace("끝 10:05:59 exit=0", "끝 10:05:59 exit=1"))
        self.assertEqual(0, values(self.run_on(self.attempt, attempt=16))["fresh_clone_asset_sha_ok"])
        (self.attempt / "STEPS.md").unlink()
        got = values(self.run_on(self.attempt, attempt=16))
        self.assertEqual((None, None), (got["fresh_clone_step_wall_s"], got["fresh_clone_asset_sha_ok"]))

    def test_phase_metrics_need_the_attempt_index(self):
        result = self.run_on(self.attempt, attempt=None)
        self.assertIsNone(values(result)["orders10_delivered"])
        self.assertTrue(any("--attempt" in note for note in result["notes"]))


class MultiRootPhaseETests(unittest.TestCase):
    """phase E(다중 PC, attempt 12·13): 같은 attempt 1 자료를 master01(stage)·master02(arm·nav·stack·web
    +event_run) 두 root 로 쪼개 aggregate_runs 가 하나로 합치는지 본다. 값은 단일 root 시험(ATTEMPT_1_VALUES)과
    같아야 한다 — 자료는 그대로고 폴더만 나눴다.
    """

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.full = materialize(self.root / "full")     # 대조용 단일 root(안 나눔)
        self.stage_root, self.stack_root = self.split()

    def split(self):
        """master01=stage, master02=arm·nav·stack+event_run+web. speed.csv 는 master02 쪽에(nav 와 같은 host)."""
        stage_root, stack_root = self.root / "m01-stage", self.root / "m02-stack"
        (stage_root / "logs").mkdir(parents=True)
        (stack_root / "logs").mkdir(parents=True)
        shutil.copy(next((self.full / "logs").glob("*-stage.log")), stage_root / "logs" / "20260925-081844-stage.log")
        for kind in ("arm", "nav", "stack"):
            shutil.copy(next((self.full / "logs").glob(f"*-{kind}.log")),
                       stack_root / "logs" / f"20260925-081844-{kind}.log")
        shutil.copytree(self.full / "event_run", stack_root / "event_run")
        # stage-only host 의 up.log 는 arm 이 없어 ROS 짝 줄이 없다(up_start_wall 이 이 root 를 건너뛰어야 한다).
        (stage_root / "up.log").write_text("[demo_v2 08:18:42] 월드 파일: zones=… routes=…(주행·웹 같은 경로)\n")
        shutil.copy(self.full / "up.log", stack_root / "up.log")            # arm 준비 ROS 짝 줄은 여기 있다
        shutil.copy(self.full / "boot_check.txt", stage_root / "boot_check.txt")
        shutil.copy(self.full / "boot_check.txt", stack_root / "boot_check.txt")
        shutil.copy(self.full / "speed.csv", stack_root / "speed.csv")
        shutil.copy(self.full / "demo_v2-env.txt", stack_root / "demo_v2-env.txt")
        shutil.copy(self.full / "phase.log", stack_root / "phase.log")
        shutil.copy(self.full / "record_qa.txt", stage_root / "record_qa.txt")
        shutil.copy(self.full / "record_qa_web.txt", stack_root / "record_qa_web.txt")
        return stage_root, stack_root

    def run_on(self, roots, attempt=1):
        return aggregate_runs.aggregate(list(roots), PROTOCOL, attempt=attempt)

    def test_split_roots_give_the_same_values_as_one_root(self):
        got = values(self.run_on([self.stage_root, self.stack_root]))
        self.assertEqual(ATTEMPT_1_VALUES, got)

    def test_root_order_does_not_matter(self):
        forward = values(self.run_on([self.stage_root, self.stack_root]))
        backward = values(self.run_on([self.stack_root, self.stage_root]))
        self.assertEqual(forward, backward)

    def test_a_boot_check_fail_on_either_host_fails_the_gate(self):
        (self.stage_root / "boot_check.txt").write_text(
            (self.stage_root / "boot_check.txt").read_text() + "[boot_check] FAIL disk — 회차 중단\n")
        got = values(self.run_on([self.stage_root, self.stack_root]))
        self.assertEqual((0, 0), (got["boot_check_pass"], got["attempt_success"]))

    def test_a_speed_csv_on_both_roots_is_noted_and_still_computes(self):
        shutil.copy(self.full / "speed.csv", self.stage_root / "speed.csv")
        result = self.run_on([self.stage_root, self.stack_root])
        self.assertEqual(ATTEMPT_1_VALUES["attempt_wall_s"], values(result)["attempt_wall_s"])
        self.assertTrue(any("speed.csv" in note and "root 여러 개" in note for note in result["notes"]))

    def test_a_missing_second_root_leaves_its_metrics_null(self):
        """master02 root 를 아예 안 주면(예: 마클2 폴더를 못 받음) 그 쪽 metric 만 null 이다 — 죽지 않는다."""
        got = values(self.run_on([self.stage_root]))
        self.assertEqual(1, got["pouch_spawn_records"])         # stage 줄만으로 되는 것
        self.assertIsNone(got["scene_refill_both"])             # event_run(REFILL_DONE 수)이 master02 에 있다
        self.assertIsNone(got["scene_container_qr"])            # arm.log 없음
        self.assertIsNone(got["vision_detect_rate"])            # stack.log 없음(P3_DECK_VISION 도 모른다)

    def test_viewport_skip_on_the_non_stage_host_does_not_fail_the_gate(self):
        """실제 회차(마클2 #240 5848373269, campaign2 attempt 12·13): master02(비-stage) 는 viewport 를,
        master01(stage) 는 window 를 SKIP 했는데 예전 규칙은 viewport SKIP 만으로 게이트를 걸었다."""
        non_stage = (self.full / "boot_check.txt").read_text().replace(
            "[boot_check] viewport PASS viewport 1920x1080", "[boot_check] viewport SKIP")
        (self.stack_root / "boot_check.txt").write_text(non_stage)
        got = values(self.run_on([self.stage_root, self.stack_root]))
        self.assertEqual((1, 1), (got["boot_check_pass"], got["attempt_success"]))

    def test_viewport_skipped_on_every_root_still_fails_the_gate(self):
        """양쪽 다 viewport 를 SKIP 하면(아무도 안 봤다) 다중 PC 라도 게이트는 실패다."""
        no_viewport = (self.full / "boot_check.txt").read_text().replace(
            "[boot_check] viewport PASS viewport 1920x1080", "[boot_check] viewport SKIP")
        (self.stage_root / "boot_check.txt").write_text(no_viewport)
        (self.stack_root / "boot_check.txt").write_text(no_viewport)
        got = values(self.run_on([self.stage_root, self.stack_root]))
        self.assertEqual(0, got["boot_check_pass"])

    def test_viewport_skip_on_the_stage_host_itself_still_fails(self):
        """비-stage host 의 viewport 가 어쩌다 PASS 로 찍혀도, stage host 자신이 SKIP 하면 안 봐준다."""
        (self.stage_root / "boot_check.txt").write_text(
            (self.full / "boot_check.txt").read_text().replace(
                "[boot_check] viewport PASS viewport 1920x1080", "[boot_check] viewport SKIP"))
        got = values(self.run_on([self.stage_root, self.stack_root]))
        self.assertEqual(0, got["boot_check_pass"])

    def test_protocol_v2_gives_the_same_metrics_as_v1_with_a_different_sha(self):
        """v2(9/27, #576 5851279552)는 purpose 4(c) 문구만 phase E 로 넓혔다 — metrics·attempt 구조는 v1 과
        글자 그대로 같아야 한다. v1(60e7d86, frozen)은 고치지 않았으니 sha256 은 다르다."""
        non_stage = (self.full / "boot_check.txt").read_text().replace(
            "[boot_check] viewport PASS viewport 1920x1080", "[boot_check] viewport SKIP")
        (self.stack_root / "boot_check.txt").write_text(non_stage)
        roots = [self.stage_root, self.stack_root]
        v1 = aggregate_runs.aggregate(roots, PROTOCOL, attempt=1)
        v2 = aggregate_runs.aggregate(roots, PROTOCOL_V2, attempt=1)
        self.assertEqual(values(v1), values(v2))
        self.assertNotEqual(v1["protocol_sha256"], v2["protocol_sha256"])
        self.assertEqual("hospital-full-acceptance-v2", v2["protocol_id"])

    def test_protocol_v4_gives_the_same_metrics_as_v1_with_a_different_sha(self):
        """v4(재범 결정 #240 5854486187, v3 를 커서 통합검증 #756 5855093172 지적으로 대체)는 §7 판정선
        문장만 다르다 — metrics·attempt 계산 코드는 protocol_id 를 안 보므로 v1 과 글자 그대로 같은 값이
        나와야 한다."""
        non_stage = (self.full / "boot_check.txt").read_text().replace(
            "[boot_check] viewport PASS viewport 1920x1080", "[boot_check] viewport SKIP")
        (self.stack_root / "boot_check.txt").write_text(non_stage)
        roots = [self.stage_root, self.stack_root]
        v1 = aggregate_runs.aggregate(roots, PROTOCOL, attempt=1)
        v4 = aggregate_runs.aggregate(roots, PROTOCOL_V4, attempt=1)
        self.assertEqual(values(v1), values(v4))
        self.assertNotEqual(v1["protocol_sha256"], v4["protocol_sha256"])
        self.assertEqual("hospital-full-acceptance-v4", v4["protocol_id"])


class AggSubfolderTests(unittest.TestCase):
    """master02의 실제 회차(#240 5851309536, campaign2 attempt 12·13, evidence-transfer-c2-multipc)는 이
    도구가 쓰는 이름이 아니라 자기 관측 스크립트의 이름(`boot_check.log`·`up.console`·`demo_env.txt`·
    `event_logger/<run_id>/`)을 쓴다. `agg/` 는 그 이름들을 이 도구가 쓰는 이름으로 이어주는 그 팀의 심볼릭
    링크 폴더다(원본은 절대경로 심볼릭 링크라 옮기면 깨진다) — Folder 는 root 에 `agg/` 가 있으면 자동으로
    같이 본다. 여기서는 심볼릭 링크 대신 같은 내용의 평범한 파일로 흉내 낸다(git 에 절대경로 링크를 넣을 수
    없다)."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.full = materialize(self.root / "full")     # 이름이 이 도구와 맞는 대조용 원본
        self.raw = self.build_raw_root()

    def build_raw_root(self):
        raw = self.root / "m2-c2-a12-mp1-raw"
        (raw / "logs").mkdir(parents=True)
        for kind in ("stage", "arm", "nav", "stack"):     # 이 넷은 master01·02 이름이 같다 — agg 가 안 필요하다
            shutil.copy(next((self.full / "logs").glob(f"*-{kind}.log")), raw / "logs" / f"20260925-081844-{kind}.log")
        # 관측 스크립트 자기 이름 그대로(agg 없이 이대로 주면 예전엔 이 넷을 못 찾았다)
        shutil.copy(self.full / "boot_check.txt", raw / "boot_check.log")
        shutil.copy(self.full / "up.log", raw / "up.console")
        shutil.copy(self.full / "demo_v2-env.txt", raw / "demo_env.txt")
        run_id = "20260925T073611Z-master02-8b5c01d7"
        shutil.copytree(self.full / "event_run", raw / "event_logger" / run_id)
        for name in ("SUMMARY.txt", "speed.csv", "phase.log", "record_qa.txt", "record_qa_web.txt"):
            shutil.copy(self.full / name, raw / name)     # 이 이름들은 이미 같다 — agg 가 안 필요하다
        # agg/ — 그 팀이 원본에서 절대경로 심볼릭 링크로 만드는 것을 여기서는 평범한 파일로 흉내 낸다
        (raw / "agg").mkdir()
        shutil.copy(self.full / "boot_check.txt", raw / "agg" / "boot_check.txt")
        shutil.copy(self.full / "up.log", raw / "agg" / "up.log")
        shutil.copy(self.full / "demo_v2-env.txt", raw / "agg" / "demo_v2-env.txt")
        shutil.copytree(self.full / "event_run", raw / "agg" / "event_run")
        return raw

    def test_a_root_with_only_agg_naming_still_gives_the_full_values(self):
        got = values(aggregate_runs.aggregate(self.raw, PROTOCOL, attempt=1))
        self.assertEqual(ATTEMPT_1_VALUES, got)

    def test_a_root_without_agg_is_unaffected(self):
        """agg/ 가 없는 root(master01 처럼 이름이 이미 맞는 쪽)는 전과 똑같이 동작한다 — 회귀 없음."""
        got = values(aggregate_runs.aggregate(self.full, PROTOCOL, attempt=1))
        self.assertEqual(ATTEMPT_1_VALUES, got)

    def test_agg_combines_with_a_second_named_correctly_root(self):
        """다중 PC: master01 은 원래 이름 그대로, master02 는 agg/ 로만 찾아 합친 결과가 단일 root 와 같다.
        (self.full·self.raw 는 같은 원본의 사본이라 phase.log 의 '수동 개입' 한 줄이 두 번 잡힌다 — 실제
        회차라면 한쪽에만 있을 값이라 이 metric 만 빼고 대조한다.)"""
        got = values(aggregate_runs.aggregate([self.full, self.raw], PROTOCOL, attempt=1))
        expected = dict(ATTEMPT_1_VALUES, unplanned_intervention_count=2)
        self.assertEqual(expected, got)


class BrokenAggSymlinkTests(unittest.TestCase):
    """campaign3 attempt12 실제 버그(#240, 마클1·마클2): agg/ 의 심볼릭 링크가 절대경로
    (`/home/rokey/markle_tmp/<folder>/event_logger/<run_id>` 등)라 마스터가 그 경로가 아니라 한 단계 더
    들어간 곳(`~/markle_tmp/m2-received/<folder>/`)에 풀면 깨진다 — agg/ 는 디렉터리로 존재하니 Folder 가
    검색 경로에 넣지만, 그 안의 모든 항목이 dangling 이라 event_run·boot_check·up.log·demo_v2-env 전부
    record_missing 이 됐다. Folder 는 이제 raw 이름(FILE_ALIASES)과 event_logger/*/meta.json 을 root 에서
    직접도 찾아, agg/ 가 깨져 있거나 아예 없어도 값이 나와야 한다."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.full = materialize(self.root / "full")

    def build_raw_root(self, with_broken_agg):
        raw = self.root / "m2-c3-a12v4-mp1-a4b1a4e"
        (raw / "logs").mkdir(parents=True)
        for kind in ("stage", "arm", "nav", "stack"):
            shutil.copy(next((self.full / "logs").glob(f"*-{kind}.log")),
                        raw / "logs" / f"20260925-081844-{kind}.log")
        shutil.copy(self.full / "boot_check.txt", raw / "boot_check.log")
        shutil.copy(self.full / "up.log", raw / "up.console")
        shutil.copy(self.full / "demo_v2-env.txt", raw / "demo_env.txt")
        run_id = "20260927T060230Z-master02-d621d3ce"
        shutil.copytree(self.full / "event_run", raw / "event_logger" / run_id)
        for name in ("SUMMARY.txt", "speed.csv", "phase.log", "record_qa.txt", "record_qa_web.txt"):
            shutil.copy(self.full / name, raw / name)
        if with_broken_agg:
            # 실제 버그 그대로: 존재하지 않는 절대경로를 향한 심볼릭 링크(다른 위치에 풀린 것을 흉내낸다)
            wrong_extraction = self.root / "markle_tmp" / "m2-received" / raw.name
            (raw / "agg").mkdir()
            for name, target in (
                ("boot_check.txt", wrong_extraction / "boot_check.log"),
                ("up.log", wrong_extraction / "up.console"),
                ("demo_v2-env.txt", wrong_extraction / "demo_env.txt"),
                ("event_run", wrong_extraction / "event_logger" / run_id),
            ):
                os.symlink(target, raw / "agg" / name)
        return raw

    def test_raw_names_alone_with_no_agg_at_all(self):
        raw = self.build_raw_root(with_broken_agg=False)
        got = values(aggregate_runs.aggregate(raw, PROTOCOL, attempt=1))
        self.assertEqual(ATTEMPT_1_VALUES, got)

    def test_raw_names_survive_a_broken_agg_symlink(self):
        raw = self.build_raw_root(with_broken_agg=True)
        got = values(aggregate_runs.aggregate(raw, PROTOCOL, attempt=1))
        self.assertEqual(ATTEMPT_1_VALUES, got)


class HealthyAggDedupTests(unittest.TestCase):
    """마1검증 리뷰(PR #746, 1026d05) 발견: `_event_dirs()`/`_first_text()`가 raw 별칭과 agg 심볼릭 링크를
    self.paths 의 별개 항목으로 순회하다 보니, agg 가 안 깨졌을 때(정상 케이스)는 같은 물리 파일을 두 번
    찾아 "root N개에 있다" note 가 부풀었다(계산되는 값 자체는 안 바뀌어 기존 값-비교 테스트로는 안 잡혔다).
    실제로 안전한 경우(같은 root 안에서 raw 이름과 agg 심볼릭 링크가 같은 파일을 가리키는 경우)와, 진짜로
    서로 다른 두 host 인 경우를 둘 다 real symlink 로 재현해 note 개수가 물리 host 수와 일치하는지 본다."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.full = materialize(self.root / "full")

    def build_raw_root_with_healthy_agg(self, name):
        raw = self.root / name
        (raw / "logs").mkdir(parents=True)
        for kind in ("stage", "arm", "nav", "stack"):
            shutil.copy(next((self.full / "logs").glob(f"*-{kind}.log")),
                        raw / "logs" / f"20260925-081844-{kind}.log")
        shutil.copy(self.full / "boot_check.txt", raw / "boot_check.log")
        shutil.copy(self.full / "up.log", raw / "up.console")
        shutil.copy(self.full / "demo_v2-env.txt", raw / "demo_env.txt")
        run_id = "20260925T073611Z-master02-8b5c01d7"
        shutil.copytree(self.full / "event_run", raw / "event_logger" / run_id)
        for fname in ("SUMMARY.txt", "speed.csv", "phase.log", "record_qa.txt", "record_qa_web.txt"):
            shutil.copy(self.full / fname, raw / fname)
        (raw / "agg").mkdir()
        os.symlink(raw / "boot_check.log", raw / "agg" / "boot_check.txt")
        os.symlink(raw / "up.console", raw / "agg" / "up.log")
        os.symlink(raw / "demo_env.txt", raw / "agg" / "demo_v2-env.txt")
        os.symlink(raw / "event_logger" / run_id, raw / "agg" / "event_run")
        return raw

    def test_a_healthy_agg_symlinking_its_own_root_counts_as_one_host(self):
        raw = self.build_raw_root_with_healthy_agg("m2-c3-healthy-agg")
        result = aggregate_runs.aggregate(raw, PROTOCOL, attempt=1)
        got = values(result)
        self.assertEqual(ATTEMPT_1_VALUES, got)
        inflated = [n for n in result["notes"] if "root 2개" in n or "root 3개" in n]
        self.assertEqual([], inflated, result["notes"])

    def test_two_real_hosts_still_get_a_two_root_note(self):
        raw1 = self.build_raw_root_with_healthy_agg("m2-c3-healthy-agg-host1")
        raw2 = self.build_raw_root_with_healthy_agg("m2-c3-healthy-agg-host2")
        result = aggregate_runs.aggregate([raw1, raw2], PROTOCOL, attempt=1)
        note_texts = " / ".join(result["notes"])
        self.assertIn("root 2개", note_texts)
        self.assertNotIn("root 3개", note_texts)
        self.assertNotIn("root 4개", note_texts)


if __name__ == "__main__":
    unittest.main()
