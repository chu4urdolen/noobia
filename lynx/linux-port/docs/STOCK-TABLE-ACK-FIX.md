# Stock metadata response parsing: require a valid acknowledgement

Upstream DAXML.read_partition_table calls send_command(noack=True), discards its
return value, then calls get_command_result unconditionally. send_command may
return an ERR string or False instead of True. In that case the subsequent read
can wait for a transfer the device never promised and produce xread: Wrong
length after a timeout. Thus our previous invalid-response result cannot identify
the initial device reply.

The preserved wrapper now checks and records that acknowledgement. Only True
permits reading the upload descriptor and table. ERR, False, an unexpected
descriptor or incomplete transfer terminates the probe without fallback. The
offline test injects rejection/missing acknowledgements and asserts that no
transfer read occurs after rejection. The unsigned stock payload is unchanged;
no authentication attempt, code patch or storage mutation is introduced.

No live outcome for this correction has yet been obtained. It should clarify
the actual result of one metadata request, not justify a blind flash.
