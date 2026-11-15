#include "core/noob_window_rise_thread.h"

#include "services/MonotonicTimeService.h"

NoobWindowRiseThreadProgram::NoobWindowRiseThreadProgram(
    uint16_t sourceFunctionId, const char *eventName,
    uint32_t sampleIntervalMs, uint32_t bucketDurationMs,
    uint16_t riseRatioPercent, int32_t minimumNewLevel,
    uint8_t rearmBuckets)
    : NoobThreadProgram(sampleIntervalMs),
      sourceFunctionId_(sourceFunctionId),
      eventName_(eventName),
      bucketDurationMs_(bucketDurationMs),
      riseRatioPercent_(riseRatioPercent),
      minimumNewLevel_(minimumNewLevel),
      rearmBuckets_(rearmBuckets) {}

void NoobWindowRiseThreadProgram::begin(NativeRegistry &registry) {
  registry_ = &registry;
  source_.configure(sourceFunctionId_, nullptr, 0);
}

NativeResult NoobWindowRiseThreadProgram::call(const int32_t *arguments,
                                                uint8_t count) {
  if (count > 2 || (count && (arguments[0] < 101 || arguments[0] > 10000)) ||
      (count > 1 && arguments[1] < 0))
    return {false, 0,
            "usage: [ratio_percent(101..10000)] [minimum_level>=0]"};
  if (count) riseRatioPercent_ = arguments[0];
  if (count > 1) minimumNewLevel_ = arguments[1];
  NativeResult result = NoobThreadProgram::call(nullptr, 0);
  result.detail += " ratio_percent=" + String(riseRatioPercent_) +
                   " minimum_level=" + String(minimumNewLevel_);
  return result;
}

void NoobWindowRiseThreadProgram::onStart() {
  for (int32_t &bucket : buckets_) bucket = 0;
  writeIndex_ = 0;
  filledBuckets_ = 0;
  bucketSum_ = 0;
  bucketSamples_ = 0;
  bucketStartedAt_ = millis();
  olderMean_ = 0;
  newerMean_ = 0;
  armed_ = true;
  stableBuckets_ = 0;
  source_.configure(sourceFunctionId_, nullptr, 0);
}

void NoobWindowRiseThreadProgram::finishBucket(int32_t average) {
  buckets_[writeIndex_] = average;
  writeIndex_ = (writeIndex_ + 1) % BUCKET_COUNT;
  if (filledBuckets_ < BUCKET_COUNT) ++filledBuckets_;
  updateMeans();
}

void NoobWindowRiseThreadProgram::updateMeans() {
  if (filledBuckets_ < BUCKET_COUNT) {
    olderMean_ = 0;
    newerMean_ = 0;
    return;
  }
  int32_t olderSum = 0;
  int32_t newerSum = 0;
  for (uint8_t offset = 0; offset < HALF_BUCKETS; ++offset) {
    olderSum += buckets_[(writeIndex_ + offset) % BUCKET_COUNT];
    newerSum +=
        buckets_[(writeIndex_ + HALF_BUCKETS + offset) % BUCKET_COUNT];
  }
  olderMean_ = (olderSum + HALF_BUCKETS / 2) / HALF_BUCKETS;
  newerMean_ = (newerSum + HALF_BUCKETS / 2) / HALF_BUCKETS;
}

bool NoobWindowRiseThreadProgram::step(String &event) {
  if (!registry_) return false;
  source_.invoke(*registry_, 0, false);
  if (!source_.lastOk()) {
    event = "NRP/1 0 EVENT " + String(eventName_) +
            "_ERROR detail=" + source_.lastDetail();
    return true;
  }

  NoobRecord sampled;
  int32_t level = 0;
  if (!source_.results().pop(sampled) || !sampled.primary(level)) return false;
  bucketSum_ += level;
  ++bucketSamples_;

  const uint32_t now = millis();
  if (uint32_t(now - bucketStartedAt_) < bucketDurationMs_) return false;
  const int32_t average = bucketSamples_
                              ? int32_t((bucketSum_ + bucketSamples_ / 2) /
                                        bucketSamples_)
                              : 0;
  bucketSum_ = 0;
  bucketSamples_ = 0;
  bucketStartedAt_ = now;
  finishBucket(average);
  if (filledBuckets_ < BUCKET_COUNT) return false;

  const bool rose = newerMean_ >= minimumNewLevel_ &&
                    int64_t(newerMean_) * 100 >=
                        int64_t(olderMean_) * riseRatioPercent_;
  if (!armed_) {
    stableBuckets_ = rose ? 0 : stableBuckets_ + 1;
    if (stableBuckets_ >= rearmBuckets_) {
      armed_ = true;
      stableBuckets_ = 0;
    }
    return false;
  }
  if (!rose) return false;

  const uint32_t detectedAt = MonotonicTimeService::milliseconds();
  publish(static_cast<int32_t>(detectedAt));
  armed_ = false;
  stableBuckets_ = 0;
  event = "NRP/1 0 EVENT " + String(eventName_) +
          " time_ms=" + String(detectedAt) +
          " older=" + String(olderMean_) +
          " newer=" + String(newerMean_);
  return true;
}

String NoobWindowRiseThreadProgram::statusDetail() const {
  return " buckets=" + String(filledBuckets_) + "/" + String(BUCKET_COUNT) +
         " older=" + String(olderMean_) + " newer=" + String(newerMean_) +
         " ratio_percent=" + String(riseRatioPercent_) +
         " minimum_level=" + String(minimumNewLevel_) +
         " armed=" + String(armed_ ? 1 : 0);
}
