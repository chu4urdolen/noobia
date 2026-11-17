# Direct metadata probe: connection fix

Session `1791593136720769367` exited with the upstream message
`Please disconnect, start mtkclient and reconnect.` It did not perform a fresh
handshake, upload a loader or request the partition table. The exit code was
zero but is not a successful diagnostic result.

Upstream DaHandler.connect could see an already enumerated interface and skip
preloader initialization when no cached .state exists. Our isolated fresh
sessions deliberately have no .state. The preserved wrapper now explicitly
requires a fresh preloader handshake and rejects prior/reinitialized sessions.
An offline test confirms initialization is called, the device is identified,
and a second call cannot reuse the old session. Write/erase guards and the
unchanged stock-payload checks still pass.

The user's Orange State observation is consistent with the existing boot loop,
not a newly flashed image. No storage operation occurred in this attempt.
