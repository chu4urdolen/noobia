; Start ten-second rolling loudness detection.
; 200% means the newer five seconds must average at least twice the older five.
0000  MOVI r0, 200
0006  MOVI r1, 20
000c  SYS  r2, MIC_RISE_START(212), r0, r1
