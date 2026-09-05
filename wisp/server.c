#define _GNU_SOURCE
#define _XOPEN_SOURCE 600

#include <arpa/inet.h>
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <netinet/in.h>
#include <poll.h>
#include <pthread.h>
#include <pty.h>
#include <signal.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#define REQ_MAX (2u * 1024u * 1024u)
#define FILE_MAX (1024u * 1024u)
#define HISTORY_MAX (256u * 1024u)
#define SSE_MAX 16

static int pty_fd = -1;
static pid_t shell_pid = -1;
static char session[65];
static const char *password;
static const char *web_dir;
static pthread_mutex_t pty_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t stream_lock = PTHREAD_MUTEX_INITIALIZER;
static int streams[SSE_MAX];
static unsigned char history[HISTORY_MAX];
static size_t history_len;

static void logmsg(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "wisp-web: ");
    vfprintf(stderr, fmt, ap);
    fputc('\n', stderr);
    va_end(ap);
}

static int write_all(int fd, const void *buf, size_t len) {
    const unsigned char *p = buf;
    while (len) {
        ssize_t n = write(fd, p, len);
        if (n < 0) {
            if (errno == EINTR) continue;
            return -1;
        }
        p += (size_t)n;
        len -= (size_t)n;
    }
    return 0;
}

static void reply(int fd, int code, const char *type, const char *extra,
                  const void *body, size_t len) {
    const char *reason = code == 200 ? "OK" : code == 204 ? "No Content" :
        code == 400 ? "Bad Request" : code == 401 ? "Unauthorized" :
        code == 404 ? "Not Found" : code == 409 ? "Conflict" :
        code == 413 ? "Payload Too Large" : "Internal Server Error";
    char head[1024];
    int n = snprintf(head, sizeof head,
        "HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %zu\r\n"
        "X-Content-Type-Options: nosniff\r\nCache-Control: no-store\r\n"
        "Connection: close\r\n%s\r\n",
        code, reason, type, len, extra ? extra : "");
    if (n > 0 && (size_t)n < sizeof head) {
        write_all(fd, head, (size_t)n);
        if (len) write_all(fd, body, len);
    }
}

static void json_error(int fd, int code, const char *message) {
    char body[512];
    int n = snprintf(body, sizeof body, "{\"ok\":false,\"error\":\"%s\"}\n", message);
    reply(fd, code, "application/json; charset=utf-8", NULL, body, (size_t)n);
}

static int random_hex(char *out, size_t bytes) {
    unsigned char raw[32];
    if (bytes > sizeof raw) return -1;
    int fd = open("/dev/urandom", O_RDONLY | O_CLOEXEC);
    if (fd < 0 || read(fd, raw, bytes) != (ssize_t)bytes) {
        if (fd >= 0) close(fd);
        return -1;
    }
    close(fd);
    for (size_t i = 0; i < bytes; i++) sprintf(out + i * 2, "%02x", raw[i]);
    out[bytes * 2] = 0;
    return 0;
}

static const char *header_value(const char *request, const char *name) {
    size_t nlen = strlen(name);
    const char *p = strstr(request, "\r\n") + 2;
    while (p && *p && strncmp(p, "\r\n", 2)) {
        const char *end = strstr(p, "\r\n");
        if (!end) return NULL;
        if ((size_t)(end - p) > nlen && !strncasecmp(p, name, nlen) && p[nlen] == ':') {
            p += nlen + 1;
            while (*p == ' ' || *p == '\t') p++;
            return p;
        }
        p = end + 2;
    }
    return NULL;
}

static bool authenticated(const char *req) {
    const char *p = header_value(req, "Cookie");
    if (!p) return false;
    const char *end = strstr(p, "\r\n");
    const char *needle = "wisp_session=";
    while ((p = strstr(p, needle)) && (!end || p < end)) {
        p += strlen(needle);
        if (!strncmp(p, session, strlen(session)) &&
            (p[strlen(session)] == ';' || p[strlen(session)] == '\r')) return true;
    }
    return false;
}

