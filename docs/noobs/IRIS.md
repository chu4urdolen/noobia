# Iris code map

Iris is the ESP32 camera Noob. Start with [`iris/README.md`](../../iris/README.md)
and the [firmware guide](../../iris/firmware/iris_noob/README.md).

| Need | Source |
| --- | --- |
| Board hardware and native calls | `iris/firmware/iris_noob/src/noobs/iris/` |
| Camera and microphone setup | `hw_camera.cpp`, `hw_microphone.cpp` in that directory |
| Protocol, VM and IDs | [`PROTOCOL.md`](../../iris/firmware/iris_noob/PROTOCOL.md), [`VM.md`](../../iris/firmware/iris_noob/VM.md) |
| Nexus-side controls | [`iris/tools/README.md`](../../iris/tools/README.md), `iris/tools/irisctl` |
| Example programs | [`iris/programs/README.md`](../../iris/programs/README.md) |
| Reusable NRP/1 implementation | [`esp/common/README.md`](../../esp/common/README.md) |

Iris's bounded native calls and sequencer are a model for Lynx's remote API.
Her ESP32 device drivers are not interchangeable with Lynx's MediaTek drivers.
