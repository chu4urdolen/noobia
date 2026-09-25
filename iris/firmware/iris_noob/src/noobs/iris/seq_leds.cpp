#include "seq_leds.h"

#include "iris_config.h"
#include <core/noob_sequence_program.h>

namespace {
constexpr uint8_t BLINK_BITS[] = {1, 0, 1, 0, 1, 0, 1, 0};
// Both tracks end low, so a finite sequence always leaves the LEDs dark.
constexpr uint8_t BLUE_POLICE_BITS[] = {1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 0};
constexpr uint8_t RED_POLICE_BITS[] = {0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0};

const SequenceService::ChannelDefinition BLUE_BLINK_CHANNELS[] = {
    {IrisFunctions::LED_BLUE, 250, BLINK_BITS,
     uint8_t(sizeof(BLINK_BITS)), nullptr, 0}};

const SequenceService::ChannelDefinition POLICE_CHANNELS[] = {
    {IrisFunctions::LED_BLUE, IrisHardware::POLICE_STEP_MS, BLUE_POLICE_BITS,
     uint8_t(sizeof(BLUE_POLICE_BITS)), nullptr, 0},
    {IrisFunctions::LED_RED, IrisHardware::POLICE_STEP_MS, RED_POLICE_BITS,
     uint8_t(sizeof(RED_POLICE_BITS)), nullptr, 0}};

class IrisBlueBlinkSequence final : public NoobSequenceProgram {
 public:
  IrisBlueBlinkSequence()
      : NoobSequenceProgram(BLUE_BLINK_CHANNELS,
                            sizeof(BLUE_BLINK_CHANNELS) /
                                sizeof(BLUE_BLINK_CHANNELS[0])) {}
};

class IrisPoliceSequence final : public NoobSequenceProgram {
 public:
  IrisPoliceSequence()
      : NoobSequenceProgram(POLICE_CHANNELS,
                            sizeof(POLICE_CHANNELS) /
                                sizeof(POLICE_CHANNELS[0])) {}
};

IrisBlueBlinkSequence blueBlink;
IrisPoliceSequence police;
}

NoobFunction &irisBlueBlinkSequence() { return blueBlink; }
NoobFunction &irisPoliceSequence() { return police; }
