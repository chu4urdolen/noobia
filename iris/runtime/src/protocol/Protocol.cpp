#include "protocol/Protocol.h"

namespace {
String nextToken(const String &text, int &position) {
  while (position < text.length() && text[position] == ' ') ++position;
  const int start = position;
  while (position < text.length() && text[position] != ' ') ++position;
  return text.substring(start, position);
}
}

bool NoobProtocol::parse(const String &frame, NoobRequest &request,
                         String &error) {
  int position = 0;
  const String version = nextToken(frame, position);
  request.requestId = nextToken(frame, position);
  request.command = nextToken(frame, position);
  while (position < frame.length() && frame[position] == ' ') ++position;
  request.arguments = frame.substring(position);
  request.command.toUpperCase();
  if (version != VERSION) {
    error = "unsupported protocol version";
    return false;
  }
  if (request.requestId.isEmpty() || request.command.isEmpty()) {
    error = "expected NRP/1 request-id command [arguments]";
    return false;
  }
  return true;
}

String NoobProtocol::ok(const String &requestId, const String &payload) {
  String result = String(VERSION) + " " + requestId + " OK";
  if (!payload.isEmpty()) result += " " + payload;
  return result;
}

String NoobProtocol::fail(const String &requestId, const String &code,
                          const String &message) {
  return String(VERSION) + " " + requestId + " ERR " + code + " " + message;
}
