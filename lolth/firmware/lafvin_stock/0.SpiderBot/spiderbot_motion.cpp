#include "spiderbot_motion.h"

#include <EEPROM.h>

#include "webserver.h"

// This file is the low-level motion layer for SpiderBot.
// It is responsible for:
// 1. attaching the eight servo outputs
// 2. applying EEPROM-based calibration offsets
// 3. interpolating between keyframes from actionarray.h
// 4. exposing one method per high-level robot action

// Cached servo state for interpolated motion playback.
int Running_Servo_POS[ALLMATRIX];

// Base interpolation interval in milliseconds.
int BASEDELAYTIME = 10;

void SpiderBotMotion::Servo_PROGRAM_Zero()
{
    // Reset the cached state first so future interpolated motions start
    // from the same pose the hardware was just moved to.
    for (int index = 0; index < ALLMATRIX; index++) {
        Running_Servo_POS[index] = Servo_Act_0[index];
    }

    // Drive each channel to the zero pose one by one.
    for (int iServo = 0; iServo < ALLSERVOS; iServo++) {
        Set_PWM_to_Servo(iServo, Running_Servo_POS[iServo]);
        delay(10);
    }
}

void SpiderBotMotion::Set_PWM_to_Servo(int iServo, int iValue)
{
    // Each servo stores a signed trim value in EEPROM so the same motion
    // table can still work after mechanical assembly differences.
    int NewPWM = iValue + (int8_t)EEPROM.read(iServo);
    NewPWM = map(NewPWM, PWMRES_Min, PWMRES_Max, SERVOMIN, SERVOMAX);

    // Logical servo order is fixed across the project. This mapping turns
    // a logical index from the motion tables into the actual GPIO servo.
    if (iServo >= 7) {
        GPIO2SERVO.write(NewPWM);
    } else if (iServo >= 6) {
        GPIO4SERVO.write(NewPWM);
    } else if (iServo >= 5) {
        GPIO5SERVO.write(NewPWM);
    } else if (iServo >= 4) {
        GPIO16SERVO.write(NewPWM);
    } else if (iServo >= 3) {
        GPIO15SERVO.write(NewPWM);
    } else if (iServo >= 2) {
        GPIO13SERVO.write(NewPWM);
    } else if (iServo >= 1) {
        GPIO12SERVO.write(NewPWM);
    } else if (iServo == 0) {
        GPIO14SERVO.write(NewPWM);
    }
}

void SpiderBotMotion::Servo_PROGRAM_Run(const int iMatrix[][ALLMATRIX], int iSteps)
{
    int INT_TEMP_A, INT_TEMP_B, INT_TEMP_C;

    for (int MainLoopIndex = 0; MainLoopIndex < iSteps; MainLoopIndex++) {
        // Stop requests are checked before each keyframe and during the
        // interpolation loop so API / avoid-mode stop commands can break in.
        if (isRobotStopRequested()) {
            return;
        }

        int InterTotalTime = iMatrix[MainLoopIndex][ALLMATRIX - 1];
        int InterDelayCounter = InterTotalTime / BASEDELAYTIME;

        for (int InterStepLoop = 0; InterStepLoop < InterDelayCounter; InterStepLoop++) {
            // Keep the web server responsive even while a blocking motion
            // sequence is being played back.
            handleClient();

            if (isRobotStopRequested()) {
                return;
            }

            for (int ServoIndex = 0; ServoIndex < ALLSERVOS; ServoIndex++) {
                INT_TEMP_A = Running_Servo_POS[ServoIndex];
                INT_TEMP_B = iMatrix[MainLoopIndex][ServoIndex];

                if (INT_TEMP_A == INT_TEMP_B) {
                    INT_TEMP_C = INT_TEMP_B;
                } else if (INT_TEMP_A > INT_TEMP_B) {
                    // Interpolate down toward the target angle.
                    INT_TEMP_C = map(BASEDELAYTIME * InterStepLoop, 0, InterTotalTime, 0, INT_TEMP_A - INT_TEMP_B);
                    if (INT_TEMP_A - INT_TEMP_C >= INT_TEMP_B) {
                        Set_PWM_to_Servo(ServoIndex, INT_TEMP_A - INT_TEMP_C);
                    }
                } else if (INT_TEMP_A < INT_TEMP_B) {
                    // Interpolate up toward the target angle.
                    INT_TEMP_C = map(BASEDELAYTIME * InterStepLoop, 0, InterTotalTime, 0, INT_TEMP_B - INT_TEMP_A);
                    if (INT_TEMP_A + INT_TEMP_C <= INT_TEMP_B) {
                        Set_PWM_to_Servo(ServoIndex, INT_TEMP_A + INT_TEMP_C);
                    }
                }
            }

            delay(BASEDELAYTIME);
        }

        for (int index = 0; index < ALLMATRIX; index++) {
            Running_Servo_POS[index] = iMatrix[MainLoopIndex][index];
        }
    }
}

void SpiderBotMotion::Servo_PROGRAM_Center()
{
    // Servo_Act_1 is the project's neutral standby pose.
    for (int index = 0; index < ALLMATRIX; index++) {
        Running_Servo_POS[index] = Servo_Act_1[index];
    }

    for (int iServo = 0; iServo < ALLSERVOS; iServo++) {
        Set_PWM_to_Servo(iServo, Running_Servo_POS[iServo]);
        delay(10);
    }
}

