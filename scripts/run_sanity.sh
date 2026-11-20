#!/usr/bin/env bash
# Run the same ansible-test sanity checks as the "Run collection certification checks" workflow, locally.
#
#   scripts/run_sanity.sh [ansible-core-ref] [python] [extra ansible-test sanity arguments...]
#
# Examples:
#   scripts/run_sanity.sh                                    # stable-2.20 on Python 3.12, every test
#   scripts/run_sanity.sh stable-2.16 3.12 --test pep8       # one test on the older core
#
# It exports the committed files (git archive HEAD) into a scratch ansible_collections tree, so commit first.

set -euo pipefail

core="${1:-stable-2.20}"
python_version="${2:-3.12}"
shift $(( $# > 2 ? 2 : $# )) || true

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
namespace="$(awk -F': *' '$1=="namespace"{print $2}' "$repo_root/galaxy.yml")"
name="$(awk -F': *' '$1=="name"{print $2}' "$repo_root/galaxy.yml")"
work="${SANITY_WORKDIR:-/tmp/aipod-sanity}"
collection="$work/ansible_collections/$namespace/$name"
venv="$work/venv-$core"

rm -rf "$work/ansible_collections"
mkdir -p "$collection"
git -C "$repo_root" archive HEAD | tar -x -C "$collection"
git -C "$collection" init -q

if [[ ! -x "$venv/bin/ansible-test" ]]; then
    "python${python_version}" -m venv "$venv"
    "$venv/bin/pip" install -q "https://github.com/ansible/ansible/archive/${core}.tar.gz"
fi

cd "$collection"
"$venv/bin/ansible-test" sanity --python "$python_version" "$@"
