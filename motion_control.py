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


def select_control_x(hands, control_hand="right"):
    """Use only the selected handedness; ambiguity or loss means hold.

    hands contains (label, centered_x) pairs. This prevents detection order
    changes, or another visible hand, from silently taking over control.
    """
    matches = [x for label, x in hands if label.lower() == control_hand.lower()]
    return matches[0] if len(matches) == 1 else None
