#pragma once

#include <FS.h>
#include "syscalls/NativeRegistry.h"

namespace Esp32SdMmcService {
struct Config {
  int clk;
  int cmd;
  int d0;
  const char *mountPoint;
  const char *captureDirectory;
  const char *capturePrefix;
};

bool begin(const Config &config);
NativeResult status(const int32_t *arguments, uint8_t count);
NativeResult list(const int32_t *arguments, uint8_t count);
NativeResult readChunk(const int32_t *arguments, uint8_t count);
NativeResult remove(const int32_t *arguments, uint8_t count);
NativeResult removePath(const String &arguments);
NativeResult listPath(const String &arguments);
String capturePath(int32_t sequence);
bool ready();
fs::FS &fs();
bool validPath(const String &path);
}
