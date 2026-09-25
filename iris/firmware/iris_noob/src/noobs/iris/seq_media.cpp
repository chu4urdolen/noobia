#include "seq_media.h"

#include "iris_config.h"
#include <core/noob_sequence_program.h>

namespace {
constexpr uint8_t CAMERA_BITS[] = {1, 1, 1, 1, 1};
constexpr uint8_t IR_BITS[] = {1, 0, 1, 0, 1, 0, 1, 0, 1, 0};
constexpr int32_t IR_ARGUMENTS[] = {10, IrisHardware::IR_CARRIER_HZ};

const SequenceService::ChannelDefinition CAMERA_CHANNELS[] = {{
    IrisFunctions::CAMERA_SEQUENCE_STEP, IrisHardware::CAMERA_SEQUENCE_INTERVAL_MS,
    CAMERA_BITS, uint8_t(sizeof(CAMERA_BITS)), nullptr, 0}};
const SequenceService::ChannelDefinition IR_CHANNELS[] = {{
    IrisFunctions::IR_SEQUENCE_STEP, IrisHardware::IR_SEQUENCE_INTERVAL_MS,
    IR_BITS, uint8_t(sizeof(IR_BITS)), IR_ARGUMENTS,
    uint8_t(sizeof(IR_ARGUMENTS) / sizeof(IR_ARGUMENTS[0]))}};

class CameraSequence final : public NoobSequenceProgram {
 public:
  CameraSequence() : NoobSequenceProgram(CAMERA_CHANNELS, 1) {}
};
class IrSequence final : public NoobSequenceProgram {
 public:
  IrSequence() : NoobSequenceProgram(IR_CHANNELS, 1) {}
};

CameraSequence cameraSequence;
IrSequence irSequence;
}

NoobFunction &irisCameraSequence() { return cameraSequence; }
NoobFunction &irisIrSequence() { return irSequence; }
