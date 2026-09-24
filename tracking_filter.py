"""Time-aware adaptive filtering for normalized hand coordinates.

Independent implementation of the 1 Euro filtering equations described by
Casiez, Roussel and Vogel (2012): https://gery.casiez.net/1euro/
Each axis is independent, so vertical movement cannot change horizontal gain.
"""

import math


class OneEuroFilter:
    def __init__(self, min_cutoff_hz=1.0, beta=5.0,
                 derivative_cutoff_hz=1.0, reset_after_s=0.5):
        for name, value in (("min_cutoff_hz", min_cutoff_hz),
                            ("derivative_cutoff_hz", derivative_cutoff_hz),
                            ("reset_after_s", reset_after_s)):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not math.isfinite(beta) or beta < 0:
            raise ValueError("beta must be finite and nonnegative")
        self.min_cutoff = min_cutoff_hz
        self.beta = beta
        self.derivative_cutoff = derivative_cutoff_hz
        self.reset_after = reset_after_s
        self.reset()

    def reset(self):
        self.time = None
        self.raw = None
        self.value = None
        self.derivative = 0.0

    @staticmethod
    def alpha(cutoff, dt):
        return 1.0 / (1.0 + 1.0 / (2.0 * math.pi * cutoff * dt))

    def __call__(self, value, timestamp):
        if value is None or not math.isfinite(value) or not math.isfinite(timestamp):
            self.reset()
            return None
        value = float(value)
        if self.time is None or timestamp - self.time > self.reset_after:
            self.time = timestamp
            self.raw = self.value = value
            self.derivative = 0.0
            return value
        dt = timestamp - self.time
        if dt <= 0:
            # Ignore duplicate/out-of-order samples without corrupting the state.
            return self.value
        derivative = (value - self.raw) / dt
        d_alpha = self.alpha(self.derivative_cutoff, dt)
        self.derivative += d_alpha * (derivative - self.derivative)
        cutoff = self.min_cutoff + self.beta * abs(self.derivative)
        self.value += self.alpha(cutoff, dt) * (value - self.value)
        self.time, self.raw = timestamp, value
        return self.value


class AdaptivePalmFilter:
    """Filter x/y in normalized camera units, before converting to pixels."""

    def __init__(self, min_cutoff_hz=1.0, beta=5.0, derivative_cutoff_hz=1.0):
        self.axes = [OneEuroFilter(min_cutoff_hz, beta, derivative_cutoff_hz)
                     for _ in range(2)]

    def __call__(self, point, timestamp):
        if point is None or len(point) != 2 or not all(math.isfinite(v) for v in point):
            for axis in self.axes:
                axis.reset()
            return None
        values = tuple(axis(value, timestamp) for axis, value in zip(self.axes, point))
        return None if any(value is None for value in values) else values
