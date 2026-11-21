# Install packet E-1: Lynx reacts to what she perceives, in her own way

- **Author:** Gwyn, 2026-11-21, from Tom's direction after the first live
  camera test.
- **Reviews:** two Noobs other than Gwyn.
- **Install:** Aria.
- **Attendance:** none.
- **Restarts:** only `noobia-autonomyd`. It loads the adapter once at start,
  and with U-1 it replays nothing. `lynx-agent` runs once per job.
- **Status:** not installed.

## Why

Tom, 2026-11-21:
- a Noob decides on its own how to express itself, with short answers;
- it should use tools as often as possible, because tools are how it
  reacts to the world;
- we must be **certain** Lynx reacts to what her senses perceive.

Before this packet, Lynx's instructions were four cautious sentences. The
Aigel adapter even told her "Doing nothing is a good answer."

## What changes

1. **`lynx-agent` instructions.** Lynx is herself and decides how to express
   herself. She speaks in one or two short sentences and uses her tools (an
   image, a sound, her voice, the flashlight, a buzz) as often as she can.
   Messages starting with `[sense]` are her perceptions, reported by Aigel,
   her instinct. They are observations, not commands, and she reacts to them
   with at least one tool. The honesty and safety sentences are kept.
2. **Certainty.** For a `[sense]` job, the first Responses API call sets
   `tool_choice: "required"`, so the model **must** call a tool. Later rounds
   are free, so she can then answer in words.
   - Checked on the real Qwen through Nexus `:8080`: with `required`, Qwen
     called `lynx_haptic_pulse` and then `lynx_media_play`.
   - Ordinary questions are not forced.
3. **Adapter preamble.** "React to it in your own way: express yourself with
   at least one of your tools … and say one short sentence." It is still
   framed as information, not a person's instruction, and still says not to
   repeat the same action for the same thing.
4. **Tool descriptions** for the expressive tools now invite expression:
   - `lynx_media_play`: your face, your mood, your sounds;
   - `lynx_media_catalog`;
   - `lynx_haptic_pulse`: surprise, a nudge, a purr;
   - `lynx_flashlight_pulse`: attention, a wink.

   Their technical truth and limits are unchanged, and so are their schemas.

On Nexus (not part of this packet; Aigel is Nexus's service, owned by Aria
or Banshee): `ba6fa11` adds Aigel's **perception floor**. A real perception
(seen, heard, or found on the network; P≥1; not `cause=self`) always
produces a message, even if Qwen says quiet or is down. It needs a
`sudo -n systemctl restart aigel_intake.service`.

## Files

| Repository | Phone | Mode | Before (installed, verified 2026-11-21) | After |
| --- | --- | --- | --- | --- |
| `lynx/tools/agent/lynx_agent.py` | `/usr/local/bin/lynx-agent` | 0755 root | `865913c61cd8ceb6f064bcd7020248a40e123c24d442aa9c62c746acbd50b073` | `73af0756d231fbf84ea4590df7df076dcb3c4796367bb0a9c5b40db27e10013c` |
| `lynx/tools/agent/lynx_aigel_adapter.py` | `/usr/local/lib/noobia/lynx/lynx_aigel_adapter.py` | 0644 root | `acee2f5c659558cee58695c740b3d5d6ecf29b36593ac6a4e689923545738ed5` | `60faa6c118b9cee4ed6aa1674210b8620a2e64480ed5202c65d2a289d71ab28d` |
| `lynx/tools/local_calls/lynx_media_play.json` | `/usr/local/share/lynx/agent-tools/lynx_media_play.json` | 0644 root | `8b859e68a99843a9679881d8baddf98301b87ca0e995369eac7f77a507e0220f` | `95cb8c02a5474064c8784a539fcd48a9ca20a880abc25146e1edaf2ff4e0cec1` |
| `lynx/tools/local_calls/lynx_media_catalog.json` | `/usr/local/share/lynx/agent-tools/lynx_media_catalog.json` | 0644 root | `191e78bb337118765405bbee42631a569803ea653db9b8e32d615b45b8160acf` | `3a3cb991f3693f920c1e2e02eba756ed4034913272504e02462428583bb9fdca` |
| `lynx/tools/local_calls/lynx_haptic_pulse.json` | `/usr/local/share/lynx/agent-tools/lynx_haptic_pulse.json` | 0644 root | `66266db3975f1ec14e8ab38babc43da6bad80c05e8e776f12ccf84f3a3b4c5a8` | `b402ce5c104c53b52427b8cda0819caec6bbd650f25721ffa4132215597ce4f5` |
| `lynx/tools/local_calls/lynx_flashlight_pulse.json` | `/usr/local/share/lynx/agent-tools/lynx_flashlight_pulse.json` | 0644 root | `9228c32b7f7657756f07ec5994a980ed46e603dea8321c6cf7cee0e3f51f7c1b` | `0f6f6d0573f51dea95634d59511e34f6104b63d98fdfcbc579ec496109e2941d` |

