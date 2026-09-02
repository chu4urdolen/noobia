#pragma once

#include <Arduino.h>

class CapabilityRegistry {
 public:
  static constexpr size_t MAX_CAPABILITIES = 32;
  bool add(const char *capability);
  bool has(const String &capability) const;
  String list() const;

 private:
  const char *items_[MAX_CAPABILITIES] = {};
  size_t count_ = 0;
};
