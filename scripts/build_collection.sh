#!/usr/bin/env bash
#
# Assemble a standard Ansible Collection tree from the subsystem-first repo.
#
# The repo keeps roles and playbooks under <NN>-<subsystem>/automation/, which
# is deliberate (one place per subsystem) but is NOT the layout ansible-galaxy
# expects. This script gathers those per-subsystem sources plus the Tier 3/4
# orchestration playbooks into build/collection/ansible_collections/cisco/aipod
# so that `cisco.aipod.*` FQCNs resolve (with the repo-root ansible.cfg).
#
# Two modes:
#   (default) DEV  — symlinks role dirs back to their in-repo location. This
#                    keeps {{ role_path }} pointing at the real
#                    <NN>/automation/roles/<role>, so the Python wedge
#                    (nd_python_root = {{ role_path }}/../..) finds scripts/.
#                    Run playbooks from the REPO by path; FQCN roles resolve
#                    via ansible.cfg collections_path. This is the path that
#                    actually works for local end-to-end runs.
#   --package      — COPIES everything (roles + co-located scripts + playbooks)
#                    for `ansible-galaxy collection build`. Produces a tarball
#                    but see OPEN ITEMS before trusting a packaged run.
#
# STATUS: UNTESTED here (ansible/ansible-galaxy not installed on this machine).
# Validate on an Ansible-equipped box.
#
# Usage:
#   scripts/build_collection.sh                 # DEV: symlink roles
#   scripts/build_collection.sh --package        # COPY + prepare for build
#   scripts/build_collection.sh --package --build # + ansible-galaxy build
#   scripts/build_collection.sh --package --install

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COLL_ROOT="${REPO_ROOT}/build/collection/ansible_collections/cisco/aipod"

MODE=dev
DO_BUILD=false
DO_INSTALL=false
for arg in "$@"; do
  case "$arg" in
    --package) MODE=package ;;
    --build)   DO_BUILD=true ;;
    --install) DO_BUILD=true; DO_INSTALL=true ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done
if { $DO_BUILD || $DO_INSTALL; } && [ "$MODE" != package ]; then
  echo "--build/--install require --package (symlinked dev tree is not packageable)" >&2
  exit 2
fi

echo "==> Mode: ${MODE}"
echo "==> Cleaning ${REPO_ROOT}/build/collection"
rm -rf "${REPO_ROOT}/build/collection"
mkdir -p \
  "${COLL_ROOT}/roles" \
  "${COLL_ROOT}/playbooks/domains" \
  "${COLL_ROOT}/plugins/filter"

cp "${REPO_ROOT}/galaxy.yml" "${COLL_ROOT}/galaxy.yml"
[ -f "${REPO_ROOT}/README.md" ] && cp "${REPO_ROOT}/README.md" "${COLL_ROOT}/README.md"

# Collection-native filters plus the shared Python they consume. Keeping the
# library under module_utils makes imports work both from the assembled dev
# tree and from an installed collection without relying on the repo root.
if [ -d "${REPO_ROOT}/plugins/filter" ]; then
  cp -R "${REPO_ROOT}/plugins/filter/." "${COLL_ROOT}/plugins/filter/"
fi
mkdir -p "${COLL_ROOT}/plugins/module_utils/shared"
cp -R "${REPO_ROOT}/shared/." "${COLL_ROOT}/plugins/module_utils/shared/"

# --- Tier 1: roles from each subsystem -------------------------------------
echo "==> Roles"
for sub in "${REPO_ROOT}"/[0-9][0-9]-*/; do
  roles_dir="${sub}automation/roles"
  [ -d "$roles_dir" ] || continue
  for role in "$roles_dir"/*/; do
    [ -d "$role" ] || continue
    name="$(basename "$role")"
    if [ "$MODE" = dev ]; then
      echo "    link role: ${name}  (from $(basename "$sub"))"
      ln -s "$role" "${COLL_ROOT}/roles/${name}"
    else
      echo "    copy role: ${name}  (from $(basename "$sub"))"
      cp -R "$role" "${COLL_ROOT}/roles/${name}"
      # Co-locate the subsystem Python so the wedge travels in the tarball.
      if [ -d "${sub}automation/scripts" ]; then
        mkdir -p "${COLL_ROOT}/roles/${name}/files/automation"
        cp -R "${sub}automation/scripts" "${COLL_ROOT}/roles/${name}/files/automation/scripts"
        # Site inventory is never bundled into the collection. Operators pass
        # inventories/<site>/inventory.yml at runtime; this also prevents local
        # OLD migration archives from entering a package.
      fi
    fi
  done
done

# --- Tier 2: subsystem playbooks -------------------------------------------
echo "==> Subsystem playbooks (Tier 2)"
for sub in "${REPO_ROOT}"/[0-9][0-9]-*/; do
  pb_dir="${sub}automation/playbooks"
  [ -d "$pb_dir" ] || continue
  for pb in "$pb_dir"/*.yml; do
    [ -f "$pb" ] || continue
    echo "    $(basename "$pb")"
    cp "$pb" "${COLL_ROOT}/playbooks/$(basename "$pb")"
  done
done

# --- Tier 3/4: orchestration playbooks -------------------------------------
echo "==> Orchestration playbooks (Tier 3/4)"
ORCH="${REPO_ROOT}/playbooks"
cp "${ORCH}/deploy_aipod.yml" "${COLL_ROOT}/playbooks/deploy_aipod.yml"
cp "${ORCH}"/domains/*.yml "${COLL_ROOT}/playbooks/domains/"

echo "==> Assembled at: ${COLL_ROOT}"

if $DO_BUILD; then
  echo "==> ansible-galaxy collection build"
  ( cd "${COLL_ROOT}" && ansible-galaxy collection build --force --output-path "${REPO_ROOT}/build" )
fi
if $DO_INSTALL; then
  TARBALL="$(ls -t "${REPO_ROOT}"/build/cisco-aipod-*.tar.gz | head -1)"
  echo "==> ansible-galaxy collection install ${TARBALL}"
  ansible-galaxy collection install "${TARBALL}" --force
fi

cat <<'NOTES'

------------------------------------------------------------------------------
RECOMMENDED DEV FLOW (works end-to-end in-repo):
  1. scripts/build_collection.sh          # symlinks roles into build/collection
  2. ansible-playbook 01-nd-cluster/automation/playbooks/01_nd_cluster.yml
     ansible-playbook playbooks/deploy_aipod.yml
  (Run from the repo root. ansible.cfg collections_path finds cisco.aipod
   in build/collection and pinned third-party collections in
   build/galaxy/<chapter-id>. That galaxy dir is not wiped here.
   Symlinked role_path keeps the Python wedge and relative import_playbook
   paths pointing at real repo files.)

OPEN ITEMS for the PACKAGED collection (--package), not needed for dev:
  1. WEDGE SCRIPT PATHS. In a copied/installed collection the scripts live at
     roles/<role>/files/automation/scripts, so nd_python_root would need to be
     {{ role_path }}/files/automation instead of {{ role_path }}/../..
  2. import_playbook PATHS. Tier 3 domain playbooks use ../../../.. hops that
     resolve in the repo but not in the flattened collection playbooks/ dir.
     Rewrite to cisco.aipod.<playbook> form, or ship only roles in the tarball
     and keep orchestration repo-only.
------------------------------------------------------------------------------
NOTES
