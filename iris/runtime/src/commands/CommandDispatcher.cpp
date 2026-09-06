#include "commands/CommandDispatcher.h"

namespace {
int hexValue(char value) {
  if (value >= '0' && value <= '9') return value - '0';
  if (value >= 'a' && value <= 'f') return value - 'a' + 10;
  if (value >= 'A' && value <= 'F') return value - 'A' + 10;
  return -1;
}

String tokenAt(const String &text, int &position) {
  while (position < text.length() && text[position] == ' ') ++position;
  const int start = position;
  while (position < text.length() && text[position] != ' ') ++position;
  return text.substring(start, position);
}
}

CommandDispatcher::CommandDispatcher(const char *noobName,
                                     const char *firmwareVersion, NoobVm &vm,
                                     NativeRegistry &natives,
                                     CapabilityRegistry &capabilities)
    : noobName_(noobName),
      firmwareVersion_(firmwareVersion),
      vm_(vm),
      natives_(natives),
      capabilities_(capabilities) {}

String CommandDispatcher::dispatch(const NoobRequest &request) {
  // These commands are common to every Noob. Device-specific operations enter
  // only through CALL or a VM syscall resolved by NativeRegistry.
  if (request.command == "PING") {
    return NoobProtocol::ok(request.requestId, "PONG");
  }
  if (request.command == "INFO") {
    return NoobProtocol::ok(request.requestId,
                            "name=" + String(noobName_) + " firmware=" +
                                firmwareVersion_ + " protocol=1 vm=1");
  }
  if (request.command == "CAPS") {
    return NoobProtocol::ok(request.requestId,
                            "caps=" + capabilities_.list() +
                                " functions=" + natives_.list());
  }
  if (request.command == "LOAD") {
    // Hex is the milestone wire encoding. It is simple to inspect and works on
    // every text transport; binary/chunked loading can be added protocol-side.
    uint8_t bytes[NoobVm::PROGRAM_BYTES];
    size_t length = 0;
    String error;
    if (!decodeHex(request.arguments, bytes, sizeof(bytes), length, error)) {
      return NoobProtocol::fail(request.requestId, "BAD_PROGRAM", error);
    }
    if (!vm_.load(bytes, length, error)) {
      return NoobProtocol::fail(request.requestId, "VM_STATE", error);
    }
    return NoobProtocol::ok(request.requestId,
                            "loaded=" + String(length));
  }
  if (request.command == "RUN") {
    String error;
    if (!vm_.run(error)) {
      return NoobProtocol::fail(request.requestId, "VM_STATE", error);
    }
    return NoobProtocol::ok(request.requestId, "started");
  }
  if (request.command == "STOP") {
    vm_.stop();
    return NoobProtocol::ok(request.requestId, vm_.status());
  }
  if (request.command == "RESET_VM") {
    vm_.reset();
    return NoobProtocol::ok(request.requestId, vm_.status());
  }
  if (request.command == "CALL") return callNative(request);
  if (request.command == "CALL_TEXT") return callTextNative(request);
  if (request.command == "STATUS") {
    return NoobProtocol::ok(request.requestId, vm_.status());
  }
  return NoobProtocol::fail(request.requestId, "UNKNOWN_COMMAND",
                            request.command);
}

bool CommandDispatcher::decodeHex(const String &text, uint8_t *output,
                                  size_t capacity, size_t &length,
                                  String &error) {
  length = 0;
  int high = -1;
  for (size_t index = 0; index < text.length(); ++index) {
    const char value = text[index];
    if (value == ' ' || value == '_' || value == ':') continue;
    const int nibble = hexValue(value);
    if (nibble < 0) {
      error = "non-hex character at " + String(index);
      return false;
    }
    if (high < 0) {
      high = nibble;
    } else {
      if (length >= capacity) {
        error = "program exceeds 1024 bytes";
        return false;
      }
      output[length++] = static_cast<uint8_t>((high << 4) | nibble);
      high = -1;
    }
  }
  if (high >= 0 || !length) {
    error = high >= 0 ? "odd number of hex digits" : "empty program";
    return false;
  }
  return true;
}

String CommandDispatcher::callNative(const NoobRequest &request) {
  int position = 0;
  const String selector = tokenAt(request.arguments, position);
  const NativeEntry *entry = nullptr;
  bool numeric = !selector.isEmpty();
  for (size_t index = 0; index < selector.length(); ++index) {
    if (!isDigit(selector[index])) numeric = false;
  }
  entry = numeric ? natives_.find(static_cast<uint16_t>(selector.toInt()))
                  : natives_.find(selector);
  if (!entry) {
    return NoobProtocol::fail(request.requestId, "NO_FUNCTION", selector);
  }
  if (!entry->function) {
    return NoobProtocol::fail(request.requestId, "FUNCTION_KIND",
                              "use CALL_TEXT for " + selector);
  }
  int32_t arguments[NoobVm::REGISTER_COUNT] = {};
  uint8_t count = 0;
  while (position < request.arguments.length() &&
         count < NoobVm::REGISTER_COUNT) {
    String token = tokenAt(request.arguments, position);
    if (!token.isEmpty()) arguments[count++] = token.toInt();
  }
  const NativeResult result = entry->function(arguments, count);
  if (!result.ok) {
    return NoobProtocol::fail(request.requestId, "NATIVE_ERROR",
                              result.detail);
  }
  String payload = "value=" + String(result.value);
  if (!result.detail.isEmpty()) payload += " detail=" + result.detail;
  return NoobProtocol::ok(request.requestId, payload);
}

String CommandDispatcher::callTextNative(const NoobRequest &request) {
  int position = 0;
  const String selector = tokenAt(request.arguments, position);
  const NativeEntry *entry = natives_.find(selector);
  if (!entry || !entry->textFunction) {
    return NoobProtocol::fail(request.requestId, "NO_TEXT_FUNCTION", selector);
  }
  while (position < request.arguments.length() && request.arguments[position] == 32)
    ++position;
  const NativeResult result =
      entry->textFunction(request.arguments.substring(position));
  if (!result.ok) {
    return NoobProtocol::fail(request.requestId, "NATIVE_ERROR", result.detail);
  }
  String payload = "value=" + String(result.value);
  if (!result.detail.isEmpty()) payload += " detail=" + result.detail;
  return NoobProtocol::ok(request.requestId, payload);
}
