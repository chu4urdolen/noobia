#include "syscalls/NativeRegistry.h"

bool NativeRegistry::add(uint16_t id, const char *name,
                         NativeFunction function) {
  if (!name || !function || count_ >= MAX_FUNCTIONS || find(id) || find(name)) {
    return false;
  }
  entries_[count_++] = {id, name, function, nullptr};
  return true;
}

bool NativeRegistry::addText(uint16_t id, const char *name,
                             NativeTextFunction function) {
  if (!name || !function || count_ >= MAX_FUNCTIONS || find(id) || find(name)) {
    return false;
  }
  entries_[count_++] = {id, name, nullptr, function};
  return true;
}

const NativeEntry *NativeRegistry::find(uint16_t id) const {
  for (size_t index = 0; index < count_; ++index) {
    if (entries_[index].id == id) return &entries_[index];
  }
  return nullptr;
}

const NativeEntry *NativeRegistry::find(const String &name) const {
  for (size_t index = 0; index < count_; ++index) {
    if (name.equalsIgnoreCase(entries_[index].name)) return &entries_[index];
  }
  return nullptr;
}

String NativeRegistry::list() const {
  String result;
  for (size_t index = 0; index < count_; ++index) {
    if (index) result += ',';
    result += String(entries_[index].id) + ':' + entries_[index].name;
  }
  return result;
}
