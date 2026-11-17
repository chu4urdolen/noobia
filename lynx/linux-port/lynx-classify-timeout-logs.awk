# Match exact stock error messages; retain every matched line as raw context.
BEGIN { mask=0 }
{
    targeted=(expected_device!="" && index($0,expected_device))
    domain=(expected_domain!="" && index($0,expected_domain "(-110)"))
    if (domain && index($0,"Failed to power on mtcmos ")) mtcmos=1
    if (domain && index($0,"Failed to power on sram/bus ")) sram=1
    if (targeted && (index($0,"Controller enable failed") || index($0,"Host controller enable failed"))) host=1
    if (targeted && index($0,"link startup failed -110")) link=1
    if (targeted && index($0,"uic cmd ") && index($0,"completion timeout")) uic=1
    if ((targeted || domain) && (index($0,"-110") || index($0,"timeout"))) generic=1
}
END { print mtcmos+2*sram+4*host+8*link+16*uic+32*generic }
