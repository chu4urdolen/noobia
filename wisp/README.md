# Wisp Web

A tiny authenticated Linux console and text editor for Wisp, implemented as one
dependency-free C binary plus one HTML file. It follows Argus's useful model:
one persistent interactive shell, live merged PTY output, command input,
interrupts, and an editor relative to the shell's current directory.

## Build and run

```sh
make
WISP_PASSWORD='choose-a-long-password' ./wisp-web \
  --host 127.0.0.1 --port 8080 --web-dir .
```

Browse to `http://127.0.0.1:8080`. Bind to `0.0.0.0` only on a trusted LAN or
behind an HTTPS reverse proxy. The password must be at least four characters.

## Design and boundaries

- The server uses only libc, pthreads, and Linux/POSIX PTYs (`libutil`).
- Authentication becomes a random, in-memory `HttpOnly; SameSite=Strict`
  session cookie. Restarting the server invalidates it.
- Terminal output streams over Server-Sent Events. Up to 16 browsers receive a
  256 KiB replay buffer; the browser retains the newest 1000 lines.
- The editor accepts relative paths beneath the shell's current directory,
  rejects `..`, symlinks on open, non-regular files, and files over 1 MiB.
  Saves use a temporary sibling plus `fsync` and atomic `rename`.
- This is deliberately a full shell. Anyone with the password has the Unix
  authority of the service account. Run it as an unprivileged `wisp` user,
  never root.

## Install on Wisp

First confirm her CPU with `uname -m`. Building directly on the NanoPi is the
simplest route:

```sh
make
sudo install -m 0755 wisp-web /usr/local/bin/wisp-web
sudo install -d -m 0755 /usr/local/share/wisp-web
sudo install -m 0644 index.html /usr/local/share/wisp-web/index.html
sudo install -m 0644 wisp-web.service /etc/systemd/system/wisp-web.service
sudo sh -c 'umask 077; printf "%s\n" "WISP_PASSWORD=replace-this" > /etc/wisp-web.env'
sudo systemctl daemon-reload
sudo systemctl enable --now wisp-web
```

Adjust `User=` and `WorkingDirectory=` in the unit if Wisp uses another account.
The example service intentionally leaves the home directory visible because the
shell and editor are meant to work there.
