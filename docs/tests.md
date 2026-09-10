# OpenShift Cluster Testing

This page indexes standalone validation tests for the OpenShift cluster,
kept separate from the main Ansible deployment automation. Each test lives
in its own folder under [tests/](../tests/) with a dedicated `README.md`
covering prerequisites, usage, and how to interpret results.

Use these after deployment (or after any operator/driver configuration
change) to confirm the cluster behaves as expected before handing it to
workload teams.

## Available Tests

| Test | Validates | Location |
|---|---|---|
| NVIDIA GPU metrics (non-admin) | Non-admin/non-root workloads can collect NVIDIA GPU profiling metrics (DCGM `DCGM_FI_PROF_*` and CUPTI/Nsight Compute counters) after setting `NVreg_RestrictProfilingToAdminUsers=0` via the GPU Operator's `kernelModuleConfig` | [tests/nvidia-metrics-non-admin/](../tests/nvidia-metrics-non-admin/) |

## Planned Tests

The following are expected to be added over time. Each should follow the
same pattern: a self-contained folder with its own `README.md`, an
orchestration script or playbook, and no dependency on cluster-admin
privileges unless the test specifically requires them.

- **Backend networking** — RDMA/RoCE connectivity and bandwidth between GPU
  nodes over the Mellanox/ConnectX fabric (NVIDIA Network Operator).
- **GPU performance** — multi-GPU/multi-node throughput benchmarks (NCCL
  all-reduce, GEMM) to validate expected performance versus the hardware
  support matrix.

## Adding a New Test

1. Create a new folder under `tests/<test-name>/`.
2. Include a `README.md` describing what it validates, prerequisites, and
   usage — model it after
   [tests/nvidia-metrics-non-admin/README.md](../tests/nvidia-metrics-non-admin/README.md).
3. Prefer a single entry-point script (Python or shell) that handles setup,
   execution, and cleanup, rather than requiring users to run a long
   sequence of manual `oc` commands.
4. Add a row to the [Available Tests](#available-tests) table above.

## Related Documentation

- [guide_troubleshooting.md](guide_troubleshooting.md) — cross-component
  triage; see the Testing and Validation section for when to reach for
  these tests versus manual diagnosis.
- [openshift.md](openshift.md) — OpenShift deployment guide.
