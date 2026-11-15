#include "hw_neo_bridge.h"

#include "iris_usb_config.h"
#include <services/Esp32VmProgramStore.h>
#include <lwip/inet.h>
#include <lwip/sockets.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>

namespace {
constexpr uint8_t REQUEST_ID = 1;
constexpr size_t REPLY_CAPACITY = 512;

NativeResult neoRequest(const char *command) {
  const int fd = socket(AF_INET, SOCK_STREAM, IPPROTO_IP);
  if (fd < 0) return {false, 0, "Neo bridge: socket failed"};

  timeval timeout{};
  timeout.tv_sec = 2;
  setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
  setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));

  sockaddr_in peer{};
  peer.sin_family = AF_INET;
  peer.sin_port = htons(IrisUsbNet::NEO_COMMAND_PORT);
  const uint32_t neoAddress =
      (uint32_t(IrisUsbNet::NEO_IP[0]) << 24) |
      (uint32_t(IrisUsbNet::NEO_IP[1]) << 16) |
      (uint32_t(IrisUsbNet::NEO_IP[2]) << 8) |
      uint32_t(IrisUsbNet::NEO_IP[3]);
  peer.sin_addr.s_addr = htonl(neoAddress);
  // Bound connect too; receive timeouts alone do not bound a missing peer.
  const int flags = fcntl(fd, F_GETFL, 0);
  if (flags < 0 || fcntl(fd, F_SETFL, flags | O_NONBLOCK) < 0) {
    close(fd);
    return {false, 0, "Neo bridge: nonblocking socket failed"};
  }
  int connected = connect(fd, reinterpret_cast<sockaddr *>(&peer), sizeof(peer));
  if (connected < 0 && errno == EINPROGRESS) {
    fd_set writable;
    FD_ZERO(&writable);
    FD_SET(fd, &writable);
    timeval connectTimeout = timeout;
    if (select(fd + 1, nullptr, &writable, nullptr, &connectTimeout) > 0) {
      int error = 0;
      socklen_t size = sizeof(error);
      if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &size) == 0 && !error)
        connected = 0;
    }
  }
  if (connected != 0 || fcntl(fd, F_SETFL, flags) < 0) {
    close(fd);
    return {false, 0, "Neo bridge: Neo command service unavailable"};
  }

  char request[512];
  const int requestLength = snprintf(request, sizeof(request),
                                     "NRP/1 %u %s\n", REQUEST_ID, command);
  bool sentAll = requestLength > 0 && requestLength < int(sizeof(request));
  for (int sent = 0; sentAll && sent < requestLength;) {
    const int result = send(fd, request + sent, requestLength - sent, 0);
    if (result <= 0) {
      sentAll = false;
      break;
    }
    sent += result;
  }
  if (!sentAll) {
    close(fd);
    return {false, 0, "Neo bridge: request send failed"};
  }

  char reply[REPLY_CAPACITY] = {};
  size_t used = 0;
  while (used + 1 < sizeof(reply)) {
    const int received = recv(fd, reply + used, sizeof(reply) - used - 1, 0);
    if (received <= 0) break;
    used += size_t(received);
    if (memchr(reply, '\n', used)) break;
  }
  close(fd);
  if (!used || !memchr(reply, '\n', used))
    return {false, 0, "Neo bridge: missing complete reply"};
  reply[used] = '\0';
  if (strncmp(reply, "NRP/1 1 ", 8) != 0)
    return {false, 0, "Neo bridge: unexpected reply ID or version"};

  char *payload = strchr(reply, ' ');
  if (!payload) return {false, 0, "Neo bridge: malformed reply"};
  payload = strchr(payload + 1, ' ');
  if (!payload) return {false, 0, "Neo bridge: malformed reply"};
  ++payload;
  char *newline = strpbrk(payload, "\r\n");
  if (newline) *newline = '\0';

  if (strncmp(payload, "OK", 2) == 0 &&
      (payload[2] == '\0' || payload[2] == ' ')) {
    String detail = payload[2] == ' ' ? String(payload + 3) : String();
    int32_t value = 0;
    const char *valueField = strstr(payload, "value=");
    if (valueField) value = static_cast<int32_t>(strtoll(valueField + 6, nullptr, 10));
    return {true, value, detail};
  }
  if (strncmp(payload, "ERR ", 4) == 0)
    return {false, 0, String("Neo: ") + (payload + 4)};
  return {false, 0, "Neo bridge: malformed reply status"};
}

