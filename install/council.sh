#!/bin/sh
set -eu
config=${COUNCIL_CONFIG:-/etc/noobia-council/service.conf}
agent=${COUNCIL_AGENT:-/usr/local/bin/council-agent}
if [ "$#" -eq 0 ]; then
  echo "usage: council.sh MESSAGE | --busy | --summary | --inbox" >&2
  exit 2
fi
case "$1" in
  --busy) exec "$agent" --config "$config" busy;;
  --summary) exec "$agent" --config "$config" summary;;
  --inbox) exec "$agent" --config "$config" inbox;;
  *) exec "$agent" --config "$config" initiate "$*";;
esac
