# Pair entry/return records per task and function, including nested calls.
function pid_of(line, value) {
    value=line; sub(/\[[^]]*\].*$/, "", value); sub(/^.*-/, "", value)
    gsub(/[[:space:]]/, "", value); return value
}
function retval(line, value) {
    if (!match(line, / ret=-?[0-9]+([[:space:]]|$)/)) { bad++; return "unknown" }
    value=substr(line,RSTART+5,RLENGTH-5); gsub(/[[:space:]]/, "", value)
    return value+0
}
function enter(kind, line, pid, name) {
    pid=pid_of(line); name=line
    if (pid !~ /^[0-9]+$/ || name !~ / name="[^"]*"/) { bad++; return }
    sub(/^.* name="/, "", name); sub(/".*$/, "", name)
    depth[kind,pid]++; names[kind,pid,depth[kind,pid]]=name
}
function leave(kind, line, pid, value, name) {
    pid=pid_of(line); value=retval(line)
    if (depth[kind,pid]<1) { bad++; return }
    name=names[kind,pid,depth[kind,pid]]
    delete names[kind,pid,depth[kind,pid]]; depth[kind,pid]--
    if (index(name,"112b0000") && index(name,"ufs") && value!="unknown") {
        count[kind]++; last[kind]=value
    }
}
/health_pid:/ {
    value=retval($0)
    if (expected_pid ~ /^[0-9]+$/ && expected_pid>0 && value==expected_pid) health++
}
/supplier_enter:/ { enter("supplier",$0) }
/supplier_return:/ { leave("supplier",$0) }
/pins_enter:/ { enter("pins",$0) }
/pins_return:/ { leave("pins",$0) }
/domain_enter:/ { enter("domain",$0) }
/domain_return:/ { leave("domain",$0) }
/mtk_probe_return:/ {
    value=retval($0); if (value!="unknown") { mtk_count++; mtk_last=value }
}
END {
    for (key in depth) if (depth[key]>0) bad++
    code=7
    if (!health || bad) code=1
    else if (registration_failed==1) code=3
    else if (mtk_count && mtk_last==0) code=2
    else if (count["supplier"] && last["supplier"]<0) code=4
    else if (count["pins"] && last["pins"]<0) code=5
    else if (count["domain"] && last["domain"]<0) code=6
    printf "%d %s %s %s %s\n",code,count["supplier"]?last["supplier"]:"unknown",count["pins"]?last["pins"]:"unknown",count["domain"]?last["domain"]:"unknown",mtk_count?mtk_last:"unknown"
}
