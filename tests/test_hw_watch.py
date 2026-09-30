"""hw_watch: nvidia-smi 를 흉내 낸 러너로 돈다. 실제 GPU 는 없이 돈다."""

import csv
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("hw_watch", SOURCE / "tools/hw_watch.py")
hw_watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hw_watch)

#: 0x20 = SW Thermal Slowdown — 늘 경보 대상(마클1 9/27 실측: 85→88 °C 오르며 0x20→0x4 로 걸렸다).
FULL_ROW = "2026-09-27 13:51:29, 67.23, 80.00, 80.00, 48, 7512, 1672, 85, 0x0000000000000020"
FULL_ROW_OK = "2026-09-27 13:51:29, 67.23, 80.00, 80.00, 48, 7512, 1672, 77, 0x0000000000000000"
#: 0x4 = SW power cap. 마1검증 9/27 실측(86 °C, 만부하 정상 동작) — 전력이 상한 근처면 조용해야 한다.
FULL_ROW_POWER_CAP = "2026-09-27 13:51:29, 67.23, 80.00, 80.00, 48, 7512, 1672, 86, 0x0000000000000004"


def fixed_runner(rows, probe_row=FULL_ROW_OK):
    """probe_fields 의 확인 호출을 `probe_row` 로 한 번 받아내고, 그 뒤 루프 호출마다 `rows` 를 하나씩 낸다.
    `rows` 가 다 떨어지면 마지막 값을 되풀이한다(loop 가 count 보다 더 부를 일은 없지만 방어적으로 둔다)."""
    calls = iter([probe_row, *rows])

    def runner(fields, timeout=10):
        row = next(calls, rows[-1] if rows else probe_row)
        return True, row + "\n", ""
    return runner


class ProbeFieldsTests(unittest.TestCase):
    def test_all_fields_accepted_on_the_first_try(self):
        calls = []

        def runner(fields, timeout=10):
            calls.append(list(fields))
            return True, FULL_ROW_OK + "\n", ""

        fields = hw_watch.probe_fields(runner)
        self.assertEqual(hw_watch.PREFERRED_FIELDS, fields)
        self.assertEqual(1, len(calls))

    def test_a_rejected_field_is_dropped(self):
        """마클1 9/27: enforced.power.limit 자체를 이 드라이버가 거부한다."""
        attempts = []

        def runner(fields, timeout=10):
            attempts.append(list(fields))
            if "enforced.power.limit" in fields:
                return False, "", 'Field "enforced.power.limit" is not a valid field to query.'
            return True, "ok\n", ""

        fields = hw_watch.probe_fields(runner)
        self.assertNotIn("enforced.power.limit", fields)
        self.assertIn("power.limit", fields)          # 겹치는 이름 때문에 같이 빠지면 안 된다
        self.assertEqual(2, len(attempts))

    def test_a_renamed_field_falls_back_to_its_alias(self):
        """일부 드라이버는 clocks_throttle_reasons.active 대신 clocks_event_reasons.active 만 받는다."""

        def runner(fields, timeout=10):
            if "clocks_throttle_reasons.active" in fields:
                return False, "", 'Field "clocks_throttle_reasons.active" is not a valid field to query.'
            return True, "ok\n", ""

        fields = hw_watch.probe_fields(runner)
        self.assertNotIn("clocks_throttle_reasons.active", fields)
        self.assertIn("clocks_event_reasons.active", fields)

    def test_no_nvidia_smi_at_all_falls_back_to_timestamp_only(self):
        def runner(fields, timeout=10):
            return False, "", "nvidia-smi 없음"

        self.assertEqual(["timestamp"], hw_watch.probe_fields(runner))


class ParseRowTests(unittest.TestCase):
    def test_numeric_fields_are_floats_and_na_is_none(self):
        row = hw_watch.parse_row("2026-09-27 13:51:29, 67.23, [N/A], 80.00, 48, 7512, 1672, 85, 0x4",
                                 hw_watch.PREFERRED_FIELDS)
        self.assertEqual(67.23, row["power.draw"])
        self.assertIsNone(row["power.limit"])
        self.assertEqual("0x4", row["clocks_throttle_reasons.active"])

    def test_wrong_column_count_is_none(self):
        self.assertIsNone(hw_watch.parse_row("67.23, 80.00", hw_watch.PREFERRED_FIELDS))


