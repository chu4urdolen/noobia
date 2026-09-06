#include "iris.h"

void irisRegisterCapabilities(CapabilityRegistry &capabilities) {
  capabilities.add("GPIO");
  capabilities.add("PWM");
  capabilities.add("ADC");
  capabilities.add("I2C");
  capabilities.add("OLED_SH1107_128X128");
  capabilities.add("SPI");
  capabilities.add("UART");
  capabilities.add("USB");
  capabilities.add("WIFI");
  capabilities.add("BLE");
  capabilities.add("CAMERA");
  capabilities.add("SD");
  capabilities.add("MIC");
  capabilities.add("RGB_LED");
  capabilities.add("SIGNAL_LED");
}
