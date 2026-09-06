#pragma once

#include <Arduino.h>

struct NativeResult {
  bool ok;
  int32_t value;
  String detail;
};

using NativeFunction = NativeResult (*)(const int32_t *arguments,
                                        uint8_t argumentCount);
using NativeTextFunction = NativeResult (*)(const String &arguments);

struct NativeEntry {
  uint16_t id;
  const char *name;
  NativeFunction function;
  NativeTextFunction textFunction;
};

class NativeRegistry {
 public:
  static constexpr size_t MAX_FUNCTIONS = 48;
  bool add(uint16_t id, const char *name, NativeFunction function);
  bool addText(uint16_t id, const char *name, NativeTextFunction function);
  const NativeEntry *find(uint16_t id) const;
  const NativeEntry *find(const String &name) const;
  String list() const;

 private:
  NativeEntry entries_[MAX_FUNCTIONS] = {};
  size_t count_ = 0;
};
