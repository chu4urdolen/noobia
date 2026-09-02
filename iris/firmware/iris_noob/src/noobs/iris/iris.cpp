#include "iris.h"
#include "iris_config.h"
#include <services/Esp32WifiService.h>
#include <services/Esp32SdMmcService.h>
#include <services/Esp32CameraService.h>
#include <services/Esp32I2sMicService.h>
#include <services/Esp32RgbLedService.h>
#include <services/Esp32SignalLedService.h>

void irisRegisterCapabilities(CapabilityRegistry &capabilities);

bool irisRegister(NoobRuntime &runtime) {
  // This is the single composition root for Iris. Common code learns what Iris
  // supports only through these registries, never through board-name checks.
  irisRegisterCapabilities(runtime.capabilities());
  const bool cameraReady = irisCameraBegin();
  const bool storageReady = irisStorageBegin();
  const bool microphoneReady = irisMicrophoneBegin();
  const bool ledReady = Esp32RgbLedService::begin(IrisPins::RGB_LED);
  const bool signalLedReady = Esp32SignalLedService::begin(IrisPins::SIGNAL_LED);
  const bool cameraRegistered = runtime.natives().add(
      IrisFunctions::CAMERA_CAPTURE, "CAMERA_CAPTURE",
      Esp32CameraService::capture);
  const bool storageRegistered = runtime.natives().add(
      IrisFunctions::STORAGE_STATUS, "STORAGE_STATUS", Esp32SdMmcService::status);
  const bool listRegistered = runtime.natives().add(
      IrisFunctions::SD_LIST, "SD_LIST", Esp32SdMmcService::list);
  const bool readRegistered = runtime.natives().add(
      IrisFunctions::SD_READ_CHUNK, "SD_READ_CHUNK", Esp32SdMmcService::readChunk);
  const bool deleteRegistered = runtime.natives().add(
      IrisFunctions::SD_DELETE, "SD_DELETE", Esp32SdMmcService::remove);
  const bool wifiReady = Esp32WifiService::begin();
  const bool scanRegistered = runtime.natives().add(
      IrisFunctions::WIFI_SCAN, "WIFI_SCAN", Esp32WifiService::scan);
  const bool rssiRegistered = runtime.natives().add(
      IrisFunctions::WIFI_RSSI, "WIFI_RSSI", Esp32WifiService::rssi);
  const bool rssiOnRegistered = runtime.natives().add(
      IrisFunctions::RSSI_ON, "RSSI_ON", Esp32WifiService::rssiOn);
  const bool rssiOffRegistered = runtime.natives().add(
      IrisFunctions::RSSI_OFF, "RSSI_OFF", Esp32WifiService::rssiOff);
  const bool micLevelRegistered = runtime.natives().add(
      IrisFunctions::MIC_LEVEL, "MIC_LEVEL", Esp32I2sMicService::level);
  const bool micAboveRegistered = runtime.natives().add(
      IrisFunctions::MIC_ABOVE, "MIC_ABOVE", Esp32I2sMicService::above);
  const bool ledRegistered = runtime.natives().add(
      IrisFunctions::LED_RGB, "LED_RGB", Esp32RgbLedService::set);
  const bool signalLedRegistered = runtime.natives().add(
      IrisFunctions::LED_SIGNAL, "LED_SIGNAL", Esp32SignalLedService::set);
  const bool rssiServiceRegistered =
      runtime.addService(Esp32WifiService::rssiService());
  return cameraReady && storageReady && microphoneReady && ledReady && signalLedReady &&
         cameraRegistered && storageRegistered &&
         listRegistered && readRegistered && deleteRegistered && wifiReady &&
         scanRegistered && rssiRegistered && rssiOnRegistered &&
         rssiOffRegistered && micLevelRegistered && micAboveRegistered &&
         ledRegistered && signalLedRegistered &&
         rssiServiceRegistered;
}
