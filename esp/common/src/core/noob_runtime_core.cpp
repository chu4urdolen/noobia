#include "core/noob_runtime_core.h"
#include "core/noob_function_ids.h"
#include "services/MonotonicTimeService.h"
#include "services/SequenceService.h"

NoobRuntime::NoobRuntime(const char *noobName, const char *firmwareVersion)
    : vm_(natives_),
      dispatcher_(noobName, firmwareVersion, vm_, natives_, capabilities_) {
  natives_.add(CommonFunctionIds::TIME_NOW, "TIME_NOW",
               MonotonicTimeService::now);
  natives_.add(CommonFunctionIds::TIME_RESET, "TIME_RESET",
               MonotonicTimeService::reset);
  SequenceService::begin(natives_);
  natives_.add(CommonFunctionIds::SEQUENCE_SET, "SEQUENCE_SET",
               SequenceService::configurationFunction());
  natives_.add(CommonFunctionIds::SEQUENCE_START, "SEQUENCE_START",
               SequenceService::start);
  natives_.add(CommonFunctionIds::SEQUENCE_STOP, "SEQUENCE_STOP",
               SequenceService::stop);
  natives_.add(CommonFunctionIds::SEQUENCE_STATUS, "SEQUENCE_STATUS",
               SequenceService::status);
  natives_.add(CommonFunctionIds::SEQUENCE_CLEAR, "SEQUENCE_CLEAR",
               SequenceService::clear);
  natives_.add(CommonFunctionIds::SEQUENCE_POP, "SEQUENCE_POP",
               SequenceService::pop);
  natives_.add(CommonFunctionIds::SEQUENCE_QUEUE_SIZE, "SEQUENCE_QUEUE_SIZE",
               SequenceService::queueSize);
  natives_.add(CommonFunctionIds::SEQUENCE_QUEUE_CLEAR,
               "SEQUENCE_QUEUE_CLEAR", SequenceService::clearQueue);
  natives_.add(CommonFunctionIds::SEQUENCE_BUSY, "SEQUENCE_BUSY",
               SequenceService::busy);
  addService(SequenceService::backgroundService());
  capabilities_.add("TIME_MONOTONIC");
  capabilities_.add("THREAD_VM");
  capabilities_.add("SEQUENCES");
}

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
void NoobRuntime::setVmLifecycle(NoobVmLifecycle &lifecycle) {
  dispatcher_.setVmLifecycle(&lifecycle);
}

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
