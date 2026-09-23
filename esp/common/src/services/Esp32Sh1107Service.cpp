#if (!defined(NOOB_ENABLE_EXTERNAL_I2C) || NOOB_ENABLE_EXTERNAL_I2C) && \
    (!defined(NOOB_ENABLE_SH1107) || NOOB_ENABLE_SH1107)
#include "services/Esp32Sh1107Service.h"

#include <U8g2lib.h>
#include <Wire.h>
#include <Esp32SoftI2cDiagnostics.h>

namespace {
U8G2_SH1107_PIMORONI_128X128_1_HW_I2C display(U8G2_R0,
                                               U8X8_PIN_NONE);
int displaySda = -1;
int displayScl = -1;
uint8_t displayAddress = 0x3c;
bool displayAcknowledged = false;

bool probe() {
  Wire.beginTransmission(displayAddress);
  return Wire.endTransmission() == 0;
}

bool drawTest() {
  // The exact GME128128-01-IIC working example uses the PIMORONI SH1107
  // geometry. Page-buffer rendering also matches the controller's 16 pages.
  display.firstPage();
  do {
    display.setDrawColor(1);
    display.drawFrame(0, 0, 128, 128);
    display.drawBox(8, 8, 32, 32);
    display.drawBox(88, 8, 32, 32);
    display.drawBox(8, 88, 32, 32);
    display.drawBox(88, 88, 32, 32);
    display.setFont(u8g2_font_helvB12_tf);
    display.drawStr(43, 70, "IRIS");
  } while (display.nextPage());
  return true;
}
}

namespace Esp32Sh1107Service {
bool begin(int sdaPin, int sclPin, uint8_t address) {
  displaySda = sdaPin;
  displayScl = sclPin;
  displayAddress = address;
  // Soft diagnostics may have changed pin modes, so explicitly reattach
  // controller 0 before U8g2 initializes this external display.
  Wire.end();
  displayAcknowledged = Wire.begin(displaySda, displayScl, 100000);
  Wire.setTimeOut(20);
  display.setI2CAddress(displayAddress << 1);
  display.begin();
  display.setContrast(255);
  displayAcknowledged &= probe();
  if (displayAcknowledged) drawTest();
  return displayAcknowledged;
}

NativeResult testPattern(const int32_t *, uint8_t) {
  displayAcknowledged = drawTest();
  return {true, displayAddress,
          "SH1107 PIMORONI page-buffer address=0x" +
              String(displayAddress, HEX)};
}
}
#endif
