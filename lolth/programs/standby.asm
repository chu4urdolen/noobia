; LAFVIN standby pose, adapted to Lolth's observed neutral angles.
; Only lower joints move. The four SYS calls run within one VM tick.
;           joint                  neutral  standby  physical motion
; servo 1   front right lower       90       60      down
; servo 4   back right lower        95       125     down
; servo 5   front left lower        75       105     down
; servo 8   back left lower         ?        60      down
; LAFVIN's published standby() uses lower angles 60,120,120,60 with
; nominal 90-degree centers. Lolth's observed centers add +5 on servo 4
; and -15 on servo 5. Servo 8's 60-degree standby target was visually
; approved; its normal angle is now under recalibration. Upper joints are
; intentionally untouched.
; r0 = servo number, r1 = absolute angle, r2 = syscall result.

0000  MOV  r0, 1
0006  MOV  r1, 60
000c  SYS  r2, SERVO_ARM(116), r0, r1
0013  MOV  r0, 4
0019  MOV  r1, 125
001f  SYS  r2, SERVO_ARM(116), r0, r1
0026  MOV  r0, 5
002c  MOV  r1, 105
0032  SYS  r2, SERVO_ARM(116), r0, r1
0039  MOV  r0, 8
003f  MOV  r1, 60
0045  SYS  r2, SERVO_ARM(116), r0, r1
004c  HALT