static char *json_string(const char *json, const char *key, size_t *out_len) {
    char needle[128];
    if (snprintf(needle, sizeof needle, "\"%s\"", key) >= (int)sizeof needle) return NULL;
    const char *p = strstr(json, needle);
    if (!p) return NULL;
    p += strlen(needle);
    while (isspace((unsigned char)*p)) p++;
    if (*p++ != ':') return NULL;
    while (isspace((unsigned char)*p)) p++;
    if (*p++ != '"') return NULL;
    size_t cap = strlen(p) + 1, len = 0;
    char *out = malloc(cap);
    if (!out) return NULL;
    while (*p && *p != '"') {
        unsigned char c = (unsigned char)*p++;
        if (c == '\\') {
            c = (unsigned char)*p++;
            if (!c) break;
            if (c == 'n') c = '\n'; else if (c == 'r') c = '\r';
            else if (c == 't') c = '\t';
            else if (c == 'b') c = '\b'; else if (c == 'f') c = '\f';
            else if (c == 'u') { /* ASCII subset; preserve non-ASCII via UTF-8 input. */
                unsigned v = 0;
                for (int i = 0; i < 4 && isxdigit((unsigned char)p[i]); i++) {
                    v = v * 16 + (isdigit((unsigned char)p[i]) ? p[i]-'0' : 10 + tolower((unsigned char)p[i])-'a');
                }
                p += 4;
                c = v < 128 ? (unsigned char)v : '?';
            }
        }
        out[len++] = (char)c;
    }
    if (*p != '"') { free(out); return NULL; }
    out[len] = 0;
    if (out_len) *out_len = len;
    return out;
}

static char *json_quote(const unsigned char *s, size_t len, size_t *result_len) {
    size_t cap = len * 6 + 3, n = 0;
    char *out = malloc(cap);
    if (!out) return NULL;
    out[n++] = '"';
    for (size_t i = 0; i < len; i++) {
        unsigned char c = s[i];
        if (c == '"' || c == '\\') { out[n++]='\\'; out[n++]=(char)c; }
        else if (c == '\n') { out[n++]='\\'; out[n++]='n'; }
        else if (c == '\r') { out[n++]='\\'; out[n++]='r'; }
        else if (c == '\t') { out[n++]='\\'; out[n++]='t'; }
        else if (c < 0x20) n += (size_t)sprintf(out+n, "\\u%04x", c);
        else out[n++] = (char)c;
    }
    out[n++] = '"'; out[n] = 0;
    if (result_len) *result_len = n;
    return out;
}

static int read_request(int fd, char **out, size_t *header_len, size_t *body_len) {
    size_t cap = 8192, len = 0, want = 0;
    char *buf = malloc(cap + 1);
    if (!buf) return -1;
    for (;;) {
        if (len == cap) {
            if (cap >= REQ_MAX) { free(buf); return -2; }
            cap *= 2; if (cap > REQ_MAX) cap = REQ_MAX;
            char *grown = realloc(buf, cap + 1);
            if (!grown) { free(buf); return -1; }
            buf = grown;
        }
        ssize_t n = read(fd, buf + len, cap - len);
        if (n <= 0) { if (n < 0 && errno == EINTR) continue; free(buf); return -1; }
        len += (size_t)n; buf[len] = 0;
        char *marker = strstr(buf, "\r\n\r\n");
        if (marker && !want) {
            *header_len = (size_t)(marker + 4 - buf);
            const char *cl = header_value(buf, "Content-Length");
            size_t content = cl ? strtoul(cl, NULL, 10) : 0;
            if (content > REQ_MAX - *header_len) { free(buf); return -2; }
            want = *header_len + content;
            *body_len = content;
        }
        if (want && len >= want) { buf[want] = 0; *out = buf; return 0; }
    }
}

static int shell_cwd(char out[PATH_MAX]) {
    char link[64];
    snprintf(link, sizeof link, "/proc/%ld/cwd", (long)shell_pid);
    ssize_t n = readlink(link, out, PATH_MAX - 1);
    if (n < 0) return -1;
    out[n] = 0;
    return 0;
}

static int safe_path(const char *name, char out[PATH_MAX]) {
    char cwd[PATH_MAX];
    if (!name || !*name || name[0] == '/' || shell_cwd(cwd) < 0) return -1;
    for (const char *p = name; *p;) {
        while (*p == '/') p++;
        const char *q = p; while (*q && *q != '/') q++;
        if ((q-p == 2 && p[0]=='.' && p[1]=='.') || q-p == 0) return -1;
        p = q;
    }
    if (snprintf(out, PATH_MAX, "%s/%s", cwd, name) >= PATH_MAX) return -1;
    return 0;
}

