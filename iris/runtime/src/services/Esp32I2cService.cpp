#if !defined(NOOB_ENABLE_EXTERNAL_I2C) || NOOB_ENABLE_EXTERNAL_I2C
#include "services/Esp32I2cService.h"

#include <Wire.h>

namespace {
// Use controller 0 for external devices. The esp32-camera component claims
// controller 1 for SCCB on boards such as Iris when its sensor is present.
TwoWire &noobI2c = Wire;
bool i2cReady = false;
int configuredSda = -1;
int configuredScl = -1;

bool validAddress(int32_t address) { return address >= 1 && address <= 126; }


NativeResult receiveBytes(int32_t address, int32_t wanted) {
  if (wanted < 1 || wanted > 4) return {false, 0, "read length must be 1..4"};
  const int got = noobI2c.requestFrom(uint8_t(address), uint8_t(wanted));
  if (got != wanted) { Serial.printf("I2C_READ short wanted=%d got=%d\n", wanted, got); return {false, got, "short I2C read"}; }
  uint32_t packed = 0;
  for (int index = 0; index < got; ++index)
    packed |= uint32_t(noobI2c.read()) << (8 * index);
  return {true, int32_t(packed), "bytes=" + String(got) + " packed_le=" + String(packed)};
}
}

namespace Esp32I2cService {
bool begin(int sdaPin, int sclPin, uint32_t frequency) {
  if (i2cReady) {
    noobI2c.end();
    if (configuredSda >= 0) pinMode(configuredSda, INPUT);
    if (configuredScl >= 0) pinMode(configuredScl, INPUT);
  }
  configuredSda = sdaPin;
  configuredScl = sclPin;
  i2cReady = noobI2c.begin(sdaPin, sclPin, frequency);
  // A disconnected or miswired peripheral must not stall the command loop.
  noobI2c.setTimeOut(5);
  return i2cReady;
}

NativeResult scan(const int32_t *arguments, uint8_t count) {
  if (!i2cReady) return {false, 0, "I2C unavailable"};
  if (count > 2) return {false, 0, "usage: [first [last]]"};
  const int32_t first = count ? arguments[0] : 8;
  const int32_t last = count == 2 ? arguments[1] : (count ? first : 119);
  if (first < 8 || last > 119 || first > last)
    return {false, 0, "address range must be within 8..119"};
  String addresses;
  int32_t found = 0;
  unsigned nack = 0, timeout = 0, other = 0;
  const uint32_t started = micros();
  for (int32_t address = first; address <= last; ++address) {
    noobI2c.beginTransmission(address);
    const uint8_t error = noobI2c.endTransmission();
    if (error == 0) {
      if (addresses.length()) addresses += ",";
      char text[5];
      snprintf(text, sizeof(text), "0x%02X", address);
      addresses += text;
      ++found;
    } else if (error == 2 || error == 3) ++nack;
    else if (error == 5) ++timeout;
    else ++other;
  }
  const String detail = "devices=" + addresses + " ack=" + String(found) +
      " nack=" + String(nack) + " timeout=" + String(timeout) +
      " other=" + String(other) + " elapsed_us=" + String(micros() - started);
  return {timeout == 0 && other == 0, found, detail};
}

NativeResult write(const int32_t *arguments, uint8_t count) {
  if (!i2cReady) return {false, 0, "I2C unavailable"};
  if (count < 2 || count > 8 || !validAddress(arguments[0]))
    return {false, 0, "usage: address byte [byte...]"};
  for (uint8_t index = 1; index < count; ++index) {
    if (arguments[index] < 0 || arguments[index] > 255)
      return {false, 0, "I2C byte outside 0..255"};
  }
  noobI2c.beginTransmission(uint8_t(arguments[0]));
  for (uint8_t index = 1; index < count; ++index) {
    noobI2c.write(uint8_t(arguments[index]));
  }
  const uint8_t error = noobI2c.endTransmission();
  if (error) Serial.printf("I2C_WRITE addr=0x%02X error=%u\n", unsigned(arguments[0]), unsigned(error));
  return error ? NativeResult{false, error, "I2C write error code=" + String(error)}
               : NativeResult{true, count - 1, "written=" + String(count - 1)};
}

NativeResult read(const int32_t *arguments, uint8_t count) {
  if (!i2cReady) return {false, 0, "I2C unavailable"};
  if (count != 2 || !validAddress(arguments[0]))
    return {false, 0, "usage: address length"};
  return receiveBytes(arguments[0], arguments[1]);
}

NativeResult writeRead(const int32_t *arguments, uint8_t count) {
  if (!i2cReady) return {false, 0, "I2C unavailable"};
  if (count != 3 || !validAddress(arguments[0]) || arguments[1] < 0 ||
      arguments[1] > 255)
    return {false, 0, "usage: address register read_length"};
  noobI2c.beginTransmission(uint8_t(arguments[0]));
  noobI2c.write(uint8_t(arguments[1]));
  const uint8_t error = noobI2c.endTransmission(false);
  if (error) Serial.printf("I2C_WRITEREAD addr=0x%02X error=%u\n", unsigned(arguments[0]), unsigned(error));
  if (error) return {false, error, "I2C register select error code=" + String(error)};
  return receiveBytes(arguments[0], arguments[2]);
}

NativeResult configure(const int32_t *arguments, uint8_t count) {
  if (count < 2 || count > 3 || arguments[0] < 0 || arguments[1] < 0)
    return {false, 0, "usage: sda scl [frequency]"};
  uint32_t frequency = count == 3 ? uint32_t(arguments[2]) : 100000;
  if (frequency < 10000 || frequency > 1000000)
    return {false, 0, "frequency must be 10000..1000000"};
  i2cReady = noobI2c.begin(arguments[0], arguments[1], frequency);
  noobI2c.setTimeOut(5);
  Serial.printf("I2C_CONFIG sda=%ld scl=%ld freq=%lu ready=%d\n", long(arguments[0]), long(arguments[1]), (unsigned long)frequency, i2cReady ? 1 : 0);
  return i2cReady ? NativeResult{true, 1, "configured"}
                   : NativeResult{false, 0, "I2C begin failed"};
}

NativeResult close(const int32_t *, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  if (i2cReady) noobI2c.end();
  i2cReady = false;
  // Wire.end() does not promise a high-impedance pin state on every ESP32
  // core. INPUT explicitly releases both lines so external pull-ups can be
  // measured and other code can safely take ownership later.
  if (configuredSda >= 0) pinMode(configuredSda, INPUT);
  if (configuredScl >= 0) pinMode(configuredScl, INPUT);
  return {true, 0, "closed pins_released=1"};
}

NativeResult lines(int sdaPin, int sclPin) {
  // Read only: do not change pin mode, enable pulls, or start the controller.
  const int sda = digitalRead(sdaPin);
  const int scl = digitalRead(sclPin);
  return {true, (sda << 1) | scl,
          "sda=" + String(sda) + " scl=" + String(scl) +
              " ready=" + String(i2cReady ? 1 : 0)};
}

}
#endif
