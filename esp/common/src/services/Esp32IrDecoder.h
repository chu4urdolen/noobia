#pragma once

#include <Arduino.h>

namespace Esp32IrDecoder {

enum Protocol : int32_t {
  RAW = 0,
  NEC = 1,
  NEC_REPEAT = 2,
  RC5 = 3,
  PULSE_DISTANCE_24 = 4,
};

struct Frame {
  Protocol protocol = RAW;
  uint16_t address = 0;
  uint8_t data = 0;
  uint8_t bits = 0;
  uint32_t code = 0;
  bool repeat = false;
};

// Decode the active-low envelope emitted by a demodulating IR receiver.
bool decode(const uint8_t *levels, const uint32_t *durationsUs, size_t count,
            Frame &frame);
const char *protocolName(Protocol protocol);

}  // namespace Esp32IrDecoder
