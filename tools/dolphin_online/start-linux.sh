#!/bin/sh
set -eu
companion_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 -c 'import sys, struct; sys.exit(0 if sys.version_info >= (3, 10) and struct.calcsize("P") == 8 else 1)' || {
    printf '%s\n' '64-bit Python 3.10 or newer is required.' >&2
    exit 1
}
exec python3 "$companion_dir/bridge.py" "$@"
