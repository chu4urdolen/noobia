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

// Every syscall target, from a GPIO primitive to a reusable behavior, shares
// this interface. VM, BLE, threads, and sequences therefore use one call path.
class NoobFunction {
 public:
  virtual ~NoobFunction() = default;
  virtual bool acceptsNumbers() const { return false; }
  virtual bool acceptsText() const { return false; }
  virtual NativeResult call(const int32_t *, uint8_t) {
    return {false, 0, "numeric call unsupported"};
  }
  virtual NativeResult callText(const String &) {
    return {false, 0, "text call unsupported"};
  }
};

class NumericFunctionAdapter final : public NoobFunction {
 public:
  void bind(NativeFunction function) { function_ = function; }
  bool acceptsNumbers() const override { return function_ != nullptr; }
  NativeResult call(const int32_t *arguments, uint8_t count) override {
    return function_ ? function_(arguments, count)
                     : NativeResult{false, 0, "numeric function not bound"};
  }

 private:
  NativeFunction function_ = nullptr;
};

class TextFunctionAdapter final : public NoobFunction {
 public:
  void bind(NativeTextFunction function) { function_ = function; }
  bool acceptsText() const override { return function_ != nullptr; }
  NativeResult callText(const String &arguments) override {
    return function_ ? function_(arguments)
                     : NativeResult{false, 0, "text function not bound"};
  }

 private:
  NativeTextFunction function_ = nullptr;
};

struct NativeEntry {
  uint16_t id;
  const char *name;
  NoobFunction *implementation;
};

class NativeRegistry {
 public:
  static constexpr size_t MAX_FUNCTIONS = 64;
  bool add(uint16_t id, const char *name, NativeFunction function);
  bool addText(uint16_t id, const char *name, NativeTextFunction function);
  bool add(uint16_t id, const char *name, NoobFunction &implementation);
  const NativeEntry *find(uint16_t id) const;
  const NativeEntry *find(const String &name) const;
  NativeResult call(const NativeEntry &entry, const int32_t *arguments,
                    uint8_t count) const;
  NativeResult callText(const NativeEntry &entry,
                        const String &arguments) const;
  String list() const;

 private:
  NativeEntry entries_[MAX_FUNCTIONS] = {};
  NumericFunctionAdapter numericAdapters_[MAX_FUNCTIONS];
  TextFunctionAdapter textAdapters_[MAX_FUNCTIONS];
  size_t count_ = 0;
};
