# Rose voice

A small C front end for Rose's local voice pipeline:

1. Piper synthesizes speech with the `en_GB-cori-high` model.
2. SoX applies the original randomized lower pitch, chorus, and reverse-reverb effects.
3. PipeWire plays the processed WAV through the selected audio sink.
4. Temporary dry and processed WAV files are removed, including after failures.

## Build and use

```sh
make install-user
rose-say "Hello from Rose."
```

SoX, Piper, and `pw-play` must be available. The existing Piper installation and
voice are used by default. Configuration can be overridden with:

- `ROSE_PIPER_BIN`
- `ROSE_PIPER_VOICE`
- `ROSE_SOX_BIN`
- `ROSE_AUDIO_SINK` (defaults to PipeWire's default output)

The `rose-say` launcher keeps these paths and the local SoX runtime configuration
in one place. After the one-time user installation, speaking requires only the
command and quoted text.