bool noArguments(uint8_t count, NativeResult &error) {
  if (count == 0) return true;
  error = {false, 0, "usage: no arguments"};
  return false;
}

String hexText(const String &text) {
  const char *digits = "0123456789abcdef";
  String hex;
  hex.reserve(text.length() * 2);
  for (size_t i = 0; i < text.length(); ++i) {
    const uint8_t c = uint8_t(text[i]);
    hex += digits[c >> 4]; hex += digits[c & 15];
  }
  return hex;
}

String nativeTextCall(const char *name, const String &text) {
  String escaped = text;
  escaped.replace("\\", "\\\\");
  escaped.replace("\"", "\\\"");
  return String("CALL_MIXED ") + name + " \"" + escaped + "\"";
}

NoobVm *displayVm = nullptr;
bool displayWanted = false;
bool displayVmOwned = false;
bool displayStopPending = false;
String displayImage;
uint32_t displayInterval = 5000;
uint32_t displayNextAttempt = 0;

class NeoDisplayService final : public NoobBackgroundService {
 public:
  bool tick(String &event) override {
    if (displayVmOwned && displayVm &&
        displayVm->state() != VmState::RUNNING &&
        displayVm->state() != VmState::WAITING) {
      displayWanted = false;
      displayVmOwned = false;
      displayStopPending = true;
      displayNextAttempt = 0;
    }
    if ((!displayWanted && !displayStopPending) ||
        int32_t(millis() - displayNextAttempt) < 0) return false;
    displayNextAttempt = millis() + IRIS_NEO_DISPLAY_RETRY_MS;
    String command = "CALL_MIXED DISPLAY_STOP \"\"";
    if (displayWanted) {
      command = nativeTextCall("DISPLAY_START", displayImage);
      command.replace("DISPLAY_START ", "DISPLAY_START " + String(displayInterval) + " ");
    }
    const NativeResult result = neoRequest(command.c_str());
    if (result.ok && displayStopPending) displayStopPending = false;
    if (result.ok) return false;
    event = "NRP/1 0 EVENT NEO_DISPLAY_PENDING detail=" + result.detail;
    return true;
  }
};
NeoDisplayService neoDisplayService;

String field(const String &detail, const char *key) {
  int start = detail.indexOf(key);
  if (start < 0) return String();
  start += strlen(key);
  int end = detail.indexOf(' ', start);
  return detail.substring(start, end < 0 ? detail.length() : size_t(end));
}

int nibble(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}
}

