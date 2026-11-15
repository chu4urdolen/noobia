#pragma once

#include "syscalls/noob_native_registry.h"
#include "core/noob_background_service.h"

// Initialization evidence, not a claim that attached wiring was exercised.
class NoobSelfTest final : public NoobFunction, public NoobBackgroundService {
 public:
  enum class State : uint8_t { UNTESTED, READY, FAILED, PENDING, NOT_AVAILABLE };
  static constexpr uint8_t MAX_CHECKS = 64;
  static constexpr uint8_t MAX_PROBES = 40;
  void bind(NativeRegistry &registry) { registry_ = &registry; }
  bool record(const char *name, State state);
  bool addProbe(const char *name, uint16_t id, const int32_t *arguments,
                uint8_t count, uint8_t attempts, uint32_t retryMs,
                bool pendingOnFailure = false, const char *ascii = "");
  void finish() { planReady_ = true; }
  bool acceptsNumbers() const override { return true; }
  NativeResult call(const int32_t *, uint8_t count) override;
  bool tick(String &event) override;

 private:
  struct Check { char name[40] = {}; State state = State::UNTESTED; };
  Check checks_[MAX_CHECKS] = {};
  uint8_t count_ = 0;
  bool finished_ = false;
  bool eventPending_ = false;
  struct Probe {
    char name[40] = {};
    uint16_t id = 0;
    int32_t arguments[4] = {};
    uint8_t count = 0, attempts = 1, tried = 0;
    uint32_t retryMs = 0;
    bool pendingOnFailure = false;
    String ascii;
  };
  Probe probes_[MAX_PROBES] = {};
  NativeRegistry *registry_ = nullptr;
  uint8_t probeCount_ = 0, nextProbe_ = 0;
  uint32_t nextAt_ = 3000;
  bool planReady_ = false;
};
