#include "services/Esp32VmProgramStore.h"

#include "services/Esp32SdMmcService.h"

namespace {
NoobVm *programVm = nullptr;
String programDirectory;

bool validName(const String &name) {
  if (!name.length() || name.length() > 32) return false;
  for (size_t index = 0; index < name.length(); ++index) {
    const char value = name[index];
    if (!isAlphaNumeric(value) && value != 45 && value != 95) return false;
  }
  return true;
}

String pathFor(String name) {
  name.trim();
  return validName(name) ? programDirectory + "/" + name + ".nvm" : String();
}
}

namespace Esp32VmProgramStore {
bool begin(NoobVm &vm, const char *directory) {
  if (!Esp32SdMmcService::ready() || !directory) return false;
  programVm = &vm;
  programDirectory = directory;
  return Esp32SdMmcService::fs().exists(programDirectory) ||
         Esp32SdMmcService::fs().mkdir(programDirectory);
}

NativeResult save(const String &arguments) {
  if (!programVm) return {false, 0, "program store unavailable"};
  String path = pathFor(arguments);
  if (path.isEmpty()) return {false, 0, "invalid program name"};
  const size_t length = programVm->programLength();
  if (!length) return {false, 0, "VM has no program"};
  if (Esp32SdMmcService::fs().exists(path))
    Esp32SdMmcService::fs().remove(path);
  File file = Esp32SdMmcService::fs().open(path, FILE_WRITE);
  if (!file) return {false, 0, "cannot create program"};
  file.seek(0);
  const size_t written = file.write(programVm->programData(), length);
  file.close();
  if (written != length) return {false, int32_t(written), "program write failed"};
  return {true, int32_t(length), "saved=" + path};
}

NativeResult load(const String &arguments) {
  if (!programVm) return {false, 0, "program store unavailable"};
  String path = pathFor(arguments);
  if (path.isEmpty()) return {false, 0, "invalid program name"};
  File file = Esp32SdMmcService::fs().open(path, FILE_READ);
  if (!file) return {false, 0, "saved program not found"};
  const size_t length = file.size();
  if (!length || length > NoobVm::PROGRAM_BYTES) {
    file.close();
    return {false, int32_t(length), "invalid saved program size"};
  }
  uint8_t bytes[NoobVm::PROGRAM_BYTES];
  const size_t got = file.read(bytes, length);
  file.close();
  if (got != length) return {false, int32_t(got), "program read failed"};
  String error;
  if (!programVm->load(bytes, length, error)) return {false, 0, error};
  return {true, int32_t(length), "loaded=" + path};
}

NativeResult list(const String &) {
  if (!programVm) return {false, 0, "program store unavailable"};
  File directory = Esp32SdMmcService::fs().open(programDirectory);
  if (!directory || !directory.isDirectory()) return {false, 0, "program directory unavailable"};
  String names;
  int32_t count = 0;
  File entry;
  while ((entry = directory.openNextFile()) && count < 32) {
    if (!entry.isDirectory()) {
      if (names.length()) names += ",";
      names += entry.name();
      ++count;
    }
    entry.close();
  }
  directory.close();
  return {true, count, "programs=" + names};
}

NativeResult remove(const String &arguments) {
  String path = pathFor(arguments);
  if (path.isEmpty()) return {false, 0, "invalid program name"};
  if (!Esp32SdMmcService::fs().remove(path)) return {false, 0, "saved program not found"};
  return {true, 1, "deleted=" + path};
}
}