class ThrottledTests(unittest.TestCase):
    def test_zero_mask_is_not_throttled(self):
        row = hw_watch.parse_row(FULL_ROW_OK, hw_watch.PREFERRED_FIELDS)
        self.assertFalse(hw_watch.throttled(row))

    def test_nonzero_mask_is_throttled(self):
        row = hw_watch.parse_row(FULL_ROW, hw_watch.PREFERRED_FIELDS)
        self.assertTrue(hw_watch.throttled(row))

    def test_missing_field_is_unknown(self):
        self.assertIsNone(hw_watch.throttled({}))


class JudgeTests(unittest.TestCase):
    def row(self, temp, mask="0x0000000000000000", draw=67.23, limit=80.00):
        text = (f"2026-09-27 13:51:29, {draw}, {limit:.2f}, {limit:.2f}, 48, 7512, 1672, {temp}, {mask}")
        return hw_watch.parse_row(text, hw_watch.PREFERRED_FIELDS)

    def test_an_always_warn_bit_warns_regardless_of_temperature_or_power(self):
        """0x20(SW thermal), 0x8/0x40/0x80(HW slowdown·열·power brake) 는 늘 경보다."""
        for mask in ("0x0000000000000008", "0x0000000000000020", "0x0000000000000040", "0x0000000000000080"):
            with self.subTest(mask=mask):
                warnings = hw_watch.judge(self.row(70, mask=mask), [], None, 0.3, 40.0)
                self.assertTrue(any("스로틀" in w for w in warnings))

    def test_gpu_idle_bit_alone_is_quiet(self):
        """0x1(GPU idle)은 유휴 GPU 가 항상 켜는 비트다 — 무해하다."""
        self.assertEqual([], hw_watch.judge(self.row(45, mask="0x0000000000000001", draw=5.0), [], None, 0.3, 40.0))

    def test_sw_power_cap_at_normal_draw_is_quiet(self):
        """0x4(SW power cap)는 상한에 닿은 정상 만부하에서 늘 켜진다(마1검증 9/27 실측: 86 °C·0x4·정상)."""
        row = self.row(86, mask="0x0000000000000004", draw=79.5, limit=80.0)
        self.assertEqual([], hw_watch.judge(row, [], None, 0.3, 40.0, power_limit_expected_w=80.0))

    def test_sw_power_cap_with_draw_far_under_the_limit_warns(self):
        """0x4 인데 전력이 상한의 절반 밑이면 진짜 이상이다."""
        row = self.row(86, mask="0x0000000000000004", draw=20.0, limit=80.0)
        warnings = hw_watch.judge(row, [], None, 0.3, 40.0, power_limit_expected_w=80.0)
        self.assertTrue(any("절반" in w for w in warnings))

    def test_sw_power_cap_with_a_wrong_limit_warns(self):
        """0x4 인데 상한 자체가 기대값과 다르면(예: 60 W 로 잘못 잡힘) 경보한다."""
        row = self.row(86, mask="0x0000000000000004", draw=59.0, limit=60.0)
        warnings = hw_watch.judge(row, [], None, 0.3, 40.0, power_limit_expected_w=80.0)
        self.assertTrue(any("기대값" in w for w in warnings))

    def test_no_power_limit_check_silences_the_sw_power_cap_branch_entirely(self):
        """마1검증 9/27 비차단 관찰: --power-limit-expected 를 안 주면(--no-power-limit-check) 0x4 판정을
        전부 끈다 — GPU 자기 신고 상한을 기준 삼아 절반-미만 판정을 몰래 계속하지 않는다."""
        row = self.row(86, mask="0x0000000000000004", draw=1.0, limit=80.0)  # 전력이 거의 0 이어도
        self.assertEqual([], hw_watch.judge(row, [], None, 0.3, 40.0, power_limit_expected_w=None))

    def test_an_unknown_bit_warns_defensively(self):
        row = self.row(70, mask="0x0000000000000002")  # 목록에 없는 비트(ApplicationsClocksSetting)
        warnings = hw_watch.judge(row, [], None, 0.3, 40.0)
        self.assertTrue(any("알려지지 않은" in w for w in warnings))

    def test_high_temperature_without_throttle_bit_still_warns(self):
        warnings = hw_watch.judge(self.row(88), [], None, 0.3, 40.0)
        self.assertTrue(any("87" in w for w in warnings))

    def test_normal_temperature_and_mask_is_quiet(self):
        self.assertEqual([], hw_watch.judge(self.row(77), [], None, 0.3, 40.0))

    def test_a_sudden_power_drop_after_a_steady_high_median_warns(self):
        """9/27 master01 미스터리(80 W 대 → 15 W)를 본뜬 시험."""
        history = [self.row(77, draw=70.0) for _ in range(5)]
        warnings = hw_watch.judge(self.row(77, draw=15.0), history, None, 0.3, 40.0)
        self.assertTrue(any("급락" in w for w in warnings))

    def test_a_low_draw_while_idle_does_not_warn(self):
        """평소 유휴 6 W 대인 장비는 급락 기준(중앙값 40 W 이상)에 안 걸린다."""
        history = [self.row(45, draw=6.0) for _ in range(5)]
        warnings = hw_watch.judge(self.row(45, draw=5.5), history, None, 0.3, 40.0)
        self.assertEqual([], warnings)

    def test_power_limit_far_from_expected_warns(self):
        warnings = hw_watch.judge(self.row(70), [], None, 0.3, 40.0, power_limit_expected_w=60.0,
                                  power_limit_tolerance_w=3.0)  # row 의 power.limit 은 80.00, 기대 60 과 다르다
        self.assertTrue(any("기대값" in w for w in warnings))

    def test_power_limit_matching_expected_is_quiet(self):
        self.assertEqual([], hw_watch.judge(self.row(70), [], None, 0.3, 40.0, power_limit_expected_w=80.0,
                                            power_limit_tolerance_w=3.0))

    def test_power_limit_uses_the_text_fallback_when_the_csv_field_is_missing(self):
        """마클1 9/27 master01: power.limit·enforced.power.limit 필드가 아예 없다(probe 가 뺐다) —
        -q -d POWER 로 미리 잰 값을 대신 판정에 쓴다."""
        row = dict(self.row(70))
        row["power.limit"] = None
        row["enforced.power.limit"] = None
        warnings = hw_watch.judge(row, [], None, 0.3, 40.0, power_limit_expected_w=80.0,
                                  power_limit_tolerance_w=3.0, power_limit_text_fallback_w=15.0)
        self.assertTrue(any("15" in w and "POWER 파싱" in w for w in warnings))

    def test_rtf_below_minimum_warns(self):
        warnings = hw_watch.judge(self.row(70), [], None, 0.3, 40.0, rtf=0.09, rtf_min=0.5)
        self.assertTrue(any("rtf" in w for w in warnings))

    def test_rtf_at_or_above_minimum_is_quiet(self):
        self.assertEqual([], hw_watch.judge(self.row(70), [], None, 0.3, 40.0, rtf=0.9, rtf_min=0.5))

    def test_load_over_twice_the_baseline_warns(self):
        original = hw_watch.boot_check.read_load
        hw_watch.boot_check.read_load = lambda: 20.0
        try:
            warnings = hw_watch.judge(self.row(70), [], 8.4, 0.3, 40.0)
        finally:
            hw_watch.boot_check.read_load = original
        self.assertTrue(any("load" in w for w in warnings))


