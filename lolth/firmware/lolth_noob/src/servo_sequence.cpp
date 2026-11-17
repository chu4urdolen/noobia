#include "lolth_config.h"

#include <core/noob_sequence_program.h>

namespace {
// Demonstrates two independently timed Noob sequence channels. The user must
// arm servo 1 first. The +5/-5 degree pairs return to the starting angle.
constexpr uint8_t UP_BITS[] = {1, 0, 1, 0};
constexpr uint8_t DOWN_BITS[] = {0, 1, 0, 1};
constexpr int32_t STEP_ARGS[] = {5};
const SequenceService::ChannelDefinition WIGGLE_CHANNELS[] = {
    {LolthFunctions::SERVO1_UP, 300, UP_BITS, 4, STEP_ARGS, 1},
    {LolthFunctions::SERVO1_DOWN, 300, DOWN_BITS, 4, STEP_ARGS, 1}};
NoobSequenceProgram wiggle(WIGGLE_CHANNELS, 2);
}

NoobFunction &lolthServo1Wiggle() { return wiggle; }
