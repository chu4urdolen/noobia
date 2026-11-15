#include <cassert>
#include <cstdio>
#include <cstring>
#include "commands/noob_command_dispatcher.h"

static int invoked;
static String lastAscii;
static NativeResult mixed(const int32_t *args, uint8_t count, const String &ascii) {
  ++invoked;
  lastAscii = ascii;
  return {true, count ? args[0] : 0, ascii};
}
static NativeResult numeric(const int32_t *args, uint8_t count) {
  ++invoked;
  return {true, count ? args[0] : 0, ""};
}
static NativeResult text(const String &ascii) {
  ++invoked;
  lastAscii = ascii;
  return {true, int32_t(ascii.length()), ""};
}

int main() {
  NativeRegistry registry;
  assert(registry.addMixed(99, "MIX", mixed));
  assert(registry.add(98, "NUM", numeric));
  assert(registry.addText(97, "TEXT", text));
  NoobVm vm(registry);
  CapabilityRegistry caps;
  CommandDispatcher dispatcher("test", "test", vm, registry, caps);
  auto command = [&](const char *body) {
    NoobRequest request;
    String error;
    assert(NoobProtocol::parse(String("NRP/1 1 ") + body, request, error));
    return dispatcher.dispatch(request);
  };
  auto success = [&](const char *body) {
    String reply = command(body);
    assert(std::strstr(reply.c_str(), "NRP/1 1 OK"));
  };
  auto failure = [&](const char *body) {
    int before = invoked;
    String reply = command(body);
    assert(std::strstr(reply.c_str(), "NRP/1 1 ERR"));
    assert(invoked == before);
  };
  success("CALL_MIXED MIX 7 \"/a file.txt\"");
  assert(lastAscii == "/a file.txt");
  success("CALL_MIXED 99 -2147483648 \"\"");
  assert(lastAscii.isEmpty());
  success("CALL_MIXED MIX 1 \"a\\\"b\\\\c\"");
  assert(lastAscii == "a\"b\\c");
  success("CALL_MIXED NUM 9 \"\"");
  failure("CALL_MIXED NUM 9 \"unexpected\"");
  success("CALL NUM 9");
  success("CALL MIX 9");
  success("CALL_TEXT TEXT original");
  success("CALL_TEXT MIX original");
  success("CALL_MIXED TEXT \"text only\"");
  String bounded = "CALL_MIXED MIX 1 \"";
  for (int i = 0; i < 255; ++i) bounded += 'a';
  bounded += '"';
  success(bounded.c_str());
  bounded = bounded.substring(0, bounded.length() - 1) + "a\"";
  failure(bounded.c_str());
  failure("CALL_MIXED MIX x \"a\"");
  failure("CALL_MIXED MIX 2147483648 \"a\"");
  failure("CALL_MIXED MIX 1 2 3 4 5 6 7 8 9 \"\"");
  failure("CALL_MIXED MIX 1 \"unterminated");
  failure("CALL_MIXED MIX 1 \"a\" trailing");
  failure("CALL_MIXED MIX 1 \"a\\n\"");
  failure("CALL_MIXED MIX 1 \"\x7f\"");

  auto run = [&](const uint8_t *bytes, size_t length) {
    vm.reset();
    String error;
    assert(vm.load(bytes, length, error));
    assert(vm.run(error));
    vm.tick(100);
  };
  const uint8_t program[] = {1,1,7,0,0,0, 0x22,0,99,0,1,1,3,'a','b','c', 0};
  run(program, sizeof(program));
  assert(vm.state() == VmState::HALTED && vm.reg(0) == 7 && lastAscii == "abc");
  const uint8_t empty[] = {0x22,0,98,0,0,0,0};
  run(empty, sizeof(empty));
  assert(vm.state() == VmState::HALTED);
  const uint8_t old[] = {0x20,0,99,0,0,0};
  run(old, sizeof(old));
  assert(vm.state() == VmState::HALTED && lastAscii.isEmpty());
  int before = invoked;
  const uint8_t truncated[] = {0x22,0,99,0,0,3,'a'};
  run(truncated, sizeof(truncated));
  assert(vm.state() == VmState::FAULT && invoked == before);
  const uint8_t invalidAscii[] = {0x22,0,99,0,0,1,0,0};
  run(invalidAscii, sizeof(invalidAscii));
  assert(vm.state() == VmState::FAULT && invoked == before);
  const uint8_t tooMany[] = {0x22,0,99,0,9};
  run(tooMany, sizeof(tooMany));
  assert(vm.state() == VmState::FAULT && invoked == before);
  std::puts("mixed native/protocol/VM checks passed");
}
