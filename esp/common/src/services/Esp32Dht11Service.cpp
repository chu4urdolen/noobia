#include "Esp32Dht11Service.h"
#include <driver/gpio.h>
namespace {
int pin = -1;
uint32_t lastAttempt;
bool attempted = false;
portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
// Bound each wait; capture pulses before allocating or logging.
int pulse(int level) {
  uint32_t start = micros();
  while (gpio_get_level(gpio_num_t(pin)) == level)
    if (uint32_t(micros()-start) >= 150) return -1;
  return int(uint32_t(micros()-start));
}
}
bool Esp32Dht11Service::begin(int p) {
  if (!GPIO_IS_VALID_OUTPUT_GPIO(p)) return false;
  pin = p;
  attempted = false;
  return true;
}
NativeResult Esp32Dht11Service::sample(int32_t &temperature,
                                       int32_t &humidity) {
  if (pin < 0) return {false, 0, "DHT11 unconfigured"};
  if (millis() < 2000 || (attempted && uint32_t(millis()-lastAttempt) < 2000))
    return {false, 0, "DHT11 cooldown_ms=2000"};
  lastAttempt = millis();
  attempted = true;
  pinMode(pin, INPUT_PULLUP);
  delay(1);
  if (!digitalRead(pin)) return {false, 0, "DHT11 idle_low"};
  // Pull low for 20ms, then release for the sensor response.
  pinMode(pin, OUTPUT_OPEN_DRAIN);
  digitalWrite(pin, LOW);
  delay(20);
  int widths[80] = {};
  int failed = -1;
  portENTER_CRITICAL(&mux);
  pinMode(pin, INPUT_PULLUP);
  if (pulse(HIGH) < 0) failed = 0;
  else if (pulse(LOW) < 0) failed = 1;
  else if (pulse(HIGH) < 0) failed = 2;
  for (int i = 0; failed < 0 && i < 80; ++i) {
    widths[i] = pulse(i % 2 ? HIGH : LOW);
    if (widths[i] < 0) failed = i + 3;
  }
  portEXIT_CRITICAL(&mux);
  if (failed >= 0) return {false, 0, "DHT11 timeout phase=" + String(failed)};
  uint8_t bytes[5] = {};
  for (int i = 0; i < 40; ++i)
    bytes[i/8] = (bytes[i/8] << 1) | (widths[2*i+1] > widths[2*i]);
  char raw[16];
  snprintf(raw, sizeof(raw), "%02x%02x%02x%02x%02x", bytes[0], bytes[1], bytes[2], bytes[3], bytes[4]);
  if (uint8_t(bytes[0]+bytes[1]+bytes[2]+bytes[3]) != bytes[4])
    return {false, 0, String("DHT11 checksum raw=") + raw};
  humidity = bytes[0]*10 + bytes[1];
  temperature = (bytes[3]&0x80 ? -1-int(bytes[2]) : int(bytes[2]))*10 + (bytes[3]&15);
  if (humidity > 1000 || temperature < -200 || temperature > 800)
    return {false, 0, String("DHT11 range raw=") + raw};
  return {true, temperature,
          "temperature_c=" + String(temperature/10.0f, 1) +
          " humidity_pct=" + String(humidity/10.0f, 1) + " raw=" + raw};
}

NativeResult Esp32Dht11Service::read(const int32_t *args, uint8_t count) {
  if (count > 1 || (count && (args[0] < 0 || args[0] > 1)))
    return {false, 0, "usage: [0=temperature|1=humidity]"};
  int32_t temperature = 0;
  int32_t humidity = 0;
  NativeResult result = sample(temperature, humidity);
  if (result.ok) result.value = count && args[0] ? humidity : temperature;
  return result;
}
