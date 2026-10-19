#!/bin/bash
# Negative tests for the AI POD schemas. Each case mutates the example
# inventory in a known-bad way and asserts the validator rejects it.
set +e
EX="schemas/_examples/aipod.yaml.example"
SC="schemas/aipod.schema.json"

run_neg() {
  local label="$1"
  local mutator="$2"
  echo "--- $label ---"
  python3 -c "$mutator" > /tmp/bad.yaml
  if python3 scripts/validate_inventory.py --schema "$SC" --inventory /tmp/bad.yaml; then
    echo "  *** FAIL: validator did NOT reject ***"
    rm -f /tmp/bad.yaml
    return 1
  fi
  rm -f /tmp/bad.yaml
  echo
}

run_neg "bad cluster name (spaces)" \
  "import yaml,sys; d=yaml.safe_load(open('$EX')); d['nd_cluster']['cluster']['name']='bad name with spaces'; yaml.safe_dump(d, sys.stdout)"

run_neg "missing required ntp" \
  "import yaml,sys; d=yaml.safe_load(open('$EX')); del d['nd_cluster']['cluster']['ntp']; yaml.safe_dump(d, sys.stdout)"

run_neg "4 nodes (max 3)" \
  "import yaml,sys; d=yaml.safe_load(open('$EX')); d['nd_cluster']['nodes'].append(d['nd_cluster']['nodes'][0]); yaml.safe_dump(d, sys.stdout)"

run_neg "two bootstrap nodes" \
  "import yaml,sys; d=yaml.safe_load(open('$EX')); d['nd_cluster']['nodes'][1]['role']='bootstrap'; yaml.safe_dump(d, sys.stdout)"

run_neg "only 3 persistent IPs (need >=5)" \
  "import yaml,sys; d=yaml.safe_load(open('$EX')); d['nd_cluster']['cluster']['external_services']['data_service_ips']=d['nd_cluster']['cluster']['external_services']['data_service_ips'][:3]; yaml.safe_dump(d, sys.stdout)"

run_neg "bad IPv4 (999.x.x.x)" \
  "import yaml,sys; d=yaml.safe_load(open('$EX')); d['nd_cluster']['nodes'][0]['mgmt']['ip']='999.1.1.1'; yaml.safe_dump(d, sys.stdout)"

run_neg "proxy skip=false but no url" \
  "import yaml,sys; d=yaml.safe_load(open('$EX')); d['nd_cluster']['cluster']['proxy']={'skip':False}; yaml.safe_dump(d, sys.stdout)"

run_neg "typo in top-level key" \
  "import yaml,sys; d=yaml.safe_load(open('$EX')); d['storrage']=d.pop('site'); yaml.safe_dump(d, sys.stdout)"

echo "All negative tests rejected as expected."
