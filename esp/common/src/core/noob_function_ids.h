#pragma once

#include <stdint.h>

// IDs 1..99 are stable functions supplied by every NoobRuntime.
namespace CommonFunctionIds {
constexpr uint16_t TIME_NOW = 1;
constexpr uint16_t TIME_RESET = 2;
constexpr uint16_t SEQUENCE_SET = 3;
constexpr uint16_t SEQUENCE_START = 4;
constexpr uint16_t SEQUENCE_STOP = 5;
constexpr uint16_t SEQUENCE_STATUS = 6;
constexpr uint16_t SEQUENCE_CLEAR = 7;
constexpr uint16_t SEQUENCE_POP = 8;
constexpr uint16_t SEQUENCE_QUEUE_SIZE = 9;
constexpr uint16_t SEQUENCE_QUEUE_CLEAR = 10;
constexpr uint16_t SEQUENCE_BUSY = 11;
}
