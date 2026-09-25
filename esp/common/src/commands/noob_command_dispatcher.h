#pragma once

#include <Arduino.h>
#include "protocol/noob_protocol.h"
#include "vm/noob_vm.h"
#include "syscalls/noob_native_registry.h"
#include "core/noob_capability_registry.h"
#include "core/noob_vm_lifecycle.h"

class CommandDispatcher {
 public:
  CommandDispatcher(const char *noobName, const char *firmwareVersion,
                    NoobVm &vm, NativeRegistry &natives,
                    CapabilityRegistry &capabilities);
  void setVmLifecycle(NoobVmLifecycle *lifecycle);
  String dispatch(const NoobRequest &request);

 private:
  bool decodeHex(const String &text, uint8_t *output, size_t capacity,
                 size_t &length, String &error);
  String callNative(const NoobRequest &request);
  String callTextNative(const NoobRequest &request);

  const char *noobName_;
  const char *firmwareVersion_;
  NoobVm &vm_;
  NativeRegistry &natives_;
  CapabilityRegistry &capabilities_;
  NoobVmLifecycle *lifecycle_ = nullptr;
};