class PowerLimitTextTests(unittest.TestCase):
    def test_parses_the_watt_value(self):
        text = "    Power Readings\n        Current Power Limit         : 80.00 W\n"
        self.assertEqual(80.0, hw_watch.power_limit_from_text(text))

    def test_missing_line_is_none(self):
        self.assertIsNone(hw_watch.power_limit_from_text("아무것도 없음"))

    def test_effective_prefers_the_csv_field_over_the_fallback(self):
        row = {"enforced.power.limit": 80.0, "power.limit": 80.0}
        self.assertEqual((80.0, "enforced.power.limit"), hw_watch.effective_power_limit(row, 15.0))

    def test_effective_uses_the_fallback_when_both_csv_fields_are_missing(self):
        row = {"enforced.power.limit": None, "power.limit": None}
        self.assertEqual((15.0, "-q -d POWER 파싱"), hw_watch.effective_power_limit(row, 15.0))

    def test_effective_is_none_with_nothing_available(self):
        self.assertEqual((None, None), hw_watch.effective_power_limit({}, None))


class LatestRtfTests(unittest.TestCase):
    def test_reads_the_last_rtf_in_the_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stage.log"
            path.write_text("[pharmacy_stage] spawn index=0\n"
                            "[pharmacy_stage] stop reason=sigint updates=1 wall_s=1 loop_hz=1 sim_s=1 rtf=0.627\n")
            self.assertEqual(0.627, hw_watch.latest_rtf(str(path)))

    def test_a_round_still_running_has_no_rtf_yet(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stage.log"
            path.write_text("[pharmacy_stage] spawn index=0\n")
            self.assertIsNone(hw_watch.latest_rtf(str(path)))

    def test_a_missing_file_is_none(self):
        self.assertIsNone(hw_watch.latest_rtf("/no/such/file.log"))


class WatchLoopTests(unittest.TestCase):
    def run_watch(self, rows, **overrides):
        args = hw_watch.argparse.Namespace(
            load_baseline=None, gpu_csv=None, interval=0.0, once=False, count=len(rows), duration=None,
            history=12, power_drop_ratio=0.3, power_drop_min_w=40.0, stale_every=0, web=None,
            max_recorders=1, tmux_prefix="p3v2-", temp_limit=87.0, power_limit_expected=None,
            power_limit_tolerance=3.0, rtf_min=None, stage_log=None)
        for key, value in overrides.items():
            setattr(args, key, value)
        out = io.StringIO()
        runner = fixed_runner(rows)
        sleeps = []
        hw_watch.watch(args, runner=runner, sleep=sleeps.append, clock=lambda: 0.0, out=out)
        return out.getvalue(), sleeps

    def test_quiet_when_every_sample_is_normal(self):
        text, _ = self.run_watch([FULL_ROW_OK, FULL_ROW_OK])
        self.assertNotIn("WARN", text)

    def test_one_warn_line_per_bad_sample(self):
        text, _ = self.run_watch([FULL_ROW_OK, FULL_ROW])
        self.assertEqual(1, text.count("WARN"))
        self.assertIn("스로틀", text)

    def test_writes_a_csv_with_a_header_once(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "gpu.csv"
            self.run_watch([FULL_ROW_OK, FULL_ROW_OK], gpu_csv=str(path))
            with path.open() as handle:
                rows = list(csv.reader(handle))
        self.assertEqual(hw_watch.PREFERRED_FIELDS, rows[0])
        self.assertEqual(3, len(rows))  # header + 2 samples

    def test_appends_to_an_existing_csv_without_a_second_header(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "gpu.csv"
            self.run_watch([FULL_ROW_OK], gpu_csv=str(path))
            self.run_watch([FULL_ROW_OK], gpu_csv=str(path))
            with path.open() as handle:
                rows = list(csv.reader(handle))
        self.assertEqual(1, sum(1 for row in rows if row == hw_watch.PREFERRED_FIELDS))
        self.assertEqual(3, len(rows))

    def test_once_stops_after_a_single_sample(self):
        text, sleeps = self.run_watch([FULL_ROW_OK, FULL_ROW_OK], once=True, count=None)
        self.assertEqual(0, len(sleeps))

    def test_dropped_field_is_announced_once(self):
        def runner(fields, timeout=10):
            if "enforced.power.limit" in fields:
                return False, "", 'Field "enforced.power.limit" is not a valid field to query.'
            row = ", ".join("0" if f != "timestamp" else "t" for f in fields)
            return True, row + "\n", ""

        args = hw_watch.argparse.Namespace(
            load_baseline=None, gpu_csv=None, interval=0.0, once=True, count=None, duration=None,
            history=12, power_drop_ratio=0.3, power_drop_min_w=40.0, stale_every=0, web=None,
            max_recorders=1, tmux_prefix="p3v2-", temp_limit=87.0, power_limit_expected=None,
            power_limit_tolerance=3.0, rtf_min=None, stage_log=None)
        out = io.StringIO()
        hw_watch.watch(args, runner=runner, sleep=lambda s: None, clock=lambda: 0.0, out=out)
        self.assertIn("enforced.power.limit", out.getvalue())

    def test_stale_every_calls_boot_check_stale(self):
        original = hw_watch.boot_check.check_stale
        hw_watch.boot_check.check_stale = lambda args: (False, "관제 창 3개")
        try:
            text, _ = self.run_watch([FULL_ROW_OK, FULL_ROW_OK], stale_every=1)
        finally:
            hw_watch.boot_check.check_stale = original
        self.assertIn("잔류: 관제 창 3개", text)

    def test_stale_check_never_sees_a_load_baseline(self):
        """작전 9/27 지적: 회차 도중 --stale-every 를 켜면 그 회차 자신의 정상 부하가 load_baseline 의
        2 배를 넘어 '잔류' 로 잘못 읽힐 수 있다. load 는 stale_warning() 이 애초에 boot_check.check_stale 에
        넘기지 않는다(judge() 가 이미 따로, 옳게 이름 붙여 본다) — 여기서 그걸 코드로 확인한다."""
        seen = []
        original = hw_watch.boot_check.check_stale
        hw_watch.boot_check.check_stale = lambda args: (seen.append(args.load_baseline), (True, ""))[-1]
        try:
            self.run_watch([FULL_ROW_OK, FULL_ROW_OK], stale_every=1, load_baseline=8.4)
        finally:
            hw_watch.boot_check.check_stale = original
        self.assertEqual([None, None], seen)

    def test_rtf_from_stage_log_warns_once_then_stays_quiet(self):
        """stop 줄이 그대로 남아 있는 동안 매 표본 다시 경보하지 않는다 — 값이 바뀔 때만."""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stage.log"
            path.write_text("[pharmacy_stage] stop reason=sigint rtf=0.090\n")
            text, _ = self.run_watch([FULL_ROW_OK, FULL_ROW_OK, FULL_ROW_OK],
                                     stage_log=str(path), rtf_min=0.5)
        self.assertEqual(1, text.count("rtf"))

    def test_power_limit_fallback_is_probed_once_at_startup_when_the_csv_field_is_missing(self):
        calls = []

        def runner(fields, timeout=10):
            if "power.limit" in fields:
                return False, "", 'Field "power.limit" is not a valid field to query.'
            if "enforced.power.limit" in fields:
                return False, "", 'Field "enforced.power.limit" is not a valid field to query.'
            row = ", ".join("0" if f != "timestamp" else "t" for f in fields)
            return True, row + "\n", ""

        def power_query():
            calls.append(1)
            return True, "Current Power Limit         : 80.00 W\n", ""

        args = hw_watch.argparse.Namespace(
            load_baseline=None, gpu_csv=None, interval=0.0, once=True, count=None, duration=None,
            history=12, power_drop_ratio=0.3, power_drop_min_w=40.0, stale_every=0, web=None,
            max_recorders=1, tmux_prefix="p3v2-", temp_limit=87.0, power_limit_expected=80.0,
            power_limit_tolerance=3.0, rtf_min=None, stage_log=None)
        hw_watch.watch(args, runner=runner, sleep=lambda s: None, clock=lambda: 0.0, out=io.StringIO(),
                       power_query=power_query)
        self.assertEqual(1, len(calls))


if __name__ == "__main__":
    unittest.main()
