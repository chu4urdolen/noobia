#pragma once
// Minimal host shim for testing the real parser, registry, and VM.
#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>
#include <type_traits>

class String {
 public:
  String() = default;
  String(const char *s) : text_(s ? s : "") {}
  String(const std::string &s) : text_(s) {}
  template<class T, typename std::enable_if<std::is_integral<T>::value, int>::type = 0>
  String(T n) : text_(std::to_string(n)) {}
  size_t length() const { return text_.size(); }
  bool isEmpty() const { return text_.empty(); }
  const char *c_str() const { return text_.c_str(); }
  void toCharArray(char *destination, size_t size) const {
    if (!size) return;
    const size_t length = std::min(text_.size(), size - 1);
    std::memcpy(destination, text_.data(), length);
    destination[length] = 0;
  }
  char operator[](size_t i) const { return text_[i]; }
  String substring(size_t start) const { return substring(start, text_.size()); }
  String substring(size_t start, size_t end) const {
    start = std::min(start, text_.size());
    end = std::max(start, std::min(end, text_.size()));
    return text_.substr(start, end - start);
  }
  void toUpperCase() {
    for (char &c : text_) c = char(std::toupper(static_cast<unsigned char>(c)));
  }
  bool equalsIgnoreCase(const String &other) const {
    String a(*this), b(other); a.toUpperCase(); b.toUpperCase(); return a == b;
  }
  long toInt() const { return std::strtol(c_str(), nullptr, 10); }
  bool reserve(size_t bytes) { text_.reserve(bytes); return true; }
  String &operator+=(const String &other) { text_ += other.text_; return *this; }
  String &operator+=(char c) { text_ += c; return *this; }
  friend String operator+(String a, const String &b) { a += b; return a; }
  friend bool operator==(const String &a, const String &b) { return a.text_ == b.text_; }
  friend bool operator!=(const String &a, const String &b) { return !(a == b); }
 private:
  std::string text_;
};

inline bool isDigit(char c) { return c >= '0' && c <= '9'; }
inline uint32_t noob_test_millis = 0;
inline uint32_t millis() { return noob_test_millis; }
