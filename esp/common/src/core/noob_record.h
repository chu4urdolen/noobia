#pragma once

#include <Arduino.h>
#include <cstring>

// One channel result is a small set of named integer values. Fixed bounds keep
// queue memory predictable on embedded targets.
class NoobRecord {
 public:
  static constexpr uint8_t MAX_FIELDS = 6;
  static constexpr uint8_t NAME_BYTES = 16;

  struct Field {
    char name[NAME_BYTES] = {};
    int32_t value = 0;
  };

  bool add(const char *name, int32_t value) {
    if (!name || !name[0] || strlen(name) >= NAME_BYTES || count_ >= MAX_FIELDS)
      return false;
    strncpy(fields_[count_].name, name, NAME_BYTES - 1);
    fields_[count_].value = value;
    ++count_;
    return true;
  }

  bool get(uint8_t index, const char *&name, int32_t &value) const {
    if (index >= count_) return false;
    name = fields_[index].name;
    value = fields_[index].value;
    return true;
  }

  bool get(const char *name, int32_t &value) const {
    if (!name) return false;
    for (uint8_t index = 0; index < count_; ++index) {
      if (!strcmp(fields_[index].name, name)) {
        value = fields_[index].value;
        return true;
      }
    }
    return false;
  }

  bool primary(int32_t &value) const {
    if (get("value", value)) return true;
    if (!count_) return false;
    value = fields_[0].value;
    return true;
  }

  uint8_t size() const { return count_; }
  bool empty() const { return count_ == 0; }

  String serialize() const {
    String result = "{";
    for (uint8_t index = 0; index < count_; ++index) {
      if (index) result += ',';
      result += fields_[index].name;
      result += ':';
      result += String(fields_[index].value);
    }
    result += '}';
    return result;
  }

 private:
  Field fields_[MAX_FIELDS] = {};
  uint8_t count_ = 0;
};

class NoobRecordQueue {
 public:
  static constexpr uint8_t CAPACITY = 8;

  void push(const NoobRecord &record) {
    if (count_ == CAPACITY) {
      head_ = (head_ + 1) % CAPACITY;
      --count_;
      ++dropped_;
    }
    records_[tail_] = record;
    tail_ = (tail_ + 1) % CAPACITY;
    ++count_;
  }

  void push(int32_t value) {
    NoobRecord record;
    record.add("value", value);
    push(record);
  }

  bool pop(NoobRecord &record) {
    if (!count_) return false;
    record = records_[head_];
    head_ = (head_ + 1) % CAPACITY;
    --count_;
    return true;
  }

  void clear() { head_ = tail_ = count_ = 0; dropped_ = 0; }
  uint8_t size() const { return count_; }
  uint32_t dropped() const { return dropped_; }

 private:
  NoobRecord records_[CAPACITY] = {};
  uint8_t head_ = 0;
  uint8_t tail_ = 0;
  uint8_t count_ = 0;
  uint32_t dropped_ = 0;
};
