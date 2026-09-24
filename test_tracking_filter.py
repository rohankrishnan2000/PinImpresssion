import math
import random
import statistics
import unittest

from tracking_filter import AdaptivePalmFilter, OneEuroFilter


class TrackingFilterTests(unittest.TestCase):
    def test_stationary_noise_is_reduced_more_than_original_ema(self):
        rng = random.Random(17)
        adaptive = OneEuroFilter()
        ema = None
        adaptive_values, ema_values = [], []
        for i in range(300):
            raw = 0.5 + rng.uniform(-0.004, 0.004)
            ema = raw if ema is None else ema + 0.4 * (raw - ema)
            value = adaptive(raw, i / 30)
            if i > 60:
                adaptive_values.append(value)
                ema_values.append(ema)
        self.assertLess(statistics.pstdev(adaptive_values), 0.8 * statistics.pstdev(ema_values))

    def test_quick_movement_has_less_lag_than_original_ema(self):
        adaptive = OneEuroFilter()
        ema = 0.0
        adaptive(0.0, 0.0)
        for i in range(1, 31):
            raw = i / 30
            ema += 0.4 * (raw - ema)
            value = adaptive(raw, i / 30)
        self.assertLess(1.0 - value, 0.8 * (1.0 - ema))

    def test_response_is_consistent_across_frame_rates(self):
        outputs = []
        for fps in (15, 30, 60):
            adaptive = OneEuroFilter()
            for i in range(fps + 1):
                value = adaptive(i / fps, i / fps)
            outputs.append(value)
        self.assertLess(max(outputs) - min(outputs), 0.005)

    def test_vertical_motion_does_not_change_horizontal_filter(self):
        still, moving = AdaptivePalmFilter(), AdaptivePalmFilter()
        for i in range(60):
            x = 0.5 + 0.003 * math.sin(i)
            a = still((x, 0.5), i / 30)
            b = moving((x, i / 60), i / 30)
            self.assertEqual(a[0], b[0])

    def test_filter_uses_normalized_coordinates_independent_of_resolution(self):
        filters = [AdaptivePalmFilter(), AdaptivePalmFilter()]
        for i in range(30):
            normalized = (i / 30, 0.5)
            pixels = []
            for width, filter_ in zip((640, 1280), filters):
                pixels.append(filter_(normalized, i / 30)[0] * width)
            self.assertEqual(pixels[1], 2 * pixels[0])

    def test_missing_invalid_and_stale_data_reset_without_old_position_drag(self):
        for invalid in (None, math.nan, math.inf):
            filter_ = OneEuroFilter()
            filter_(0.1, 0)
            self.assertIsNone(filter_(invalid, 0.03))
            self.assertEqual(filter_(0.9, 0.06), 0.9)
        filter_ = OneEuroFilter()
        filter_(0.1, 0)
        self.assertEqual(filter_(0.9, 1), 0.9)

    def test_non_increasing_time_is_ignored(self):
        filter_ = OneEuroFilter()
        self.assertEqual(filter_(0.2, 1), 0.2)
        self.assertEqual(filter_(0.9, 1), 0.2)
        self.assertEqual(filter_(0.9, 0.5), 0.2)
        self.assertEqual(filter_(0.2, 1.03), 0.2)

    def test_bad_parameters_fail_early(self):
        for name in ("min_cutoff_hz", "derivative_cutoff_hz", "reset_after_s"):
            for value in (0, -1, math.nan, math.inf):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    OneEuroFilter(**{name: value})
        for beta in (-1, math.nan, math.inf):
            with self.assertRaises(ValueError):
                OneEuroFilter(beta=beta)
        OneEuroFilter(beta=0)  # Disabling speed adaptation is supported.


if __name__ == "__main__":
    unittest.main()
