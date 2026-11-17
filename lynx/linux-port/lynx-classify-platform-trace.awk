# Observe driver matching and platform setup; incomplete evidence is unknown.
function pid_of(line, value) {
    value=line;sub(/\[[^]]*\].*$/, "", value);sub(/^.*-/, "", value)
    gsub(/[[:space:]]/, "", value);return value
}
function retval(line, value) {
    if (!match(line,/ ret=-?[0-9]+([[:space:]]|$)/)) { bad++;return "unknown" }
    value=substr(line,RSTART+5,RLENGTH-5);gsub(/[[:space:]]/, "", value);return value+0
}
function enter(kind,line,pid,name,driver) {
    pid=pid_of(line);name=line
    if (pid !~ /^[0-9]+$/ || name !~ / name="[^"]*"/) { bad++;return }
    sub(/^.* name="/, "", name);sub(/".*$/, "", name)
    driver=""
    if (kind=="match") {
        if (line !~ / driver="[^"]*"/) { bad++;return }
        driver=line;sub(/^.* driver="/, "", driver);sub(/".*$/, "", driver)
    }
    depth[kind,pid]++;names[kind,pid,depth[kind,pid]]=name
    drivers[kind,pid,depth[kind,pid]]=driver
}
function leave(kind,line,pid,value,name,driver) {
    pid=pid_of(line);value=retval(line)
    if (depth[kind,pid]<1) { bad++;return }
    name=names[kind,pid,depth[kind,pid]];driver=drivers[kind,pid,depth[kind,pid]]
    delete names[kind,pid,depth[kind,pid]];delete drivers[kind,pid,depth[kind,pid]];depth[kind,pid]--
    if (index(name,"112b0000") && index(name,"ufs") && value!="unknown" && (kind!="match" || driver=="ufshcd-mtk")) {
        count[kind]++;last[kind]=value
    }
}
/health_pid:/ { value=retval($0);if (expected_pid ~ /^[0-9]+$/ && expected_pid>0 && value==expected_pid) health++ }
/match_enter:/ { enter("match",$0) }
/match_return:/ { leave("match",$0) }
/dma_enter:/ { enter("dma",$0) }
/dma_return:/ { leave("dma",$0) }
/platform_enter:/ { enter("platform",$0) }
/platform_return:/ { leave("platform",$0) }
END {
    for (key in depth) if (depth[key]>0) bad++
    if (!health || bad) code=1
    else if (count["match"] && last["match"]<=0) code=2
    else if (count["dma"] && last["dma"]!=0) code=3
    else if (count["platform"] && last["platform"]!=0) code=4
    else if (count["platform"] && last["platform"]==0) code=7
    else if (!count["match"]) code=5
    else code=6
    printf "%d %s %s %s %d\n",code,count["match"]?last["match"]:"unknown",count["dma"]?last["dma"]:"unknown",count["platform"]?last["platform"]:"unknown",health
}
