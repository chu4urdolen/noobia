#include <cassert>
#include <fstream>
#include <string>
#include <vector>
#include <cstdio>
#include "vm/noob_vm.h"

static unsigned displays, police;
static unsigned pending;
static NativeResult display(const int32_t *a, uint8_t n, const String &text) {
  assert(n == 1 && a[0] == 5000 && text == "Iris_formatted.gif");
  ++displays;
  return {true, 1, "requested"};
}
static NativeResult start(const int32_t *, uint8_t) { return {true, 1, ""}; }
static NativeResult sequence(const int32_t *, uint8_t) { ++police; return {true, 1, ""}; }
static NativeResult idle(const int32_t *, uint8_t) { return {true, 0, ""}; }
static NativeResult pop(unsigned id) {
  if (pending != id) return {true, 0, ""};
  pending = 0;
  return {true, 123, ""};
}
static NativeResult ultrasound(const int32_t *, uint8_t) { return pop(206); }
static NativeResult light(const int32_t *, uint8_t) { return pop(211); }
static NativeResult mic(const int32_t *, uint8_t) { return pop(216); }

int main(int argc, char **argv) {
  assert(argc == 2);
  std::ifstream input(argv[1]);
  std::string hex;
  input >> hex;
  assert(!hex.empty() && hex.size() % 2 == 0);
  std::vector<uint8_t> bytes;
  for (size_t i = 0; i < hex.size(); i += 2)
    bytes.push_back(uint8_t(std::stoul(hex.substr(i, 2), nullptr, 16)));
  NativeRegistry r;
  assert(r.addMixed(269, "DISPLAY", display));
  assert(r.add(202, "US_START", start));
  assert(r.add(207, "LIGHT_START", start));
  assert(r.add(212, "MIC_START", start));
  assert(r.add(206, "US_POLL", ultrasound));
  assert(r.add(211, "LIGHT_POLL", light));
  assert(r.add(216, "MIC_POLL", mic));
  assert(r.add(201, "POLICE", sequence));
  assert(r.add(6, "SEQ_STATUS", idle));
  NoobVm vm(r);
  String error;
  assert(vm.load(bytes.data(), bytes.size(), error) && vm.run(error));
  vm.tick(1000);
  assert(displays == 1 && vm.state() == VmState::WAITING);
  for (unsigned id : {206u, 211u, 216u}) {
    unsigned before = police;
    pending = id;
    noob_test_millis += 250;
    vm.tick(1000);
    assert(vm.state() == VmState::WAITING && police == before + 1);
    noob_test_millis += 50;
    vm.tick(1000);
    assert(vm.state() == VmState::WAITING && !pending);
  }
  vm.stop();
  noob_test_millis += 1000;
  vm.tick(1000);
  assert(vm.state() == VmState::STOPPED && displays == 1 && police == 3);
  std::puts("police/display VM: startup, all three triggers and STOP passed");
}
