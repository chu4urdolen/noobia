#pragma once

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
String capturePath(int32_t sequence);
bool ready();
}
