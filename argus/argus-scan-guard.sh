#!/bin/bash
/home/todor/argus/argus-scans.sh &
LOGGER_PID=$!

/home/todor/argus/argus-scans-parser.py &
GUARD_PID=$!

wait -n $LOGGER_PID $GUARD_PID
