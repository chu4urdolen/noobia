# Common VM v1; CALL_MIXED SEQUENCE_SET 0 200 HAPTIC_SET 4 1010 append=1 duration=80ms.
# Four positions: pulse, stop, pulse, stop. Finite; motor off at completion.
MOVI r0, 0
MOVI r1, 200
MOVI r2, 300
MOVI r3, 4
MOVI r4, 0b1010
MOVI r5, 1
MOVI r6, 80
SYS_MIXED r0, SEQUENCE_SET, r0..r6, ""
SYS r0, SEQUENCE_START
HALT
