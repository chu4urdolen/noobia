; Three detectors plus a Neo OLED thread. Neo image is persistent /img storage.
; DISPLAY_START schedules retries: a slow Neo boot must not fault this VM.
        MOVI r0, 5000
        SYS_MIXED r2, NEO_DISPLAY_START(269), r0, "Iris_formatted.gif"

        MOVI r0, 100
        MOVI r1, 250
        SYS r2, ULTRASONIC_CHANGE_START(202), r0, r1
        MOVI r0, 200
        SYS r2, LIGHT_CHANGE_START(207), r0, r1
        MOVI r3, 20
        SYS r2, MIC_RISE_START(212), r0, r3
poll:
        SYS r4, ULTRASONIC_CHANGE_POLL(206)
        JNZ r4, trigger
        SYS r5, LIGHT_CHANGE_POLL(211)
        JNZ r5, trigger
        SYS r6, MIC_RISE_POLL(216)
        JZ r6, idle
trigger:
        SYS r2, POLICE_SEQUENCE(201)
sequence_wait:
        WAIT 50
        SYS r7, SEQUENCE_STATUS(6)
        JNZ r7, sequence_wait
drain_ultrasonic:
        SYS r4, ULTRASONIC_CHANGE_POLL(206)
        JNZ r4, drain_ultrasonic
        JMP poll
idle:
        WAIT 250
        JMP poll