void SpiderBotMotion::init()
{
    // Attach all servo channels with the same min/max pulse range that is
    // used by the rest of the motion system.
    GPIO14SERVO.attach(14, SERVOMIN, SERVOMAX);
    GPIO12SERVO.attach(12, SERVOMIN, SERVOMAX);
    GPIO13SERVO.attach(13, SERVOMIN, SERVOMAX);
    GPIO15SERVO.attach(15, SERVOMIN, SERVOMAX);
    GPIO16SERVO.attach(16, SERVOMIN, SERVOMAX);
    GPIO5SERVO.attach(5, SERVOMIN, SERVOMAX);
    GPIO4SERVO.attach(4, SERVOMIN, SERVOMAX);
    GPIO2SERVO.attach(2, SERVOMIN, SERVOMAX);
}

void SpiderBotMotion::Servo_Setup()
{
    // Directly write the stored zero pose without interpolation.
    GPIO14SERVO.write(Servo_Act_0[0]);
    GPIO12SERVO.write(Servo_Act_0[1]);
    GPIO13SERVO.write(Servo_Act_0[2]);
    GPIO15SERVO.write(Servo_Act_0[3]);
    GPIO16SERVO.write(Servo_Act_0[4]);
    GPIO5SERVO.write(Servo_Act_0[5]);
    GPIO4SERVO.write(Servo_Act_0[6]);
    GPIO2SERVO.write(Servo_Act_0[7]);
}

void SpiderBotMotion::calibration()
{
    // Simple serial calibration helper kept for bench testing.
    // Expected command: S,<servo_pin>,<offset>
    while (Serial.available() > 0) {
        char command = Serial.read();

        // Servo command format: S,<servo_pin>,<offset>
        if (command == 'S' || command == 's') {
            Serial.print(command);
            Serial.print(',');
            int servoNo = Serial.parseInt();
            Serial.print(servoNo);
            Serial.print(',');
            int servoAngle = Serial.parseInt();
            Serial.print(servoAngle);
            Serial.println();

            switch (servoNo) {
                case 14:
                    GPIO14SERVO.write(Servo_Act_0[0] + servoAngle);
                    break;
                case 12:
                    GPIO12SERVO.write(Servo_Act_0[1] + servoAngle);
                    break;
                case 13:
                    GPIO13SERVO.write(Servo_Act_0[2] + servoAngle);
                    break;
                case 15:
                    GPIO15SERVO.write(Servo_Act_0[3] + servoAngle);
                    break;
                case 16:
                    GPIO16SERVO.write(Servo_Act_0[4] + servoAngle);
                    break;
                case 5:
                    GPIO5SERVO.write(Servo_Act_0[5] + servoAngle);
                    break;
                case 4:
                    GPIO4SERVO.write(Servo_Act_0[6] + servoAngle);
                    break;
                case 2:
                    GPIO2SERVO.write(Servo_Act_0[7] + servoAngle);
                    break;
                default:
                    break;
            }
        }
    }
}

void SpiderBotMotion::standby()
{
    Servo_PROGRAM_Run(Servo_Prg_1, Servo_Prg_1_Step);
}

void SpiderBotMotion::forward()
{
    Servo_PROGRAM_Run(Servo_Prg_2, Servo_Prg_2_Step);
}

void SpiderBotMotion::backward()
{
    Servo_PROGRAM_Run(Servo_Prg_3, Servo_Prg_3_Step);
}

void SpiderBotMotion::leftshift()
{
    Servo_PROGRAM_Run(Servo_Prg_4, Servo_Prg_4_Step);
}

void SpiderBotMotion::rightshift()
{
    Servo_PROGRAM_Run(Servo_Prg_5, Servo_Prg_5_Step);
}

void SpiderBotMotion::turnleft()
{
    Servo_PROGRAM_Run(Servo_Prg_6, Servo_Prg_6_Step);
}

void SpiderBotMotion::turnright()
{
    Servo_PROGRAM_Run(Servo_Prg_7, Servo_Prg_7_Step);
}

void SpiderBotMotion::lie()
{
    Servo_PROGRAM_Run(Servo_Prg_8, Servo_Prg_8_Step);
}

void SpiderBotMotion::hello()
{
    // The hello motion intentionally returns to standby when it finishes.
    Servo_PROGRAM_Run(Servo_Prg_9, Servo_Prg_9_Step);
    Servo_PROGRAM_Run(Servo_Prg_1, Servo_Prg_1_Step);
}

void SpiderBotMotion::fighting()
{
    Servo_PROGRAM_Run(Servo_Prg_10, Servo_Prg_10_Step);
}

void SpiderBotMotion::pushup()
{
    Servo_PROGRAM_Run(Servo_Prg_11, Servo_Prg_11_Step);
}

void SpiderBotMotion::sleep()
{
    // Sleep first passes through standby so the robot reaches the rest pose
    // from a predictable body position.
    Servo_PROGRAM_Run(Servo_Prg_1, Servo_Prg_1_Step);
    Servo_PROGRAM_Run(Servo_Prg_12, Servo_Prg_12_Step);
}

void SpiderBotMotion::dance1()
{
    Servo_PROGRAM_Run(Servo_Prg_13, Servo_Prg_13_Step);
}

void SpiderBotMotion::dance2()
{
    Servo_PROGRAM_Run(Servo_Prg_14, Servo_Prg_14_Step);
}

void SpiderBotMotion::dance3()
{
    Servo_PROGRAM_Run(Servo_Prg_15, Servo_Prg_15_Step);
}

void SpiderBotMotion::center()
{
    Servo_PROGRAM_Center();
    delay(300);
}

void SpiderBotMotion::zero()
{
    Servo_PROGRAM_Zero();
    delay(300);
}
