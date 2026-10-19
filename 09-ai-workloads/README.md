# Subsystem 09 - AI validation workloads

Stub. Per D15/S3, scope is **strictly limited to validation workloads**:

- NCCL allreduce benchmark (validates GPU + NVLink + RDMA backend fabric end-to-end)
- small training reference (validates storage + scheduler + driver stack)
- inference reference (validates the inference operator path)

Production / customer workloads remain out of scope and are a partner/customer concern. The CVD's "validated" claim requires a workload that demonstrates validation; this scope mirrors the Pure AIPod CVD's validation approach.

Schema: [`schemas/ai-workloads.schema.json`](../schemas/ai-workloads.schema.json) (stub today).
