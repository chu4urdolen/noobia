#pragma once

#include <Arduino.h>

struct NoobRequest {
  String requestId;
  String command;
  String arguments;
};

namespace NoobProtocol {
constexpr const char *VERSION = "NRP/1";
bool parse(const String &frame, NoobRequest &request, String &error);
String ok(const String &requestId, const String &payload = "");
String fail(const String &requestId, const String &code,
            const String &message);
}
