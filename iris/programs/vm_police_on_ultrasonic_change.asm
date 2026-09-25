; Start ultrasonic change detection: 100 mm delta, 250 ms samples.
0000  MOVI r0, 100
0006  MOVI r1, 250
000c  SYS  r2, ULTRASONIC_CHANGE_START(202), r0, r1

; Poll the thread event queue. Zero means no event yet.
0013 poll:
0013  SYS  r3, ULTRASONIC_CHANGE_POLL(206)
0018  JZ   r3, idle

; A timestamp was received. Run the compiled finite police sequence.
001c  SYS  r4, POLICE_SEQUENCE(201)

; Do not start a second sequence while the first owns the sequencer.
0021 sequence_wait:
0021  WAIT 50
0024  SYS  r5, SEQUENCE_STATUS(6)
0029  JNZ  r5, sequence_wait

; Coalesce changes that happened while the lights were busy.
002d drain:
002d  SYS  r3, ULTRASONIC_CHANGE_POLL(206)
0032  JNZ  r3, drain
0036  JMP  poll

0039 idle:
0039  WAIT 250
003c  JMP  poll
