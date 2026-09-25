#pragma once

#include <Arduino.h>

class NoobVm;

// Optional persistence/audit hook for common VM state changes.
class NoobVmLifecycle {
 public:
  virtual ~NoobVmLifecycle() = default;
  virtual String onStarted(const NoobVm &vm) = 0;
  virtual String onStopped(const NoobVm &vm) = 0;
  virtual String onReset(const NoobVm &vm) = 0;
};
