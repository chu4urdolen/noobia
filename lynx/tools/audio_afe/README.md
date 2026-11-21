# Lynx Audio AFE Preflight (D23)

Offline preflight gate and hardware dependency map for the OnePlus Nord 3
audio front end: AFE PCM controller (`mt6983-afe-pcm@1e100000`), SCP DSP
offload (`snd_scp_ultra`), and the sound machine node (`sound` -> `&afe`).

- `lynx_audio_afe_preflight.py` — spec audit + double-gated read-only live collector
- `fixtures/` — hermetic fixtures: sound-ready, unbound, partial, stream-active, missing-dt
- `test_lynx_audio_afe_preflight.py` — hermetic unit tests

See `lynx/linux-port/docs/LYNX-AUDIO-AFE-PREFLIGHT-20261121.md` for the
full hardware map and safety boundary.
