# Lynx Infrared (IR) Blaster Preflight Architecture

**Author:** Banshee 💙 (Spirit of Initiative)  
**Date:** 2026-11-21  
**Target:** OnePlus Nord 3 5G (CPH2493, MediaTek MT6983 / Dimensity 9000)  
**Task Item:** B21 (Round 7)  
**Status:** Landed & Validated  

---

## 1. Executive Summary

This document establishes the hardware mapping, Device Tree configuration, signal modulation architecture, and preflight validation gates for the **Consumer Infrared (CIR) transmitter / IR blaster** on the OnePlus Nord 3.

The OnePlus Nord 3 incorporates a dedicated consumer infrared LED positioned on the top edge of the device. This optical emitter enables the phone to function as a universal remote control across home entertainment, climate control, and audio systems. Unlike simple GPIO bit-banging, the MediaTek MT6983 pairs an SoC hardware PWM timing channel with KooKong IR protocol acceleration logic to synthesize carrier-modulated waveforms.

---

## 2. Hardware Mapping & Device Tree Topology

From the runtime merged Device Tree (`stock-merged.dtb`), the infrared transmitter subsystem consists of two nodes:

```
+-----------------------------------------------------------------------------------------+
|                               MediaTek MT6983 SoC                                       |
|                                                                                         |
|  +-----------------------------------------------------------------------------------+  |
|  | Hardware PWM Generator (mtk-pwm / pwm-num channel)                                |  |
|  | - DMA buffer allocation & high-precision microsecond timing                        |  |
|  | - Carrier synthesis: 30 kHz - 60 kHz (38 kHz standard)                            |  |
|  | - Duty cycle control: 33% nominal pulse width                                     |  |
|  +----------------------------------------+------------------------------------------+  |
|                                           |                                             |
|                                           v                                             |
|  +-----------------------------------------------------------------------------------+  |
|  | KooKong Consumer IR PWM Controller (oplus,kookong_ir_pwm)                         |  |
|  | - Device Tree node: consumerIr (status = "okay")                                   |  |
|  | - Core framework node: consumer_ir_core (oplus,kookong_ir_core)                    |  |
|  +----------------------------------------+------------------------------------------+  |
|                                           |                                             |
|                                           v                                             |
|  +-----------------------------------------------------------------------------------+  |
|  | Top Edge Consumer IR LED Transceiver & Current Driver                             |  |
|  +-----------------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------------+
```

### 2.1 Device Tree Node Bindings
- **PWM Controller Node:** `consumerIr`
  - `compatible = "oplus,kookong_ir_pwm"`
  - `status = "okay"`
  - `pwm-num`: MediaTek PWM channel index
- **Core Node:** `consumer_ir_core`
  - `compatible = "oplus,kookong_ir_core"`
  - `status = "okay"`

### 2.2 Kernel Drivers & Character Interface
- **Kernel Modules:**
  - `oplus_bsp_ir_core.ko`: Core protocol framework and transmission workqueue coordinator.
  - `oplus_bsp_kookong_ir_pwm.ko`: Hardware PWM modulator interfacing with `mtk-pwm`.
- **Character Device Node:** `/dev/ir_remote` (character device registered for user-space pattern injection).

---

## 3. Modulation & Carrier Waveform Envelopes

Consumer infrared protocols rely on high-frequency carrier wave packets interspersed with space intervals:

| Parameter | Nominal Value | Valid Operating Band | Standard Protocols |
|---|---|---|---|
| **Carrier Frequency** | 38,000 Hz (38 kHz) | 30,000 Hz – 60,000 Hz | NEC, Sony SIRC (40 kHz), Philips RC5/RC6 (36 kHz), RC-MM (56 kHz) |
| **Transmit Duty Cycle** | 33% | 10% – 60% | Minimizes LED thermal dissipation while ensuring receiver photodiode saturation |
| **Pulse Duration Resolution** | Microsecond ($\mu\text{s}$) | $\ge 1\,\mu\text{s}$ | DMA-driven timing fidelity via SoC PWM clock |

---

## 4. Preflight Validator Implementation & Safety Invariants

The preflight tool `lynx/tools/ir_blaster/lynx_ir_blaster_preflight.py` audits Device Tree configuration, character device registration, and runtime binding state against invariant safety envelopes:

1. **Preflight Operating States:**
   - `BOUND_READY` (Status `OK`): Device Tree nodes verified, driver bound, `/dev/ir_remote` character device active and ready for commands.
   - `UNBOUND_QUIESCENT` (Status `OK`): Device Tree topology verified, driver safely quiescent/unbound, no device node instantiated.
   - `MALFORMED_SPEC` (Status `FAIL`): Missing required Device Tree nodes (`consumerIr` or `consumer_ir_core`) or disabled status.
   - `WARNING` (Status `WARN`): Out-of-band carrier frequency ($< 30\text{kHz}$ or $> 60\text{kHz}$) or unusual duty cycle.

2. **Strict Safety Invariants:**
   - **Zero Optical Emission:** Preflight NEVER writes data frames to `/dev/ir_remote`, never calls `ir_pwm_file_write`, and never transmits IR bursts.
   - **Zero Module Injections:** Observes existing driver binding without loading or unloading kernel modules.
   - **Double-Gated Live Probes:** Live interrogation over SSH requires explicit `--live --allow-live`.

---

## 5. Test Evidence

```
test_ast_safety_and_no_writes (test_lynx_ir_blaster_preflight.TestLynxIrBlasterPreflight) ... ok
test_boot_id_mismatch (test_lynx_ir_blaster_preflight.TestLynxIrBlasterPreflight) ... ok
test_bound_ready (test_lynx_ir_blaster_preflight.TestLynxIrBlasterPreflight) ... ok
test_carrier_frequency_warning (test_lynx_ir_blaster_preflight.TestLynxIrBlasterPreflight) ... ok
test_cli_live_safety_gate (test_lynx_ir_blaster_preflight.TestLynxIrBlasterPreflight) ... ok
test_cli_validate_offline (test_lynx_ir_blaster_preflight.TestLynxIrBlasterPreflight) ... ok
test_duty_cycle_warning (test_lynx_ir_blaster_preflight.TestLynxIrBlasterPreflight) ... ok
test_missing_dt (test_lynx_ir_blaster_preflight.TestLynxIrBlasterPreflight) ... ok
test_module_inactive_warning (test_lynx_ir_blaster_preflight.TestLynxIrBlasterPreflight) ... ok
test_unbound_quiescent (test_lynx_ir_blaster_preflight.TestLynxIrBlasterPreflight) ... ok

----------------------------------------------------------------------
Ran 10 tests in 0.091s

OK
```
