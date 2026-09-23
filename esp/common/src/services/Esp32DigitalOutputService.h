#pragma once

#include <Arduino.h>
#include "syscalls/NativeRegistry.h"

// Reusable one-pin output primitive. Board modules decide which pins callers
// may reach; this service contains no board names or pin map.
namespace Esp32DigitalOutputService {
NativeResult set(int pin, bool high);
}

// Binds one board-selected pin to the common integer function interface.
class Esp32DigitalOutputFunction final : public NoobFunction {
 public:
  explicit Esp32DigitalOutputFunction(int pin) : pin_(pin) {}
  bool acceptsNumbers() const override { return true; }
  NativeResult call(const int32_t *arguments, uint8_t count) override;

 private:
  int pin_;
};
