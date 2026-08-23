# Resilience behavior

Arbiter priorities are numeric and lower values win: Aria is 10, Argus is 20,
and Clover is reserved as 30. An initiator tries the next arbiter only when the
higher-priority endpoint is unreachable. A `BUSY` response is authoritative and
stops failover.

Each accepted message refreshes a persisted 300-second activity lease. Successful
initiators mirror that timestamp locally so a backup arbiter also refuses a new
conversation during a primary outage. Lease acquisition is protected by the
service mutex; an eight-way contention test accepted exactly one initiation.

Presence checks authenticate each AI endpoint. If the current speaker disappears,
a status probe records an `offline-grant` event and assigns the next online AI.
Unknown and offline addressed targets fail explicitly and are not misrouted.

Verified fault cases:

- invalid authentication;
- unknown and offline targets;
- participant loss after a speaking grant;
- primary-arbiter loss and backup failover;
- busy state across restart;
- startup memory regeneration without altering full logs;
- eight simultaneous initiations;
- out-of-turn messages and files.
