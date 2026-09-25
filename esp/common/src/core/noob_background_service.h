#pragma once

#include <Arduino.h>

// A cooperative service may emit at most one event per runtime pass. This
// keeps background hardware work independent from transports and dispatch.
class NoobBackgroundService {
 public:
  virtual ~NoobBackgroundService() = default;
  virtual bool tick(String &event) = 0;
};
