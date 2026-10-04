#include <cassert>
#include <cstdio>
#include "core/noob_program.h"
#include "services/SequenceService.h"
#include "core/noob_sampling_thread.h"

static NativeResult mixed(const int32_t *args, uint8_t count, const String &text) {
  assert(count == 1 && args[0] == 7 && text == "Iris.png");
  return {true, 42, "mixed"};
}
static NativeResult text(const String &value) {
  assert(value == "Hello Iris");
  return {true, 9, "text"};
}
int main() {
  NativeRegistry registry;
  assert(registry.addMixed(500, "MIXED", mixed));
  assert(registry.addText(501, "TEXT", text));
  NoobProgramChannel channel;
  const int32_t fixed[] = {7};
  assert(channel.configure(500, fixed, 1, "Iris.png"));
  channel.invoke(registry, 0, false);
  assert(channel.lastOk() && !channel.busy() && channel.results().size() == 1);
  assert(!channel.configure(500, fixed, 1, "bad\ntext"));
  assert(channel.configure(501, nullptr, 0, "Hello Iris"));
  channel.invoke(registry, 0, false);
  assert(channel.lastOk());
  channel.invoke(registry, 1, true);
  assert(!channel.lastOk() && !channel.busy());
  assert(channel.configure(999, nullptr, 0));
  channel.invoke(registry, 0, false);
  assert(!channel.lastOk() && !channel.busy());

  SequenceService::begin(registry);
  const int32_t config[] = {0, 250, 500, 1, 1, 0, 7};
  assert(SequenceService::setMixed(config, 7, "Iris.png").ok);
  assert(SequenceService::start(nullptr, 0).ok);
  String event;
  assert(SequenceService::backgroundService().tick(event));
  assert(SequenceService::pop(config, 1).value == 42);
  assert(!SequenceService::busyMask());
  const uint8_t bits[] = {1};
  const SequenceService::ChannelDefinition definition[] = {
    {501, 250, bits, 1, nullptr, 0, "Hello Iris", false}};
  assert(SequenceService::load(definition, 1).ok);
  assert(SequenceService::start(nullptr, 0).ok);
  assert(SequenceService::backgroundService().tick(event));
  assert(SequenceService::pop(config, 1).value == 9);
  NoobSamplingThreadProgram thread(500, "TEST", 250, 0, fixed, 1);
  thread.begin(registry);
  const int32_t timing[] = {0, 250};
  assert(thread.callMixed(timing, 2, "Iris.png").ok);
  thread.tick(event);
  assert(thread.pop().value == 42);
  assert(!thread.callMixed(timing, 2, "bad\ntext").ok);
  assert(thread.stop().ok);
  std::puts("channel calls: mixed/text, queues, busy cleanup and sequence definitions passed");
}
