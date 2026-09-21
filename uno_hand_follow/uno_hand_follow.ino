// Elegoo/Arduino Uno R3 + Panucatt SD8825. Install AccelStepper 1.64.
// Pins refer to the labels on the SD8825, not to a generic carrier diagram.
// RST and SLP must be held HIGH externally. See README for all connections.
// A HELLO session defines the stationary shaft's current position as zero.
// No homing or physical position feedback is provided by this sketch.
#include <AccelStepper.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>

const uint8_t STEP_PIN = 3;
const uint8_t DIR_PIN = 2;
const uint8_t ENABLE_PIN = 4;  // SD8825 EN is active LOW
const unsigned long COMMAND_TIMEOUT_MS = 750;
const long MAX_TARGET_STEPS = 1000000L;  // Numeric bound, not a travel limit
const long MAX_SPEED_STEPS_S = 4000;
const long MAX_ACCEL_STEPS_S2 = 5000;

// enable=false prevents pin setup/energizing before setup() sets EN HIGH.
AccelStepper motor(AccelStepper::DRIVER, STEP_PIN, DIR_PIN, 0, 0, false);
char lineBuffer[64];
uint8_t lineLength = 0;
bool droppingLine = false;
bool configured = false;
bool sessionStarted = false;
unsigned long lastCommandMs = 0;

// Continuous-rotation (SPEED) mode: the speed ramps toward the requested
// value at the configured acceleration instead of jumping.
const unsigned long RAMP_INTERVAL_US = 2000;
bool spinMode = false;
float spinTarget = 0;   // steps/s, signed
float spinCurrent = 0;  // steps/s, signed
float spinAccel = 1;    // steps/s^2
unsigned long lastRampUs = 0;

void leaveSpinMode() {
  spinMode = false;
  spinTarget = 0;
  spinCurrent = 0;
  motor.setSpeed(0);
}

void rampSpin() {
  unsigned long now = micros();
  unsigned long dt = now - lastRampUs;
  if (dt < RAMP_INTERVAL_US) return;
  lastRampUs = now;
  float dv = spinAccel * dt * 1e-6;
  if (spinCurrent < spinTarget) {
    spinCurrent = min(spinCurrent + dv, spinTarget);
  } else {
    spinCurrent = max(spinCurrent - dv, spinTarget);
  }
  motor.setSpeed(spinCurrent);
}

void stepMotor() {
  if (spinMode) {
    rampSpin();
    motor.runSpeed();
  } else {
    motor.run();
  }
}

void holdHere() {
  leaveSpinMode();
  // Cancels queued movement and resets speed to zero, retaining holding torque.
  // An abrupt pulse stop can lose mechanical position under load.
  motor.setCurrentPosition(motor.currentPosition());
}

void disarm() {
  holdHere();
  motor.disableOutputs();
  configured = false;
  sessionStarted = false;
}

void rejectCommand(const __FlashStringHelper *message) {
  disarm();
  Serial.println(message);
}

bool parseLong(const char *text, long &value) {
  if (text == NULL || *text == '\0') return false;
  char *end;
  errno = 0;
  value = strtol(text, &end, 10);
  return errno != ERANGE && end != text && *end == '\0';
}

