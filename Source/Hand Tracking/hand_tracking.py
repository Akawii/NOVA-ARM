import cv2
import mediapipe as mp
import math
import serial
import time
import numpy as np
from pythonosc.udp_client import SimpleUDPClient

# =========================
# SERIAL CONNECTION TO ESP32
# =========================

ser = serial.Serial("COM3", 115200, timeout=1)
time.sleep(2)

# =========================
# OSC CONNECTION TO TOUCHDESIGNER
# =========================

osc = SimpleUDPClient("127.0.0.1", 9000)

# =========================
# MEDIAPIPE SETUP
# =========================

mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

cap = cv2.VideoCapture(0)

# =========================
# KALMAN FILTER CLASS
# =========================

class KalmanFilter1D:
    def __init__(self, process_noise=1.0, measurement_noise=10.0):
        self.q = process_noise
        self.r = measurement_noise
        self.p = 1.0
        self.x = 0.0
        self.k = 0.0

    def update(self, measurement):
        self.p += self.q
        self.k = self.p / (self.p + self.r)
        self.x += self.k * (measurement - self.x)
        self.p *= (1 - self.k)
        return self.x

# =========================
# FINGER FILTERS
# =========================

kalman = {
    "Thumb":  KalmanFilter1D(process_noise=1.0, measurement_noise=8.0),
    "Index":  KalmanFilter1D(process_noise=1.0, measurement_noise=8.0),
    "Middle": KalmanFilter1D(process_noise=1.0, measurement_noise=8.0),
    "Ring":   KalmanFilter1D(process_noise=1.0, measurement_noise=8.0),
    "Pinky":  KalmanFilter1D(process_noise=1.0, measurement_noise=8.0),
}

# =========================
# DEADZONE
# =========================

DEADZONE = 3

last_sent = {
    "Thumb": 0,
    "Index": 0,
    "Middle": 0,
    "Ring": 0,
    "Pinky": 0
}

def apply_deadzone(name, value):

    if abs(value - last_sent[name]) < DEADZONE:
        return last_sent[name]

    last_sent[name] = value
    return value

# =========================
# CALIBRATION STORAGE
# =========================

cal = {
    "Thumb":  {"min": 9999, "max": -9999},
    "Index":  {"min": 9999, "max": -9999},
    "Middle": {"min": 9999, "max": -9999},
    "Ring":   {"min": 9999, "max": -9999},
    "Pinky":  {"min": 9999, "max": -9999},
}

cal_phase = 0
cal_timer = 0
CAL_DURATION = 3

# =========================
# HAND LOCAL COORDINATES
# =========================

def get_hand_local_landmarks(lm):

    pts = np.array([[l.x, l.y, l.z] for l in lm.landmark])

    origin = pts[0]

    x_axis = pts[5] - pts[0]
    x_axis /= (np.linalg.norm(x_axis) + 1e-9)

    y_ref = pts[17] - pts[0]

    z_axis = np.cross(x_axis, y_ref)
    z_axis /= (np.linalg.norm(z_axis) + 1e-9)

    y_axis = np.cross(z_axis, x_axis)
    y_axis /= (np.linalg.norm(y_axis) + 1e-9)

    R = np.stack([x_axis, y_axis, z_axis], axis=0)

    local_pts = (pts - origin) @ R.T

    return local_pts

# =========================
# VECTOR + ANGLE FUNCTIONS
# =========================

def vec_local(pts, a, b):
    return pts[b] - pts[a]

def angle_between_np(v1, v2):

    dot = np.dot(v1, v2)

    mag = np.linalg.norm(v1) * np.linalg.norm(v2)

    if mag < 1e-9:
        return 0.0

    return math.degrees(
        math.acos(
            max(-1.0, min(1.0, dot / mag))
        )
    )

# =========================
# FINGER JOINT DEFINITIONS
# =========================

FINGER_JOINTS = {
    "Thumb":  [(1, 2, 3), (2, 3, 4)],
    "Index":  [(5, 6, 7), (6, 7, 8)],
    "Middle": [(9, 10, 11), (10, 11, 12)],
    "Ring":   [(13, 14, 15), (14, 15, 16)],
    "Pinky":  [(17, 18, 19), (18, 19, 20)],
}

# =========================
# FINGER RAW VALUE
# =========================

