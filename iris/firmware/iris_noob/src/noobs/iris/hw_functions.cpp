#include "hw_functions.h"

#include "iris_config.h"
#include <services/Esp32DigitalOutputService.h>
#include <services/Esp32UltrasonicService.h>

namespace {
Esp32DigitalOutputFunction blueLed(IrisPins::EXTERNAL_LED_2);
Esp32DigitalOutputFunction redLed(IrisPins::EXTERNAL_LED_0);

class IrisDistanceFunction final : public NoobFunction {
 public:
  bool acceptsNumbers() const override { return true; }
  NativeResult call(const int32_t *, uint8_t count) override {
    if (count > 1) return {false, 0, "usage: no arguments"};
    return Esp32UltrasonicService::measure(nullptr, 0);
  }
};

IrisDistanceFunction distance;
}

NoobFunction &irisBlueLedFunction() { return blueLed; }
NoobFunction &irisRedLedFunction() { return redLed; }
NoobFunction &irisDistanceFunction() { return distance; }
