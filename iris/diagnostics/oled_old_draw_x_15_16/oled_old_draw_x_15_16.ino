#include <Wire.h>
#include "../diagnostic_config.h"

// Match the old Argus diagnostic: send each control/value pair once, ignore
// its status, and wait 1 ms before the next pair.
void sendPair(uint8_t control, uint8_t value) {
  Wire.beginTransmission(DIAG_OLED_ADDRESS);
  Wire.write(control);
  Wire.write(value);
  Wire.endTransmission(true);
  delay(1);
}

void setup() {
  pinMode(DIAG_SIGNAL_LED_PIN, OUTPUT);
  digitalWrite(DIAG_SIGNAL_LED_PIN, LOW);
  Wire.begin(DIAG_SDA_PIN, DIAG_SCL_PIN, DIAG_I2C_HZ);
  Wire.setTimeOut(20);

  sendPair(0x00, 0xa4);
  sendPair(0x00, 0xa6);
  sendPair(0x00, 0xaf);
  delay(150);

  for (uint8_t page = 0; page < 1; ++page) {
    sendPair(0x00, 0xb0 | page);
    sendPair(0x00, 0x00);
    sendPair(0x00, 0x10);
    for (uint8_t column = 0; column < 128; ++column) {
      uint8_t pixels = 0;
      if (column == 0 || column == 127) pixels = 0xff;
      if (page == 0) pixels |= 0x01;
      if (page == 15) pixels |= 0x80;
      if ((column >> 3) == page) pixels |= 1u << (column & 7);
      const uint8_t reverse = 127 - column;
      if ((reverse >> 3) == page) pixels |= 1u << (reverse & 7);
      sendPair(0x40, pixels);
    }
    digitalWrite(DIAG_SIGNAL_LED_PIN, page & 1);
  }

  digitalWrite(DIAG_SIGNAL_LED_PIN, HIGH);
}

void loop() {}
