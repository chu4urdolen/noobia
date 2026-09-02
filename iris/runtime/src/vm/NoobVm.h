#pragma once

#include <Arduino.h>
#include "syscalls/NativeRegistry.h"

enum class VmState { EMPTY, READY, RUNNING, WAITING, HALTED, STOPPED, FAULT };

class NoobVm {
 public:
  // Fixed limits keep memory use deterministic on small embedded targets.
  static constexpr size_t PROGRAM_BYTES = 1024;
  static constexpr size_t MEMORY_BYTES = 256;
  static constexpr size_t REGISTER_COUNT = 8;
  static constexpr size_t CALL_DEPTH = 8;

  explicit NoobVm(NativeRegistry &natives);
  bool load(const uint8_t *program, size_t length, String &error);
  bool run(String &error);
  void stop();
  void reset();
  void tick(size_t instructionBudget = 32);
  VmState state() const;
  String status() const;
  int32_t reg(uint8_t index) const;

 private:
  bool need(size_t bytes);
  uint8_t read8();
  uint16_t read16();
  int32_t read32();
  bool validRegister(uint8_t index);
  void fault(const String &message);
  void executeOne();

  NativeRegistry &natives_;
  uint8_t program_[PROGRAM_BYTES] = {};
  uint8_t memory_[MEMORY_BYTES] = {};
  int32_t registers_[REGISTER_COUNT] = {};
  uint16_t returnStack_[CALL_DEPTH] = {};
  size_t programLength_ = 0;
  uint16_t pc_ = 0;
  uint8_t stackDepth_ = 0;
  uint32_t wakeAt_ = 0;
  VmState state_ = VmState::EMPTY;
  String faultMessage_;
};
