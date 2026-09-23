#include "transport/StreamTransport.h"

StreamTransport::StreamTransport(const char *transportName, Stream &stream,
                                 size_t maximumLine)
    : transportName_(transportName),
      stream_(stream),
      maximumLine_(maximumLine) {}

const char *StreamTransport::name() const { return transportName_; }

bool StreamTransport::receive(String &message) {
  while (stream_.available()) {
    const char value = static_cast<char>(stream_.read());
    if (value == '\n' || value == '\r') {
      if (!input_.isEmpty()) {
        message = input_;
        input_ = "";
        return true;
      }
    } else if (input_.length() < maximumLine_) {
      input_ += value;
    } else {
      input_ = "";
    }
  }
  return false;
}

void StreamTransport::send(const String &message) { stream_.println(message); }
