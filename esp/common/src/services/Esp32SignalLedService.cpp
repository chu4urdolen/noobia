#include "services/Esp32SignalLedService.h"

namespace {
int signalLedPin = -1;
}

namespace Esp32SignalLedService {
bool begin(uint8_t pin) {
  signalLedPin = pin;
  pinMode(pin, OUTPUT);
  digitalWrite(pin, LOW);
  return true;
}

NativeResult set(const int32_t *arguments, uint8_t argumentCount) {
  if (signalLedPin < 0) return {false, 0, "signal LED unavailable"};
  if (argumentCount != 1 || (arguments[0] != 0 && arguments[0] != 1)) {
    return {false, 0, "LED_SIGNAL expects 0 or 1"};
  }
  digitalWrite(signalLedPin, arguments[0] ? HIGH : LOW);
  return {true, arguments[0], "state=" + String(arguments[0])};
}
}
