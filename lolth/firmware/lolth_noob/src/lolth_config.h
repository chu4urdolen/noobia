#pragma once

#include <Arduino.h>

namespace LolthPins {
// LAFVIN's G14, G12, G13, G15, G16, G5, G4, G2 servo order.
constexpr uint8_t SERVO[8] = {14, 12, 13, 15, 16, 5, 4, 2};
constexpr uint8_t ULTRASONIC_TRIGGER = 1;  // TX
constexpr uint8_t ULTRASONIC_ECHO = 3;     // RX
}

namespace LolthCalibration {
// Reference pose from LAFVIN's course, not yet verified on Lolth's joints.
constexpr uint8_t FACTORY_ZERO[8] = {135, 45, 135, 45, 45, 135, 45, 135};
}

namespace LolthFunctions {
constexpr uint16_t SERVO1_UP = 100;
constexpr uint16_t SERVO1_DOWN = 101;
constexpr uint16_t SERVO2_UP = 102;
constexpr uint16_t SERVO2_DOWN = 103;
constexpr uint16_t SERVO3_UP = 104;
constexpr uint16_t SERVO3_DOWN = 105;
constexpr uint16_t SERVO4_UP = 106;
constexpr uint16_t SERVO4_DOWN = 107;
constexpr uint16_t SERVO5_UP = 108;
constexpr uint16_t SERVO5_DOWN = 109;
constexpr uint16_t SERVO6_UP = 110;
constexpr uint16_t SERVO6_DOWN = 111;
constexpr uint16_t SERVO7_UP = 112;
constexpr uint16_t SERVO7_DOWN = 113;
constexpr uint16_t SERVO8_UP = 114;
constexpr uint16_t SERVO8_DOWN = 115;
constexpr uint16_t SERVO_ARM = 116;
constexpr uint16_t SERVO_SET = 117;
constexpr uint16_t SERVO_STATE = 118;
constexpr uint16_t SERVO_DETACH = 119;
constexpr uint16_t SERVO_DETACH_ALL = 120;
constexpr uint16_t DISTANCE_MM = 121;
constexpr uint16_t SERVO1_WIGGLE = 122;
}
