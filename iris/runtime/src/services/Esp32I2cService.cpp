#include "services/Esp32I2cService.h"

#include <Wire.h>

namespace {
TwoWire noobI2c(1);
bool i2cReady = false;

bool validAddress(int32_t address) { return address >= 1 && address <= 126; }

NativeResult receiveBytes(int32_t address, int32_t wanted) {
  if (wanted < 1 || wanted > 4) return {false, 0, "read length must be 1..4"};
  const int got = noobI2c.requestFrom(uint8_t(address), uint8_t(wanted));
  if (got != wanted) return {false, got, "short I2C read"};
  uint32_t packed = 0;
  for (int index = 0; index < got; ++index)
    packed |= uint32_t(noobI2c.read()) << (8 * index);
  return {true, int32_t(packed), "bytes=" + String(got) + " packed_le=" + String(packed)};
}
}

namespace Esp32I2cService {
bool begin(int sdaPin, int sclPin, uint32_t frequency) {
  i2cReady = noobI2c.begin(sdaPin, sclPin, frequency);
  // A disconnected or miswired peripheral must not stall the command loop.
  noobI2c.setTimeOut(5);
  return i2cReady;
}

NativeResult scan(const int32_t *, uint8_t) {
  if (!i2cReady) return {false, 0, "I2C unavailable"};
  String addresses;
  int32_t found = 0;
  for (uint8_t address = 1; address < 127; ++address) {
    noobI2c.beginTransmission(address);
    if (noobI2c.endTransmission() == 0) {
      if (addresses.length()) addresses += ",";
      char text[5];
      snprintf(text, sizeof(text), "0x%02X", address);
      addresses += text;
      ++found;
    }
  }
  return {true, found, "devices=" + addresses};
}

NativeResult write(const int32_t *arguments, uint8_t count) {
  if (!i2cReady) return {false, 0, "I2C unavailable"};
  if (count < 2 || count > 8 || !validAddress(arguments[0]))
    return {false, 0, "usage: address byte [byte...]"};
  noobI2c.beginTransmission(uint8_t(arguments[0]));
  for (uint8_t index = 1; index < count; ++index) {
    if (arguments[index] < 0 || arguments[index] > 255)
      return {false, 0, "I2C byte outside 0..255"};
    noobI2c.write(uint8_t(arguments[index]));
  }
  const uint8_t error = noobI2c.endTransmission();
  return error ? NativeResult{false, error, "I2C write error"}
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
  if (error) return {false, error, "I2C register select error"};
  return receiveBytes(arguments[0], arguments[2]);
}
}
