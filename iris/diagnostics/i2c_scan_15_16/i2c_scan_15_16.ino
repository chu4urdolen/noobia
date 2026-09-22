#include <Wire.h>
#include "../diagnostic_config.h"

// Narrow, read-only bus diagnostic for Iris's external OLED wiring.
// This sketch uses only GPIO15 (SDA) and GPIO16 (SCL). It probes I2C
// addresses but sends no display initialization or framebuffer data.
void setup() {
  pinMode(DIAG_SIGNAL_LED_PIN, OUTPUT);
  digitalWrite(DIAG_SIGNAL_LED_PIN, LOW);
  Serial0.begin(115200);
  delay(1000);

  const bool started = Wire.begin(DIAG_SDA_PIN, DIAG_SCL_PIN, DIAG_I2C_HZ);
  Serial0.printf("I2C_BEGIN sda=%d scl=%d hz=%lu ok=%d\n", DIAG_SDA_PIN,
                 DIAG_SCL_PIN, static_cast<unsigned long>(DIAG_I2C_HZ), started);
}

void loop() {
  digitalWrite(DIAG_SIGNAL_LED_PIN, LOW);
  unsigned devices = 0;

  Serial0.println("I2C_SCAN_BEGIN");
  for (uint8_t address = 1; address < 127; ++address) {
    Wire.beginTransmission(address);
    const uint8_t error = Wire.endTransmission(true);
    if (error == 0) {
      Serial0.printf("I2C_DEVICE address=0x%02X\n", address);
      ++devices;
      if (address == DIAG_OLED_ADDRESS) digitalWrite(DIAG_SIGNAL_LED_PIN, HIGH);
    }
  }
  Serial0.printf("I2C_SCAN_END devices=%u\n", devices);
  delay(5000);
}
