#!/bin/sh
set -eu

usage() {
  echo "usage: sudo $0 --config FILE --contacts FILE --bridge-key FILE --web-key FILE --web-password FILE" >&2
  exit 2
}

config= contacts= bridge_key= web_key= web_password=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --config) config=$2; shift 2 ;;
    --contacts) contacts=$2; shift 2 ;;
    --bridge-key) bridge_key=$2; shift 2 ;;
    --web-key) web_key=$2; shift 2 ;;
    --web-password) web_password=$2; shift 2 ;;
    *) usage ;;
  esac
done

[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }
[ -s "$config" ] && [ -s "$contacts" ] && [ -s "$bridge_key" ] &&
[ -s "$web_key" ] && [ -s "$web_password" ] || usage

setting() {
  awk -F= -v wanted="$1" '
    $0 !~ /^[[:space:]]*#/ && $1 == wanted {
      sub(/^[^=]*=/, ""); gsub(/^[[:space:]]+|[[:space:]]+$/, ""); print; exit
    }' "$config"
}

os_user=$(setting os_user)
name=$(setting name)
desired_ip=$(setting desired_ip)
mac=$(setting mac)
[ -n "$os_user" ] && [ -n "$name" ] || { echo "config requires os_user and name" >&2; exit 2; }
id "$os_user" >/dev/null 2>&1 || { echo "unknown os_user: $os_user" >&2; exit 2; }

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
cmake -S "$script_dir" -B "$build_dir" -DCMAKE_BUILD_TYPE=Release
cmake --build "$build_dir" --parallel 2
ctest --test-dir "$build_dir" --output-on-failure

for program in noobia-council councilctl council-agent council-live council-send-file council-web council-codex-bridge; do
  install -m 0755 "$build_dir/$program" "/usr/local/bin/$program"
done
install -m 0755 "$script_dir/install/council.sh" /usr/local/bin/council.sh

getent group noobia-council >/dev/null || groupadd --system noobia-council
id noobia-council >/dev/null 2>&1 ||
  useradd --system --gid noobia-council --home-dir /var/lib/noobia-council --shell /usr/sbin/nologin noobia-council
usermod -aG noobia-council "$os_user"
install -d -m 0750 -o noobia-council -g noobia-council \
  /etc/noobia-council /var/lib/noobia-council /var/lib/noobia-council/files
install -d -m 0750 -o "$os_user" -g "$os_user" /noobia/council-agent-state
install -m 0640 -o noobia-council -g noobia-council "$config" /etc/noobia-council/service.conf
install -m 0640 -o noobia-council -g noobia-council "$contacts" /etc/noobia-council/contacts.json
install -m 0640 -o "$os_user" -g noobia-council "$bridge_key" /etc/noobia-council/bridge.key
install -m 0640 -o noobia-council -g noobia-council "$web_key" /etc/noobia-council/web-council.key
install -m 0640 -o noobia-council -g noobia-council "$web_password" /etc/noobia-council/web-password

install -m 0644 "$script_dir/install/noobia-council.service" /etc/systemd/system/noobia-council.service
install -m 0644 "$script_dir/install/noobia-council-web.service" /etc/systemd/system/noobia-council-web.service
install -m 0644 "$script_dir/install/noobia-council-codex-bridge@.service" /etc/systemd/system/noobia-council-codex-bridge@.service

if [ -n "$desired_ip" ] || [ -n "$mac" ]; then
  [ -n "$desired_ip" ] && [ -n "$mac" ] || { echo "desired_ip and mac must both be configured" >&2; exit 2; }
  printf 'name=%s\nmac=%s\nip=%s\n' "$name" "$mac" "$desired_ip" > /etc/noobia-council/dhcp-reservation.txt
  chmod 0600 /etc/noobia-council/dhcp-reservation.txt
fi

systemctl daemon-reload
systemctl enable --now noobia-council.service
systemctl enable --now "noobia-council-codex-bridge@$os_user.service"
systemctl enable --now noobia-council-web.service
systemctl --no-pager --full status noobia-council.service \
  "noobia-council-codex-bridge@$os_user.service" noobia-council-web.service
