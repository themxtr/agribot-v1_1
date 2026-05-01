import cv2
import numpy as np
from collections import deque

# Start laptop camera
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

# Define colors in HSV
colors = {
    "Red": [(0, 120, 70), (10, 255, 255)],
    "Green": [(36, 25, 25), (86, 255, 255)],
    "Blue": [(94, 80, 2), (126, 255, 255)],
    "Yellow": [(15, 150, 20), (35, 255, 255)],
    "Orange": [(5, 150, 150), (15, 255, 255)],
    "Purple": [(129, 50, 70), (158, 255, 255)]
}

# Store points for motion tracking
max_points = 50  # number of previous positions to store
points = {color: deque(maxlen=max_points) for color in colors}

while True:
    ret, frame = cap.read()
    if not ret:
        print("Cannot read camera")
        break

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    for color_name, (lower, upper) in colors.items():
        lower = np.array(lower)
        upper = np.array(upper)

        mask = cv2.inRange(hsv, lower, upper)
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        center = None
        for cnt in contours:
            if cv2.contourArea(cnt) > 1000:
                x, y, w, h = cv2.boundingRect(cnt)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                cv2.putText(frame, color_name, (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                # Calculate center of object for tracking
                center = (x + w // 2, y + h // 2)
                points[color_name].append(center)

        # Draw the trail of movement
        for i in range(1, len(points[color_name])):
            if points[color_name][i - 1] is None or points[color_name][i] is None:
                continue
            cv2.line(frame, points[color_name][i - 1], points[color_name][i], (0, 255, 255), 2)

    cv2.imshow("Enhanced Color Detection + Motion Tracking", frame)

    # Press 'q' to quit
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