void handleLine(char *line) {
  char *context = NULL;
  char *cmd = strtok_r(line, " \r", &context);
  char *first = strtok_r(NULL, " \r", &context);
  char *second = strtok_r(NULL, " \r", &context);
  char *extra = strtok_r(NULL, " \r", &context);
  if (cmd == NULL || extra != NULL) {
    rejectCommand(F("ERR FORMAT"));
    return;
  }

  if (strcmp(cmd, "HELLO") == 0 && first == NULL) {
    disarm();
    motor.setCurrentPosition(0);
    sessionStarted = true;
    lastCommandMs = millis();
    Serial.println(F("READY HAND_FOLLOW 1"));
    return;
  }
  if (strcmp(cmd, "STOP") == 0 && first == NULL) {
    disarm();
    Serial.println(F("OK STOP"));
    return;
  }
  if (!sessionStarted) {
    rejectCommand(F("ERR SESSION"));
    return;
  }
  if (strcmp(cmd, "CONFIG") == 0) {
    long speed, acceleration;
    if (!parseLong(first, speed) || !parseLong(second, acceleration) ||
        speed < 1 || speed > MAX_SPEED_STEPS_S ||
        acceleration < 1 || acceleration > MAX_ACCEL_STEPS_S2) {
      rejectCommand(F("ERR CONFIG"));
      return;
    }
    holdHere();
    motor.setMaxSpeed(speed);
    motor.setAcceleration(acceleration);
    spinAccel = acceleration;
    configured = true;
    lastCommandMs = millis();
    Serial.println(F("OK CONFIG"));
    return;
  }
  if (!configured) {
    rejectCommand(F("ERR CONFIG_REQUIRED"));
    return;
  }
  if (strcmp(cmd, "HOLD") == 0 && first == NULL) {
    holdHere();
    lastCommandMs = millis();
    Serial.println(F("OK HOLD"));
    return;
  }
  if (strcmp(cmd, "TARGET") == 0 && second == NULL) {
    long target;
    if (!parseLong(first, target) || target < -MAX_TARGET_STEPS || target > MAX_TARGET_STEPS) {
      rejectCommand(F("ERR TARGET"));
      return;
    }
    if (spinMode) holdHere();
    motor.enableOutputs();
    motor.moveTo(target);
    lastCommandMs = millis();
    Serial.println(F("OK TARGET"));
    return;
  }
  if (strcmp(cmd, "SPEED") == 0 && second == NULL) {
    long speed;
    if (!parseLong(first, speed) || speed < -(long)motor.maxSpeed() || speed > (long)motor.maxSpeed()) {
      rejectCommand(F("ERR SPEED"));
      return;
    }
    motor.enableOutputs();
    if (!spinMode) {
      // Start from rest at the current position; ramp from zero.
      holdHere();
      spinMode = true;
      lastRampUs = micros();
    }
    spinTarget = speed;
    lastCommandMs = millis();
    Serial.println(F("OK SPEED"));
    return;
  }
  rejectCommand(F("ERR COMMAND"));
}

void setup() {
  // Write the inactive level before switching to output mode.
  digitalWrite(ENABLE_PIN, HIGH);
  pinMode(ENABLE_PIN, OUTPUT);
  // setEnablePin initially writes HIGH with the library's default polarity.
  // Apply active-low polarity AFTER that call to avoid a brief enable pulse.
  motor.setEnablePin(ENABLE_PIN);
  motor.setPinsInverted(false, false, true);
  motor.disableOutputs();
  motor.setMinPulseWidth(3);  // DRV8825 requires >=1.9 us STEP high/low.
  motor.setCurrentPosition(0);
  Serial.begin(115200);
  Serial.println(F("READY HAND_FOLLOW 1"));
}

void loop() {
  if (sessionStarted && (unsigned long)(millis() - lastCommandMs) > COMMAND_TIMEOUT_MS) {
    disarm();
    Serial.println(F("ERR TIMEOUT"));
  }
  // Bounded, nonblocking input: motor.run() stays frequent during serial traffic.
  for (uint8_t i = 0; i < 32 && Serial.available() > 0; ++i) {
    char c = (char)Serial.read();
    if (c == '\n') {
      if (!droppingLine) {
        lineBuffer[lineLength] = '\0';
        handleLine(lineBuffer);
      }
      droppingLine = false;
      lineLength = 0;
    } else if (!droppingLine) {
      if (c == '\0' || lineLength >= sizeof(lineBuffer) - 1) {
        droppingLine = true;  // Discard the entire line, never execute a prefix.
        rejectCommand(F("ERR LINE"));
      } else {
        lineBuffer[lineLength++] = c;
      }
    }
    stepMotor();
  }
  stepMotor();
}
