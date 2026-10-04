#include "syscalls/noob_native_registry.h"

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

bool NativeRegistry::addMixed(uint16_t id, const char *name,
                              NativeMixedFunction function) {
  if (!name || !function || count_ >= MAX_FUNCTIONS || find(id) || find(name))
    return false;
  mixedAdapters_[count_].bind(function);
  entries_[count_] = {id, name, &mixedAdapters_[count_]};
  ++count_;
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
  return callMixed(entry, arguments, count, String());
}

NativeResult NativeRegistry::callText(const NativeEntry &entry,
                                      const String &arguments) const {
  if (!entry.implementation || !entry.implementation->acceptsText())
    return {false, 0, "text call unsupported"};
  // Legacy text calls retain their UTF-8 behavior.
  return entry.implementation->callMixed(nullptr, 0, arguments);
}

NativeResult NativeRegistry::callMixed(const NativeEntry &entry,
                                       const int32_t *arguments,
                                       uint8_t count,
                                       const String &ascii) const {
  if (!entry.implementation || (count && !arguments))
    return {false, 0, "invalid native arguments"};
  if (ascii.length() > MAX_ASCII_BYTES)
    return {false, 0, "ASCII argument exceeds 255 bytes"};
  for (size_t i = 0; i < ascii.length(); ++i) {
    const uint8_t c = static_cast<uint8_t>(ascii[i]);
    if (c < 32 || c > 126)
      return {false, 0, "ASCII argument must contain printable ASCII"};
  }
  return entry.implementation->callMixed(arguments, count, ascii);
}

String NativeRegistry::list() const {
  String result;
  for (size_t index = 0; index < count_; ++index) {
    if (index) result += ',';
    result += String(entries_[index].id) + ':' + entries_[index].name;
  }
  return result;
}
