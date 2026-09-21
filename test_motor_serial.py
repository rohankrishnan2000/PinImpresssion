"""Exercise the USB protocol without opening a port or moving hardware."""
import unittest

from motion_control import MotorCommand
from motor_serial import UnoMotor, MotorConnectionError


class FakeSerial:
    def __init__(self, **kwargs):
        self.writes = []
        self.reply = b""
        self.override = None
        self.closed = False
        self.short_write = False

    def reset_input_buffer(self):
        self.reply = b""

    def write(self, data):
        self.writes.append(data)
        cmd = data.split()[0]
        self.reply = b"READY HAND_FOLLOW 1\r\n" if cmd == b"HELLO" else b"OK " + cmd + b"\r\n"
        return len(data) - 1 if self.short_write else len(data)

    def read_until(self, expected, size):
        return self.reply if self.override is None else self.override

    def close(self):
        self.closed = True


class SerialTests(unittest.TestCase):
    def make_motor(self, **kwargs):
        serial = FakeSerial()
        motor = UnoMotor("TEST", 90, serial_factory=lambda **_: serial, boot_wait=0, **kwargs)
        self.addCleanup(motor.close)
        return motor, serial

    def test_connect_is_inert_and_converts_speed_to_microsteps(self):
        _, serial = self.make_motor(microsteps=8, acceleration_degrees_s2=180)
        self.assertEqual(serial.writes, [b"HELLO\n", b"CONFIG 400 800\n"])

    def test_angle_conversion_and_absolute_targets(self):
        motor, serial = self.make_motor(microsteps=8)
        for i, angle in enumerate((18, 18, -18, 0)):
            motor.update(MotorCommand(angle, 90), now=i)
        self.assertEqual(serial.writes[2:], [b"TARGET 80\n", b"TARGET 80\n",
                                             b"TARGET -80\n", b"TARGET 0\n"])

    def test_microstep_change_changes_pulse_count(self):
        motor, serial = self.make_motor(microsteps=1)
        motor.update(MotorCommand(18, 90), now=0)
        self.assertEqual(serial.writes[1:], [b"CONFIG 50 100\n", b"TARGET 10\n"])

    def test_rate_limit_sends_latest_target_and_refreshes_stationary_target(self):
        motor, serial = self.make_motor(microsteps=8)
        motor.update(MotorCommand(18, 90), now=0)
        motor.update(MotorCommand(36, 90), now=0.01)
        motor.update(MotorCommand(54, 90), now=0.1)
        motor.update(MotorCommand(54, 90), now=0.2)
        self.assertEqual(serial.writes[2:], [b"TARGET 80\n", b"TARGET 240\n", b"TARGET 240\n"])

    def test_hand_loss_sends_hold_immediately_and_heartbeats_while_paused(self):
        motor, serial = self.make_motor()
        motor.update(MotorCommand(18, 90), now=0)
        motor.update(MotorCommand(None, 90), now=0.001)
        motor.update(MotorCommand(None, 90), now=0.1)
        self.assertEqual(serial.writes[-2:], [b"HOLD\n", b"HOLD\n"])

    def test_failure_responses_abort_session(self):
        for reply in (b"", b"OK TARGET", b"ERR TIMEOUT\r\n", b"READY HAND_FOLLOW 1\r\n"):
            with self.subTest(reply=reply):
                motor, serial = self.make_motor()
                serial.override = reply
                with self.assertRaises(MotorConnectionError):
                    motor.update(MotorCommand(18, 90), now=0)

    def test_partial_write_is_an_error(self):
        motor, serial = self.make_motor()
        serial.short_write = True
        with self.assertRaises(MotorConnectionError):
            motor.update(MotorCommand(18, 90))

    def test_close_sends_stop_once_and_closes_port(self):
        motor, serial = self.make_motor()
        motor.close()
        motor.close()
        self.assertEqual(serial.writes.count(b"STOP\n"), 1)
        self.assertTrue(serial.closed)
        with self.assertRaises(MotorConnectionError):
            motor.update(MotorCommand(18, 90))

    def test_failed_handshake_closes_port(self):
        serial = FakeSerial()
        serial.override = b"unrelated Arduino sketch\r\n"
        with self.assertRaises(MotorConnectionError):
            UnoMotor("TEST", 90, serial_factory=lambda **_: serial, boot_wait=0)
        self.assertTrue(serial.closed)
        self.assertNotIn(b"CONFIG 400 800\n", serial.writes)

    def test_invalid_target_cancels_previous_motion(self):
        motor, serial = self.make_motor()
        with self.assertRaises(MotorConnectionError):
            motor.update(MotorCommand(float("inf"), 90))
        self.assertEqual(serial.writes[-1], b"HOLD\n")

    def test_invalid_hardware_settings_fail_before_opening_port(self):
        def fail_open(**_):
            self.fail("Invalid settings must not open a serial port")
        for kwargs in ({"microsteps": 3}, {"max_speed_degrees_s": 10000},
                       {"max_speed_degrees_s": float("nan")},
                       {"acceleration_degrees_s2": 0}):
            args = {"max_speed_degrees_s": 90, **kwargs}
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                UnoMotor("TEST", serial_factory=fail_open, boot_wait=0, **args)

    def test_spin_sends_signed_clamped_speed_at_command_rate(self):
        motor, serial = self.make_motor(microsteps=8)  # 90 deg/s cap -> 400 steps/s
        motor.spin(45, now=0)
        motor.spin(-45, now=0.01)  # rate limited
        motor.spin(-45, now=0.1)
        motor.spin(1000, now=0.2)
        motor.spin(0, now=0.21, force=True)
        self.assertEqual(serial.writes[2:], [b"SPEED 200\n", b"SPEED -200\n",
                                             b"SPEED 400\n", b"SPEED 0\n"])


if __name__ == "__main__":
    unittest.main()
