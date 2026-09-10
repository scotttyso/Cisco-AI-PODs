// Minimal CUDA workload for Nsight Compute to profile. Runs a fixed, small
// number of kernel launches so `ncu` finishes quickly rather than replaying a
// long-running loop.
#include <cstdio>
#include <cuda_runtime.h>

__global__ void fma_kernel(float *out, int iters) {
    int idx = blockIdx.x * blockDim.x + threadIdx.x;
    float a = out[idx];
    float b = 1.000001f;
    for (int i = 0; i < iters; ++i) {
        a = fmaf(a, b, 0.5f);
    }
    out[idx] = a;
}

int main() {
    const int n = 1 << 20;
    float *d_out = nullptr;

    if (cudaMalloc(&d_out, n * sizeof(float)) != cudaSuccess) {
        std::fprintf(stderr, "cudaMalloc failed\n");
        return 1;
    }
    cudaMemset(d_out, 0, n * sizeof(float));

    for (int launch = 0; launch < 5; ++launch) {
        fma_kernel<<<n / 256, 256>>>(d_out, 1000);
    }

    cudaError_t err = cudaDeviceSynchronize();
    if (err != cudaSuccess) {
        std::fprintf(stderr, "kernel failed: %s\n", cudaGetErrorString(err));
        return 1;
    }

    cudaFree(d_out);
    std::printf("cuda-load: 5 kernel launches completed\n");
    return 0;
}
