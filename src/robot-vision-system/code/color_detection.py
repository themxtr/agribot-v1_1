import cv2
import numpy as np

cap = cv2.VideoCapture(0)  # Laptop camera

while True:
    ret, frame = cap.read()
    if not ret:
        print("Camera not working")
        break

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    colors = {
        "Red": [(0, 120, 70), (10, 255, 255)],
        "Green": [(36, 25, 25), (86, 255, 255)],
        "Blue": [(94, 80, 2), (126, 255, 255)],
        "Yellow": [(15, 150, 20), (35, 255, 255)]
    }

    for color_name, (lower, upper) in colors.items():
        mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            if cv2.contourArea(cnt) > 1000:
                x, y, w, h = cv2.boundingRect(cnt)
                cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(frame, color_name, (x, y-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    cv2.imshow("Robot Vision - Color Detection", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
