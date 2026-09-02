#include "core/Runtime.h"

NoobRuntime::NoobRuntime(const char *noobName, const char *firmwareVersion)
    : vm_(natives_),
      dispatcher_(noobName, firmwareVersion, vm_, natives_, capabilities_) {}

bool NoobRuntime::addTransport(NoobTransport &transport) {
  if (transportCount_ >= MAX_TRANSPORTS) return false;
  transports_[transportCount_++] = &transport;
  return true;
}

bool NoobRuntime::addService(NoobBackgroundService &service) {
  if (serviceCount_ >= MAX_SERVICES) return false;
  services_[serviceCount_++] = &service;
  return true;
}

NativeRegistry &NoobRuntime::natives() { return natives_; }
CapabilityRegistry &NoobRuntime::capabilities() { return capabilities_; }
NoobVm &NoobRuntime::vm() { return vm_; }

void NoobRuntime::loop() {
  // VM execution is cooperative: each pass consumes a bounded instruction
  // budget before transports are serviced, so WAIT and long programs do not
  // permanently starve command handling.
  vm_.tick();
  for (size_t serviceIndex = 0; serviceIndex < serviceCount_; ++serviceIndex) {
    String event;
    if (!services_[serviceIndex]->tick(event) || event.isEmpty()) continue;
    for (size_t transportIndex = 0; transportIndex < transportCount_;
         ++transportIndex) {
      transports_[transportIndex]->send(event);
    }
  }
  for (size_t index = 0; index < transportCount_; ++index) {
    String frame;
    if (!transports_[index]->receive(frame)) continue;
    NoobRequest request;
    String error;
    if (!NoobProtocol::parse(frame, request, error)) {
      // Parse failures travel back over the same transport that supplied the
      // malformed frame. Other transports remain independent.
      transports_[index]->send(
          NoobProtocol::fail(request.requestId.isEmpty() ? "-" : request.requestId,
                             "BAD_FRAME", error));
      continue;
    }
    transports_[index]->send(dispatcher_.dispatch(request));
  }
}
