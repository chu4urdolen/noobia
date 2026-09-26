#include "services/Esp32IrDecoder.h"

namespace {
bool within(uint32_t value, uint32_t minimum, uint32_t maximum) {
  return value >= minimum && value <= maximum;
}

bool mark(const uint8_t *levels, const uint32_t *durations, size_t index,
          uint32_t minimum, uint32_t maximum) {
  return levels[index] == LOW && within(durations[index], minimum, maximum);
}

bool space(const uint8_t *levels, const uint32_t *durations, size_t index,
           uint32_t minimum, uint32_t maximum) {
  return levels[index] == HIGH && within(durations[index], minimum, maximum);
}
}

namespace Esp32IrDecoder {
bool decode(const uint8_t *levels, const uint32_t *durationsUs, size_t count,
            Frame &frame) {
  frame = {};
  if (!levels || !durationsUs || count < 3) return false;

  // Generic pulse-distance frame seen from this Thomson remote: a roughly
  // 4 ms mark/space lead-in, 24 marks near 500 us, spaces near 1 or 2 ms, then
  // a stop mark. Keep this as a raw code; its address/command split is not
  // defined by the captured evidence.
  for (size_t start = 0; start + 50 < count; ++start) {
    if (!mark(levels, durationsUs, start, 3400, 4600) ||
        !space(levels, durationsUs, start + 1, 3400, 4600))
      continue;
    uint32_t raw = 0;
    bool valid = true;
    for (uint8_t bit = 0; bit < 24; ++bit) {
      const size_t markIndex = start + 2 + size_t(bit) * 2;
      const size_t spaceIndex = markIndex + 1;
      if (!mark(levels, durationsUs, markIndex, 350, 650) ||
          !space(levels, durationsUs, spaceIndex, 800, 2300)) {
        valid = false;
        break;
      }
      if (durationsUs[spaceIndex] >= 1500) raw |= uint32_t(1) << bit;
    }
    if (!valid) continue;
    if (start + 50 < count &&
        !mark(levels, durationsUs, start + 50, 350, 650))
      continue;
    frame.protocol = PULSE_DISTANCE_24;
    frame.code = raw;
    frame.bits = 24;
    return true;
  }

  // Thomson sets commonly use RC5. Expand each run into nominal 889 us
  // Manchester half-bits, allowing the receiver's edge jitter and merged
  // adjacent halves. Try either phase because capture can begin on either
  // side of the receiver's idle transition.
  for (size_t start = 0; start < count; ++start) {
    uint8_t halves[36] = {};
    size_t halfCount = 0;
    size_t edge = start;
    while (edge < count && halfCount < 28) {
      const uint32_t duration = durationsUs[edge];
      const uint32_t units = (duration + 444) / 889;
      if (units < 1 || units > 3 ||
          duration < units * 889 * 65 / 100 ||
          duration > units * 889 * 135 / 100)
        break;
      for (uint32_t unit = 0; unit < units; ++unit)
        halves[halfCount++] = levels[edge];
      ++edge;
    }
    for (size_t offset = 0; offset + 28 <= halfCount; ++offset) {
      uint16_t raw = 0;
      bool valid = true;
      for (uint8_t bit = 0; bit < 14; ++bit) {
        const uint8_t first = halves[offset + size_t(bit) * 2];
        const uint8_t second = halves[offset + size_t(bit) * 2 + 1];
        if (first == second) {
          valid = false;
          break;
        }
        // Active-low receiver: a carrier mark in the first half is bit 1.
        if (first == LOW) raw |= uint16_t(1) << (13 - bit);
      }
      if (!valid) continue;
      const uint8_t startBit = (raw >> 13) & 1;
      const uint8_t fieldBit = (raw >> 12) & 1;
      if (!startBit || (raw & 0x0fff) == 0x0fff) continue;
      const uint16_t address = (raw >> 6) & 0x1f;
      const uint8_t commandLow = raw & 0x3f;
      frame.protocol = RC5;
      frame.address = address;
    frame.data = uint8_t(commandLow | (fieldBit ? 0 : 0x40));
    frame.bits = 14;
    frame.code = raw;
      return true;
    }
  }

  // Captures may contain leading noise or several remote repeats. Search for a
  // complete leader instead of assuming that array element zero is aligned.
  for (size_t start = 0; start + 66 < count; ++start) {
    if (!mark(levels, durationsUs, start, 7500, 10000) ||
        !space(levels, durationsUs, start + 1, 3500, 5500))
      continue;
    uint32_t raw = 0;
    bool valid = true;
    for (uint8_t bit = 0; bit < 32; ++bit) {
      const size_t markIndex = start + 2 + size_t(bit) * 2;
      const size_t spaceIndex = markIndex + 1;
      if (!mark(levels, durationsUs, markIndex, 300, 850) ||
          !space(levels, durationsUs, spaceIndex, 300, 2100)) {
        valid = false;
        break;
      }
      if (durationsUs[spaceIndex] > 1000) raw |= uint32_t(1) << bit;
    }
    if (!valid) continue;
    const uint8_t addressLow = raw & 0xff;
    const uint8_t addressHigh = (raw >> 8) & 0xff;
    const uint8_t data = (raw >> 16) & 0xff;
    const uint8_t dataInverse = (raw >> 24) & 0xff;
    if (uint8_t(data ^ dataInverse) != 0xff) continue;

    frame.protocol = NEC;
    frame.address = uint8_t(addressLow ^ addressHigh) == 0xff
                        ? addressLow
                        : uint16_t(addressLow) |
                              (uint16_t(addressHigh) << 8);
    frame.data = data;
    frame.bits = 32;
    frame.code = raw;
    return true;
  }

  // NEC repeat: 9 ms mark, 2.25 ms space, 560 us mark.
  for (size_t start = 0; start + 2 < count; ++start) {
    if (mark(levels, durationsUs, start, 7500, 10000) &&
        space(levels, durationsUs, start + 1, 1700, 3000) &&
        mark(levels, durationsUs, start + 2, 300, 850)) {
      frame.protocol = NEC_REPEAT;
      frame.repeat = true;
      return true;
    }
  }
  return false;
}

const char *protocolName(Protocol protocol) {
  switch (protocol) {
    case NEC: return "NEC";
    case NEC_REPEAT: return "NEC_REPEAT";
    case RC5: return "RC5";
    case PULSE_DISTANCE_24: return "PD24";
    default: return "RAW";
  }
}
}  // namespace Esp32IrDecoder
