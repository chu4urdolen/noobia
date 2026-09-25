#include "services/Esp32VmProgramStore.h"

#include "services/Esp32SdMmcService.h"

namespace {
NoobVm *programVm = nullptr;
String programDirectory;
String lastProgramPath;
String lastRunPath;
String persistenceStatus = "unavailable";

bool atomicWrite(const String &path, const uint8_t *data, size_t length,
                 String &error) {
  fs::FS &storage = Esp32SdMmcService::fs();
  const String temporary = path + ".tmp";
  const String backup = path + ".bak";
  storage.remove(temporary);
  File file = storage.open(temporary, FILE_WRITE);
  if (!file) {
    error = "cannot create " + temporary;
    return false;
  }
  const size_t written = file.write(data, length);
  file.close();
  if (written != length) {
    storage.remove(temporary);
    error = "short write " + String(written) + "/" + String(length);
    return false;
  }

  storage.remove(backup);
  const bool hadPrevious = storage.exists(path);
  if (hadPrevious && !storage.rename(path, backup)) {
    storage.remove(temporary);
    error = "cannot preserve previous " + path;
    return false;
  }
  if (!storage.rename(temporary, path)) {
    if (hadPrevious) storage.rename(backup, path);
    error = "cannot install " + path;
    return false;
  }
  storage.remove(backup);
  return true;
}

void recoverFile(const String &path) {
  fs::FS &storage = Esp32SdMmcService::fs();
  const String temporary = path + ".tmp";
  const String backup = path + ".bak";
  storage.remove(temporary);
  if (!storage.exists(path) && storage.exists(backup))
    storage.rename(backup, path);
  else
    storage.remove(backup);
}

bool writeRunFlag(bool enabled, String &error) {
  const uint8_t value = enabled ? '1' : '0';
  return atomicWrite(lastRunPath, &value, 1, error);
}

bool readRunFlag() {
  File file = Esp32SdMmcService::fs().open(lastRunPath, FILE_READ);
  if (!file) return false;
  const int value = file.read();
  file.close();
  return value == '1';
}

bool writeCurrentProgram(const NoobVm &vm, String &error) {
  const size_t length = vm.programLength();
  if (!length) {
    error = "VM has no program";
    return false;
  }
  return atomicWrite(lastProgramPath, vm.programData(), length, error);
}

void removeRuntimeFiles() {
  fs::FS &storage = Esp32SdMmcService::fs();
  const String paths[] = {
      lastProgramPath, lastProgramPath + ".tmp", lastProgramPath + ".bak",
      lastRunPath, lastRunPath + ".tmp", lastRunPath + ".bak"};
  for (const String &path : paths) storage.remove(path);
}

class ProgramStoreLifecycle final : public NoobVmLifecycle {
 public:
  String onStarted(const NoobVm &vm) override {
    if (!programVm) return "persistence=unavailable";
    String error;
    // Disable the previous snapshot before replacing it.
    if (!writeRunFlag(false, error) || !writeCurrentProgram(vm, error) ||
        !writeRunFlag(true, error)) {
      String ignored;
      writeRunFlag(false, ignored);
      persistenceStatus = "error:" + error;
      return "persistence=failed";
    }
    persistenceStatus = "stored:autorun";
    return "persistence=stored autorun=1";
  }

  String onStopped(const NoobVm &) override {
    if (!programVm) return "persistence=unavailable";
    String error;
    if (!writeRunFlag(false, error)) {
      persistenceStatus = "error:" + error;
      return "persistence=failed";
    }
    persistenceStatus = "stored:stopped";
    return "persistence=stored autorun=0";
  }

  String onReset(const NoobVm &) override {
    if (!programVm) return "persistence=unavailable";
    removeRuntimeFiles();
    persistenceStatus = "cleared";
    return "persistence=cleared";
  }
};

ProgramStoreLifecycle storeLifecycle;

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
  if (!validName(name)) return String();
  if (!name.startsWith("prog_")) name = "prog_" + name;
  return programDirectory + "/" + name + ".nvm";
}

String legacyPathFor(String name) {
  name.trim();
  return validName(name) ? programDirectory + "/" + name + ".nvm" : String();
}
}

namespace Esp32VmProgramStore {
bool begin(NoobVm &vm, const char *directory) {
  if (!Esp32SdMmcService::ready() || !directory) return false;
  programVm = &vm;
  programDirectory = directory;
  if (!Esp32SdMmcService::fs().exists(programDirectory) &&
      !Esp32SdMmcService::fs().mkdir(programDirectory))
    return false;
  lastProgramPath = programDirectory + "/runtime_last.nvm";
  lastRunPath = programDirectory + "/runtime_last.run";
  recoverFile(lastProgramPath);
  recoverFile(lastRunPath);
  persistenceStatus = "ready";
  return true;
}

NoobVmLifecycle &lifecycle() { return storeLifecycle; }

NativeResult restoreLast() {
  if (!programVm) return {false, 0, "program store unavailable"};
  File file = Esp32SdMmcService::fs().open(lastProgramPath, FILE_READ);
  if (!file) {
    persistenceStatus = "ready:none";
    return {true, 0, "restored=none autorun=0"};
  }
  const size_t length = file.size();
  if (!length || length > NoobVm::PROGRAM_BYTES) {
    file.close();
    String ignored;
    writeRunFlag(false, ignored);
    persistenceStatus = "error:invalid runtime program";
    return {false, int32_t(length), "invalid runtime program size"};
  }
  uint8_t bytes[NoobVm::PROGRAM_BYTES];
  const size_t got = file.read(bytes, length);
  file.close();
  if (got != length) {
    String ignored;
    writeRunFlag(false, ignored);
    persistenceStatus = "error:short runtime read";
    return {false, int32_t(got), "runtime program read failed"};
  }

  String error;
  if (!programVm->load(bytes, length, error)) {
    String ignored;
    writeRunFlag(false, ignored);
    persistenceStatus = "error:" + error;
    return {false, 0, error};
  }
  const bool autorun = readRunFlag();
  if (autorun && !programVm->run(error)) {
    String ignored;
    writeRunFlag(false, ignored);
    persistenceStatus = "error:" + error;
    return {false, int32_t(length), error};
  }
  persistenceStatus = autorun ? "restored:autorun" : "restored:ready";
  return {true, int32_t(length),
          "restored=" + lastProgramPath +
              " autorun=" + String(autorun ? 1 : 0)};
}

NativeResult lastStatus(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  if (!programVm) return {false, 0, "program store unavailable"};
  File file = Esp32SdMmcService::fs().open(lastProgramPath, FILE_READ);
  const int32_t length = file ? int32_t(file.size()) : 0;
  if (file) file.close();
  const bool autorun = length && readRunFlag();
  return {true, autorun ? 1 : 0,
          "stored=" + String(length ? 1 : 0) +
              " bytes=" + String(length) +
              " autorun=" + String(autorun ? 1 : 0) +
              " state=" + persistenceStatus};
}

NativeResult clearLast(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  if (!programVm) return {false, 0, "program store unavailable"};
  removeRuntimeFiles();
  persistenceStatus = "cleared";
  return {true, 1, "runtime snapshot cleared"};
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
  if (!file) {
    path = legacyPathFor(arguments);
    file = Esp32SdMmcService::fs().open(path, FILE_READ);
  }
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
  if (!Esp32SdMmcService::fs().remove(path)) {
    path = legacyPathFor(arguments);
    if (!Esp32SdMmcService::fs().remove(path))
      return {false, 0, "saved program not found"};
  }
  return {true, 1, "deleted=" + path};
}
}
