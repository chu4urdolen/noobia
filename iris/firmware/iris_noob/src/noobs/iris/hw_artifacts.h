#pragma once

#include <syscalls/noob_native_registry.h>

bool irisArtifactsBegin();
NativeResult irisCameraSequenceStep(const int32_t *arguments, uint8_t count);
NativeResult irisIrSequenceStep(const int32_t *arguments, uint8_t count);
NativeResult irisRssiSnapshot(const int32_t *arguments, uint8_t count);
NativeResult irisIrSnapshot(const int32_t *arguments, uint8_t count);
NativeResult irisEnvSnapshot(const int32_t *arguments, uint8_t count);
NativeResult irisEnvTemperature(const int32_t *arguments, uint8_t count);
NativeResult irisEnvHumidity(const int32_t *arguments, uint8_t count);
