# Complementary context, gated externally on same-boot platform retval -110.
# A message cascade may set several bits; this is not a first-failure selector.
{
    targeted=(expected_device!="" && index($0,expected_device))
    domain=(expected_domain!="" && index($0,expected_domain "(-110"))
    if (targeted && index($0,"probe failed -110")) probe=1
    if (domain && index($0,"Failed to ")) power=1
    if (targeted && index($0,"Initialization failed")) init=1
    if (targeted && index($0,"variant ") && index($0,"init failed err -110")) variant=1
    if (targeted && (index($0,"regulator init failed -110") || (index($0,"va09") && index($0,"failed") && index($0,"-110")))) regulator=1
    if (targeted && (index($0,"clock parse failed -110") || (index($0,"clk") && index($0,"failed") && index($0,"-110")))) clock=1
}
END { print probe+2*power+4*init+8*variant+16*regulator+32*clock }
