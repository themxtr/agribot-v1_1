import cv2
import numpy as np
from collections import deque

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

# HSV color ranges
colors = {
    "Red": [(0, 120, 70), (10, 255, 255)],
    "Green": [(36, 25, 25), (86, 255, 255)],
    "Blue": [(94, 80, 2), (126, 255, 255)],
    "Yellow": [(15, 150, 20), (35, 255, 255)],
    "Orange": [(5, 150, 150), (15, 255, 255)],
    "Purple": [(129, 50, 70), (158, 255, 255)]
}

trail_colors = {
    "Red": (0, 0, 255),
    "Green": (0, 255, 0),
    "Blue": (255, 0, 0),
    "Yellow": (0, 255, 255),
    "Orange": (0, 165, 255),
    "Purple": (255, 0, 255)
}

max_points = 30
points = {color: deque(maxlen=max_points) for color in colors}

# Create a transparent overlay for trails
ret, frame = cap.read()
overlay = np.zeros_like(frame)

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
            if cv2.contourArea(cnt) > 1500:
                x, y, w, h = cv2.boundingRect(cnt)
                cv2.rectangle(frame, (x, y), (x+w, y+h), trail_colors[color_name], 2)
                cv2.putText(frame, color_name, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, trail_colors[color_name], 2)

                center = (x + w//2, y + h//2)
                if not points[color_name] or np.linalg.norm(np.array(center) - np.array(points[color_name][-1])) > 5:
                    points[color_name].append(center)

        # Draw trails on overlay
        for i in range(1, len(points[color_name])):
            if points[color_name][i-1] is None or points[color_name][i] is None:
                continue
            thickness = int(np.sqrt(max_points / float(i+1)) * 2)
            cv2.line(overlay, points[color_name][i-1], points[color_name][i], trail_colors[color_name], thickness)

        # Draw current center
        if center:
            cv2.circle(frame, center, 5, trail_colors[color_name], -1)

    # Combine overlay with frame
    output = cv2.addWeighted(frame, 1.0, overlay, 0.6, 0)

    cv2.imshow("Neat Color Tracking", output)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
