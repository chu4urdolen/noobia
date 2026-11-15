; Runtime baseline, 200-count dynamic delta, 250 ms samples.
0000  MOVI r0, 200
0006  MOVI r1, 250
000c  SYS  r2, LIGHT_CHANGE_START(207), r0, r1
0013  HALT
