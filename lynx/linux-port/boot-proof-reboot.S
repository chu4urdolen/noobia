/* Freestanding AArch64 Linux program: exactly one standard RESTART2 request.
 * No device access, storage operations, raw registers or authentication. */
.global _start
.text
_start:
    movz x0, #0xdead
    movk x0, #0xfee1, lsl #16
    movz x1, #0x1969
    movk x1, #0x2812, lsl #16
    movz x2, #0xc3d4
    movk x2, #0xa1b2, lsl #16
    adr x3, boot_mode
    mov x8, #142
    svc #0
    /* Any returned reboot call is a failure, never retry. */
    mov x0, #125
    mov x8, #93
    svc #0
1:  b 1b
.section .rodata
boot_mode: .asciz "bootloader"
.section .note.GNU-stack,"",@progbits
