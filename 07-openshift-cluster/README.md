# Subsystem 07 - OpenShift cluster

Stub. Will install Red Hat OpenShift spanning `mgmt-nodes-ucs` (Subsystem 05) as control-plane or compact nodes and `workload-nodes-ucs` (Subsystem 06) as workers, then deploy the operator stack on top: NVIDIA GPU operator, NVIDIA Network operator, NFD, GPUDirect RDMA / Storage.

Per D17/N3, the original `06-nvidia-operators/` placeholder was deleted in the 2026-05-04 atomic restructure — NVIDIA operators are deployed via OCP OperatorHub as part of the OpenShift install path, not as a separate provisioning subsystem.

Schema: [`schemas/openshift-cluster.schema.json`](../schemas/openshift-cluster.schema.json) (stub today). When fleshed out, this schema cross-references `mgmt-nodes-ucs` and `workload-nodes-ucs` by subsystem name.
