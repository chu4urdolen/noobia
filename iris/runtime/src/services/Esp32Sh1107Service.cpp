#include "services/Esp32Sh1107Service.h"

#include <U8g2lib.h>
#include <Esp32SoftI2cDiagnostics.h>

namespace {
U8G2_SH1107_128X128_F_SW_I2C *display = nullptr;
uint8_t displayAddress = 0x3c;
bool displayAcknowledged = false;

bool probe() {
  return Esp32SoftI2cDiagnostics::probe(displayAddress);
}

void drawTest() {
  display->clearBuffer();
  display->drawFrame(0, 0, 128, 128);
  display->setFont(u8g2_font_helvB12_tr);
  display->drawStr(38, 50, "IRIS");
  display->setFont(u8g2_font_6x12_tr);
  display->drawStr(27, 74, "SH1107 ONLINE");
  display->drawCircle(64, 98, 12);
  display->sendBuffer();
}
}

namespace Esp32Sh1107Service {
bool begin(int sdaPin, int sclPin, uint8_t address) {
  displayAddress = address;
  display = new U8G2_SH1107_128X128_F_SW_I2C(
      U8G2_R0, sclPin, sdaPin, U8X8_PIN_NONE);
  display->setI2CAddress(address << 1);
  display->begin();
  displayAcknowledged = probe();
  if (displayAcknowledged) drawTest();
  return displayAcknowledged;
}

NativeResult testPattern(const int32_t *, uint8_t) {
  if (!display) return {false, 0, "SH1107 service unavailable"};
  displayAcknowledged = probe();
  if (!displayAcknowledged)
    return {false, displayAddress, "SH1107 did not acknowledge"};
  drawTest();
  return {true, displayAddress,
          "SH1107 128x128 address=0x" + String(displayAddress, HEX)};
}
}
