#include "services/Esp32RgbLedService.h"

#include <esp32-hal-rgb-led.h>

namespace {
int statusLedPin = -1;
}

namespace Esp32RgbLedService {
bool begin(uint8_t pin) {
  statusLedPin = pin;
  // Leave the LED dark until a native call or VM program chooses a colour.
  rgbLedWrite(pin, 0, 0, 0);
  return true;
}

NativeResult set(const int32_t *arguments, uint8_t argumentCount) {
  if (statusLedPin < 0) return {false, 0, "RGB LED unavailable"};
  if (argumentCount != 3) return {false, 0, "LED_RGB expects red green blue"};
  for (uint8_t index = 0; index < 3; ++index) {
    if (arguments[index] < 0 || arguments[index] > 255) {
      return {false, 0, "RGB values must be 0..255"};
    }
  }
  rgbLedWrite(statusLedPin, arguments[0], arguments[1], arguments[2]);
  return {true, 0, "rgb=" + String(arguments[0]) + "," +
                       String(arguments[1]) + "," + String(arguments[2])};
}
}
