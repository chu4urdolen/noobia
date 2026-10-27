# Common VM v1; CALL_MIXED SEQUENCE_SET 0 500 IMAGE_CHOOSE 4 1010 append=1 poses=(0,1).
# Pose index 0 is standing; 1 is talking in the current sorted catalog.
MOVI r0, 0
MOVI r1, 500
MOVI r2, 311
MOVI r3, 4
MOVI r4, 0b1010
MOVI r5, 1
MOVI r6, 0
MOVI r7, 1
SYS_MIXED r0, SEQUENCE_SET, r0..r7, ""
SYS r0, SEQUENCE_START
HALT
