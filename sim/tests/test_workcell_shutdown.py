"""SIGINT must finish the probe while the stage is still available."""
import os
from pathlib import Path
import signal
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'standalone'))
from hospital_workcell_demo import run_review_loop  # noqa: E402


class ReviewShutdownTest(unittest.TestCase):
    def test_sigint_records_before_closing_kit_and_restores_handler(self):
        events = []
        app, probe = Mock(), Mock()
        app.is_running.return_value = True
        probe.step.side_effect = lambda: os.kill(os.getpid(), signal.SIGINT)
        probe.abort.side_effect = lambda: events.append('result')
        probe.log.close.side_effect = lambda: events.append('log closed')
        app.close.side_effect = lambda: events.append('Kit closed')
        previous = signal.getsignal(signal.SIGINT)
        run_review_loop(app, probe=probe)
        self.assertEqual(events, ['result', 'log closed', 'Kit closed'])
        self.assertEqual(signal.getsignal(signal.SIGINT), previous)
        probe.step.assert_called_once()

    def test_result_write_failure_still_closes_log_and_kit(self):
        app, probe = Mock(), Mock()
        app.is_running.return_value = False
        probe.abort.side_effect = OSError('disk full')
        previous = signal.getsignal(signal.SIGINT)
        with self.assertRaisesRegex(OSError, 'disk full'):
            run_review_loop(app, probe=probe)
        probe.log.close.assert_called_once()
        app.close.assert_called_once()
        self.assertEqual(signal.getsignal(signal.SIGINT), previous)
