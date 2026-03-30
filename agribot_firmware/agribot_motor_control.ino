/**
 * Agribot Motor Control Firmware
 * Hardware: Arduino Nano + L298N + HC-SR04 + ACS712
 * Protocol: 'F:speed', 'B:speed', 'L:speed', 'R:speed', 'S'
 */

// L298N Pin Definitions
const int ENA = 3;  // Left Motor PWM
const int IN1 = 2;
const int IN2 = 4;
const int ENB = 5;  // Right Motor PWM
const int IN3 = 7;
const int IN4 = 8;

// Ultrasonic Sensor Pins
const int TRIG_PIN = 9;
const int ECHO_PIN = 10;

// Current Sensor Pin
const int CURRENT_PIN = A0;

// Variables
int motorSpeed = 0;
long duration;
int distance;
float currentVal = 0.0;

void setup() {
  Serial.begin(9600);
  
  // Motor Pins
  pinMode(ENA, OUTPUT);
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(ENB, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  
  // Ultrasonic Pins
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  
  stopMotors();
  Serial.println("STATUS:READY");
}

void loop() {
  checkObstacle();
  readCurrent();
  
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    parseCommand(cmd);
  }
  
  // Periodic status feedback (every 500ms approx)
  static unsigned long lastUpdate = 0;
  if (millis() - lastUpdate > 500) {
    sendStatus();
    lastUpdate = millis();
  }
}

void parseCommand(String cmd) {
  cmd.trim();
  int colonIndex = cmd.indexOf(':');
  char action = cmd.charAt(0);
  
  if (colonIndex != -1) {
    motorSpeed = cmd.substring(colonIndex + 1).toInt();
    motorSpeed = constrain(motorSpeed, 0, 255);
  }

  // Safety check: Don't move forward if obstacle is near
  if (distance < 20 && action == 'F') {
    Serial.println("ERROR:OBSTACLE_DETECTED");
    stopMotors();
    return;
  }

  switch (action) {
    case 'F': moveForward(motorSpeed); break;
    case 'B': moveBackward(motorSpeed); break;
    case 'L': turnLeft(motorSpeed); break;
    case 'R': turnRight(motorSpeed); break;
    case 'S': stopMotors(); break;
    default: Serial.println("ERROR:INVALID_CMD"); break;
  }
}

void moveForward(int s) {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  analogWrite(ENA, s); analogWrite(ENB, s);
}

void moveBackward(int s) {
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
  analogWrite(ENA, s); analogWrite(ENB, s);
}

void turnLeft(int s) {
  digitalWrite(IN1, LOW); digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW);
  analogWrite(ENA, s); analogWrite(ENB, s);
}

void turnRight(int s) {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, HIGH);
  analogWrite(ENA, s); analogWrite(ENB, s);
}

void stopMotors() {
  digitalWrite(IN1, LOW); digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW); digitalWrite(IN4, LOW);
  analogWrite(ENA, 0); analogWrite(ENB, 0);
}

void checkObstacle() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  duration = pulseIn(ECHO_PIN, HIGH);
  distance = duration * 0.034 / 2;
}

void readCurrent() {
  int sensorValue = analogRead(CURRENT_PIN);
  // Basic conversion for ACS712-05B
  currentVal = (sensorValue - 512) * (5.0 / 1024.0) / 0.185; 
}

void sendStatus() {
  Serial.print("SPEED:"); Serial.print(motorSpeed);
  Serial.print(",DIST:"); Serial.print(distance);
  Serial.print(",CURR:"); Serial.println(currentVal);
}
