#pragma once

#include "core/noob_thread_program.h"

// Reduces frequent integer samples into ten buckets and detects a sustained
// rise between the older and newer five-bucket halves.
class NoobWindowRiseThreadProgram : public NoobThreadProgram {
 public:
  static constexpr uint8_t BUCKET_COUNT = 10;
  static constexpr uint8_t HALF_BUCKETS = BUCKET_COUNT / 2;

  NoobWindowRiseThreadProgram(uint16_t sourceFunctionId, const char *eventName,
                              uint32_t sampleIntervalMs,
                              uint32_t bucketDurationMs,
                              uint16_t riseRatioPercent,
                              int32_t minimumNewLevel,
                              uint8_t rearmBuckets);
  void begin(NativeRegistry &registry);
  NativeResult call(const int32_t *arguments, uint8_t count) override;

 protected:
  void onStart() override;
  bool step(String &event) override;
  String statusDetail() const override;

 private:
  void finishBucket(int32_t average);
  void updateMeans();

  NativeRegistry *registry_ = nullptr;
  NoobProgramChannel source_;
  uint16_t sourceFunctionId_;
  const char *eventName_;
  uint32_t bucketDurationMs_;
  uint16_t riseRatioPercent_;
  int32_t minimumNewLevel_;
  uint8_t rearmBuckets_;
  int32_t buckets_[BUCKET_COUNT] = {};
  uint8_t writeIndex_ = 0;
  uint8_t filledBuckets_ = 0;
  int64_t bucketSum_ = 0;
  uint16_t bucketSamples_ = 0;
  uint32_t bucketStartedAt_ = 0;
  int32_t olderMean_ = 0;
  int32_t newerMean_ = 0;
  bool armed_ = true;
  uint8_t stableBuckets_ = 0;
};
