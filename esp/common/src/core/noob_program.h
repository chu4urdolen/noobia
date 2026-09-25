#pragma once

#include "syscalls/noob_native_registry.h"

enum class NoobProgramType { THREAD, SEQUENCE };

class NoobIntegerQueue {
 public:
  static constexpr uint8_t CAPACITY = 16;

  void push(int32_t value) {
    if (count_ == CAPACITY) {
      head_ = (head_ + 1) % CAPACITY;
      --count_;
      ++dropped_;
    }
    values_[tail_] = value;
    tail_ = (tail_ + 1) % CAPACITY;
    ++count_;
  }

  bool pop(int32_t &value) {
    if (!count_) return false;
    value = values_[head_];
    head_ = (head_ + 1) % CAPACITY;
    --count_;
    return true;
  }

  void clear() { head_ = tail_ = count_ = 0; dropped_ = 0; }
  uint8_t size() const { return count_; }
  uint32_t dropped() const { return dropped_; }

 private:
  int32_t values_[CAPACITY] = {};
  uint8_t head_ = 0;
  uint8_t tail_ = 0;
  uint8_t count_ = 0;
  uint32_t dropped_ = 0;
};

// Channel calls are void. Results, when meaningful, enter the channel queue.
class NoobProgramChannel {
 public:
  static constexpr uint8_t MAX_ARGUMENTS = 7;

  bool configure(uint16_t functionId, const int32_t *arguments,
                 uint8_t argumentCount) {
    if (argumentCount > MAX_ARGUMENTS ||
        (argumentCount && !arguments)) return false;
    functionId_ = functionId;
    argumentCount_ = argumentCount;
    for (uint8_t index = 0; index < argumentCount; ++index)
      arguments_[index] = arguments[index];
    results_.clear();
    lastOk_ = true;
    lastDetail_ = "";
    return true;
  }

  void invoke(NativeRegistry &registry, int32_t input,
              bool appendInput = true) {
    busy_ = true;
    const NativeEntry *entry = registry.find(functionId_);
    if (!entry) {
      lastOk_ = false;
      lastDetail_ = "function missing";
      busy_ = false;
      return;
    }
    int32_t callArguments[8] = {};
    for (uint8_t index = 0; index < argumentCount_; ++index)
      callArguments[index] = arguments_[index];
    if (appendInput) callArguments[argumentCount_] = input;
    const NativeResult result =
        registry.call(*entry, callArguments,
                      argumentCount_ + (appendInput ? 1 : 0));
    lastOk_ = result.ok;
    lastDetail_ = result.detail;
    if (result.ok) results_.push(result.value);
    busy_ = false;
  }

  uint16_t functionId() const { return functionId_; }
  bool lastOk() const { return lastOk_; }
  const String &lastDetail() const { return lastDetail_; }
  bool busy() const { return busy_; }
  NoobIntegerQueue &results() { return results_; }

 private:
  uint16_t functionId_ = 0;
  int32_t arguments_[MAX_ARGUMENTS] = {};
  uint8_t argumentCount_ = 0;
  bool lastOk_ = true;
  volatile bool busy_ = false;
  String lastDetail_;
  NoobIntegerQueue results_;
};

// Higher-level programs are callable from both BLE and VM syscalls.
class NoobProgram : public NoobFunction {
 public:
  explicit NoobProgram(NoobProgramType type) : type_(type) {}
  NoobProgramType type() const { return type_; }
  virtual NativeResult stop() = 0;

 private:
  NoobProgramType type_;
};
