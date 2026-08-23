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

If `~/.config/rose-tools/hue.conf` exists, `rose-say` also animates the configured
Hue light from the speech envelope. Set `ROSE_HUE_ENABLED=0` for audio only, or
set `ROSE_HUE_COLOR=red,green,blue` to change the default green light color.

Text is split at sentence-ending punctuation and processed through three ordered,
independent stages. Piper may generate later dry WAVs while SoX processes an
earlier sentence and PipeWire plays the sentence before that. Playback remains in
text order. Completion waits for both producer stages, darkens the Hue target,
releases the shared lock, and removes every temporary WAV.
