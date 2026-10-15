# Values0..120 encode success or negative errno;121..127 are explicit sentinels.
function pid_of(line, value) {
    value=line;sub(/\[[^]]*\].*$/, "", value);sub(/^.*-/, "", value)
    gsub(/[[:space:]]/, "", value);return value
}
function retval(line,value) {
    if (!match(line,/ ret=-?[0-9]+([[:space:]]|$)/)) { bad++;return "unknown" }
    value=substr(line,RSTART+5,RLENGTH-5);gsub(/[[:space:]]/, "", value);return value+0
}
/health_pid:/ { value=retval($0);if (expected_pid ~ /^[0-9]+$/ && expected_pid>0 && value==expected_pid) health++ }
/platform_enter:/ {
    pid=pid_of($0);name=$0
    if (pid !~ /^[0-9]+$/ || name !~ / name="[^"]*"/) { bad++;next }
    sub(/^.* name="/, "", name);sub(/".*$/, "", name)
    depth[pid]++;names[pid,depth[pid]]=name
}
/platform_return:/ {
    pid=pid_of($0);value=retval($0)
    if (depth[pid]<1) { bad++;next }
    name=names[pid,depth[pid]];delete names[pid,depth[pid]];depth[pid]--
    if (expected_device!="" && name==expected_device && value!="unknown") { count++;last=value }
}
END {
    for (pid in depth) if (depth[pid]>0) bad++
    if (!health) code=125
    else if (bad) code=126
    else if (!count || expected_device=="") code=124
    else if (last==0) code=0
    else if (last<0 && last>=-120) code=-last
    else if (last==-517) code=121
    else if (last<0) code=122
    else code=123
    printf "%d %s %d %d\n",code,count?last:"unknown",count,health
}
