"""Set up and run the NVIDIA non-admin GPU metrics test on OpenShift.

This script is a thin wrapper around `oc` and `podman`/BuildConfig builds. It:
  1. Confirms the internal image registry is usable (and can enable it).
  2. Builds the test image from image/ using an OpenShift BuildConfig.
  3. Renders openshift/job.yaml.tmpl for the target namespace.
  4. Creates the Job and optionally tails its logs.

Requires: the `oc` CLI, logged in to the target cluster.

Usage:
    python3 setup.py --namespace my-namespace
    python3 setup.py --namespace my-namespace --node gpu-worker-03 --follow
    python3 setup.py --namespace my-namespace --enable-registry --storage-class px-csi-gold-file
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
IMAGE_DIR = SCRIPT_DIR / "image"
OPENSHIFT_DIR = SCRIPT_DIR / "openshift"
JOB_TEMPLATE = OPENSHIFT_DIR / "job.yaml.tmpl"
REGISTRY_PVC_TEMPLATE = OPENSHIFT_DIR / "image-registry-pvc.yaml.tmpl"
RENDERED_JOB = OPENSHIFT_DIR / "job.rendered.yaml"

IMAGE_NAME = "gpu-metrics-test"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print(f"+ {' '.join(cmd)}")
    return subprocess.run(cmd, check=True, **kwargs)


def run_ok(cmd: list[str]) -> bool:
    return subprocess.run(cmd, capture_output=True, check=False).returncode == 0


def capture(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def require_oc() -> None:
    if not shutil.which("oc"):
        sys.exit("error: the 'oc' CLI is not on PATH")
    try:
        user = capture(["oc", "whoami"])
    except subprocess.CalledProcessError:
        sys.exit("error: not logged in to an OpenShift cluster (run 'oc login' first)")
    print(f"Logged in as: {user}")


def check_registry() -> dict:
    """Return {'management_state': str, 'usable': bool}."""
    try:
        state = capture(
            [
                "oc",
                "get",
                "configs.imageregistry.operator.openshift.io/cluster",
                "-o",
                "jsonpath={.spec.managementState}",
            ]
        )
    except subprocess.CalledProcessError:
        return {"management_state": "Unknown", "usable": False}

    usable = state == "Managed"
    return {"management_state": state or "Unknown", "usable": usable}


def enable_registry(storage_class: str) -> None:
    print(f"\nEnabling the internal image registry with storage class '{storage_class}'...")
    pvc_yaml = REGISTRY_PVC_TEMPLATE.read_text().replace("__STORAGE_CLASS__", storage_class)
    proc = subprocess.run(
        ["oc", "apply", "-f", "-"], input=pvc_yaml, text=True, check=False
    )
    if proc.returncode != 0:
        sys.exit("error: failed to create the image-registry-storage PVC")

    print("Waiting for the PVC to bind...")
    run(
        [
            "oc",
            "wait",
            "pvc/image-registry-storage",
            "-n",
            "openshift-image-registry",
            "--for=jsonpath={.status.phase}=Bound",
            "--timeout=300s",
        ]
    )

    patch = (
        '{"spec":{"managementState":"Managed","replicas":1,'
        '"rolloutStrategy":"Recreate","defaultRoute":true,'
        '"storage":{"pvc":{"claim":"image-registry-storage"}}}}'
    )
    run(
        [
            "oc",
            "patch",
            "configs.imageregistry.operator.openshift.io/cluster",
            "--type=merge",
            "-p",
            patch,
        ]
    )

    print("Waiting for the image-registry cluster operator to become Available...")
    run(
        [
            "oc",
            "wait",
            "co/image-registry",
            "--for=condition=Available=True",
            "--timeout=300s",
        ]
    )


def ensure_buildconfig(namespace: str) -> None:
    bc_exists = run_ok(["oc", "get", "bc", IMAGE_NAME, "-n", namespace])
    if bc_exists:
        print(f"BuildConfig '{IMAGE_NAME}' already exists in {namespace}, reusing it.")
        return

    run(
        [
            "oc",
            "new-build",
            f"--name={IMAGE_NAME}",
            "--binary",
            "--strategy=docker",
            f"--to={IMAGE_NAME}:latest",
            "-n",
            namespace,
        ]
    )


def build_image(namespace: str) -> None:
    ensure_buildconfig(namespace)
    run(
        [
            "oc",
            "start-build",
            IMAGE_NAME,
            f"--from-dir={IMAGE_DIR}",
            "--follow",
            "-n",
            namespace,
        ]
    )


def render_job(namespace: str, node: str | None) -> Path:
    text = JOB_TEMPLATE.read_text().replace("__NAMESPACE__", namespace)
    if node:
        text = text.replace(
            "    spec:\n      restartPolicy: Never\n",
            f"    spec:\n      restartPolicy: Never\n      nodeSelector:\n        kubernetes.io/hostname: {node}\n",
        )
    RENDERED_JOB.write_text(text)
    return RENDERED_JOB


def run_job(namespace: str, job_file: Path, follow: bool) -> None:
    run(["oc", "delete", "job", "gpu-metrics-test", "-n", namespace, "--ignore-not-found"])
    run(["oc", "create", "-f", str(job_file), "-n", namespace])
    if follow:
        run(["oc", "wait", "pod", "-l", "app=gpu-metrics-test", "-n", namespace, "--for=condition=Ready", "--timeout=300s"])
        run(["oc", "logs", "-f", "job/gpu-metrics-test", "-n", namespace])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--namespace", help="Namespace to build and run in (default: current oc project)")
    parser.add_argument("--node", help="Pin the test Job to a specific node (kubernetes.io/hostname)")
    parser.add_argument("--enable-registry", action="store_true", help="Enable the internal image registry if it is not usable")
    parser.add_argument("--storage-class", help="Storage class for the registry PVC (required with --enable-registry)")
    parser.add_argument("--skip-build", action="store_true", help="Skip building the image (reuse the existing tag)")
    parser.add_argument("--no-follow", action="store_true", help="Do not tail Job logs after creating it")
    args = parser.parse_args()

    require_oc()

    namespace = args.namespace or capture(["oc", "project", "-q"])
    print(f"Using namespace: {namespace}")

    registry = check_registry()
    print(f"Image registry managementState: {registry['management_state']}")
    if not registry["usable"]:
        if args.enable_registry:
            if not args.storage_class:
                sys.exit("error: --storage-class is required with --enable-registry")
            enable_registry(args.storage_class)
        else:
            sys.exit(
                "error: the internal image registry is not Managed.\n"
                "Re-run with --enable-registry --storage-class <name>, or see README.md."
            )

    if not args.skip_build:
        build_image(namespace)

    job_file = render_job(namespace, args.node)
    print(f"Rendered Job manifest: {job_file}")

    run_job(namespace, job_file, follow=not args.no_follow)
    return 0


if __name__ == "__main__":
    sys.exit(main())
