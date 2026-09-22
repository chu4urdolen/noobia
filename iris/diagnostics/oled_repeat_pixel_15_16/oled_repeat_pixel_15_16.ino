#include <Wire.h>
#include "../diagnostic_config.h"

bool sendPair(uint8_t control, uint8_t value) {
  Wire.beginTransmission(DIAG_OLED_ADDRESS);
  Wire.write(control);
  Wire.write(value);
  return Wire.endTransmission(true) == 0;
}

void setup() {
  pinMode(DIAG_SIGNAL_LED_PIN, OUTPUT);
  digitalWrite(DIAG_SIGNAL_LED_PIN, LOW);
  Wire.begin(DIAG_SDA_PIN, DIAG_SCL_PIN, DIAG_I2C_HZ);
  Wire.setTimeOut(20);

  unsigned pageAck = 0;
  unsigned lowAck = 0;
  unsigned highAck = 0;
  unsigned pixelAck = 0;
  for (unsigned cycle = 1; cycle <= DIAG_RETRY_COUNT; ++cycle) {
    pageAck += sendPair(0x80, 0xb0);
    lowAck += sendPair(0x80, 0x00);
    highAck += sendPair(0x80, 0x10);
    pixelAck += sendPair(0x40, 0x01);
    delay(DIAG_WRITE_PAUSE_MS);
  }

  digitalWrite(DIAG_SIGNAL_LED_PIN,
               pageAck == DIAG_RETRY_COUNT && lowAck == DIAG_RETRY_COUNT &&
                       highAck == DIAG_RETRY_COUNT && pixelAck == DIAG_RETRY_COUNT
                   ? HIGH
                   : LOW);
}

void loop() {}
