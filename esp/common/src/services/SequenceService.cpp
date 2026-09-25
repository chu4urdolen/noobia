#include "services/SequenceService.h"

#include <limits.h>
#include "core/noob_program.h"

namespace {
constexpr uint8_t MAX_TRACKS = 4;
constexpr uint8_t MAX_BITS = 64;
constexpr uint8_t MAX_FIXED_ARGUMENTS = 7;
constexpr uint32_t MAX_INTERVAL_MS = 60000;

struct Track {
  bool configured = false;
  bool active = false;
  uint32_t intervalMs = 0;
  uint32_t nextAt = 0;
  char bits[MAX_BITS + 1] = {};
  uint8_t bitCount = 0;
  uint8_t position = 0;
  NoobProgramChannel channel;
};

NativeRegistry *nativeRegistry = nullptr;
Track tracks[MAX_TRACKS];
volatile bool channelBusy[MAX_TRACKS] = {};
bool running = false;
bool repeating = false;

String tokenAt(const String &text, int &position) {
  while (position < text.length() && text[position] == ' ') ++position;
  const int start = position;
  while (position < text.length() && text[position] != ' ') ++position;
  return text.substring(start, position);
}

bool parseInteger(const String &token, int32_t &value) {
  if (token.isEmpty()) return false;
  size_t position = 0;
  bool negative = false;
  if (token[0] == '-') {
    negative = true;
    position = 1;
  }
  if (position == token.length()) return false;
  int64_t parsed = 0;
  for (; position < token.length(); ++position) {
    if (!isDigit(token[position])) return false;
    parsed = parsed * 10 + token[position] - '0';
    if ((!negative && parsed > INT32_MAX) ||
        (negative && parsed > int64_t(INT32_MAX) + 1))
      return false;
  }
  value = negative ? -parsed : parsed;
  return true;
}

uint8_t configuredCount() {
  uint8_t count = 0;
  for (const Track &track : tracks)
    if (track.configured) ++count;
  return count;
}

uint8_t activeCount() {
  uint8_t count = 0;
  for (const Track &track : tracks)
    if (track.active) ++count;
  return count;
}

String stateDetail() {
  String detail = "running=" + String(running ? 1 : 0) +
                  " repeat=" + String(repeating ? 1 : 0) +
                  " configured=" + String(configuredCount()) +
                  " active=" + String(activeCount()) + " channel_busy=";
  for (uint8_t slot = 0; slot < MAX_TRACKS; ++slot) {
    if (slot) detail += ',';
    detail += channelBusy[slot] ? '1' : '0';
  }
  detail += " positions=";
  for (uint8_t slot = 0; slot < MAX_TRACKS; ++slot) {
    if (slot) detail += ',';
    detail += tracks[slot].configured
                  ? String(tracks[slot].position) + "/" +
                        String(tracks[slot].bitCount)
                  : "-";
  }
  return detail;
}

void stopAll() {
  running = false;
  for (uint8_t slot = 0; slot < MAX_TRACKS; ++slot) {
    tracks[slot].active = false;
    channelBusy[slot] = false;
  }
}

class SequenceRunner : public NoobBackgroundService {
 public:
  bool tick(String &event) override {
    if (!running) return false;
    const uint32_t now = millis();
    bool invoked = false;
    for (uint8_t slot = 0; slot < MAX_TRACKS; ++slot) {
      Track &track = tracks[slot];
      if (!track.active || static_cast<int32_t>(now - track.nextAt) < 0)
        continue;

      track.channel.invoke(*nativeRegistry,
                           track.bits[track.position] == '1');
      invoked = true;
      if (!track.channel.lastOk()) {
        stopAll();
        event = "NRP/1 0 EVENT SEQUENCE_ERROR slot=" + String(slot) +
                " function=" + String(track.channel.functionId()) +
                " detail=" + track.channel.lastDetail();
        return true;
      }

      ++track.position;
      if (track.position >= track.bitCount) {
        if (repeating)
          track.position = 0;
        else {
          track.active = false;
          channelBusy[slot] = false;
        }
      }
      track.nextAt = now + track.intervalMs;
    }

    if (invoked && !activeCount()) {
      running = false;
      event = "NRP/1 0 EVENT SEQUENCE_COMPLETE";
      return true;
    }
    return false;
  }
};

SequenceRunner runner;

class SequenceConfigurationFunction final : public NoobFunction {
 public:
  bool acceptsNumbers() const override { return true; }
  bool acceptsText() const override { return true; }
  NativeResult call(const int32_t *arguments, uint8_t count) override {
    return SequenceService::setNumeric(arguments, count);
  }
  NativeResult callText(const String &arguments) override {
    return SequenceService::set(arguments);
  }
};

SequenceConfigurationFunction configuration;
}

