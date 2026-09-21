"""Driver-independent horizontal hand position -> motor target.

This module does not connect to hardware. A driver-specific Arduino bridge
must consume these commands before the motor can move.
"""

from dataclasses import dataclass
import math

import motor_config as config


@dataclass(frozen=True)
class MotorCommand:
    # None means cancel motion and hold, NOT return to the center.
    target_degrees: float | None
    max_speed_degrees_s: float


class HorizontalMotorMapper:
    """Map centered x pixels to an absolute angle about a future motor zero.

    Position scale and speed are independent: changing speed_factor does not
    change the destination. No calibration or travel limits are applied here.
    """

    BASE_SPEED_DEGREES_S = config.BASE_SPEED_DEGREES_S

    def __init__(self, degrees_per_pixel=config.DEGREES_PER_PIXEL,
                 speed_factor=config.SPEED_FACTOR, reverse=config.REVERSE_MOTOR):
        for name, value in (("degrees_per_pixel", degrees_per_pixel),
                            ("speed_factor", speed_factor)):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and greater than zero")
        self.degrees_per_pixel = degrees_per_pixel
        self.max_speed = self.BASE_SPEED_DEGREES_S * speed_factor
        if not math.isfinite(self.max_speed) or self.max_speed <= 0:
            raise ValueError("BASE_SPEED_DEGREES_S times speed_factor must be finite and positive")
        self.direction = -1 if reverse else 1

    def command(self, centered_x):
        if centered_x is None or not math.isfinite(centered_x):
            return MotorCommand(None, self.max_speed)
        target = centered_x * self.degrees_per_pixel * self.direction
        if not math.isfinite(target):
            return MotorCommand(None, self.max_speed)
        return MotorCommand(target, self.max_speed)


class SpinSpeedMapper:
    """Map centered x pixels to a signed continuous rotation speed.

    Zero inside the deadzone around the center, rising linearly to max_speed
    at full_speed_px from the center, clamped beyond it. Loss means stop.
    """

    def __init__(self, max_speed_degrees_s=config.MAX_SPIN_DEGREES_S,
                 deadzone_px=config.SPIN_DEADZONE_PX, reverse=config.REVERSE_MOTOR):
        if not math.isfinite(max_speed_degrees_s) or max_speed_degrees_s <= 0:
            raise ValueError("max spin speed must be finite and greater than zero")
        if not math.isfinite(deadzone_px) or deadzone_px < 0:
            raise ValueError("deadzone must be finite and not negative")
        self.max_speed = max_speed_degrees_s
        self.deadzone = deadzone_px
        self.direction = -1 if reverse else 1

    def speed(self, centered_x, full_speed_px):
        if centered_x is None or not math.isfinite(centered_x):
            return 0.0
        distance = abs(centered_x) - self.deadzone
        span = full_speed_px - self.deadzone
        if distance <= 0 or span <= 0:
            return 0.0
        fraction = min(1.0, distance / span)
        return math.copysign(fraction * self.max_speed, centered_x) * self.direction


def select_control_x(hands, control_hand="right"):
    """Use only the selected handedness; ambiguity or loss means hold.

    hands contains (label, centered_x) pairs. This prevents detection order
    changes, or another visible hand, from silently taking over control.
    """
    matches = [x for label, x in hands if label.lower() == control_hand.lower()]
    return matches[0] if len(matches) == 1 else None
