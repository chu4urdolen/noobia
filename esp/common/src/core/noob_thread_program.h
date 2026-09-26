#pragma once

#include "core/noob_background_service.h"
#include "core/noob_program.h"

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
  NativeResult field(const int32_t *arguments, uint8_t count) const;
  bool lastPopped(NoobRecord &record) const;
  bool tick(String &event) override;

 protected:
  virtual bool step(String &event) = 0;
  virtual void onStart() {}
  virtual void onStop() {}
  virtual String statusDetail() const { return ""; }
  void publish(int32_t value) { results_.push(value); }
  void publish(const NoobRecord &record) { results_.push(record); }
  void setInterval(uint32_t intervalMs) { intervalMs_ = intervalMs; }

 private:
  uint32_t intervalMs_;
  uint32_t nextAt_ = 0;
  bool running_ = false;
  NoobRecordQueue results_;
  NoobRecord lastPopped_;
  bool haveLastPopped_ = false;
  volatile bool channelBusy_[1] = {false};
};

class NoobThreadFieldFunction final : public NoobFunction {
 public:
  explicit NoobThreadFieldFunction(NoobThreadProgram &thread)
      : thread_(thread) {}
  bool acceptsNumbers() const override { return true; }
  NativeResult call(const int32_t *arguments, uint8_t count) override {
    return thread_.field(arguments, count);
  }

 private:
  NoobThreadProgram &thread_;
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
