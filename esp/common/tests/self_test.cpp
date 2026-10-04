#include <cassert>
#include <cstdio>
#include <cstring>
#include "core/noob_self_test.h"

static unsigned sensorCalls;
static NativeResult sensor(const int32_t *, uint8_t) {
  ++sensorCalls;
  return {sensorCalls > 1, 0, "transient sensor read"};
}
static NativeResult fail(const int32_t *, uint8_t) { return {false, 0, "no response"}; }
static NativeResult text(const String &value) {
  assert(value == "/noob/runtime_iris.txt");
  return {true, 32, "read only"};
}
int main() {
  NativeRegistry registry;
  assert(registry.add(190, "SENSOR", sensor));
  assert(registry.add(260, "REMOTE", fail));
  assert(registry.add(261, "BROKEN", fail));
  assert(registry.addText(106, "READ", text));
  NoobSelfTest test;
  test.bind(registry);
  assert(test.addProbe("TEMP_HUMIDITY_READ", 190, nullptr, 0, 2, 250));
  assert(test.addProbe("REMOTE", 260, nullptr, 0, 1, 0, true));
  assert(test.addProbe("BROKEN", 261, nullptr, 0, 2, 250));
  assert(test.addProbe("DISABLED", 999, nullptr, 0, 1, 0));
  assert(test.addProbe("READ", 106, nullptr, 0, 1, 0, false, "/noob/runtime_iris.txt"));
  assert(!test.addProbe("BAD_RETRY", 190, nullptr, 0, 4, 0));
  assert(test.record("LED_VISIBLE_OUTPUT", NoobSelfTest::State::UNTESTED));
  String event;
  assert(!test.tick(event));
  test.finish();
  assert(!test.tick(event));
  noob_test_millis = 3000;
  assert(test.tick(event) && sensorCalls == 1);
  assert(!test.tick(event));
  noob_test_millis += 250;
  assert(test.tick(event) && sensorCalls == 2);
  assert(test.tick(event));
  assert(test.tick(event));
  noob_test_millis += 250;
  while (test.tick(event)) {}
  NativeResult result = test.call(nullptr, 0);
  assert(result.ok && result.value == 1);
  assert(std::strstr(result.detail.c_str(), "complete=1"));
  assert(std::strstr(result.detail.c_str(), "TEMP_HUMIDITY_READ:ready"));
  assert(std::strstr(result.detail.c_str(), "REMOTE:pending"));
  assert(std::strstr(result.detail.c_str(), "DISABLED:disabled"));
  assert(std::strstr(result.detail.c_str(), "LED_VISIBLE_OUTPUT:untested"));
  assert(sensorCalls == 2);
  assert(!test.call(nullptr, 1).ok);
  std::puts("boot diagnostics: bounded retry, permanent failure, pending peer, disabled and untested passed");
}
