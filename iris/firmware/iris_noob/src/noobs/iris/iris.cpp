#include "iris.h"
#include "iris_config.h"
#include "iris_secrets.h"
#include <transport/BleClientTransport.h>
#include <services/Esp32WifiService.h>
#include <services/Esp32SdMmcService.h>
#include <services/Esp32CameraService.h>
#include <services/Esp32I2sMicService.h>
#include <services/Esp32RgbLedService.h>
#include <services/Esp32SignalLedService.h>
#include <services/Esp32I2cService.h>
#include <services/Esp32VmProgramStore.h>
#include <Esp32GpioInspector.h>
#include <Esp32SoftI2cDiagnostics.h>
#include <services/Esp32Sh1107Service.h>

void irisRegisterCapabilities(CapabilityRegistry &capabilities);

bool irisRegister(NoobRuntime &runtime) {
  // This is the single composition root for Iris. Common code learns what Iris
  // supports only through these registries, never through board-name checks.
  irisRegisterCapabilities(runtime.capabilities());
  bool ok = irisCameraBegin();
  ok &= irisStorageBegin();
  ok &= irisMicrophoneBegin();
  ok &= Esp32RgbLedService::begin(IrisPins::RGB_LED);
  ok &= Esp32SignalLedService::begin(IrisPins::SIGNAL_LED);
  ok &= Esp32I2cService::begin(IrisPins::I2C_SDA, IrisPins::I2C_SCL);
  ok &= Esp32SoftI2cDiagnostics::begin(IrisPins::I2C_SDA, IrisPins::I2C_SCL);
  // Absence of an optional display must not prevent the rest of Iris starting.
  Esp32Sh1107Service::begin(IrisPins::I2C_SDA, IrisPins::I2C_SCL, 0x3c);
  ok &= Esp32WifiService::begin(IrisSecrets::WIFI_SSID,
                                IrisSecrets::WIFI_PASSWORD);
  ok &= Esp32VmProgramStore::begin(runtime.vm());
  ok &= Esp32GpioInspector::begin(48);
  const uint8_t cameraPins[] = {2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 21};
  for (uint8_t pin : cameraPins) ok &= Esp32GpioInspector::reserve(pin, "camera");
  for (uint8_t pin = 26; pin <= 32; ++pin) ok &= Esp32GpioInspector::reserve(pin, "flash-psram");
  const uint8_t sdPins[] = {38, 39, 41, 42};
  for (uint8_t pin : sdPins) ok &= Esp32GpioInspector::reserve(pin, "sd");
  const uint8_t micPins[] = {35, 36, 37};
  for (uint8_t pin : micPins) ok &= Esp32GpioInspector::reserve(pin, "mic");
  ok &= Esp32GpioInspector::reserve(1, "i2c-sda");
  ok &= Esp32GpioInspector::reserve(40, "i2c-scl");
  ok &= Esp32GpioInspector::reserve(19, "usb-dminus");
  ok &= Esp32GpioInspector::reserve(20, "usb-dplus");
  ok &= Esp32GpioInspector::reserve(33, "rgb-led");
  ok &= Esp32GpioInspector::reserve(34, "signal-led");
  ok &= Esp32GpioInspector::reserve(43, "uart0-tx");
  ok &= Esp32GpioInspector::reserve(44, "uart0-rx");
  ok &= Esp32GpioInspector::reserve(0, "boot-strap");
  ok &= Esp32GpioInspector::reserve(45, "strap");
  ok &= Esp32GpioInspector::reserve(46, "strap-input-only");
  const uint8_t pullTestPins[] = {15, 16, 47, 48};
  for (uint8_t pin : pullTestPins) ok &= Esp32GpioInspector::allowPullTest(pin);

  // Iris selects capabilities and IDs here; every implementation below is a
  // reusable ESP32 service with no knowledge of the Iris board pin map.
  ok &= runtime.natives().add(IrisFunctions::CAMERA_CAPTURE, "CAMERA_CAPTURE", Esp32CameraService::capture);
  ok &= runtime.natives().add(IrisFunctions::CAMERA_VIDEO, "CAMERA_VIDEO", Esp32CameraService::recordMjpeg);
  ok &= runtime.natives().add(IrisFunctions::STORAGE_STATUS, "STORAGE_STATUS", Esp32SdMmcService::status);
  ok &= runtime.natives().add(IrisFunctions::SD_LIST, "CAPTURE_LIST", Esp32SdMmcService::list);
  ok &= runtime.natives().add(IrisFunctions::SD_READ_CHUNK, "CAPTURE_READ_CHUNK", Esp32SdMmcService::readChunk);
  ok &= runtime.natives().add(IrisFunctions::SD_DELETE, "CAPTURE_DELETE", Esp32SdMmcService::remove);
  ok &= runtime.natives().addText(IrisFunctions::SD_DELETE_PATH, "SD_DELETE", Esp32SdMmcService::removePath);
  ok &= runtime.natives().addText(IrisFunctions::SD_LIST_PATH, "SD_LIST", Esp32SdMmcService::listPath);
  ok &= runtime.natives().add(IrisFunctions::WIFI_SCAN, "WIFI_SCAN", Esp32WifiService::scan);
  ok &= runtime.natives().add(IrisFunctions::WIFI_RSSI, "WIFI_RSSI", Esp32WifiService::rssi);
  ok &= runtime.natives().add(IrisFunctions::RSSI_ON, "RSSI_ON", Esp32WifiService::rssiOn);
  ok &= runtime.natives().add(IrisFunctions::RSSI_OFF, "RSSI_OFF", Esp32WifiService::rssiOff);
  ok &= runtime.natives().add(IrisFunctions::WIFI_CONNECT, "WIFI_CONNECT", Esp32WifiService::connect);
  ok &= runtime.natives().add(IrisFunctions::WIFI_DISCONNECT, "WIFI_DISCONNECT", Esp32WifiService::disconnect);
  ok &= runtime.natives().add(IrisFunctions::WIFI_STATUS, "WIFI_STATUS", Esp32WifiService::status);
  ok &= runtime.natives().addText(IrisFunctions::WIFI_CREDENTIALS_SET, "WIFI_CREDENTIALS_SET", Esp32WifiService::setCredentials);
  ok &= runtime.natives().add(IrisFunctions::MIC_LEVEL, "MIC_LEVEL", Esp32I2sMicService::level);
  ok &= runtime.natives().add(IrisFunctions::MIC_ABOVE, "MIC_ABOVE", Esp32I2sMicService::above);
  ok &= runtime.natives().add(IrisFunctions::AUDIO_RECORD, "AUDIO_RECORD", Esp32I2sMicService::recordWav);
  ok &= runtime.natives().add(IrisFunctions::LED_RGB, "LED_RGB", Esp32RgbLedService::set);
  ok &= runtime.natives().add(IrisFunctions::LED_SIGNAL, "LED_SIGNAL", Esp32SignalLedService::set);
  ok &= runtime.natives().addText(IrisFunctions::VM_SAVE, "VM_SAVE", Esp32VmProgramStore::save);
  ok &= runtime.natives().addText(IrisFunctions::VM_LOAD_SAVED, "VM_LOAD_SAVED", Esp32VmProgramStore::load);
  ok &= runtime.natives().addText(IrisFunctions::VM_LIST_SAVED, "VM_LIST_SAVED", Esp32VmProgramStore::list);
  ok &= runtime.natives().addText(IrisFunctions::VM_DELETE_SAVED, "VM_DELETE_SAVED", Esp32VmProgramStore::remove);
  ok &= runtime.natives().add(IrisFunctions::I2C_SCAN, "I2C_SCAN", Esp32I2cService::scan);
  ok &= runtime.natives().add(IrisFunctions::I2C_WRITE, "I2C_WRITE", Esp32I2cService::write);
  ok &= runtime.natives().add(IrisFunctions::I2C_READ, "I2C_READ", Esp32I2cService::read);
  ok &= runtime.natives().add(IrisFunctions::I2C_WRITE_READ, "I2C_WRITE_READ", Esp32I2cService::writeRead);
  ok &= runtime.natives().add(IrisFunctions::I2C_SOFT_SCAN, "I2C_SOFT_SCAN", Esp32SoftI2cDiagnostics::scan);
  ok &= runtime.natives().add(IrisFunctions::BLE_SCAN, "BLE_SCAN", BleClientTransport::scan);
  ok &= runtime.natives().addText(IrisFunctions::BLE_PEER_SET, "BLE_PEER_SET", BleClientTransport::setPeer);
  ok &= runtime.natives().add(IrisFunctions::BLE_STATUS, "BLE_STATUS", BleClientTransport::nativeStatus);
  ok &= runtime.natives().add(IrisFunctions::GPIO_AUDIT, "GPIO_AUDIT", Esp32GpioInspector::audit);
  ok &= runtime.natives().add(IrisFunctions::GPIO_INSPECT, "GPIO_INSPECT", Esp32GpioInspector::inspect);
  ok &= runtime.natives().add(IrisFunctions::GPIO_PULL_TEST, "GPIO_PULL_TEST", Esp32GpioInspector::pullTest);
  ok &= runtime.natives().add(IrisFunctions::OLED_TEST, "OLED_TEST", Esp32Sh1107Service::testPattern);
  ok &= runtime.addService(Esp32WifiService::rssiService());
  return ok;
}
