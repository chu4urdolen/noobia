; Start the rolling mic detector: 2x rise and minimum RMS 20.
0000  MOVI r0, 200
0006  MOVI r1, 20
000c  SYS  r2, MIC_RISE_START(212), r0, r1

; Poll timestamp events and run one finite police sequence per loud episode.
0013 poll:
0013  SYS  r3, MIC_RISE_POLL(216)
0018  JZ   r3, idle
001c  SYS  r4, POLICE_SEQUENCE(201)

0021 sequence_wait:
0021  WAIT 50
0024  SYS  r5, SEQUENCE_STATUS(6)
0029  JNZ  r5, sequence_wait
002d  JMP  poll

0030 idle:
0030  WAIT 250
0033  JMP  poll