static void serve_file(int fd, const char *name, const char *type) {
    char path[PATH_MAX];
    if (snprintf(path, sizeof path, "%s/%s", web_dir, name) >= (int)sizeof path) {
        json_error(fd, 500, "web path too long"); return;
    }
    int f = open(path, O_RDONLY | O_CLOEXEC);
    if (f < 0) { json_error(fd, 404, "not found"); return; }
    struct stat st;
    if (fstat(f, &st) < 0 || st.st_size < 0 || st.st_size > 4*1024*1024) {
        close(f); json_error(fd, 500, "cannot read asset"); return;
    }
    char *data = malloc((size_t)st.st_size);
    if (!data || read(f, data, (size_t)st.st_size) != st.st_size) {
        close(f); free(data); json_error(fd, 500, "cannot read asset"); return;
    }
    close(f); reply(fd, 200, type, NULL, data, (size_t)st.st_size); free(data);
}

static char *url_decode(const char *src) {
    size_t len = strlen(src); char *out = malloc(len + 1), *d = out;
    if (!out) return NULL;
    while (*src) {
        if (*src == '%' && isxdigit((unsigned char)src[1]) && isxdigit((unsigned char)src[2])) {
            char h[3] = {src[1], src[2], 0}; *d++ = (char)strtol(h, NULL, 16); src += 3;
        } else { *d++ = *src == '+' ? ' ' : *src; src++; }
    }
    *d = 0; return out;
}

static void api_open(int fd, const char *target) {
    const char *q = strstr(target, "?path=");
    char *name = q ? url_decode(q + 6) : NULL;
    char path[PATH_MAX];
    if (!name || safe_path(name, path) < 0) { free(name); json_error(fd, 400, "invalid relative path"); return; }
    free(name);
    int f = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (f < 0) {
        if (errno == ENOENT) {
            char body[PATH_MAX + 64]; int n = snprintf(body, sizeof body, "{\"ok\":true,\"exists\":false,\"path\":\"%s\",\"content\":\"\"}\n", path);
            reply(fd, 200, "application/json; charset=utf-8", NULL, body, (size_t)n);
        } else json_error(fd, 400, "cannot open file");
        return;
    }
    struct stat st;
    if (fstat(f, &st) < 0 || !S_ISREG(st.st_mode)) { close(f); json_error(fd, 400, "not a regular file"); return; }
    if ((size_t)st.st_size > FILE_MAX) { close(f); json_error(fd, 413, "file exceeds 1 MiB"); return; }
    unsigned char *data = malloc((size_t)st.st_size + 1);
    if (!data || read(f, data, (size_t)st.st_size) != st.st_size) { close(f); free(data); json_error(fd, 500, "read failed"); return; }
    close(f);
    size_t qlen; char *quoted = json_quote(data, (size_t)st.st_size, &qlen); free(data);
    if (!quoted) { json_error(fd, 500, "out of memory"); return; }
    size_t cap = qlen + strlen(path) + 128; char *body = malloc(cap);
    int n = snprintf(body, cap, "{\"ok\":true,\"exists\":true,\"path\":\"%s\",\"bytes\":%ld,\"content\":%s}\n", path, (long)st.st_size, quoted);
    free(quoted); reply(fd, 200, "application/json; charset=utf-8", NULL, body, (size_t)n); free(body);
}

static void api_save(int fd, const char *body) {
    size_t content_len; char *name = json_string(body, "path", NULL);
    char *content = json_string(body, "content", &content_len), path[PATH_MAX];
    if (!name || !content || content_len > FILE_MAX || safe_path(name, path) < 0) {
        free(name); free(content); json_error(fd, content_len > FILE_MAX ? 413 : 400, "invalid path or content"); return;
    }
    free(name);
    char temp[PATH_MAX];
    if (snprintf(temp, sizeof temp, "%s.wisp-XXXXXX", path) >= (int)sizeof temp) {
        free(content); json_error(fd, 400, "path too long"); return;
    }
    int out = mkstemp(temp);
    if (out < 0) { free(content); json_error(fd, 400, "cannot create file (parent must exist)"); return; }
    int ok = write_all(out, content, content_len);
    if (fsync(out) < 0) ok = -1;
    close(out); free(content);
    if (ok < 0 || rename(temp, path) < 0) { unlink(temp); json_error(fd, 500, "atomic save failed"); return; }
    char response[PATH_MAX + 80]; int n = snprintf(response, sizeof response,
        "{\"ok\":true,\"path\":\"%s\",\"bytes\":%zu}\n", path, content_len);
    reply(fd, 200, "application/json; charset=utf-8", NULL, response, (size_t)n);
}

