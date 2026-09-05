static char connector_token[65];
static time_t connector_seen;
static unsigned long connector_job_id;
static bool connector_job_waiting;
static bool connector_job_taken;
static char connector_prompt[32768];

static bool connector_auth_target(const char *target) {
    const char *p=strstr(target,"token=");
    return p && !strncmp(p+6,connector_token,64) && (p[70]==0 || p[70]=='&');
}
static bool connector_auth_body(const char *body) {
    char *t=json_string(body,"token",NULL); bool ok=t&&!strcmp(t,connector_token); free(t); return ok;
}
static void connector_status(int fd) {
    pthread_mutex_lock(&codex_lock); bool online=time(NULL)-connector_seen<8; bool running=codex_running; pthread_mutex_unlock(&codex_lock);
    char b[128]; int n=snprintf(b,sizeof b,"{\"ok\":true,\"connected\":%s,\"running\":%s}\n",online?"true":"false",running?"true":"false");
    reply(fd,200,"application/json",NULL,b,(size_t)n);
}
static void connector_download(int fd) {
    const char *base=getenv("WISP_PUBLIC_URL"); if(!base||!*base)base="http://192.168.100.8:8080";
    char *script=malloc(16384); if(!script){json_error(fd,500,"out of memory");return;}
    int n=snprintf(script,16384,
"@echo off\r\n"
"title Wisp Connector\r\n"
"echo Connecting this computer's Codex to Wisp...\r\n"
"powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command \"$b='%s';$t='%s'; Write-Host 'Wisp Connector is running. Keep this window open.' -ForegroundColor Green; while($true){try{$j=Invoke-RestMethod -Uri ($b+'/connector/poll?token='+$t) -TimeoutSec 12;if($j.job){Write-Host 'Codex is working...';$p=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($j.prompt));$o=($p | codex exec --json --skip-git-repo-check - 2>&1 | Out-String);$x=@{token=$t;id=[string]$j.id;output=$o}|ConvertTo-Json -Compress;Invoke-RestMethod -Method Post -Uri ($b+'/connector/result') -ContentType 'application/json' -Body $x | Out-Null;Write-Host 'Task finished.'}}catch{Write-Host ('Waiting for Wisp: '+$_.Exception.Message) -ForegroundColor DarkYellow};Start-Sleep 2}\"\r\n"
"echo The connector stopped. You may close this window.\r\npause\r\n",base,connector_token);
    const char *extra="Content-Disposition: attachment; filename=Start-Wisp-Connector.cmd\r\n";
    reply(fd,200,"application/octet-stream",extra,script,(size_t)n); free(script);
}
static void connector_poll(int fd,const char *target) {
    if(!connector_auth_target(target)){json_error(fd,401,"invalid connector token");return;}
    pthread_mutex_lock(&codex_lock); connector_seen=time(NULL);
    if(connector_job_waiting&&!connector_job_taken){connector_job_taken=true;size_t bl;char*b64=base64((unsigned char*)connector_prompt,strlen(connector_prompt),&bl);char *out=malloc(bl+128);int n=snprintf(out,bl+128,"{\"ok\":true,\"job\":true,\"id\":%lu,\"prompt\":\"%s\"}\n",connector_job_id,b64);free(b64);pthread_mutex_unlock(&codex_lock);reply(fd,200,"application/json",NULL,out,(size_t)n);free(out);return;}
    pthread_mutex_unlock(&codex_lock);const char*b="{\"ok\":true,\"job\":false}\n";reply(fd,200,"application/json",NULL,b,strlen(b));
}
static void connector_result(int fd,const char *body) {
    if(!connector_auth_body(body)){json_error(fd,401,"invalid connector token");return;}
    char *id=json_string(body,"id",NULL);size_t len;char*out=json_string(body,"output",&len);
    if(!id||!out||strtoul(id,NULL,10)!=connector_job_id){free(id);free(out);json_error(fd,409,"unknown job");return;}
    pthread_mutex_lock(&codex_lock);if(len>CODEX_OUTPUT_MAX)len=CODEX_OUTPUT_MAX;memcpy(codex_output,out,len);codex_output_len=len;codex_running=false;connector_job_waiting=false;connector_job_taken=false;pthread_mutex_unlock(&codex_lock);free(id);free(out);
    const char*y="{\"ok\":true}\n";reply(fd,200,"application/json",NULL,y,strlen(y));
}
static void codex_run(int fd,const char*body) {
    size_t n;char*p=json_string(body,"prompt",&n);if(!p||!n||n>=sizeof connector_prompt){free(p);json_error(fd,400,"enter a task first");return;}
    pthread_mutex_lock(&codex_lock);bool online=time(NULL)-connector_seen<8;if(!online||codex_running){pthread_mutex_unlock(&codex_lock);free(p);json_error(fd,409,!online?"Clover Connector is not running":"Codex is already running");return;}
    snprintf(connector_prompt,sizeof connector_prompt,"%s",p);connector_job_id++;connector_job_waiting=true;connector_job_taken=false;codex_running=true;codex_output_len=0;pthread_mutex_unlock(&codex_lock);free(p);
    const char*y="{\"ok\":true}\n";reply(fd,200,"application/json",NULL,y,strlen(y));
}
static void codex_result(int fd){pthread_mutex_lock(&codex_lock);size_t ql;char*q=json_quote(codex_output,codex_output_len,&ql);bool run=codex_running;pthread_mutex_unlock(&codex_lock);size_t cap=ql+80;char*b=malloc(cap);int n=snprintf(b,cap,"{\"ok\":true,\"running\":%s,\"output\":%s}\n",run?"true":"false",q);free(q);reply(fd,200,"application/json",NULL,b,(size_t)n);free(b);}
static void codex_stop(int fd){pthread_mutex_lock(&codex_lock);codex_running=false;connector_job_waiting=false;connector_job_taken=false;pthread_mutex_unlock(&codex_lock);const char*y="{\"ok\":true}\n";reply(fd,200,"application/json",NULL,y,strlen(y));}
static void connector_reset(int fd){pthread_mutex_lock(&codex_lock);random_hex(connector_token,32);connector_seen=0;codex_running=false;connector_job_waiting=false;connector_job_taken=false;pthread_mutex_unlock(&codex_lock);const char*y="{\"ok\":true}\n";reply(fd,200,"application/json",NULL,y,strlen(y));}
