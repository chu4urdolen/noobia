#pragma once

#include <Arduino.h>

class NoobTransport {
 public:
  virtual ~NoobTransport() = default;
  virtual const char *name() const = 0;
  virtual bool receive(String &message) = 0;
  virtual void send(const String &message) = 0;
};
