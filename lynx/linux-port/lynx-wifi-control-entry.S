.global _start
.section .text
_start:
    ldr x0, [sp]
    add x1, sp, #8
    bl main
    mov x8, #93
    svc #0
1:  b 1b
.section .note.GNU-stack,"",%progbits
