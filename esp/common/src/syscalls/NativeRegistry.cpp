#include "syscalls/NativeRegistry.h"

bool NativeRegistry::add(uint16_t id, const char *name,
                         NativeFunction function) {
  if (!name || !function || count_ >= MAX_FUNCTIONS || find(id) || find(name)) {
    return false;
  }
  numericAdapters_[count_].bind(function);
  entries_[count_] = {id, name, &numericAdapters_[count_]};
  ++count_;
  return true;
}

bool NativeRegistry::addText(uint16_t id, const char *name,
                             NativeTextFunction function) {
  if (!name || !function || count_ >= MAX_FUNCTIONS || find(id) || find(name)) {
    return false;
  }
  textAdapters_[count_].bind(function);
  entries_[count_] = {id, name, &textAdapters_[count_]};
  ++count_;
  return true;
}

bool NativeRegistry::add(uint16_t id, const char *name,
                         NoobFunction &implementation) {
  if (!name || count_ >= MAX_FUNCTIONS || find(id) || find(name)) return false;
  entries_[count_++] = {id, name, &implementation};
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

NativeResult NativeRegistry::call(const NativeEntry &entry,
                                  const int32_t *arguments,
                                  uint8_t count) const {
  if (!entry.implementation || !entry.implementation->acceptsNumbers())
    return {false, 0, "numeric call unsupported"};
  return entry.implementation->call(arguments, count);
}

NativeResult NativeRegistry::callText(const NativeEntry &entry,
                                      const String &arguments) const {
  if (!entry.implementation || !entry.implementation->acceptsText())
    return {false, 0, "text call unsupported"};
  return entry.implementation->callText(arguments);
}

String NativeRegistry::list() const {
  String result;
  for (size_t index = 0; index < count_; ++index) {
    if (index) result += ',';
    result += String(entries_[index].id) + ':' + entries_[index].name;
  }
  return result;
}
