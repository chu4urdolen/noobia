#include "core/CapabilityRegistry.h"

bool CapabilityRegistry::add(const char *capability) {
  if (!capability || count_ >= MAX_CAPABILITIES) return false;
  for (size_t index = 0; index < count_; ++index) {
    if (String(items_[index]) == capability) return true;
  }
  items_[count_++] = capability;
  return true;
}

bool CapabilityRegistry::has(const String &capability) const {
  for (size_t index = 0; index < count_; ++index) {
    if (capability.equalsIgnoreCase(items_[index])) return true;
  }
  return false;
}

String CapabilityRegistry::list() const {
  String result;
  for (size_t index = 0; index < count_; ++index) {
    if (index) result += ',';
    result += items_[index];
  }
  return result;
}