static const char b64tab[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
static char *base64(const unsigned char *in, size_t len, size_t *olen) {
    size_t n = 4 * ((len + 2) / 3); char *out = malloc(n + 1);
    if (!out) return NULL;
    for (size_t i=0,j=0; i<len;) {
        uint32_t a=i<len?in[i++]:0, b=i<len?in[i++]:0, c=i<len?in[i++]:0, v=(a<<16)|(b<<8)|c;
        out[j++]=b64tab[(v>>18)&63]; out[j++]=b64tab[(v>>12)&63];
        out[j++]=b64tab[(v>>6)&63]; out[j++]=b64tab[v&63];
    }
    if (len%3) { out[n-1]='='; if (len%3==1) out[n-2]='='; }
    out[n]=0; *olen=n; return out;
}

static int sse_send(int fd, const unsigned char *data, size_t len) {
    size_t b64len; char *b64 = base64(data, len, &b64len);
    if (!b64) return -1;
    char pre[64]; int n = snprintf(pre, sizeof pre, "event: output\ndata: ");
    int ok = write_all(fd, pre, (size_t)n) || write_all(fd, b64, b64len) || write_all(fd, "\n\n", 2);
    free(b64); return ok ? -1 : 0;
}

static void *pty_reader(void *unused) {
    (void)unused; unsigned char buf[4096];
    for (;;) {
        ssize_t n = read(pty_fd, buf, sizeof buf);
        if (n <= 0) break;
        pthread_mutex_lock(&stream_lock);
        size_t add = (size_t)n;
        if (history_len + add > HISTORY_MAX) {
            size_t drop = history_len + add - HISTORY_MAX;
            memmove(history, history + drop, history_len - drop);
            history_len -= drop;
        }
        memcpy(history + history_len, buf, add);
        history_len += add;
        for (int i=0;i<SSE_MAX;i++) if (streams[i]>=0 && sse_send(streams[i],buf,add)<0) { close(streams[i]); streams[i]=-1; }
        pthread_mutex_unlock(&stream_lock);
    }
    static const unsigned char closed[]="\r\n[wisp shell closed]\r\n";
    pthread_mutex_lock(&stream_lock);
    for (int i=0;i<SSE_MAX;i++) if (streams[i]>=0) { sse_send(streams[i],closed,sizeof(closed)-1); close(streams[i]); streams[i]=-1; }
    pthread_mutex_unlock(&stream_lock);
    return NULL;
}

static bool start_stream(int fd) {
    static const char head[] = "HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nCache-Control: no-store\r\nX-Accel-Buffering: no\r\nConnection: keep-alive\r\n\r\n";
    if (write_all(fd, head, sizeof head - 1) < 0) return false;
    pthread_mutex_lock(&stream_lock);
    int slot=-1; for(int i=0;i<SSE_MAX;i++) if(streams[i]<0){slot=i;break;}
    if(slot>=0) { streams[slot]=fd; if(history_len) sse_send(fd,history,history_len); }
    pthread_mutex_unlock(&stream_lock);
    if(slot<0) { close(fd); return false; }
    return true;
}

static void *client_thread(void *arg) {
    int fd = (int)(intptr_t)arg; char *req=NULL; size_t hlen=0, blen=0;
    struct timeval tv={.tv_sec=10}; setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&tv,sizeof tv);
    int rr=read_request(fd,&req,&hlen,&blen);
    if(rr<0){ if(rr==-2) json_error(fd,413,"request too large"); close(fd); return NULL; }
    char method[8], target[2048];
    if(sscanf(req,"%7s %2047s",method,target)!=2){json_error(fd,400,"malformed request");goto done;}
    char *body=req+hlen;
    if(!strcmp(method,"GET") && !strcmp(target,"/")){serve_file(fd,"index.html","text/html; charset=utf-8");goto done;}
    if(!strcmp(method,"POST") && !strcmp(target,"/api/login")){
        char *given=json_string(body,"password",NULL); bool ok=given && !strcmp(given,password); free(given);
        if(ok){char extra[256];snprintf(extra,sizeof extra,"Set-Cookie: wisp_session=%s; HttpOnly; SameSite=Strict; Path=/\r\n",session);const char yes[]="{\"ok\":true}\n";reply(fd,200,"application/json",extra,yes,sizeof yes-1);}
        else json_error(fd,401,"incorrect password");
        goto done;
    }
    if(!authenticated(req)){json_error(fd,401,"authentication required");goto done;}
    if(!strcmp(method,"GET") && !strcmp(target,"/events")){free(req);if(start_stream(fd))return NULL;return NULL;}
    if(!strcmp(method,"GET") && !strcmp(target,"/api/cwd")){
        char cwd[PATH_MAX],response[PATH_MAX+32]; if(shell_cwd(cwd)<0){json_error(fd,500,"shell unavailable");goto done;}
        int n=snprintf(response,sizeof response,"{\"cwd\":\"%s\"}\n",cwd);reply(fd,200,"application/json",NULL,response,(size_t)n);goto done;
    }
    if(!strcmp(method,"GET") && !strncmp(target,"/api/file?path=",15)){api_open(fd,target);goto done;}
    if(!strcmp(method,"PUT") && !strcmp(target,"/api/file")){api_save(fd,body);goto done;}
    if(!strcmp(method,"POST") && !strcmp(target,"/api/run")){
        size_t len; char *cmd=json_string(body,"cmd",&len); if(!cmd){json_error(fd,400,"cmd required");goto done;}
        pthread_mutex_lock(&pty_lock); int ok=write_all(pty_fd,cmd,len)||write_all(pty_fd,"\n",1);pthread_mutex_unlock(&pty_lock);free(cmd);
        if(ok)json_error(fd,500,"shell write failed");else{const char yes[]="{\"ok\":true}\n";reply(fd,200,"application/json",NULL,yes,sizeof yes-1);}goto done;
    }
    if(!strcmp(method,"POST") && !strcmp(target,"/api/signal")){
        char *sig=json_string(body,"signal",NULL);int signo=sig&&!strcmp(sig,"INT")?SIGINT:sig&&!strcmp(sig,"TERM")?SIGTERM:0;free(sig);
        if(!signo){json_error(fd,400,"signal must be INT or TERM");goto done;}
        pid_t pg=tcgetpgrp(pty_fd);if(pg<0)pg=shell_pid;int ok=kill(-pg,signo);if(ok)json_error(fd,500,"signal failed");else{const char yes[]="{\"ok\":true}\n";reply(fd,200,"application/json",NULL,yes,sizeof yes-1);}goto done;
    }
    json_error(fd,404,"not found");
done: free(req); close(fd); return NULL;
}

