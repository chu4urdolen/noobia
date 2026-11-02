# One bounded pulse; native call enforces the health gate and OFF.
# A failed pulse faults the VM, so FLASH_STOP remains callable directly.
MOVI r0, 100
SYS r1, FLASH_PULSE, r0
SYS r2, FLASH_STOP
HALT
