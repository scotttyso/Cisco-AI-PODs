#!/usr/bin/env bash
set -uo pipefail

DURATION="${TEST_DURATION:-120}"
PORT="${DCGM_HOSTENGINE_PORT:-5555}"
FIELD="${PROF_FIELD:-1004}"
RC=0

section() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail()    { printf '  [FAIL] %s\n' "$1"; RC=1; }
pass()    { printf '  [PASS] %s\n' "$1"; }

section "Runtime identity"
echo "  uid=$(id -u) gid=$(id -g) groups=$(id -G)"
echo "  capabilities: $(grep -E '^Cap(Eff|Prm)' /proc/self/status | tr '\n' ' ')"

section "Driver profiling restriction"
if [[ -r /proc/driver/nvidia/params ]]; then
  # NVreg_RestrictProfilingToAdminUsers is exposed at runtime as RmProfilingAdminOnly.
  RESTRICT=$(awk -F': ' '/RmProfilingAdminOnly|RestrictProfilingToAdminUsers/ {print $2; exit}' /proc/driver/nvidia/params)
  if [[ -z "${RESTRICT}" ]]; then
    echo "  RmProfilingAdminOnly not listed in /proc/driver/nvidia/params"
    echo "  (informational only - the DCGM and CUPTI checks below are definitive)"
  else
    echo "  RmProfilingAdminOnly=${RESTRICT}"
    if [[ "${RESTRICT}" == "0" ]]; then
      pass "profiling counters are available to non-admin users"
    else
      fail "profiling is admin-restricted; DCGM_FI_PROF_* will be missing"
    fi
  fi
else
  echo "  /proc/driver/nvidia/params not mounted into the container (informational only)"
fi

section "Visible GPUs"
if nvidia-smi -L; then
  pass "nvidia-smi enumerated the injected devices"
else
  fail "nvidia-smi failed - check runtimeClassName and nvidia.com/gpu limit"
fi

section "Starting embedded nv-hostengine on 127.0.0.1:${PORT}"
# -n keeps it in the foreground so the backgrounded PID is the real process.
nv-hostengine -n -p "${PORT}" -b 127.0.0.1 >/work/hostengine.log 2>&1 &
HOSTENGINE_PID=$!
trap 'kill "${HOSTENGINE_PID}" 2>/dev/null' EXIT

for _ in $(seq 1 20); do
  dcgmi discovery --host "127.0.0.1:${PORT}" -l >/dev/null 2>&1 && break
  sleep 1
done

if dcgmi discovery --host "127.0.0.1:${PORT}" -l; then
  pass "hostengine reachable"
else
  fail "hostengine did not start"
  cat /work/hostengine.log
  exit 1
fi

section "Generating GPU load (dcgmproftester field ${FIELD}, ${DURATION}s)"
# dcgmproftester is CUDA-major-version specific and must match the installed driver.
CUDA_MAJOR=$(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: *\([0-9]\+\).*/\1/p' | head -1)
PROFTESTER=""
for cand in "dcgmproftester${CUDA_MAJOR}" dcgmproftester13 dcgmproftester12 dcgmproftester; do
  if command -v "${cand}" >/dev/null 2>&1; then
    PROFTESTER=$(command -v "${cand}")
    break
  fi
done
echo "  driver CUDA major=${CUDA_MAJOR:-unknown}, using ${PROFTESTER:-none}"

if [[ -n "${PROFTESTER}" ]]; then
  "${PROFTESTER}" --no-dcgm-validation -t "${FIELD}" -d "${DURATION}" &
  LOAD_PID=$!
else
  fail "no usable dcgmproftester binary found in image"
  LOAD_PID=""
fi

section "Sampling profiling fields"
python3 /usr/local/bin/collect-metrics.py --port "${PORT}" --samples 10 --interval 5 || RC=1

[[ -n "${LOAD_PID}" ]] && wait "${LOAD_PID}" 2>/dev/null

if [[ "${RUN_CUPTI_TEST:-1}" == "1" ]]; then
  section "CUPTI kernel profiling (Nsight Compute) as non-root"
  NCU_OUT=$(ncu --target-processes all \
                --metrics smsp__cycles_active.sum,sm__throughput.avg.pct_of_peak_sustained_elapsed \
                /usr/local/bin/cuda-load 2>&1)
  echo "${NCU_OUT}"

  # ERR_NVGPUCTRPERM is the driver's explicit "profiling is admin-only" refusal.
  if grep -q 'ERR_NVGPUCTRPERM' <<<"${NCU_OUT}"; then
    fail "CUPTI counters denied - NVreg_RestrictProfilingToAdminUsers is still 1"
  elif grep -q 'smsp__cycles_active.sum' <<<"${NCU_OUT}"; then
    pass "unprivileged CUPTI kernel profiling works"
  else
    fail "ncu did not report the requested metrics; see output above"
  fi
fi

section "Result"
[[ ${RC} -eq 0 ]] && echo "  ALL CHECKS PASSED" || echo "  ONE OR MORE CHECKS FAILED"
exit "${RC}"
