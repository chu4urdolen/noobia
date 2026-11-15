# Portable Noob VM programs

These programs depend only on common syscall IDs:

- `arithmetic.hex`: computes an integer expression and halts.
- `time_now.hex`: reads common monotonic time.
- `time_reset.hex`: resets the logical monotonic epoch.

Board-specific programs belong to that Noob's directory. A VM can define a
sequence by loading registers with slot, interval, function ID, bit count, and
a packed bit pattern, then calling syscall 3. It starts the configured channels
with syscall 4.
