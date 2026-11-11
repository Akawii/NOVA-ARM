#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver();

// Servo channels 0-4
// Order: Thumb, Index, Middle, Ring, Pinky
int ch[5] = {0, 1, 2, 3, 4};

#define SERVOMIN 200
#define SERVOMAX 500

// Invert per finger if servo is mounted in reverse
// true = invert, false = normal
// Tune these if any finger moves backwards
bool invert[5] = {true, true, true, true, true};

// Clamp helper
int clamp(int val, int lo, int hi) {
  return max(lo, min(hi, val));
}

void setup() {
  Serial.begin(115200);
  pwm.begin();
  pwm.setPWMFreq(50);

  // Start all servos at closed position
  for (int i = 0; i < 5; i++) {
    pwm.setPWM(ch[i], 0, SERVOMIN);
  }

  Serial.println("Ready.");
}

void loop() {
  if (Serial.available()) {

    String data = Serial.readStringUntil('\n');
    data.trim();

    int thumb, indexF, middleF, ringF, littleF;

    int parsed = sscanf(
      data.c_str(),
      "%d,%d,%d,%d,%d",
      &thumb,
      &indexF,
      &middleF,
      &ringF,
      &littleF
    );

    if (parsed == 5) {

      int values[5] = {
        clamp(thumb,   0, 100),
        clamp(indexF,  0, 100),
        clamp(middleF, 0, 100),
        clamp(ringF,   0, 100),
        clamp(littleF, 0, 100)
      };

      for (int i = 0; i < 5; i++) {
        int pwmValue;
        if (invert[i]) {
          pwmValue = map(values[i], 0, 100, SERVOMAX, SERVOMIN);
        } else {
          pwmValue = map(values[i], 0, 100, SERVOMIN, SERVOMAX);
        }
        pwm.setPWM(ch[i], 0, pwmValue);
      }

      Serial.println(data);
    }
  }
}