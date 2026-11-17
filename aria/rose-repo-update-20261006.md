# Rose repository update and speech test

Syra's `/noobia` repository was fast-forwarded from `152a5b0` to `cdf9038`.
The pre-existing untracked Council tree and voice contact book were preserved
under `/home/rose/.local/state/noobia-repairs/repo-update-20261006-210030/`.
The previous Git revision also has a backup branch. Rose's AGENTS.md and other
local directories were retained.

Public fetches now use HTTPS; the original SSH push URL is preserved. No commit
was published. Updated the voice Makefile's Council path from `../..` to
`../../council`, then rebuilt and installed the voice tools and restarted Rose's
voice worker. The same Makefile fix is present on Nexus. This path fix remains
an uncommitted local modification on both machines.

Rose's private voice-worker contacts now use Nexus `.106` and Argus's saved
`.105` without changing credentials.

Played: “Hello Noob. This is Rose speaking from Syra, with my lights following
my voice.” `rose-say` exited successfully in 10.33 seconds with Hue enabled and
the JBL configured as the default speaker. The two Piper stages ran on Aria
(996 ms and 1907 ms); SoX and envelope stages ran on Rose. No stage errors or
Hue animation errors were reported. The strip's original on/off, brightness,
and xy colour state was restored afterward through the Hue API.

Noob reported no visible lights in that first run. Added explicit Hue activation,
envelope-range, and accepted-update diagnostics, plus physical direct-pulse and
speech-with-state-sampling tests. Direct control was confirmed visually by Noob.
The next speech test logged 34 successful updates and sampled 15 distinct lit
brightness levels; Noob confirmed the spoken light animation worked. The reason
the first animation was not seen was not conclusively established.

The new test's restoration initially included an effect field that the strip
rejected. The tests do not change that field, so it is now left untouched while
on/off, brightness, and the original colour mode are restored. Direct pulse and
restoration checks passed. Test commands are `/noobia/aria/test-strip` and
`/noobia/aria/test-speech-lights`, available on Nexus and Syra.
