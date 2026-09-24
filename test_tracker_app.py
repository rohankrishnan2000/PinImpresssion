"""Exercise the actual event loop without camera or motor hardware."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
import unittest
from unittest.mock import patch
try:
    import pygame as pg
except ImportError:
    pg = None
import hand_tracker as app


class FakeMotor:
    def __init__(self, *args):
        self.commands = []
        self.closed = False

    def update(self, command, **kwargs):
        self.commands.append(('hold' if command.target_degrees is None else 'target', command.target_degrees))

    def spin(self, speed):
        self.commands.append(('speed', speed))

    def close(self):
        self.closed = True


@unittest.skipIf(pg is None, 'pygame-ce required for event-loop tests')
class AppTests(unittest.TestCase):
    def run_frames(self, frames, extra=()):
        motor = FakeMotor()
        args = app.arguments(['--mode', 'manual', '--motor-port', 'TEST', *extra])
        with patch.object(app, 'UnoMotor', return_value=motor), \
             patch.object(app, 'Camera', side_effect=AssertionError('manual opened camera')), \
             patch.object(pg.event, 'get', side_effect=frames):
            app.run(args)
        self.assertTrue(motor.closed)
        return motor.commands

    def test_key_release_focus_loss_and_rearm(self):
        down = lambda key: pg.event.Event(pg.KEYDOWN, key=key, repeat=False)
        up = lambda key: pg.event.Event(pg.KEYUP, key=key)
        commands = self.run_frames([
            [down(pg.K_a)],                       # paused: ignored
            [down(pg.K_m), down(pg.K_a)],         # arm and rotate
            [up(pg.K_a)],                         # release holds immediately
            [down(pg.K_d)],                       # rotate other direction
            [pg.event.Event(pg.WINDOWFOCUSLOST)],  # clears held keys and pauses
            [down(pg.K_d)],                       # still paused
            [down(pg.K_m)],                       # rearm does not revive D
            [down(pg.K_w), down(pg.K_s)],          # reserved
            [pg.event.Event(pg.QUIT)],
        ])
        self.assertEqual([c for c in commands if c[0] == 'speed'], [('speed', -90), ('speed', 90)])
        self.assertEqual(commands[-1], ('hold', None))

    def test_both_keys_stop_and_repeat_does_not_rearm(self):
        down = lambda key, repeat=False: pg.event.Event(pg.KEYDOWN, key=key, repeat=repeat)
        commands = self.run_frames([
            [down(pg.K_a)], [down(pg.K_d)],
            [down(pg.K_m)], [down(pg.K_m, True)], [pg.event.Event(pg.QUIT)],
        ], ['--start-armed'])
        self.assertEqual(commands[0], ('speed', -90))
        self.assertTrue(all(c[0] == 'hold' for c in commands[1:]))

    def test_position_events_boundary_save_and_filter_toggle(self):
        import numpy as np
        import tempfile
        from pathlib import Path
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        motor = FakeMotor()
        class FakeCamera:
            def __init__(self, *args):
                pass
            def read(self):
                return frame, [('Right', (.5, .5))]
        down = lambda key: pg.event.Event(pg.KEYDOWN, key=key, repeat=False)
        with tempfile.TemporaryDirectory() as directory:
            boundary_path = Path(directory) / 'boundary.json'
            args = app.arguments(['--motor-port', 'TEST', '--boundary-file', str(boundary_path)])
            with patch.object(app, 'UnoMotor', return_value=motor), \
                 patch.object(app, 'Camera', FakeCamera), \
                 patch.object(pg.event, 'get', side_effect=[
                     [],  # first render establishes the camera viewport
                     [down(pg.K_b),
                      pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=(100, 250)),
                      pg.event.Event(pg.MOUSEBUTTONUP, button=1, pos=(600, 500))],
                     [down(pg.K_m), down(pg.K_f)],
                     [down(pg.K_f)],
                     [pg.event.Event(pg.QUIT)],
                 ]):
                app.run(args)
            saved = app.Boundary.load(boundary_path, True)
            self.assertTrue(saved.contains((.5, .5)))
            expected = app.BoundedPositionMapper(saved).command((.5, .5)).target_degrees
            targets = [c[1] for c in motor.commands if c[0] == 'target']
            self.assertEqual(targets, [expected, expected])
            self.assertTrue(all(c[0] == 'hold' for c in motor.commands[:-2]))
            self.assertTrue(motor.closed)

    def test_camera_failure_closes_motor(self):
        motor = FakeMotor()
        class BrokenCamera:
            def __init__(self, *args):
                pass
            def read(self):
                raise ValueError('camera disconnected')
        args = app.arguments(['--motor-port', 'TEST'])
        with patch.object(app, 'UnoMotor', return_value=motor), \
             patch.object(app, 'Camera', BrokenCamera), \
             patch.object(pg.event, 'get', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'camera disconnected'):
                app.run(args)
        self.assertTrue(motor.closed)

    def test_position_default_and_optional_smoothing(self):
        args = app.arguments([])
        self.assertEqual(args.mode, 'position')
        self.assertFalse(args.smooth)
        self.assertEqual(args.microsteps, 1)
        self.assertTrue(app.arguments(['--smooth']).smooth)


if __name__ == '__main__':
    unittest.main()
