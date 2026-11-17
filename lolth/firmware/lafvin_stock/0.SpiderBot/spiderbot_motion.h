#ifndef spiderbot_motion_h
#define spiderbot_motion_h

#include <Arduino.h>
#include <Servo.h>

#include "actionarray.h"

class SpiderBotMotion {
public:
    Servo GPIO14SERVO;
    Servo GPIO12SERVO;
    Servo GPIO13SERVO;
    Servo GPIO15SERVO;
    Servo GPIO16SERVO;
    Servo GPIO5SERVO;
    Servo GPIO4SERVO;
    Servo GPIO2SERVO;

    void Servo_PROGRAM_Zero(); // Move all servos to the zero pose.
    void Set_PWM_to_Servo(int iServo, int iValue); // Apply one target angle to a servo channel.
    void Servo_PROGRAM_Run(const int iMatrix[][ALLMATRIX], int iSteps); // Execute one motion matrix.
    void Servo_PROGRAM_Center(); // Move all servos to the center / standby pose.
    void Servo_Setup(); // Load the initial servo pose.

    void standby(); // Idle / standby pose.
    void forward(); // Walk forward.
    void backward(); // Walk backward.
    void leftshift(); // Shift left.
    void rightshift(); // Shift right.
    void turnleft(); // Turn left.
    void turnright(); // Turn right.
    void lie(); // Lie down.
    void hello(); // Greeting motion.
    void fighting(); // Fighting pose.
    void pushup(); // Push-up motion.
    void sleep(); // Sleep pose.
    void dance1(); // Dance motion 1.
    void dance2(); // Dance motion 2.
    void dance3(); // Dance motion 3.
    void center();
    void zero();

    void init();
    void calibration();
};

#endif
