"""Sample DCGM profiling fields and report whether any produced non-zero data.

Exit code 0 means every requested profiling field returned at least one valid,
non-zero sample - i.e. NVreg_RestrictProfilingToAdminUsers=0 took effect and an
unprivileged pod can read the same counters dcgm-exporter publishes.
"""

import argparse
import sys
import time

import pydcgm
import dcgm_fields
import dcgm_structs

# The DCGM_FI_PROF_* fields that dcgm-exporter scrapes for DCGM_FI_PROF_* metrics.
PROF_FIELDS = {
    dcgm_fields.DCGM_FI_PROF_GR_ENGINE_ACTIVE: "DCGM_FI_PROF_GR_ENGINE_ACTIVE",
    dcgm_fields.DCGM_FI_PROF_SM_ACTIVE: "DCGM_FI_PROF_SM_ACTIVE",
    dcgm_fields.DCGM_FI_PROF_SM_OCCUPANCY: "DCGM_FI_PROF_SM_OCCUPANCY",
    dcgm_fields.DCGM_FI_PROF_PIPE_TENSOR_ACTIVE: "DCGM_FI_PROF_PIPE_TENSOR_ACTIVE",
    dcgm_fields.DCGM_FI_PROF_DRAM_ACTIVE: "DCGM_FI_PROF_DRAM_ACTIVE",
    dcgm_fields.DCGM_FI_PROF_PCIE_TX_BYTES: "DCGM_FI_PROF_PCIE_TX_BYTES",
    dcgm_fields.DCGM_FI_PROF_PCIE_RX_BYTES: "DCGM_FI_PROF_PCIE_RX_BYTES",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="5555")
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--interval", type=int, default=5)
    args = parser.parse_args()

    handle = pydcgm.DcgmHandle(ipAddress=f"127.0.0.1:{args.port}")
    system = pydcgm.DcgmSystem(handle)
    gpu_ids = system.discovery.GetAllSupportedGpuIds()
    if not gpu_ids:
        print("  no DCGM-supported GPUs discovered", file=sys.stderr)
        return 1

    # DCGM 4.6 dropped the gpuIds kwarg; DCGM_GROUP_DEFAULT covers all GPUs.
    group = pydcgm.DcgmGroup(
        handle, groupName="prof-test", groupType=dcgm_structs.DCGM_GROUP_DEFAULT
    )
    field_group = pydcgm.DcgmFieldGroup(
        handle, name="prof-fields", fieldIds=list(PROF_FIELDS)
    )

    try:
        group.samples.WatchFields(
            field_group,
            updateFreq=int(args.interval * 1_000_000 / 2),
            maxKeepAge=3600.0,
            maxKeepSamples=0,
        )
    except dcgm_structs.DCGMError as err:
        print(f"  cannot watch profiling fields: {err}", file=sys.stderr)
        print("  this is the expected failure when profiling is admin-restricted")
        return 1

    seen_nonzero = {name: False for name in PROF_FIELDS.values()}

    for i in range(args.samples):
        time.sleep(args.interval)
        system.UpdateAllFields(True)
        values = group.samples.GetLatest(field_group).values
        print(f"  --- sample {i + 1}/{args.samples} ---")
        for gpu_id in gpu_ids:
            for field_id, name in PROF_FIELDS.items():
                entry = values[gpu_id][field_id][0]
                if entry.isBlank:
                    print(f"    gpu{gpu_id} {name:<32} <blank>")
                    continue
                print(f"    gpu{gpu_id} {name:<32} {entry.value}")
                if entry.value:
                    seen_nonzero[name] = True

    print("\n  --- summary ---")
    rc = 0
    for name, ok in seen_nonzero.items():
        print(f"    {'[PASS]' if ok else '[WARN]'} {name}")
        if not ok:
            rc = 1
    if rc:
        print("    fields reporting only blank/zero values are either unsupported")
        print("    on this GPU model or were not exercised by the load generator")
    return rc


if __name__ == "__main__":
    sys.exit(main())
