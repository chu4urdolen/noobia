; Return Lolth's four lower joints from standby to observed normal angles.
; Upper joints are untouched. The four SYS calls run within one VM tick.
; Servo 1 front right lower: 90 degrees
; Servo 4 back right lower: 95 degrees
; Servo 5 front left lower: 75 degrees
; Servo 8 back left lower: 105 degrees (candidate; +15 from prior 90)
; r0 = servo number, r1 = absolute angle, r2 = syscall result.

0000  MOV  r0, 1
0006  MOV  r1, 90
000c  SYS  r2, SERVO_ARM(116), r0, r1
0013  MOV  r0, 4
0019  MOV  r1, 95
001f  SYS  r2, SERVO_ARM(116), r0, r1
0026  MOV  r0, 5
002c  MOV  r1, 75
0032  SYS  r2, SERVO_ARM(116), r0, r1
0039  MOV  r0, 8
003f  MOV  r1, 105
0045  SYS  r2, SERVO_ARM(116), r0, r1
004c  HALT