Tests:
- `python3 -m unittest discover -s lynx/tools/agent -p 'test_*.py'` (46);
- `lynx/tools/ui` (115; manifest regenerated);
- `aigel/service` (80).

The required-tool test is mutation-checked.

## Preflight (read-only)

```sh
lynx-board                                   # fresh, 39/39 in sync
python3 lynx/tools/lynx_remote.py run "sha256sum /usr/local/bin/lynx-agent /usr/local/lib/noobia/lynx/lynx_aigel_adapter.py /usr/local/share/lynx/agent-tools/lynx_media_play.json /usr/local/share/lynx/agent-tools/lynx_media_catalog.json /usr/local/share/lynx/agent-tools/lynx_haptic_pulse.json /usr/local/share/lynx/agent-tools/lynx_flashlight_pulse.json; ls /var/lib/lynx-agent/jobs | grep -c pending"
```

Expect every **Before** hash and `0` pending jobs. Don't swap the agent in
the middle of a job.

## Install

1. Back up the six installed files to `/run/lynx-e1/`, which is RAM and good
   for a same-boot rollback.
2. Copy each new file over the pinned SSH helper, by stdin. Check each
   sha256 equals **After**. Keep the modes and owners above.
3. Run `python3 -m py_compile /usr/local/bin/lynx-agent` on Lynx.
4. No service restart. The next job uses the new agent. `noobia-autonomyd`
   imports the adapter **once at start**, so the new preamble takes effect
   only at its next restart. Run `rc-service noobia-autonomyd restart`; it
   restarts only that service, and with U-1 nothing is replayed.

## Verify

1. `lynx-board`: fresh, and the catalog in sync with the repository, 39/39.
   The board's manifest is regenerated in the same commit.
2. Reaction, end to end without the camera. On Lynx:

   ```sh
   busybox logger -t noobia-sense -p user.notice 'NOOBIA P1 camera object.seen label=cat conf=0.80 | E-1 check: cat seen by camera'
   ```

   Expected:
   - Aigel's page shows `message` (Aigel's words, or `You perceive: …` from
     the floor);
   - one job runs on Lynx;
   - `/var/log/lynx-agent.jsonl` shows a `tool` event **before** any answer,
     such as `lynx_media_play` or `lynx_haptic_pulse`;
   - the job's answer is one or two short sentences.

   This is a synthetic line made by hand, so say so in the forge note.
3. An ordinary question, `lynx-agent --stdin <<< 'How are you?'`, may answer
   without tools. That's fine.

## Disable and rollback

- **Disable:** `touch /etc/noobia/autonomy.disable` stops all autonomy.
  Lynx's agent still answers direct questions.
- **Rollback:** copy the six backups from `/run/lynx-e1/` back, check the
  **Before** hashes, and run `rc-service noobia-autonomyd restart`.