static void shutdown_handler(int sig) {
    (void)sig;
    if(shell_pid>0)kill(-shell_pid,SIGTERM);
    _exit(0);
}

int main(int argc,char **argv){
    int port=8080;const char *host="127.0.0.1";web_dir=".";
    for(int i=1;i<argc;i++){
        if(!strcmp(argv[i],"--host")&&i+1<argc)host=argv[++i];
        else if(!strcmp(argv[i],"--port")&&i+1<argc)port=atoi(argv[++i]);
        else if(!strcmp(argv[i],"--web-dir")&&i+1<argc)web_dir=argv[++i];
        else{fprintf(stderr,"usage: %s [--host ADDRESS] [--port PORT] [--web-dir DIRECTORY]\n",argv[0]);return 2;}
    }
    password=getenv("WISP_PASSWORD");
    if(!password||strlen(password)<4){fprintf(stderr,"WISP_PASSWORD must contain at least 4 characters\n");return 2;}
    if(random_hex(session,32)<0){perror("random session");return 1;}
    for(int i=0;i<SSE_MAX;i++)streams[i]=-1;
    signal(SIGPIPE,SIG_IGN);signal(SIGTERM,shutdown_handler);signal(SIGINT,shutdown_handler);
    struct winsize win={.ws_row=30,.ws_col=120};
    shell_pid=forkpty(&pty_fd,NULL,NULL,&win);
    if(shell_pid<0){perror("forkpty");return 1;}
    if(shell_pid==0){setenv("TERM","dumb",1);const char *shell=getenv("SHELL");if(!shell)shell="/bin/bash";execl(shell,shell,"-i",(char*)NULL);_exit(127);}
    pthread_t reader;pthread_create(&reader,NULL,pty_reader,NULL);pthread_detach(reader);
    int server=socket(AF_INET,SOCK_STREAM|SOCK_CLOEXEC,0),one=1;if(server<0){perror("socket");return 1;}setsockopt(server,SOL_SOCKET,SO_REUSEADDR,&one,sizeof one);
    struct sockaddr_in addr={.sin_family=AF_INET,.sin_port=htons((uint16_t)port)};
    if(inet_pton(AF_INET,host,&addr.sin_addr)!=1){fprintf(stderr,"invalid IPv4 address: %s\n",host);return 2;}
    if(bind(server,(struct sockaddr*)&addr,sizeof addr)<0||listen(server,32)<0){perror("listen");return 1;}
    logmsg("listening on http://%s:%d",host,port);
    for(;;){int fd=accept4(server,NULL,NULL,SOCK_CLOEXEC);if(fd<0){if(errno==EINTR)continue;perror("accept");break;}pthread_t t;if(pthread_create(&t,NULL,client_thread,(void*)(intptr_t)fd)==0)pthread_detach(t);else close(fd);}
    return 1;
}
