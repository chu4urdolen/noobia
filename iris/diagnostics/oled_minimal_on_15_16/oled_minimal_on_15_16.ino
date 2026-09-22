#include <Wire.h>
#include "../diagnostic_config.h"

bool sendCommand(uint8_t command) {
  Wire.beginTransmission(DIAG_OLED_ADDRESS);
  Wire.write(0x80);  // SH1107 command control byte.
  Wire.write(command);
  const bool acknowledged = Wire.endTransmission(true) == 0;
  delay(100);
  return acknowledged;
}

bool sendData(uint8_t value) {
  Wire.beginTransmission(DIAG_OLED_ADDRESS);
  Wire.write(0x40);
  Wire.write(value);
  return Wire.endTransmission(true) == 0;
}

void setup() {
  pinMode(DIAG_SIGNAL_LED_PIN, OUTPUT);
  digitalWrite(DIAG_SIGNAL_LED_PIN, LOW);
  delay(1000);

  if (!Wire.begin(DIAG_SDA_PIN, DIAG_SCL_PIN, DIAG_I2C_HZ)) {
    return;
  }

  // Acknowledge the address before sending any controller command.
  Wire.beginTransmission(DIAG_OLED_ADDRESS);
  if (Wire.endTransmission(true) != 0) {
    return;
  }

  // Minimal SH1107 test: display on, then force every pixel on independently
  // of display RAM. No graphics library, framebuffer, or addressing involved.
  bool ok = sendCommand(0xae) && sendCommand(0xd5) && sendCommand(0x51) && sendCommand(0x20) && sendCommand(0x81) && sendCommand(0x4f) && sendCommand(0xad) && sendCommand(0x8a) && sendCommand(0xa0) && sendCommand(0xc0) && sendCommand(0xdc) && sendCommand(0x00) && sendCommand(0xd3) && sendCommand(0x60) && sendCommand(0xd9) && sendCommand(0x22) && sendCommand(0xdb) && sendCommand(0x35) && sendCommand(0xa8) && sendCommand(0x3f) && sendCommand(0xa4) && sendCommand(0xa6) && sendCommand(0xd3) && sendCommand(0x00) && sendCommand(0xa8) && sendCommand(0x7f) && sendCommand(0xaf) && sendCommand(0xa5);
  for (uint8_t page = 0; page < 16; ++page) {
    ok = sendCommand(0xb0 | page) && ok;
    ok = sendCommand(0x00) && ok;
    ok = sendCommand(0x10) && ok;
    for (uint8_t column = 0; column < 128; ++column) {
      ok = sendData(0xff) && ok;
    }
  }
  ok = sendCommand(0xa4) && ok;
  digitalWrite(DIAG_SIGNAL_LED_PIN, ok ? HIGH : LOW);
}

void loop() {}
