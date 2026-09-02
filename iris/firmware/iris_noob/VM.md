# Noob VM version 1

The VM has 1,024 bytes of program storage, 256 bytes of data memory, eight
signed 32-bit registers, and an eight-entry return stack. All multi-byte values
are little-endian. Execution is cooperative and bounded per runtime loop.

| Opcode | Encoding | Operation |
|---|---|---|
| `00` | `00` | halt |
| `01` | `01 dst imm32` | move immediate |
| `02` | `02 dst src` | move register |
| `03` | `03 dst a b` | add |
| `04` | `04 dst a b` | subtract |
| `05` | `05 dst a b` | multiply |
| `06` | `06 dst a b` | divide |
| `10` | `10 addr16` | jump |
| `11` | `11 reg addr16` | jump if zero |
| `12` | `12 reg addr16` | jump if nonzero |
| `13` | `13 addr16` | call VM subroutine |
| `14` | `14` | return |
| `20` | `20 dst func16 argc regs...` | native syscall |
| `21` | `21 milliseconds16` | nonblocking wait |
| `30` | `30 dst address8` | load memory byte |
| `31` | `31 address8 src` | store memory byte |

Verified programs:

- Waiting loop with `r0=42`: `01002a00000021e803100600`
- Compute `7+5` into `r2`: `0100070000000101050000000302000100`
- Iris camera syscall 100: `200064000000`

The Nexus-side named program store lives in `/noobia/iris/programs`. It
contains wire-ready examples for arithmetic, one-shot capture, timed RSSI
gathering, and sound-triggered capture.

Native failures and invalid bytecode place the VM in `FAULT`. `RESET_VM` clears
program memory, data memory, registers, call stack, and fault state.
