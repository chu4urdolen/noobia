# Start the compiled image-cycle thread at 500 ms and halt the VM.
# Stop the thread separately with CALL IMAGE_CYCLE_STOP.
MOVI r0, 500
SYS r1, IMAGE_CYCLE_START, r0
HALT
