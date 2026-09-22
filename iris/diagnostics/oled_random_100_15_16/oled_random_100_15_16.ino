#include <Wire.h>
#include "../diagnostic_config.h"

bool sendPair(uint8_t control, uint8_t value) {
  Wire.beginTransmission(DIAG_OLED_ADDRESS);
  Wire.write(control);
  Wire.write(value);
  return Wire.endTransmission(true) == 0;
}

int commandRetry(uint8_t command) {
  for (int attempt = 0; attempt < DIAG_RETRY_COUNT; ++attempt) {
    if (sendPair(0x80, command)) return attempt + 1;
    delay(10);
  }
  return 0;
}

void setup() {
  pinMode(DIAG_SIGNAL_LED_PIN, OUTPUT);
  digitalWrite(DIAG_SIGNAL_LED_PIN, LOW);
  Wire.begin(DIAG_SDA_PIN, DIAG_SCL_PIN, DIAG_I2C_HZ);

  const int onTries = commandRetry(0xaf);
  delay(150);
  const int ramTries = commandRetry(0xa4);
  const int normalTries = commandRetry(0xa6);

  uint32_t random = 0x49524953u;  // Reproducible "IRIS" seed.
  unsigned addressed = 0;
  unsigned dataAcked = 0;
  for (unsigned point = 0; point < 100; ++point) {
    random = random * 1664525u + 1013904223u;
    uint8_t x = static_cast<uint8_t>(random >> 24) & 127;
    random = random * 1664525u + 1013904223u;
    uint8_t y = static_cast<uint8_t>(random >> 24) & 127;

    const int page = commandRetry(0xb0 | (y >> 3));
    const int low = commandRetry(x & 0x0f);
    const int high = commandRetry(0x10 | (x >> 4));
    if (page && low && high) ++addressed;
    dataAcked += sendPair(0x40, 1u << (y & 7));
    delay(2);
  }

  digitalWrite(DIAG_SIGNAL_LED_PIN,
               onTries && ramTries && normalTries && addressed == 100 &&
                       dataAcked == 100
                   ? HIGH
                   : LOW);
}

void loop() {}
