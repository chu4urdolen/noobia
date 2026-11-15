#pragma once

#include <Arduino.h>
#include "core/noob_record.h"

struct NativeResult {
  bool ok;
  int32_t value;
  String detail;
  NoobRecord record;
};

using NativeFunction = NativeResult (*)(const int32_t *arguments,
                                        uint8_t argumentCount);
using NativeTextFunction = NativeResult (*)(const String &arguments);
using NativeMixedFunction = NativeResult (*)(const int32_t *arguments,
                                             uint8_t argumentCount,
                                             const String &ascii);

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
  virtual NativeResult callMixed(const int32_t *arguments, uint8_t count,
                                 const String &ascii) {
    if (ascii.isEmpty() && acceptsNumbers()) return call(arguments, count);
    if (!count && acceptsText()) return callText(ascii);
    return {false, 0, "mixed arguments unsupported"};
  }
};

class MixedFunctionAdapter final : public NoobFunction {
 public:
  void bind(NativeMixedFunction function) { function_ = function; }
  bool acceptsNumbers() const override { return function_ != nullptr; }
  bool acceptsText() const override { return function_ != nullptr; }
  NativeResult call(const int32_t *arguments, uint8_t count) override {
    return callMixed(arguments, count, String());
  }
  NativeResult callText(const String &ascii) override {
    return callMixed(nullptr, 0, ascii);
  }
  NativeResult callMixed(const int32_t *arguments, uint8_t count,
                         const String &ascii) override {
    return function_ ? function_(arguments, count, ascii)
                     : NativeResult{false, 0, "mixed function not bound"};
  }

 private:
  NativeMixedFunction function_ = nullptr;
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
  static constexpr size_t MAX_FUNCTIONS = 128;
  bool add(uint16_t id, const char *name, NativeFunction function);
  bool addText(uint16_t id, const char *name, NativeTextFunction function);
  bool addMixed(uint16_t id, const char *name, NativeMixedFunction function);
  bool add(uint16_t id, const char *name, NoobFunction &implementation);
  const NativeEntry *find(uint16_t id) const;
  const NativeEntry *find(const String &name) const;
  NativeResult call(const NativeEntry &entry, const int32_t *arguments,
                    uint8_t count) const;
  NativeResult callText(const NativeEntry &entry,
                        const String &arguments) const;
  NativeResult callMixed(const NativeEntry &entry, const int32_t *arguments,
                         uint8_t count, const String &ascii) const;
  static constexpr size_t MAX_ASCII_BYTES = 255;
  String list() const;

 private:
  NativeEntry entries_[MAX_FUNCTIONS] = {};
  NumericFunctionAdapter numericAdapters_[MAX_FUNCTIONS];
  TextFunctionAdapter textAdapters_[MAX_FUNCTIONS];
  MixedFunctionAdapter mixedAdapters_[MAX_FUNCTIONS];
  size_t count_ = 0;
};
