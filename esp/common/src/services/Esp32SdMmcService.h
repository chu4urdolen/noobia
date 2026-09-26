#pragma once

#include <FS.h>
#include "syscalls/noob_native_registry.h"

namespace Esp32SdMmcService {
struct Config {
  int clk;
  int cmd;
  int d0;
  int spiCs; // -1 selects SDMMC; otherwise use the SD card's DAT3/CS pin.
  const char *mountPoint;
  const char *captureDirectory;
  const char *capturePrefix;
  uint32_t clockKhz;
};

bool begin(const Config &config);
NativeResult status(const int32_t *arguments, uint8_t count);
NativeResult list(const int32_t *arguments, uint8_t count);
NativeResult readChunk(const int32_t *arguments, uint8_t count);
NativeResult readPathChunk(const String &arguments);
NativeResult remove(const int32_t *arguments, uint8_t count);
NativeResult removePath(const String &arguments);
NativeResult listPath(const String &arguments);
String capturePath(int32_t sequence);
const char *captureDirectory();
bool ready();
fs::FS &fs();
bool validPath(const String &path);
}