namespace SequenceService {
void begin(NativeRegistry &registry) {
  nativeRegistry = &registry;
  stopAll();
  for (uint8_t slot = 0; slot < MAX_TRACKS; ++slot) {
    tracks[slot] = Track{};
    channelBusy[slot] = false;
  }
}

NativeResult set(const String &arguments) {
  if (running) return {false, 0, "stop sequence before editing"};
  int position = 0;
  int32_t slot = 0;
  int32_t interval = 0;
  const String slotToken = tokenAt(arguments, position);
  const String intervalToken = tokenAt(arguments, position);
  const String selector = tokenAt(arguments, position);
  const String bits = tokenAt(arguments, position);
  if (!parseInteger(slotToken, slot) || slot < 0 || slot >= MAX_TRACKS)
    return {false, 0, "slot must be 0..3"};
  if (!parseInteger(intervalToken, interval) || interval < 1 ||
      interval > int32_t(MAX_INTERVAL_MS))
    return {false, 0, "interval must be 1..60000 ms"};
  if (selector.isEmpty() || bits.isEmpty() || bits.length() > MAX_BITS)
    return {false, 0, "usage: slot interval_ms function bits [args...]"};
  for (size_t index = 0; index < bits.length(); ++index)
    if (bits[index] != '0' && bits[index] != '1')
      return {false, 0, "bits must contain only 0 or 1"};

  int32_t numericSelector = 0;
  const bool selectorIsNumber = parseInteger(selector, numericSelector);
  if (selectorIsNumber &&
      (numericSelector < 0 || numericSelector > UINT16_MAX))
    return {false, 0, "function ID must be 0..65535"};
  const NativeEntry *entry =
      selectorIsNumber
          ? nativeRegistry->find(uint16_t(numericSelector))
          : nativeRegistry->find(selector);
  if (!entry || !entry->implementation ||
      !entry->implementation->acceptsNumbers())
    return {false, 0, "function must be a numeric native function"};

  Track configured;
  configured.configured = true;
  configured.intervalMs = interval;
  configured.channel.configure(entry->id, nullptr, 0);
  bits.toCharArray(configured.bits, sizeof(configured.bits));
  configured.bitCount = bits.length();
  int32_t fixedArguments[MAX_FIXED_ARGUMENTS] = {};
  uint8_t fixedArgumentCount = 0;
  while (position < arguments.length()) {
    if (fixedArgumentCount >= MAX_FIXED_ARGUMENTS)
      return {false, 0, "at most 7 fixed arguments"};
    int32_t value = 0;
    if (!parseInteger(tokenAt(arguments, position), value))
      return {false, 0, "arguments must be integers"};
    fixedArguments[fixedArgumentCount++] = value;
  }
  configured.channel.configure(entry->id, fixedArguments, fixedArgumentCount);
  tracks[slot] = configured;
  return {true, slot,
          "slot=" + String(slot) + " interval_ms=" + String(interval) +
              " function=" + String(entry->id) + " bits=" + bits};
}

NativeResult setNumeric(const int32_t *arguments, uint8_t count) {
  if (running) return {false, 0, "stop sequence before editing"};
  if (count < 5)
    return {false, 0,
            "usage: slot interval_ms function_id bit_count packed_bits [args...]"};
  const int32_t slot = arguments[0];
  const int32_t interval = arguments[1];
  const int32_t functionId = arguments[2];
  const int32_t bitCount = arguments[3];
  if (slot < 0 || slot >= MAX_TRACKS)
    return {false, 0, "slot must be 0..3"};
  if (interval < 1 || interval > int32_t(MAX_INTERVAL_MS))
    return {false, 0, "interval must be 1..60000 ms"};
  if (functionId < 0 || functionId > UINT16_MAX)
    return {false, 0, "function ID must be 0..65535"};
  if (bitCount < 1 || bitCount > 32)
    return {false, 0, "VM packed pattern must contain 1..32 bits"};
  if (count - 5 > MAX_FIXED_ARGUMENTS)
    return {false, 0, "at most 7 fixed arguments"};

  const NativeEntry *entry = nativeRegistry->find(uint16_t(functionId));
  if (!entry || !entry->implementation ||
      !entry->implementation->acceptsNumbers())
    return {false, 0, "function must be a numeric native function"};

  Track configured;
  configured.configured = true;
  configured.intervalMs = interval;
  configured.bitCount = bitCount;
  const uint32_t packed = uint32_t(arguments[4]);
  for (int32_t index = 0; index < bitCount; ++index)
    configured.bits[index] =
        ((packed >> (bitCount - index - 1)) & 1U) ? '1' : '0';
  configured.channel.configure(entry->id, arguments + 5, count - 5);
  tracks[slot] = configured;
  return {true, slot,
          "slot=" + String(slot) + " interval_ms=" + String(interval) +
              " function=" + String(functionId) +
              " bits=" + String(configured.bits)};
}

NativeResult load(const ChannelDefinition *channels, uint8_t count) {
  if (running) return {false, 0, "stop sequence before replacing"};
  if (!channels || !count || count > MAX_TRACKS)
    return {false, 0, "sequence must contain 1..4 channels"};

  Track loaded[MAX_TRACKS];
  for (uint8_t slot = 0; slot < count; ++slot) {
    const ChannelDefinition &source = channels[slot];
    if (!source.bits || !source.bitCount || source.bitCount > MAX_BITS ||
        !source.intervalMs || source.intervalMs > MAX_INTERVAL_MS ||
        source.argumentCount > MAX_FIXED_ARGUMENTS ||
        (source.argumentCount && !source.arguments))
      return {false, slot, "invalid channel definition"};
    const NativeEntry *entry = nativeRegistry->find(source.functionId);
    if (!entry || !entry->implementation ||
        !entry->implementation->acceptsNumbers())
      return {false, slot, "channel function is not registered"};

    Track &target = loaded[slot];
    target.configured = true;
    target.intervalMs = source.intervalMs;
    target.bitCount = source.bitCount;
    for (uint8_t index = 0; index < source.bitCount; ++index) {
      if (source.bits[index] > 1)
        return {false, slot, "channel bits must be 0 or 1"};
      target.bits[index] = source.bits[index] ? '1' : '0';
    }
    target.channel.configure(source.functionId, source.arguments,
                             source.argumentCount);
  }

  for (Track &track : tracks) track = Track{};
  for (uint8_t slot = 0; slot < count; ++slot) tracks[slot] = loaded[slot];
  return {true, count, "channels=" + String(count)};
}

NativeResult start(const int32_t *arguments, uint8_t count) {
  if (count > 1 || (count == 1 && arguments[0] != 0 && arguments[0] != 1))
    return {false, 0, "usage: [repeat(0|1)]"};
  if (running) return {false, 0, "sequence already running"};
  if (!configuredCount())
    return {false, 0, "no sequence tracks configured"};
  repeating = count && arguments[0];
  const uint32_t now = millis();
  for (Track &track : tracks) {
    track.active = track.configured;
    track.position = 0;
    track.nextAt = now;
  }
  for (uint8_t slot = 0; slot < MAX_TRACKS; ++slot)
    channelBusy[slot] = tracks[slot].active;
  running = true;
  return {true, configuredCount(), stateDetail()};
}

NativeResult stop(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  stopAll();
  return {true, 0, stateDetail()};
}

NativeResult status(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  return {true, running ? 1 : 0, stateDetail()};
}

NativeResult clear(const int32_t *arguments, uint8_t count) {
  if (running) return {false, 0, "stop sequence before clearing"};
  if (count > 1) return {false, 0, "usage: [slot]"};
  if (!count) {
    for (Track &track : tracks) track = Track{};
    return {true, 0, "cleared=all"};
  }
  if (arguments[0] < 0 || arguments[0] >= MAX_TRACKS)
    return {false, 0, "slot must be 0..3"};
  tracks[arguments[0]] = Track{};
  return {true, arguments[0], "cleared=" + String(arguments[0])};
}

NativeResult pop(const int32_t *arguments, uint8_t count) {
  if (count != 1 || arguments[0] < 0 || arguments[0] >= MAX_TRACKS)
    return {false, 0, "usage: slot(0..3)"};
  NoobIntegerQueue &queue = tracks[arguments[0]].channel.results();
  int32_t value = 0;
  if (!queue.pop(value)) return {false, 0, "channel queue empty"};
  return {true, value,
          "slot=" + String(arguments[0]) +
              " remaining=" + String(queue.size()) +
              " dropped=" + String(queue.dropped())};
}

NativeResult queueSize(const int32_t *arguments, uint8_t count) {
  if (count != 1 || arguments[0] < 0 || arguments[0] >= MAX_TRACKS)
    return {false, 0, "usage: slot(0..3)"};
  NoobIntegerQueue &queue = tracks[arguments[0]].channel.results();
  return {true, queue.size(),
          "slot=" + String(arguments[0]) +
              " dropped=" + String(queue.dropped())};
}

NativeResult clearQueue(const int32_t *arguments, uint8_t count) {
  if (count != 1 || arguments[0] < 0 || arguments[0] >= MAX_TRACKS)
    return {false, 0, "usage: slot(0..3)"};
  tracks[arguments[0]].channel.results().clear();
  return {true, 0, "slot=" + String(arguments[0]) + " cleared=1"};
}

NativeResult busy(const int32_t *arguments, uint8_t count) {
  if (count != 1 || arguments[0] < 0 || arguments[0] >= MAX_TRACKS)
    return {false, 0, "usage: slot(0..3)"};
  const bool isBusy = channelBusy[arguments[0]];
  return {true, isBusy ? 1 : 0,
          "slot=" + String(arguments[0]) +
              " channel_busy=" + String(isBusy ? 1 : 0)};
}

uint8_t busyMask() {
  uint8_t mask = 0;
  for (uint8_t slot = 0; slot < MAX_TRACKS; ++slot)
    if (channelBusy[slot]) mask |= uint8_t(1U << slot);
  return mask;
}

NoobBackgroundService &backgroundService() { return runner; }
NoobFunction &configurationFunction() { return configuration; }
}
