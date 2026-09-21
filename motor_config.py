"""Edit the prototype settings here. CLI options can override motion settings."""

# REFERENCE ONLY: user-estimated supply ratings; confirm the physical label.
# Changing these values does NOT change the supply voltage or its current limit.
POWER_SUPPLY_VOLTAGE_V = 12.0
POWER_SUPPLY_MAX_CURRENT_A = 1.5
POWER_SUPPLY_CONFIRMED = False

# Motor label. Set the driver's physical current limit separately, not via USB.
MOTOR_RATED_PHASE_CURRENT_A = 1.0
MOTOR_STEP_ANGLE_DEGREES = 1.8

# Must match the physical SD8825 mode-pin wiring. 8 = M0 HIGH, M1 HIGH, M2 LOW.
MICROSTEPS = 8

CONTROL_HAND = "right"
DEGREES_PER_PIXEL = 0.1
SPEED_FACTOR = 1.0
BASE_SPEED_DEGREES_S = 90.0
ACCELERATION_DEGREES_S2 = 180.0
REVERSE_MOTOR = False

SERIAL_BAUD = 115200
COMMAND_RATE_HZ = 20.0
