#include "services/Esp32SdMmcService.h"

#include <SD_MMC.h>

namespace {
bool storageReady = false;
Esp32SdMmcService::Config active = {};

String hexBytes(const uint8_t *data, size_t length) {
  static const char digits[] = "0123456789ABCDEF";
  String result;
  result.reserve(length * 2);
  for (size_t i = 0; i < length; ++i) {
    result += digits[data[i] >> 4];
    result += digits[data[i] & 0x0f];
  }
  return result;
}
}

namespace Esp32SdMmcService {
bool begin(const Config &config) {
  active = config;
  if (!SD_MMC.setPins(active.clk, active.cmd, active.d0)) return false;
  storageReady = SD_MMC.begin(active.mountPoint, true, false);
  if (storageReady) SD_MMC.mkdir(active.captureDirectory);
  return storageReady;
}

bool ready() { return storageReady && SD_MMC.cardType() != CARD_NONE; }

fs::FS &fs() { return SD_MMC; }

bool validPath(const String &path) {
  return path.length() > 1 && path.length() < 192 && path[0] == 47 &&
         path.indexOf("..") < 0 && path.indexOf(92) < 0;
}

String capturePath(int32_t sequence) {
  if (sequence < 0 || !active.captureDirectory || !active.capturePrefix)
    return String();
  char path[96];
  snprintf(path, sizeof(path), "%s/%s%08ld.jpg", active.captureDirectory,
           active.capturePrefix, (long)sequence);
  return String(path);
}

NativeResult status(const int32_t *, uint8_t) {
  if (!ready()) return {false, 0, "SD unavailable"};
  const uint64_t sizeMb = SD_MMC.cardSize() / 1048576ULL;
  const uint64_t usedMb = SD_MMC.usedBytes() / 1048576ULL;
  return {true, static_cast<int32_t>(sizeMb),
          "size_mb=" + String(sizeMb) + " used_mb=" + String(usedMb)};
}

NativeResult list(const int32_t *arguments, uint8_t count) {
  if (!ready()) return {false, 0, "SD unavailable"};
  const int32_t cursor = count ? arguments[0] : 0;
  if (cursor < 0) return {false, 0, "cursor must be nonnegative"};
  File directory = SD_MMC.open(active.captureDirectory);
  if (!directory || !directory.isDirectory())
    return {false, 0, "capture directory unavailable"};
  File entry;
  int32_t position = 0;
  while ((entry = directory.openNextFile())) {
    if (!entry.isDirectory() && position++ == cursor) {
      String name = entry.name();
      const size_t size = entry.size();
      entry.close();
      directory.close();
      return {true, cursor + 1,
              "cursor=" + String(cursor) + " name=" + name +
                  " size=" + String(size) + " eof=0"};
    }
    entry.close();
  }
  directory.close();
  return {true, cursor, "cursor=" + String(cursor) + " eof=1"};
}

NativeResult readChunk(const int32_t *arguments, uint8_t count) {
  if (!ready()) return {false, 0, "SD unavailable"};
  if (count < 2) return {false, 0, "usage: sequence offset [length]"};
  const String path = capturePath(arguments[0]);
  const int32_t offset = arguments[1];
  const int32_t wanted = count > 2 ? arguments[2] : 16;
  if (path.isEmpty() || offset < 0 || wanted < 1 || wanted > 32)
    return {false, 0, "invalid sequence, offset, or length (1..32)"};
  File file = SD_MMC.open(path, FILE_READ);
  if (!file) return {false, 0, "capture not found"};
  const size_t total = file.size();
  if (static_cast<size_t>(offset) > total || !file.seek(offset)) {
    file.close();
    return {false, 0, "offset beyond file"};
  }
  uint8_t bytes[32];
  const size_t got = file.read(bytes, wanted);
  file.close();
  return {true, offset + static_cast<int32_t>(got),
          "offset=" + String(offset) + " size=" + String(total) +
              " data=" + hexBytes(bytes, got) +
              " eof=" + String(offset + got >= total ? 1 : 0)};
}

NativeResult remove(const int32_t *arguments, uint8_t count) {
  if (!ready()) return {false, 0, "SD unavailable"};
  if (!count) return {false, 0, "usage: sequence"};
  const String path = capturePath(arguments[0]);
  if (path.isEmpty() || !SD_MMC.exists(path))
    return {false, 0, "capture not found"};
  if (!SD_MMC.remove(path)) return {false, 0, "delete failed"};
  return {true, arguments[0], "deleted=" + path};
}

NativeResult removePath(const String &arguments) {
  String path = arguments;
  path.trim();
  if (!ready()) return {false, 0, "SD unavailable"};
  if (!validPath(path)) return {false, 0, "invalid absolute SD path"};
  File target = SD_MMC.open(path);
  if (!target) return {false, 0, "path not found"};
  const bool directory = target.isDirectory();
  target.close();
  const bool removed = directory ? SD_MMC.rmdir(path) : SD_MMC.remove(path);
  if (!removed) return {false, 0, "delete failed or directory not empty"};
  return {true, 1, "deleted=" + path};
}

NativeResult listPath(const String &arguments) {
  String path = arguments;
  path.trim();
  if (path.isEmpty()) path = "/";
  if (!ready()) return {false, 0, "SD unavailable"};
  if (path[0] != 47 || path.indexOf("..") >= 0)
    return {false, 0, "invalid absolute SD path"};
  File directory = SD_MMC.open(path);
  if (!directory || !directory.isDirectory())
    return {false, 0, "directory unavailable"};
  String names;
  int32_t count = 0;
  File entry;
  while ((entry = directory.openNextFile()) && count < 20) {
    if (names.length()) names += ",";
    names += entry.name();
    if (entry.isDirectory()) names += "/";
    ++count;
    entry.close();
  }
  directory.close();
  return {true, count, "path=" + path + " entries=" + names};
}
}
