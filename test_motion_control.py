import math
import unittest

from motion_control import HorizontalMotorMapper, select_control_x


class MotionControlTests(unittest.TestCase):
    def test_position_follows_hand_without_accumulating_rotation(self):
        mapper = HorizontalMotorMapper(degrees_per_pixel=0.2)
        for x, expected in [(0, 0), (100, 20), (100, 20), (-50, -10), (0, 0)]:
            self.assertAlmostEqual(mapper.command(x).target_degrees, expected)

    def test_speed_coefficient_does_not_change_destination(self):
        slow = HorizontalMotorMapper(speed_factor=0.5).command(100)
        fast = HorizontalMotorMapper(speed_factor=2).command(100)
        self.assertEqual(slow.target_degrees, fast.target_degrees)
        self.assertEqual(slow.max_speed_degrees_s, 45)
        self.assertEqual(fast.max_speed_degrees_s, 180)

    def test_reverse(self):
        self.assertEqual(HorizontalMotorMapper(reverse=True).command(100).target_degrees, -10)

    def test_loss_and_invalid_coordinates_hold_instead_of_returning_to_zero(self):
        mapper = HorizontalMotorMapper()
        for x in (None, math.nan, math.inf, -math.inf):
            self.assertIsNone(mapper.command(x).target_degrees)
        self.assertEqual(mapper.command(0).target_degrees, 0)

    def test_hand_selection_survives_order_changes(self):
        hands = [("Left", -100), ("Right", 150)]
        self.assertEqual(select_control_x(hands), 150)
        self.assertEqual(select_control_x(list(reversed(hands))), 150)
        self.assertEqual(select_control_x(hands, "left"), -100)

    def test_missing_or_ambiguous_hand_holds(self):
        for hands in ([], [("Left", 100)], [("Right", 100), ("Right", -100)]):
            self.assertIsNone(select_control_x(hands))

    def test_invalid_settings_fail_early(self):
        for option in ("degrees_per_pixel", "speed_factor"):
            for value in (0, -1, math.nan, math.inf):
                with self.subTest(option=option, value=value), self.assertRaises(ValueError):
                    HorizontalMotorMapper(**{option: value})


if __name__ == "__main__":
    unittest.main()
