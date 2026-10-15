# Classify only our events; keep complete raw traces separately.
function pid_of(line, value) {
    value=line
    sub(/\[[^]]*\].*$/, "", value)
    sub(/^.*-/, "", value)
    gsub(/[[:space:]]/, "", value)
    return value
}
function retval(line, value) {
    if (!match(line, / ret=-?[0-9]+([[:space:]]|$)/)) { malformed++; return "unknown" }
    value=substr(line,RSTART+5,RLENGTH-5)
    gsub(/[[:space:]]/, "", value)
    return value+0
}
/domain_enter:/ {
    pid=pid_of($0)
    name=$0
    if (name !~ / name="[^"]*"/) { malformed++; next }
    sub(/^.* name="/, "", name)
    sub(/".*$/, "", name)
    depth[pid]++
    names[pid,depth[pid]]=name
}
/domain_return:/ {
    pid=pid_of($0)
    value=retval($0)
    if (depth[pid]<1) { unpaired++; next }
    name=names[pid,depth[pid]]
    delete names[pid,depth[pid]]
    depth[pid]--
    if (index(name,"112b0000") && index(name,"ufs") && value!="unknown") {
        domain_count++
        domain_last=value
    }
}
/init_return:/ {
    value=retval($0)
    if (value!="unknown") { ufs_count++; ufs_last=value }
}
END {
    code=8
    if (ufs_count) {
        if (ufs_last==-517) code=2
        else if (ufs_last==-22 || ufs_last==-19 || ufs_last==-2) code=4
        else if (ufs_last==-110 || ufs_last==-5) code=5
        else if (ufs_last==0) code=7
        else code=6
    } else if (domain_count && domain_last<0 && !unpaired && !malformed) code=3
    for (pid in depth) if (depth[pid]>0) unfinished+=depth[pid]
    printf "%d %d %s %d %s %d %d %d\n",code,ufs_count,ufs_count?ufs_last:"unknown",domain_count,domain_count?domain_last:"unknown",unpaired,malformed,unfinished
}
