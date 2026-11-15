#pragma once

#include <Arduino.h>

class HalDigitalIo {
 public:
  virtual ~HalDigitalIo() = default;
  virtual bool configure(uint8_t pin, uint8_t mode) = 0;
  virtual bool write(uint8_t pin, bool value) = 0;
  virtual bool read(uint8_t pin, bool &value) = 0;
};

class HalClock {
 public:
  virtual ~HalClock() = default;
  virtual uint32_t milliseconds() const = 0;
};

class HalStorage {
 public:
  virtual ~HalStorage() = default;
  virtual bool ready() const = 0;
  virtual bool remove(const String &path) = 0;
};
