#pragma once

#include <Arduino.h>
#include "transport/noob_transport.h"
#include "commands/noob_command_dispatcher.h"
#include "core/noob_background_service.h"

class NoobRuntime {
 public:
  // Runtime owns no hardware. The physical Noob registers capabilities and
  // native functions, then attaches one or more message transports.
  static constexpr size_t MAX_TRANSPORTS = 4;
  static constexpr size_t MAX_SERVICES = 12;
  NoobRuntime(const char *noobName, const char *firmwareVersion);
  bool addTransport(NoobTransport &transport);
  bool addService(NoobBackgroundService &service);
  NativeRegistry &natives();
  CapabilityRegistry &capabilities();
  NoobVm &vm();
  void setVmLifecycle(NoobVmLifecycle &lifecycle);
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