def finger_raw(pts, name):

    total = 0.0

    for (a, b, c) in FINGER_JOINTS[name]:

        v1 = vec_local(pts, b, a)
        v2 = vec_local(pts, b, c)

        total += angle_between_np(v1, v2)

    return total

# =========================
# CALIBRATION FUNCTIONS
# =========================

def update_cal(name, raw):

    if raw < cal[name]["min"]:
        cal[name]["min"] = raw

    if raw > cal[name]["max"]:
        cal[name]["max"] = raw

def to_percent(name, raw):

    lo = cal[name]["min"]
    hi = cal[name]["max"]

    if hi - lo < 0.01:
        return 0

    percent = (raw - lo) / (hi - lo) * 100

    return max(0, min(100, percent))

# =========================
# MAIN LOOP
# =========================

with mp_hands.Hands(
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.7
) as hands:

    cal_timer = time.time()

    while True:

        ret, frame = cap.read()

        if not ret:
            break

        # mirror webcam
        frame = cv2.flip(frame, 1)

        # convert to RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # process hand
        res = hands.process(rgb)

        elapsed = time.time() - cal_timer

        # =========================
        # UI TEXT
        # =========================

        if cal_phase == 0:
            msg = f"OPEN hand fully ({int(CAL_DURATION - elapsed)}s)"
            color = (0, 200, 255)

        elif cal_phase == 1:
            msg = f"CLOSE hand fully ({int(CAL_DURATION - elapsed)}s)"
            color = (0, 100, 255)

        else:
            msg = "Tracking"
            color = (0, 255, 0)

        cv2.putText(
            frame,
            msg,
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            color,
            2
        )

        y = 80

        # =========================
        # HAND FOUND
        # =========================

        if res.multi_hand_landmarks:

            for hand in res.multi_hand_landmarks:

                # draw hand
                mp_draw.draw_landmarks(
                    frame,
                    hand,
                    mp_hands.HAND_CONNECTIONS
                )

                # =========================
                # WRIST OSC OUTPUT
                # =========================

                wrist = hand.landmark[0]

                osc.send_message("/hand0/x", wrist.x)
                osc.send_message("/hand0/y", wrist.y)
                osc.send_message("/hand0/z", wrist.z)

                # debug text
                cv2.putText(
                    frame,
                    f"Wrist X:{wrist.x:.2f} Y:{wrist.y:.2f} Z:{wrist.z:.2f}",
                    (20, y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255,255,0),
                    2
                )

                y += 40

                # =========================
                # LOCAL SPACE
                # =========================

                local_pts = get_hand_local_landmarks(hand)

                # =========================
                # RAW FINGER VALUES
                # =========================

                raw = {
                    name: finger_raw(local_pts, name)
                    for name in ["Thumb", "Index", "Middle", "Ring", "Pinky"]
                }

                # =========================
                # CALIBRATION
                # =========================

                if cal_phase < 2:

                    for name, val in raw.items():
                        update_cal(name, val)

                if cal_phase < 2 and elapsed >= CAL_DURATION:

                    cal_phase += 1
                    cal_timer = time.time()

                # =========================
                # NORMALIZE
                # =========================

                percent = {
                    name: to_percent(name, val)
                    for name, val in raw.items()
                }

                # =========================
                # FILTER
                # =========================

                filtered = {
                    name: kalman[name].update(val)
                    for name, val in percent.items()
                }

                # =========================
                # DEADZONE
                # =========================

                fingers = {
                    name: apply_deadzone(name, int(val))
                    for name, val in filtered.items()
                }

                # =========================
                # SEND TO ESP32
                # =========================

                if cal_phase == 2:

                    data = (
                        f"{fingers['Thumb']},"
                        f"{fingers['Index']},"
                        f"{fingers['Middle']},"
                        f"{fingers['Ring']},"
                        f"{fingers['Pinky']}\n"
                    )

                    ser.write(data.encode())

                    print(data.strip())

                # =========================
                # DEBUG FINGER VALUES
                # =========================

                for name, val in fingers.items():

                    cv2.putText(
                        frame,
                        f"{name}: {val}%",
                        (20, y),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        color,
                        2
                    )

                    y += 30

        # =========================
        # SHOW WINDOW
        # =========================

        cv2.imshow("Hand Tracking", frame)

        # ESC TO EXIT
        if cv2.waitKey(1) & 0xFF == 27:
            break

# =========================
# CLEANUP
# =========================

cap.release()
ser.close()
cv2.destroyAllWindows()