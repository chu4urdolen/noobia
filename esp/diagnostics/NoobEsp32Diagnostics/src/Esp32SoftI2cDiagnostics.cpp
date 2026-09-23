#include "Esp32SoftI2cDiagnostics.h"

namespace {
int configuredSda = -1;
int configuredScl = -1;

void releaseLine(int pin) { pinMode(pin, INPUT_PULLUP); }
void lowerLine(int pin) { pinMode(pin, OUTPUT); digitalWrite(pin, LOW); }
void halfClock() { delayMicroseconds(5); }
}

namespace Esp32SoftI2cDiagnostics {
bool begin(int sdaPin, int sclPin) {
  configuredSda = sdaPin;
  configuredScl = sclPin;
  releaseLine(configuredSda);
  releaseLine(configuredScl);
  return true;
}

bool probe(uint8_t address) {
  if (configuredSda < 0 || configuredScl < 0) return false;
  releaseLine(configuredSda); releaseLine(configuredScl); halfClock();
  lowerLine(configuredSda); halfClock(); lowerLine(configuredScl);
  uint8_t value = address << 1;
  for (uint8_t mask = 0x80; mask; mask >>= 1) {
    if (value & mask) releaseLine(configuredSda); else lowerLine(configuredSda);
    halfClock(); releaseLine(configuredScl); halfClock(); lowerLine(configuredScl);
  }
  releaseLine(configuredSda); halfClock(); releaseLine(configuredScl); halfClock();
  const bool acknowledged = digitalRead(configuredSda) == LOW;
  lowerLine(configuredScl); lowerLine(configuredSda); halfClock();
  releaseLine(configuredScl); halfClock(); releaseLine(configuredSda); halfClock();
  return acknowledged;
}

NativeResult scan(const int32_t *, uint8_t) {
  if (configuredSda < 0 || configuredScl < 0)
    return {false, 0, "software I2C pins unavailable"};
  String addresses;
  int32_t found = 0;
  for (uint8_t address = 1; address < 127; ++address) {
    if (probe(address)) {
      if (addresses.length()) addresses += ",";
      char text[5];
      snprintf(text, sizeof(text), "0x%02X", address);
      addresses += text;
      ++found;
    }
  }
  return {true, found, "software_devices=" + addresses};
}
}
