# NOVA ARM

A camera-only, glove-free, gesture-controlled robotic hand for live performance.

A webcam sees the operator's bare hand. MediaPipe Hands extracts 21 landmarks, the host converts them into one flexion value per finger, and an ESP32 drives five servos through a PCA9685 so that the robotic hand mirrors the operator's fingers in real time. The wrist position is also streamed over OSC, for example to a TouchDesigner visual.

This repository accompanies the technical note *NOVA ARM: A Camera-Only, Glove-Free Gesture-Controlled Robotic Hand for Live Performance*. It contains the host tracking code, the ESP32 firmware and the printable parts.

> **Status:** research prototype. Read [Safety and known limitations](#safety-and-known-limitations) before powering the arm.

## How it works

```
Webcam -> MediaPipe Hands (21 landmarks) -> per-finger joint-angle sum
       -> calibration (min/max) -> normalise to 0-100 %
       -> Kalman filter (per finger) -> dead zone
       -> serial CSV -> ESP32 + PCA9685 -> 5 servos

MediaPipe wrist landmark -> OSC -> TouchDesigner (optional, independent branch)
```

1. **Sensing.** For each finger, the interior angles at two joints are computed from pairs of bone vectors and added. The thumb uses landmarks 1-2-3 and 2-3-4, and the other fingers use their MCP-PIP-DIP and PIP-DIP-TIP triplets. The thumb's CMC joint and the MCP joints of the other fingers are not captured.
2. **Calibration.** At start-up the operator keeps the hand fully open for 3 s and then fully closed for 3 s. The minimum and maximum of each finger's value over both phases define the range. Nothing is sent to the arm until calibration ends.
3. **Normalisation and filtering.** Each value is mapped to 0-100 %, where 0 means closed and 100 means open. A scalar Kalman filter (process noise 1.0, measurement noise 8.0) smooths it, and a dead zone of 3 percentage points blocks small changes.
4. **Serial protocol.** While a hand is tracked, the host sends one line per frame over USB serial at 115200 baud:

   ```
   thumb,index,middle,ring,pinky\n
   ```

   Each value is an integer from 0 to 100. The ESP32 clamps it to that range and ignores lines from which five integers cannot be read. When no hand is detected, nothing is sent and the servos hold their last position.
5. **Actuation.** The firmware maps each value linearly to a PCA9685 pulse count between `SERVOMIN = 200` and `SERVOMAX = 500` at 50 Hz (about 0.98-2.44 ms). Every channel has an inversion flag, and all five are set in the current firmware, so 100 maps to `SERVOMIN` (open) and 0 maps to `SERVOMAX` (closed).

Channels 0-4 of the PCA9685 are thumb, index, middle, ring and pinky.

## Hardware

| Part | Used here |
|---|---|
| Host computer | Laptop running Python 3, with its built-in webcam |
| Microcontroller | ESP32 development board (WROOM-32 class) |
| Servo driver | PCA9685, 16-channel, I2C |
| Servos | 5 x MG995 metal-gear |
| Power supply | 12 V DC, 10 A, 120 W |
| Step-down converter | Joy-IT SBC-Buck02 (9-35 V in, 5 V out, max 5 A / 25 W) |

The servo rail (PCA9685 `V+`) is powered from the 5 V converter and is kept separate from the ESP32's logic supply. The PCA9685 logic supply (`VCC`) comes from the ESP32's 3.3 V. All grounds are common. The ESP32 is powered and programmed over USB.

## Software requirements

Tested with:

| Package | Version |
|---|---|
| Python | 3.12.10 |
| MediaPipe | 0.10.14 |
| OpenCV | 5.0.0 |
| NumPy | 2.5.3 |

```
pip install mediapipe==0.10.14 opencv-python numpy pyserial python-osc
```

* Install **`pyserial`**, not the unrelated `serial` package.
* The tracking script uses the legacy `mediapipe.solutions` API, which is not available in recent MediaPipe releases. Use `mediapipe==0.10.14` or another release that still provides `mp.solutions`.

For the firmware you need the Arduino IDE with ESP32 board support and the Adafruit PWM Servo Driver library.

## Running

1. **Flash the ESP32.** Open the firmware (`ESP32_ARM.ino`) in the Arduino IDE, select your ESP32 board and port, and upload it. The serial monitor runs at 115200 baud.
2. **Check the serial port.** The tracking script opens `COM3` by default. Change the port in the line `serial.Serial("COM3", 115200, timeout=1)` to match your machine.
3. **Check the camera.** The script reads camera index 0 (`cv2.VideoCapture(0)`) with the camera's default mode (640 x 480 at 30 fps on the built-in webcam used here). No resolution or frame rate is set in the code.
4. **Run the tracker**, from the folder that contains `hand_tracking.py`:

   ```
   py hand_tracking.py
   ```

5. **Calibrate.** Follow the on-screen text: open the hand fully for 3 s, then close it fully for 3 s. Tracking starts after that. Press `Esc` to quit.

MediaPipe runs for at most one hand, with detection and tracking confidence thresholds of 0.7. The window shows the landmarks and the current value of each finger.

### OSC output

The wrist (landmark 0) is sent to `127.0.0.1:9000` as normalised MediaPipe coordinates:

```
/hand0/x
/hand0/y
/hand0/z
```

This branch is independent of the servo control. Change the address and port in the `SimpleUDPClient(...)` line if needed.

## Generative visual subsystem

The technical note also describes a generative visual pipeline (a browser-based Prompt Studio, keyword extraction, a locally hosted ComfyUI texture workflow and TouchDesigner). It does not control the hardware. The only link to the tracking code is the wrist OSC stream above.

## Printable parts

The printable parts of the arm are in this repository. Print settings and the assembly order are not documented here yet.

## Safety and known limitations

* **Power stage.** The 5 V converter is rated for 5 A and 25 W. Five MG995 servos running unloaded draw about 0.85 A, but their stall current is approximately 1.2-2.5 A each, so five stalled servos could need an estimated 6-12.5 A. The converter is therefore not sized for a simultaneous stall of all five servos, and the stall figures themselves have not been measured.
* **No end-stop protection.** `SERVOMIN` and `SERVOMAX` are shared by all channels, so travel is not limited per finger and a linkage can be driven against its mechanical end stop. Per-channel PWM limits are not implemented.
* **No fail-safe.** The firmware has no timeout and no overcurrent protection. If lines stop arriving, whether because no hand is detected or because the link is lost, the servos hold their last commanded position, even against an end stop.
* **Tracking.** Thumb flexion is the weakest signal. There is no wrist rotation. Mapping each finger to a single value means individual joints cannot be controlled.
* **Latency.** End-to-end latency has not been measured. On the test laptop the host loop (MediaPipe, angle computation and display, without the serial write) ran at about 30 fps.
