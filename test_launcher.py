"""Preferences, compatibility and real child-process lifecycle, no hardware."""
from contextlib import redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import launcher_settings as settings
from launcher_process import SessionRunner
from session_control import SessionControl, PREFIX
from hand_tracker import arguments


class SettingsTests(unittest.TestCase):
    def test_defaults_launch_preview_paused_and_full_frame(self):
        args = arguments(settings.to_argv(settings.defaults()))
        self.assertTrue(args.motor_preview)
        self.assertFalse(args.start_armed)
        self.assertTrue(args.full_frame)
        self.assertEqual(args.microsteps, 1)

    def test_all_axis_values_and_modes_use_existing_validation(self):
        s = settings.defaults()
        s.update(mode='manual', output='motor', port='COM12', control_hand='left',
                 smooth=True, mirror=False, full_frame=False)
        s['axes']['x'].update(position_min='-45', position_max='120', manual_speed='180',
                              acceleration='300', reverse=True)
        args = arguments(settings.to_argv(s))
        self.assertEqual((args.speed, args.acceleration, args.motor_port), (180, 300, 'COM12'))
        self.assertTrue(args.reverse_motor)
        self.assertTrue(args.no_mirror)
        self.assertFalse(args.full_frame)

    def test_invalid_port_and_ranges_rejected_before_start(self):
        s = settings.defaults()
        s['output'] = 'motor'
        with self.assertRaisesRegex(ValueError, 'port'):
            settings.to_argv(s)
        s.update(output='preview')
        s['axes']['x']['position_min'] = '1'
        with self.assertRaisesRegex(ValueError, 'straddle'):
            settings.to_argv(s)
        s['axes']['x'].update(position_min='-90', manual_speed='nan')
        s['mode'] = 'manual'
        with self.assertRaises(ValueError):
            settings.to_argv(s)

    def test_saved_overrides_roundtrip_and_new_config_defaults_flow_through(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'prefs.json'
            s = settings.defaults()
            s['camera'] = '2'
            s['axes']['x']['position_min'] = '-45'
            settings.save(path, s)
            self.assertEqual(settings.load(path), s)
            payload = json.loads(path.read_text())
            self.assertNotIn('manual_speed', payload['settings']['axes']['x'])
            with patch.object(settings.config, 'MANUAL_SPEED_DEGREES_S', 60):
                loaded = settings.load(path)
            self.assertEqual(loaded['axes']['x']['manual_speed'], '60')
            self.assertEqual(loaded['axes']['x']['position_min'], '-45')
            self.assertFalse(path.with_suffix('.json.tmp').exists())

    def test_reset_saves_empty_overrides(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'prefs.json'
            settings.save(path, settings.defaults())
            self.assertEqual(json.loads(path.read_text())['settings'], {})

    def test_bad_saved_data_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'prefs.json'
            for content in ('broken', '{"version":2,"settings":{}}',
                            '{"version":1,"settings":{"smooth":"false"}}',
                            '{"version":1,"settings":{"axes":{"y":{}}}}'):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    settings.load(path)
                self.assertEqual(path.read_text(), content)

    def test_original_cli_defaults_unchanged(self):
        args = arguments([])
        self.assertFalse(args.full_frame)
        self.assertFalse(args.launcher_control)
        self.assertFalse(args.start_armed)
        self.assertEqual(args.mode, 'position')


class ChannelTests(unittest.TestCase):
    def test_only_quit_and_parent_pipe_closure_can_stop(self):
        channel = SessionControl(StringIO('MOVE 999\nQUIT\n'), StringIO())
        channel.thread.join(timeout=1)
        self.assertTrue(channel.quit_requested())
        eof = SessionControl(StringIO(''), StringIO())
        eof.thread.join(timeout=1)
        self.assertTrue(eof.quit_requested())

    def test_status_is_structured(self):
        output = StringIO()
        channel = SessionControl(StringIO(''), output)
        channel.report('paused', motor=False, mode='manual')
        data = json.loads(output.getvalue().removeprefix(PREFIX))
        self.assertEqual(data, {'state': 'paused', 'motor': False, 'mode': 'manual'})


class ProcessTests(unittest.TestCase):
    def test_real_camera_free_preview_start_and_graceful_stop(self):
        try:
            import pygame
        except ImportError:
            self.skipTest('pygame-ce required')
        runner = SessionRunner()
        s = settings.defaults()
        s['mode'] = 'manual'
        with patch.dict('os.environ', {'SDL_VIDEODRIVER': 'dummy', 'PYGAME_HIDE_SUPPORT_PROMPT': '1'}):
            runner.start(settings.to_argv(s), Path(__file__).parent)
        try:
            with self.assertRaises(ValueError):
                runner.start([], Path(__file__).parent)
            updates = []
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                updates.extend(runner.poll())
                if any(u['state'] == 'paused' for u in updates) or not runner.running:
                    break
                time.sleep(.02)
            self.assertTrue(any(u['state'] == 'paused' and not u['motor'] for u in updates), runner.log)
            runner.stop()
            deadline = time.monotonic() + 5
            while runner.running and time.monotonic() < deadline:
                updates.extend(runner.poll())
                time.sleep(.02)
            self.assertFalse(runner.running)
            ended = [u for u in updates if u['state'] == 'ended']
            self.assertEqual(ended[0]['code'], 0)
            self.assertFalse(runner.terminated)
        finally:
            if runner.process:
                runner.process.kill()
                runner.process.wait(timeout=2)


if __name__ == '__main__':
    unittest.main()
