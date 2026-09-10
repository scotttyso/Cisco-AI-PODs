# Test image for validating NVIDIA GPU metrics collection from an unprivileged
# OpenShift workload (restricted-v2 SCC, arbitrary UID, no CAP_SYS_ADMIN).
#
# Covers two independent paths gated by NVreg_RestrictProfilingToAdminUsers:
#   1. DCGM profiling fields (DCGM_FI_PROF_*), the dcgm-exporter path.
#   2. CUPTI kernel-level profiling via Nsight Compute, the ncu/nsys/torch path.
ARG CUDA_IMAGE=docker.io/nvidia/cuda
ARG CUDA_TAG=13.0.1-devel-ubuntu24.04
ARG DCGM_IMAGE=nvcr.io/nvidia/cloud-native/dcgm
ARG DCGM_TAG=4.6.1-1-ubuntu24.04

# Static cudart keeps the final image free of a CUDA runtime dependency.
FROM ${CUDA_IMAGE}:${CUDA_TAG} AS builder
COPY cuda_kernel.cu /tmp/cuda_kernel.cu
RUN nvcc -cudart static -o /tmp/cuda-load /tmp/cuda_kernel.cu

FROM ${DCGM_IMAGE}:${DCGM_TAG}

USER 0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl jq procps python3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /tmp/cuda-load /usr/local/bin/cuda-load
COPY --from=builder /opt/nvidia/nsight-compute /opt/nvidia/nsight-compute

COPY entrypoint.sh /usr/local/bin/gpu-metrics-test
COPY collect-metrics.py /usr/local/bin/collect-metrics.py

# OpenShift runs the container with a random UID that is always a member of
# GID 0, so every path the entrypoint writes to must be group-writable.
RUN mkdir -p /work \
    && chmod -R g=u /work /usr/local/bin/gpu-metrics-test /usr/local/bin/collect-metrics.py \
    && chmod 0755 /usr/local/bin/gpu-metrics-test /usr/local/bin/collect-metrics.py /usr/local/bin/cuda-load

# pydcgm/dcgm_fields ship with the base image but are not on the default path,
# and the directory is DCGM-major-version specific. Resolve it at build time so
# the image keeps working across base image bumps.
RUN set -eux; \
    bindings=$(dirname "$(find /usr/share /usr/local -name pydcgm.py -print -quit)"); \
    sitedir=$(python3 -c 'import site; print(site.getsitepackages()[0])'); \
    echo "${bindings}" > "${sitedir}/dcgm-bindings.pth"

# ncu lives in a versioned subdirectory; pin it to a stable path.
RUN set -eux; \
    ncu=$(find /opt/nvidia/nsight-compute -name ncu -type f -print -quit); \
    ln -s "${ncu}" /usr/local/bin/ncu

ENV HOME=/work \
    DCGM_HOSTENGINE_PORT=5555 \
    TEST_DURATION=120 \
    PROF_FIELD=1004 \
    RUN_CUPTI_TEST=1

WORKDIR /work
USER 1001

ENTRYPOINT ["/usr/local/bin/gpu-metrics-test"]
