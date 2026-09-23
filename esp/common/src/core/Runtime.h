#pragma once

#include <Arduino.h>
#include "transport/Transport.h"
#include "commands/CommandDispatcher.h"
#include "core/BackgroundService.h"

class NoobRuntime {
 public:
  // Runtime owns no hardware. The physical Noob registers capabilities and
  // native functions, then attaches one or more message transports.
  static constexpr size_t MAX_TRANSPORTS = 4;
  static constexpr size_t MAX_SERVICES = 8;
  NoobRuntime(const char *noobName, const char *firmwareVersion);
  bool addTransport(NoobTransport &transport);
  bool addService(NoobBackgroundService &service);
  NativeRegistry &natives();
  CapabilityRegistry &capabilities();
  NoobVm &vm();
  void loop();

 private:
  NativeRegistry natives_;
  CapabilityRegistry capabilities_;
  NoobVm vm_;
  CommandDispatcher dispatcher_;
  NoobTransport *transports_[MAX_TRANSPORTS] = {};
  size_t transportCount_ = 0;
  NoobBackgroundService *services_[MAX_SERVICES] = {};
  size_t serviceCount_ = 0;
};
