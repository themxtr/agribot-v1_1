import cv2
import numpy as np
from collections import deque

# Start laptop camera
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

# HSV color ranges
colors = {
    "Red": [(0, 120, 70), (10, 255, 255)],
    "Blue": [(94, 80, 2), (126, 255, 255)],
    "Pink": [(160, 100, 100), (179, 255, 255)],
    "Yellow": [(15, 150, 20), (35, 255, 255)],
    "Orange": [(5, 150, 150), (15, 255, 255)],
    "Black": [(0, 0, 0), (180,255,40)],
    "Purple": [(129, 50, 70), (158, 255, 255)]
}

trail_colors = {
    "Red": (0, 0, 255),
    "Pink": (203, 192, 255),
    "Blue": (255, 0, 0),
    "Yellow": (0, 255, 255),
    "Orange": (0, 165, 255),
    "Purple": (255, 0, 255),
    "Black": (0,0,0)
}

# Store only last 2 points to draw a single line
points = {color: deque(maxlen=2) for color in colors}

while True:
    ret, frame = cap.read()
    if not ret:
        break
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    for color_name, (lower, upper) in colors.items():
        lower = np.array(lower)
        upper = np.array(upper)

        mask = cv2.inRange(hsv, lower, upper)
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        center = None
        for cnt in contours:
            if cv2.contourArea(cnt) > 1500:  # ignore small noise
                x, y, w, h = cv2.boundingRect(cnt)
                cv2.rectangle(frame, (x, y), (x + w, y + h), trail_colors[color_name], 2)
                cv2.putText(frame, color_name, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, trail_colors[color_name], 2)
                center = (x + w//2, y + h//2)

                # Add to points only if moved
                if not points[color_name] or np.linalg.norm(np.array(center) - np.array(points[color_name][-1])) > 5:
                    points[color_name].append(center)

        # Draw a single line to show motion (if 2 points exist)
        if len(points[color_name]) == 2:
            cv2.line(frame, points[color_name][0], points[color_name][1], trail_colors[color_name], 2)

    cv2.imshow("Clean Color Detection + Motion", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
