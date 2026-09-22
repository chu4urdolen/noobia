#include <U8g2lib.h>
#include "../diagnostic_config.h"

// Exact display variant used by a working GME128128-01-IIC project. Only the
// ESP32-S3 pin assignment differs from the Arduino example.
U8G2_SH1107_PIMORONI_128X128_1_SW_I2C oled(
    U8G2_R0, DIAG_SCL_PIN, DIAG_SDA_PIN, U8X8_PIN_NONE);

void setup() {
  // Iris test wiring: SDA is GPIO15 and SCL is GPIO16.
  pinMode(DIAG_SIGNAL_LED_PIN, OUTPUT);
  digitalWrite(DIAG_SIGNAL_LED_PIN, LOW);
  oled.setI2CAddress(DIAG_OLED_ADDRESS << 1);
  oled.begin();
  oled.setContrast(255);
  oled.clearDisplay();

  oled.firstPage();
  do {
    oled.drawFrame(0, 0, 128, 128);
    oled.drawBox(8, 8, 32, 32);
    oled.drawBox(88, 8, 32, 32);
    oled.drawBox(8, 88, 32, 32);
    oled.drawBox(88, 88, 32, 32);
    oled.setFont(u8g2_font_helvB12_tf);
    oled.drawStr(43, 70, "IRIS");
  } while (oled.nextPage());
  digitalWrite(DIAG_SIGNAL_LED_PIN, HIGH);
}

void loop() {}
