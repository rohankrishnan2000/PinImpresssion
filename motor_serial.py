"""Bounded USB serial commands for uno_hand_follow/uno_hand_follow.ino.

One acknowledged command at a time prevents queued, outdated target positions.
Serial is imported only when connecting; preview/tests need no USB hardware.
"""

import math
import time

import motor_config as config


class MotorConnectionError(RuntimeError):
    pass


class UnoMotor:
    # Match the protocol limits in the Arduino sketch. These are numeric bounds,
    # NOT mechanical travel limits or verified limits of a particular motor.
    MAX_TARGET_STEPS = 1_000_000
    MAX_SPEED_STEPS_S = 2000
    MAX_ACCEL_STEPS_S2 = 5000

    def __init__(self, port, max_speed_degrees_s,
                 acceleration_degrees_s2=config.ACCELERATION_DEGREES_S2,
                 microsteps=config.MICROSTEPS, serial_factory=None, boot_wait=2.0):
        if microsteps not in (1, 2, 4, 8, 16, 32):
            raise ValueError("microsteps must be 1, 2, 4, 8, 16, or 32")
        step_angle = config.MOTOR_STEP_ANGLE_DEGREES
        if not math.isfinite(step_angle) or step_angle <= 0:
            raise ValueError("MOTOR_STEP_ANGLE_DEGREES must be finite and positive")
        self.steps_per_degree = microsteps / step_angle
        self.speed = self._positive_steps(max_speed_degrees_s, self.MAX_SPEED_STEPS_S, "speed")
        self.acceleration = self._positive_steps(acceleration_degrees_s2,
                                                 self.MAX_ACCEL_STEPS_S2, "acceleration")
        if not math.isfinite(config.COMMAND_RATE_HZ) or not 5 <= config.COMMAND_RATE_HZ <= 50:
            raise ValueError("COMMAND_RATE_HZ must be between 5 and 50")
        self.interval = 1.0 / config.COMMAND_RATE_HZ
        self.last_sent = -math.inf
        self.holding = None
        self.closed = False
        self.serial = None
        if serial_factory is None:
            try:
                from serial import Serial
            except ImportError as exc:
                raise MotorConnectionError("Install requirements.txt first (pyserial is required).") from exc
            serial_factory = Serial
        try:
            self.serial = serial_factory(port=port, baudrate=config.SERIAL_BAUD,
                                         timeout=0.2, write_timeout=0.2)
            # Opening an Uno serial port commonly resets the board.
            time.sleep(boot_wait)
            self.serial.reset_input_buffer()
            self._exchange("HELLO", "READY HAND_FOLLOW 1")
            self._exchange(f"CONFIG {self.speed} {self.acceleration}", "OK CONFIG")
        except Exception as exc:
            if self.serial is not None:
                self.close()
            if isinstance(exc, MotorConnectionError):
                raise
            raise MotorConnectionError(f"Cannot initialize motor connection: {exc}") from exc

    def _positive_steps(self, degrees, upper, name):
        if not math.isfinite(degrees) or degrees <= 0:
            raise ValueError(f"{name} must be finite and positive")
        converted = degrees * self.steps_per_degree
        if not math.isfinite(converted) or not 1 <= converted <= upper:
            raise ValueError(f"{name} must correspond to 1..{upper} driver steps per second"
                             + (" squared" if name == "acceleration" else ""))
        return round(converted)

    def _exchange(self, command, expected):
        try:
            payload = (command + "\n").encode("ascii")
            if self.serial.write(payload) != len(payload):
                raise MotorConnectionError("Incomplete serial write")
            reply = self.serial.read_until(b"\n", size=64)
            if not reply.endswith(b"\n") or reply.rstrip(b"\r\n") != expected.encode("ascii"):
                raise MotorConnectionError(f"Uno response to {command.split()[0]}: {reply!r}; "
                                           f"expected {expected!r}. Motor session stopped.")
        except MotorConnectionError:
            raise
        except Exception as exc:
            raise MotorConnectionError(f"Motor USB connection failed: {exc}") from exc

    def update(self, command, now=None, force=False):
        if self.closed:
            raise MotorConnectionError("Motor connection is closed")
        now = time.monotonic() if now is None else now
        holding = command.target_degrees is None
        # Hand loss/disarming bypasses the normal rate limit immediately.
        if not force and holding == self.holding and now - self.last_sent < self.interval:
            return
        if holding:
            self._exchange("HOLD", "OK HOLD")
        else:
            target = command.target_degrees * self.steps_per_degree
            if not math.isfinite(target) or abs(target) > self.MAX_TARGET_STEPS:
                # Cancel the previous move before rejecting an invalid target.
                self._exchange("HOLD", "OK HOLD")
                raise MotorConnectionError("Motor target exceeds the numeric protocol range")
            self._exchange(f"TARGET {round(target)}", "OK TARGET")
        self.holding = holding
        self.last_sent = now

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.serial is not None:
            try:
                self._exchange("STOP", "OK STOP")
            except MotorConnectionError:
                # Firmware independently stops/disarms after 750 ms without commands.
                pass
            finally:
                self.serial.close()
