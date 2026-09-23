#pragma once

#include "transport/Transport.h"

class StreamTransport : public NoobTransport {
 public:
  StreamTransport(const char *transportName, Stream &stream,
                  size_t maximumLine = 2048);
  const char *name() const override;
  bool receive(String &message) override;
  void send(const String &message) override;

 private:
  const char *transportName_;
  Stream &stream_;
  String input_;
  size_t maximumLine_;
};