namespace IrisNeoBridge {
NativeResult ledSet(const int32_t *args, uint8_t count) {
  if (count != 2 || (args[1] != 0 && args[1] != 1))
    return {false, 0, "usage: physical_pin 0|1"};
  String command = "CALL LED_SET " + String(args[0]) + " " + String(args[1]);
  return neoRequest(command.c_str());
}
NativeResult ledStatus(const int32_t *args, uint8_t count) {
  if (count != 1) return {false, 0, "usage: physical_pin"};
  String command = "CALL LED_STATUS " + String(args[0]);
  return neoRequest(command.c_str());
}
NoobBackgroundService &displayService(NoobVm &vm) {
  displayVm = &vm;
  return neoDisplayService;
}

NativeResult imageFormat(const int32_t *, uint8_t count, const String &name) {
  if (count || name.isEmpty()) return {false, 0, "usage: image basename"};
  return neoRequest(nativeTextCall("IMAGE_FORMAT", name).c_str());
}
NativeResult oledDraw(const int32_t *, uint8_t count, const String &name) {
  if (count || name.isEmpty()) return {false, 0, "usage: GIF basename"};
  return neoRequest(nativeTextCall("OLED_DRAW", name).c_str());
}
NativeResult oledText(const int32_t *, uint8_t count, const String &text) {
  if (count || text.isEmpty()) return {false, 0, "usage: text"};
  return neoRequest(nativeTextCall("OLED_TEXT", text).c_str());
}
NativeResult displayStart(const int32_t *args, uint8_t count, const String &name) {
  if (count != 1 || args[0] < 1000 || args[0] > 60000 || name.isEmpty() || name.length() > 100)
    return {false, 0, "usage: interval_ms(1000..60000), GIF basename"};
  for (size_t i = 0; i < name.length(); ++i)
    if (!(isalnum(uint8_t(name[i])) || name[i] == '_' || name[i] == '-' || name[i] == '.'))
      return {false, 0, "invalid image basename"};
  if (name.indexOf("..") >= 0) return {false, 0, "invalid image basename"};
  displayImage = name;
  displayInterval = args[0];
  displayWanted = true;
  displayStopPending = false;
  displayVmOwned = displayVm && (displayVm->state() == VmState::RUNNING ||
                                displayVm->state() == VmState::WAITING);
  displayNextAttempt = 0;
  return {true, 1, "display requested; retry while Neo boots"};
}
NativeResult displayStop(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  displayWanted = false;
  displayVmOwned = false;
  displayStopPending = true;
  displayNextAttempt = 0;
  return {true, 0, "display stop requested"};
}
NativeResult displayStatus(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  return neoRequest("CALL_MIXED DISPLAY_STATUS \"\"");
}
NativeResult caps(const int32_t *, uint8_t count) {
  NativeResult error{};
  if (!noArguments(count, error)) return error;
  return neoRequest("CAPS");
}

NativeResult irStatus(const int32_t *, uint8_t count) {
  NativeResult error{};
  if (!noArguments(count, error)) return error;
  return neoRequest("CALL_MIXED IR_STATUS \"\"");
}

NativeResult irScanStart(const int32_t *, uint8_t count) {
  NativeResult error{};
  if (!noArguments(count, error)) return error;
  return neoRequest("CALL_MIXED IR_SCAN_START \"\"");
}

NativeResult irScanStop(const int32_t *, uint8_t count) {
  NativeResult error{};
  if (!noArguments(count, error)) return error;
  return neoRequest("CALL_MIXED IR_SCAN_STOP \"\"");
}

NativeResult irScanRead(const int32_t *, uint8_t count) {
  NativeResult error{};
  if (!noArguments(count, error)) return error;
  return neoRequest("CALL_MIXED IR_SCAN_READ \"\"");
}

NativeResult fileDownload(const int32_t *, uint8_t count, const String &path) {
  if (count || path.isEmpty() || path.length() >= 192)
    return {false, 0, "usage: NEO_FILE_DOWNLOAD 0 numeric args, SD path"};
  return neoRequest(nativeTextCall("FILE_DOWNLOAD", path).c_str());
}

NativeResult audioPlay(const int32_t *, uint8_t count, const String &name) {
  if (count || name.isEmpty() || name.length() >= 192)
    return {false, 0, "usage: AUDIO_PLAY 0 numeric args, audio basename"};
  return neoRequest(nativeTextCall("AUDIO_PLAY", name).c_str());
}

NativeResult fileStatus(const int32_t *, uint8_t count) {
  NativeResult error{};
  if (!noArguments(count, error)) return error;
  return neoRequest("CALL_MIXED FILE_STATUS \"\"");
}

NativeResult vmDownload(const int32_t *arguments, uint8_t count,
                        const String &filename) {
  if (count > 1 || (count && arguments[0] != 0 && arguments[0] != 1) ||
      filename.length() < 5 || filename.length() > 80 ||
      !filename.endsWith(".nvm"))
    return {false, 0, "usage: VM_DOWNLOAD [replace=0|1] ASCII basename.nvm"};
  uint8_t bytes[NoobVm::PROGRAM_BYTES];
  size_t offset = 0, expected = 0;
  const String encoded = hexText(filename);
  while (offset < sizeof(bytes)) {
    const String command = "VM_READ " + String(offset) + " " + encoded;
    NativeResult result = neoRequest(command.c_str());
    if (!result.ok) return result;
    const long size = field(result.detail, "size=").toInt();
    const String data = field(result.detail, "data=");
    const String eof = field(result.detail, "eof=");
    if (size <= 0 || size > long(sizeof(bytes)) ||
        (expected && expected != size_t(size)) || data.length() % 2 ||
        data.length() > 256 || offset + data.length()/2 > size_t(size))
      return {false, 0, "Neo bridge: invalid VM chunk"};
    expected = size_t(size);
    for (size_t i = 0; i < data.length(); i += 2) {
      const int high = nibble(data[i]), low = nibble(data[i+1]);
      if (high < 0 || low < 0) return {false, 0, "invalid VM hex"};
      bytes[offset++] = uint8_t(high * 16 + low);
    }
    if (eof == "1") {
      if (offset != expected) return {false, 0, "incomplete VM download"};
      return Esp32VmProgramStore::storeBytes(
          filename.substring(0, filename.length()-4), bytes, offset,
          count && arguments[0] == 1);
    }
    if (data.isEmpty() || eof != "0") return {false, 0, "invalid VM EOF"};
  }
  return {false, 0, "incomplete VM download"};
}
}
