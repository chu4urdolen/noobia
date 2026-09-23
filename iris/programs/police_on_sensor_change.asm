; Start both dynamic detectors at 250 ms.
0000  MOVI r0, 100
0006  MOVI r1, 250
000c  SYS  r2, ULTRASONIC_CHANGE_START(202), r0, r1
0013  MOVI r0, 200
0019  SYS  r2, LIGHT_CHANGE_START(207), r0, r1

; Either timestamp triggers one police burst.
0020 poll:
0020  SYS  r3, ULTRASONIC_CHANGE_POLL(206)
0025  JNZ  r3, trigger
0029  SYS  r4, LIGHT_CHANGE_POLL(211)
002e  JZ   r4, idle

; The light thread stays running. Its sampler sees the sequence channel busy
; bits and pauses until both LED channels have ended.
0032 trigger:
0032  SYS  r2, POLICE_SEQUENCE(201)

0037 sequence_wait:
0037  WAIT 50
003a  SYS  r5, SEQUENCE_STATUS(6)
003f  JNZ  r5, sequence_wait

; Coalesce ultrasonic changes during the light burst. Light sampling was
; suppressed, so the light queue cannot contain self-generated events.
0043 drain_ultrasonic:
0043  SYS  r3, ULTRASONIC_CHANGE_POLL(206)
0048  JNZ  r3, drain_ultrasonic
004c  JMP  poll

004f idle:
004f  WAIT 250
0052  JMP  poll
