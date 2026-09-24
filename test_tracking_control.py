import json
from pathlib import Path
import tempfile
import unittest
from tracking_control import (Boundary, BoundedPositionMapper, ManualKeys,
                              point_in_view, select_hand)


class BoundaryTests(unittest.TestCase):
    def test_left_center_right_and_intermediates(self):
        mapper = BoundedPositionMapper(Boundary(.2, .2, .8, .8), -60, 120)
        for x, target in ((.2, -60), (.35, -30), (.5, 0), (.65, 60), (.8, 120)):
            self.assertAlmostEqual(mapper.command((x, .5)).target_degrees, target)

    def test_holding_hand_still_does_not_integrate_motion(self):
        mapper = BoundedPositionMapper(Boundary())
        targets = [mapper.command((.7, .5)).target_degrees for _ in range(1000)]
        self.assertEqual(min(targets), max(targets))

    def test_vertical_motion_does_not_change_x_target(self):
        mapper = BoundedPositionMapper(Boundary())
        self.assertEqual(mapper.command((.6, .2)), mapper.command((.6, .8)))

    def test_raw_outside_or_lost_holds_even_with_inside_filtered_point(self):
        mapper = BoundedPositionMapper(Boundary())
        for point in (None, (.1, .5), (.9, .5), (.5, .1), (.5, .9), (float('nan'), .5)):
            self.assertIsNone(mapper.command(point, (.5, .5)).target_degrees)

    def test_filtered_overshoot_clamps_and_reverse_preserves_asymmetric_range(self):
        mapper = BoundedPositionMapper(Boundary(), -60, 120, reverse=True)
        self.assertEqual(mapper.command((.2, .5), (-1, .5)).target_degrees, 120)
        self.assertEqual(mapper.command((.8, .5), (2, .5)).target_degrees, -60)

    def test_reacquisition_uses_original_absolute_mapping(self):
        mapper = BoundedPositionMapper(Boundary())
        before = mapper.command((.7, .5))
        mapper.command(None)
        self.assertEqual(before, mapper.command((.7, .5)))

    def test_save_load_resolution_independent_and_mirror_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'boundary.json'
            boundary = Boundary.from_drag((.8, .9), (.1, .2))
            boundary.save(path, True)
            self.assertEqual(boundary, Boundary.load(path, True))
            with self.assertRaises(ValueError):
                Boundary.load(path, False)
            self.assertFalse(path.with_suffix('.json.tmp').exists())
            path.write_text(json.dumps({'version': 1, 'mirrored': True, 'rect': [0, 0, 0, 1]}))
            with self.assertRaises(ValueError):
                Boundary.load(path, True)

    def test_bad_rectangles_and_motor_ranges_rejected(self):
        for rect in ((0, 0, .01, 1), (1, 0, 0, 1), (-.1, 0, 1, 1), (0, 0, float('nan'), 1)):
            with self.assertRaises(ValueError):
                Boundary(*rect)
        for lo, hi, speed in ((0, 90, 90), (-90, -1, 90), (-90, 90, 0), (-90, float('inf'), 90)):
            with self.assertRaises(ValueError):
                BoundedPositionMapper(Boundary(), lo, hi, speed)

    def test_missing_or_duplicate_selected_hand_holds(self):
        self.assertIsNone(select_hand([('Left', (.2, .5))], 'right'))
        self.assertIsNone(select_hand([('Right', (.2, .5)), ('Right', (.7, .5))], 'right'))
        self.assertEqual(select_hand([('Left', (.1, .2)), ('Right', (.7, .5))], 'right'), (.7, .5))

    def test_letterboxing_and_drag_coordinates(self):
        rect = (20, 100, 800, 450)
        self.assertEqual(point_in_view((420, 325), rect), (.5, .5))
        self.assertIsNone(point_in_view((420, 50), rect))
        self.assertEqual(point_in_view((900, 600), rect, clamp=True), (1, 1))
        # Same location after a 2x resize.
        self.assertEqual(point_in_view((840, 650), (40, 200, 1600, 900)), (.5, .5))


class ManualTests(unittest.TestCase):
    def test_hold_release_both_and_reverse(self):
        keys = ManualKeys()
        keys.press('a')
        self.assertEqual(keys.speed(90), -90)
        self.assertEqual(keys.speed(90, reverse=True), 90)
        keys.press('d')
        self.assertEqual(keys.speed(90), 0)
        keys.release('a')
        self.assertEqual(keys.speed(90), 90)
        keys.release('d')
        self.assertEqual(keys.speed(90), 0)

    def test_reserved_keys_clear_and_repeats(self):
        keys = ManualKeys()
        for key in ('w', 's', 'a', 'a'):
            keys.press(key)
        keys.release('a')
        self.assertEqual(keys.speed(90), 0)
        keys.press('d')
        keys.clear()
        self.assertEqual(keys.speed(90), 0)


if __name__ == '__main__':
    unittest.main()
