# NoobRuntime

NoobRuntime is the common embedded execution environment for physical Noobs.
It contains no board names, pin assignments, or Iris-specific branches.

## Runtime path

    transport -> NRP/1 parser -> command dispatcher
              -> VM or native registry -> NRP/1 reply -> transport

Current modules:

- `src/transport`: interchangeable transport interface, an Arduino `Stream`
  implementation for UART/USB, and an outbound BLE client transport.
- `src/protocol`: versioned request/reply framing and parse errors.
- `src/commands`: common command dispatcher.
- `src/vm`: bounded bytecode VM.
- `src/syscalls`: numeric/name native-function registry.
- `src/core`: runtime orchestration and capability registry.
- `src/hal`: reusable HAL contracts. Concrete ESP32 HAL implementations will
  be added as capabilities require them.

The BLE transport seeks a configured peer GATT server, subscribes to command
notifications, writes replies, and reconnects on a bounded schedule. Future
Wi-Fi transports should implement the same `NoobTransport` contract; neither
transport needs to alter the protocol, dispatcher, or VM.
