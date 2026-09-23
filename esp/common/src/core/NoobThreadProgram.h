#pragma once

#include "core/BackgroundService.h"
#include "core/NoobProgram.h"

class NoobThreadProgram : public NoobProgram,
                          public NoobBackgroundService {
 public:
  explicit NoobThreadProgram(uint32_t intervalMs);
  bool acceptsNumbers() const override { return true; }
  NativeResult call(const int32_t *arguments, uint8_t count) override;
  NativeResult stop() override;
  NativeResult status() const;
  NativeResult pop();
  NativeResult poll();
  bool tick(String &event) override;

 protected:
  virtual bool step(String &event) = 0;
  virtual void onStart() {}
  virtual void onStop() {}
  virtual String statusDetail() const { return ""; }
  void publish(int32_t value) { results_.push(value); }
  void setInterval(uint32_t intervalMs) { intervalMs_ = intervalMs; }

 private:
  uint32_t intervalMs_;
  uint32_t nextAt_ = 0;
  bool running_ = false;
  NoobIntegerQueue results_;
  volatile bool channelBusy_[1] = {false};
};

class NoobThreadStopFunction final : public NoobFunction {
 public:
  explicit NoobThreadStopFunction(NoobThreadProgram &thread)
      : thread_(thread) {}
  bool acceptsNumbers() const override { return true; }
  NativeResult call(const int32_t *, uint8_t count) override {
    return count ? NativeResult{false, 0, "usage: no arguments"}
                 : thread_.stop();
  }

 private:
  NoobThreadProgram &thread_;
};

class NoobThreadStatusFunction final : public NoobFunction {
 public:
  explicit NoobThreadStatusFunction(NoobThreadProgram &thread)
      : thread_(thread) {}
  bool acceptsNumbers() const override { return true; }
  NativeResult call(const int32_t *, uint8_t count) override {
    return count ? NativeResult{false, 0, "usage: no arguments"}
                 : thread_.status();
  }

 private:
  NoobThreadProgram &thread_;
};

class NoobThreadPopFunction final : public NoobFunction {
 public:
  explicit NoobThreadPopFunction(NoobThreadProgram &thread)
      : thread_(thread) {}
  bool acceptsNumbers() const override { return true; }
  NativeResult call(const int32_t *, uint8_t count) override {
    return count ? NativeResult{false, 0, "usage: no arguments"}
                 : thread_.pop();
  }

 private:
  NoobThreadProgram &thread_;
};

// Poll is VM-friendly: an empty queue is normal and returns zero.
class NoobThreadPollFunction final : public NoobFunction {
 public:
  explicit NoobThreadPollFunction(NoobThreadProgram &thread)
      : thread_(thread) {}
  bool acceptsNumbers() const override { return true; }
  NativeResult call(const int32_t *, uint8_t count) override {
    return count ? NativeResult{false, 0, "usage: no arguments"}
                 : thread_.poll();
  }

 private:
  NoobThreadProgram &thread_;
};
