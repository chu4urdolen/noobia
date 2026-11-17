#include "lolth.h"

#include "lolth_config.h"

void lolthBeginSensor() {
  pinMode(LolthPins::ULTRASONIC_TRIGGER, OUTPUT);
  digitalWrite(LolthPins::ULTRASONIC_TRIGGER, LOW);
  pinMode(LolthPins::ULTRASONIC_ECHO, INPUT);
}

NativeResult lolthDistanceMm(const int32_t *arguments, uint8_t count) {
  if (count) return {false, 0, "usage: no arguments"};
  digitalWrite(LolthPins::ULTRASONIC_TRIGGER, LOW);
  delayMicroseconds(2);
  digitalWrite(LolthPins::ULTRASONIC_TRIGGER, HIGH);
  delayMicroseconds(10);
  digitalWrite(LolthPins::ULTRASONIC_TRIGGER, LOW);
  const unsigned long echoUs =
      pulseIn(LolthPins::ULTRASONIC_ECHO, HIGH, 25000UL);
  if (!echoUs) return {false, 0, "no ultrasonic echo"};
  const int32_t millimetres = (echoUs * 343UL + 1000UL) / 2000UL;
  if (millimetres < 20 || millimetres > 4000)
    return {false, 0, "echo outside 20..4000 mm"};
  NoobRecord record;
  record.add("distance_mm", millimetres);
  record.add("echo_us", echoUs);
  return {true, millimetres, "", record};
}
