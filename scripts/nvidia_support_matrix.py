"""
NVIDIA AI Enterprise Support Matrix Script

This script extracts GPU model compatibility data from the NVIDIA AI Enterprise
Support Matrix documentation and cross-references it with the local
configuration files.

Usage:
    python nvidia_support_matrix.py [--format json|csv|table] [--version VERSION]
    python nvidia_support_matrix.py --fetch-live [--version VERSION]
    python nvidia_support_matrix.py --check-updates

Data sources:
  - AI Enterprise versions/components:
      https://docs.nvidia.com/ai-enterprise/support-matrix/latest/index.html
  - DOCA container image tags (per Network Operator version):
      https://docs.nvidia.com/networking/display/kubernetes{VER}/platform-support.html
      e.g. Network Operator 26.4.0 -> kubernetes2640

How to update when a new AI Enterprise version (e.g. 8.2, 9.0) is released:
  1. Run: python nvidia_support_matrix.py --check-updates
     This checks the NVIDIA release notes pages for versions not in the local matrix.
  2. Add the new version block to NVIDIA_SUPPORT_MATRIX below, using data from:
       https://docs.nvidia.com/ai-enterprise/support-matrix/latest/index.html
  3. Run: python nvidia_support_matrix.py --fetch-live --version X.Y
     This auto-populates DOCA OFED Driver Container and DOCA Telemetry Service tags
     from the corresponding Network Operator component matrix page.
"""

import json
import re
import urllib.request
import urllib.error
import yaml
import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional
from tabulate import tabulate

# Hardcoded support matrix data from NVIDIA documentation
# Source: https://docs.nvidia.com/ai-enterprise/support-matrix/latest/index.html
#
# DOCA container image tags sourced from the Network Operator component matrix:
#   https://docs.nvidia.com/networking/display/kubernetes{VER}/platform-support.html
# where {VER} = Network Operator minor version with patch zeroed (e.g. 26.4.0 -> 2640, 25.10.1 -> 25100).
# The component matrix table is on the platform-support sub-page of that doc set.
#
# To fetch/refresh DOCA container tags for a version, run with --fetch-live.
# Note: Some versions may have limited EOL support. Check NVIDIA docs for current status.
NVIDIA_SUPPORT_MATRIX = {
    "8.1": {
        "openshift_supported": True,
        "infrastructure_software": {
            "NVIDIA Data Center GPU Driver": "595.71.05",
            "NVIDIA DOCA Driver for Networking": "3.4.0",
            "NVIDIA GPU Operator": "26.3.3",
            "NVIDIA Network Operator": "26.4.0",
            "NVIDIA NIM Operator": "3.1.1",
            "NVIDIA Run:ai": "2.25",
            # Source: https://docs.nvidia.com/networking/display/kubernetes2640/platform-support.html
            "DOCA OFED Driver Container": "doca3.4.0-26.04-0.8.6.0-0",
            "DOCA Telemetry Service": "1.25.5-doca3.4.0-host",
        },
        "gpu_models": {
            "B300 SXM": {"architecture": "Blackwell Ultra", "deployment": "HGX Server"},
            "B200 SXM": {"architecture": "Blackwell", "deployment": "HGX Server"},
            "H200 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H200 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100": {"architecture": "Hopper", "deployment": "DGX Server"},
            "H100 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "L40": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "L40S": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "RTX PRO 4500 Blackwell Server Edition": {
                "architecture": "Blackwell",
                "deployment": "PCIe GPU Server",
            },
            "RTX PRO 6000 Blackwell Server Edition": {
                "architecture": "Blackwell",
                "deployment": "PCIe GPU Server",
            },
        },
    },
    "8.0": {
        "openshift_supported": True,
        "infrastructure_software": {
            "NVIDIA Data Center GPU Driver": "595.58.03",
            "NVIDIA DOCA Driver for Networking": "3.3.0",
            "NVIDIA GPU Operator": "26.3.0",
            "NVIDIA Network Operator": "26.1.0",
            "NVIDIA NIM Operator": "3.1.0",
            "NVIDIA Run:ai": "2.24",
            # Source: https://docs.nvidia.com/networking/display/kubernetes2610/platform-support.html
            "DOCA OFED Driver Container": "doca3.3.0-26.01-1.0.0.0-0",
            "DOCA Telemetry Service": "1.23.4-doca3.2.0-host",
        },
        "gpu_models": {
            "B300 SXM": {"architecture": "Blackwell Ultra", "deployment": "HGX Server"},
            "B200 SXM": {"architecture": "Blackwell", "deployment": "HGX Server"},
            "H200 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H200 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100": {"architecture": "Hopper", "deployment": "DGX Server"},
            "H100 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "L40": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "L40S": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "RTX PRO 4500 Blackwell Server Edition": {
                "architecture": "Blackwell",
                "deployment": "PCIe GPU Server",
            },
            "RTX PRO 6000 Blackwell Server Edition": {
                "architecture": "Blackwell",
                "deployment": "PCIe GPU Server",
            },
        },
    },
    "7.7": {
        "openshift_supported": True,
        "infrastructure_software": {
            "NVIDIA Data Center GPU Driver": "580.173.02",
            "NVIDIA DOCA Driver for Networking": "3.4.0",
            "NVIDIA GPU Operator": "26.3.3",
            "NVIDIA Network Operator": "26.4.0",
            "NVIDIA NIM Operator": "3.1.1",
            "NVIDIA Run:ai": "2.25",
            # Source: https://docs.nvidia.com/networking/display/kubernetes2640/platform-support.html
            "DOCA OFED Driver Container": "doca3.4.0-26.04-0.8.6.0-0",
            "DOCA Telemetry Service": "1.25.5-doca3.4.0-host",
        },
        "gpu_models": {
            "B300 SXM": {"architecture": "Blackwell Ultra", "deployment": "HGX Server"},
            "B200 SXM": {"architecture": "Blackwell", "deployment": "HGX Server"},
            "H200 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H200 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100": {"architecture": "Hopper", "deployment": "DGX Server"},
            "H100 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "L40": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "L40S": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "RTX PRO 6000 Blackwell Server Edition": {
                "architecture": "Blackwell",
                "deployment": "PCIe GPU Server",
            },
        },
    },
    "7.6": {
        "openshift_supported": True,
        "infrastructure_software": {
            "NVIDIA Data Center GPU Driver": "580.167.08",
            "NVIDIA DOCA Driver for Networking": "3.4.0",
            "NVIDIA GPU Operator": "26.3.3",
            "NVIDIA Network Operator": "26.4.0",
            "NVIDIA NIM Operator": "3.1.1",
            "NVIDIA Run:ai": "2.23",
            # Source: https://docs.nvidia.com/networking/display/kubernetes2640/platform-support.html
            "DOCA OFED Driver Container": "doca3.4.0-26.04-0.8.6.0-0",
            "DOCA Telemetry Service": "1.25.5-doca3.4.0-host",
        },
        "gpu_models": {
            "B300 SXM": {"architecture": "Blackwell Ultra", "deployment": "HGX Server"},
            "B200 SXM": {"architecture": "Blackwell", "deployment": "HGX Server"},
            "H200 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H200 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100": {"architecture": "Hopper", "deployment": "DGX Server"},
            "H100 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "L40": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "L40S": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "RTX PRO 6000 Blackwell Server Edition": {
                "architecture": "Blackwell",
                "deployment": "PCIe GPU Server",
            },
        },
    },
    "7.5": {
        "openshift_supported": True,
        "infrastructure_software": {
            # Source: https://docs.nvidia.com/ai-enterprise/release-7/latest/support/support-matrix-7/7.5.html
            "NVIDIA Data Center GPU Driver": "580.159.03",
            "NVIDIA DOCA Driver for Networking": "3.3.0",
            "NVIDIA GPU Operator": "26.3.1",
            "NVIDIA Network Operator": "26.1.1",
            "NVIDIA NIM Operator": "3.1.0",
            "NVIDIA Run:ai": "2.25",
            # Source: https://docs.nvidia.com/networking/display/kubernetes2610/platform-support.html
            "DOCA OFED Driver Container": "doca3.3.0-26.01-1.0.0.0-0",
            "DOCA Telemetry Service": "1.23.4-doca3.2.0-host",
        },
        "gpu_models": {
            "B300 SXM": {"architecture": "Blackwell Ultra", "deployment": "HGX Server"},
            "B200 SXM": {"architecture": "Blackwell", "deployment": "HGX Server"},
            "H200 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H200 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100": {"architecture": "Hopper", "deployment": "DGX Server"},
            "H100 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "L40": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "L40S": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "RTX PRO 6000 Blackwell Server Edition": {
                "architecture": "Blackwell",
                "deployment": "PCIe GPU Server",
            },
        },
    },
    "7.4": {
        "openshift_supported": True,
        "infrastructure_software": {
            # Source: https://docs.nvidia.com/ai-enterprise/release-7/latest/support/support-matrix-7/7.4.html
            "NVIDIA Data Center GPU Driver": "580.126.09",
            "NVIDIA DOCA Driver for Networking": "3.2.0",
            "NVIDIA GPU Operator": "25.10.1",
            "NVIDIA Network Operator": "25.10.0",
            "NVIDIA NIM Operator": "3.0.2",
            "NVIDIA Run:ai": "2.24",
            # Source: https://docs.nvidia.com/networking/display/kubernetes25100/platform-support.html
            "DOCA OFED Driver Container": "doca3.2.0-25.10-1.2.8.0-2",
            "DOCA Telemetry Service": "1.22.5-doca3.1.0-host",
        },
        "gpu_models": {
            "B300 SXM": {"architecture": "Blackwell Ultra", "deployment": "HGX Server"},
            "B200 SXM": {"architecture": "Blackwell", "deployment": "HGX Server"},
            "H200 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H200 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100": {"architecture": "Hopper", "deployment": "DGX Server"},
            "H100 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "L40": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "L40S": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "RTX PRO 6000 Blackwell Server Edition": {
                "architecture": "Blackwell",
                "deployment": "PCIe GPU Server",
            },
        },
    },
    "7.3": {
        "openshift_supported": True,
        "infrastructure_software": {
            # Source: https://docs.nvidia.com/ai-enterprise/release-7/latest/support/support-matrix-7/7.3.html
            "NVIDIA Data Center GPU Driver": "580.105.08",
            "NVIDIA DOCA Driver for Networking": "3.1.0",
            "NVIDIA GPU Operator": "25.10.0",
            "NVIDIA Network Operator": "25.7.0",
            "NVIDIA NIM Operator": "3.0.1",
            "NVIDIA Run:ai": "2.20",
            # Source: https://docs.nvidia.com/networking/display/kubernetes2570/platform-support.html
            "DOCA OFED Driver Container": "doca3.1.0-25.07-0.9.7.0-0",
            "DOCA Telemetry Service": "1.21.4-doca3.0.0-host",
        },
        "gpu_models": {
            "B300 SXM": {"architecture": "Blackwell Ultra", "deployment": "HGX Server"},
            "B200 SXM": {"architecture": "Blackwell", "deployment": "HGX Server"},
            "H200 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H200 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100": {"architecture": "Hopper", "deployment": "DGX Server"},
            "H100 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "L40": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "L40S": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "RTX PRO 6000 Blackwell Server Edition": {
                "architecture": "Blackwell",
                "deployment": "PCIe GPU Server",
            },
        },
    },
    "7.2": {
        "openshift_supported": True,
        "infrastructure_software": {
            # Source: https://docs.nvidia.com/ai-enterprise/release-7/latest/support/support-matrix-7/7.2.html
            "NVIDIA Data Center GPU Driver": "580.95.05",
            "NVIDIA DOCA Driver for Networking": "3.1.0",
            "NVIDIA GPU Operator": "25.10.0",
            "NVIDIA Network Operator": "25.7.0",
            "NVIDIA NIM Operator": "3.0.1",
            "NVIDIA Run:ai": "2.19",
            # Source: https://docs.nvidia.com/networking/display/kubernetes2570/platform-support.html
            "DOCA OFED Driver Container": "doca3.1.0-25.07-0.9.7.0-0",
            "DOCA Telemetry Service": "1.21.4-doca3.0.0-host",
        },
        "gpu_models": {
            "B200 SXM": {"architecture": "Blackwell", "deployment": "HGX Server"},
            "H200 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H200 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100": {"architecture": "Hopper", "deployment": "DGX Server"},
            "H100 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "L40": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "L40S": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "RTX PRO 6000 Blackwell Server Edition": {
                "architecture": "Blackwell",
                "deployment": "PCIe GPU Server",
            },
        },
    },
    "7.1": {
        "openshift_supported": True,
        "infrastructure_software": {
            # Source: https://docs.nvidia.com/ai-enterprise/release-7/latest/support/support-matrix-7/7.1.html
            "NVIDIA Data Center GPU Driver": "580.82.07",
            "NVIDIA DOCA Driver for Networking": "3.1.0",
            "NVIDIA GPU Operator": "25.3.2",
            "NVIDIA Network Operator": "25.7.0",
            "NVIDIA NIM Operator": "3.0.0",
            "NVIDIA Run:ai": "2.18",
            # Source: https://docs.nvidia.com/networking/display/kubernetes2570/platform-support.html
            "DOCA OFED Driver Container": "doca3.1.0-25.07-0.9.7.0-0",
            "DOCA Telemetry Service": "1.21.4-doca3.0.0-host",
        },
        "gpu_models": {
            "B200 SXM": {"architecture": "Blackwell", "deployment": "HGX Server"},
            "H200 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H200 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100": {"architecture": "Hopper", "deployment": "DGX Server"},
            "H100 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "L40": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "L40S": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "RTX PRO 6000 Blackwell Server Edition": {
                "architecture": "Blackwell",
                "deployment": "PCIe GPU Server",
            },
        },
    },
    "7.0": {
        "openshift_supported": True,
        "infrastructure_software": {
            # Source: https://docs.nvidia.com/ai-enterprise/release-7/latest/support/support-matrix-7/7.0.html
            "NVIDIA Data Center GPU Driver": "580.65.06",
            "NVIDIA DOCA Driver for Networking": "3.0.0",
            "NVIDIA GPU Operator": "25.3.2",
            "NVIDIA Network Operator": "25.4.0",
            "NVIDIA NIM Operator": "2.0.2",
            "NVIDIA Run:ai": "2.17",
            # Source: https://docs.nvidia.com/networking/display/kubernetes2540/platform-support.html
            "DOCA OFED Driver Container": "25.04-0.6.1.0-2",
            "DOCA Telemetry Service": "1.16.5-doca2.6.0-host",
        },
        "gpu_models": {
            "B200 SXM": {"architecture": "Blackwell", "deployment": "HGX Server"},
            "H200 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H200 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100": {"architecture": "Hopper", "deployment": "DGX Server"},
            "H100 SXM": {"architecture": "Hopper", "deployment": "HGX Server"},
            "H100 NVL": {"architecture": "Hopper", "deployment": "HGX Server"},
            "L40": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "L40S": {"architecture": "Ada", "deployment": "PCIe GPU Server"},
            "RTX PRO 6000 Blackwell Server Edition": {
                "architecture": "Blackwell",
                "deployment": "PCIe GPU Server",
            },
        },
    },
}


def _network_operator_version_to_url_key(version: str) -> str:
    """Convert Network Operator version to the URL path segment used in NVIDIA docs.

    NVIDIA publishes one docs page per minor release (YY.MM), not per patch.
    The URL key is always major + minor + "0", regardless of the patch version.

    Examples:
        "26.4.0"  -> "2640"   (26 + 4 + 0)
        "25.10.0" -> "25100"  (25 + 10 + 0)
        "25.10.1" -> "25100"  (25 + 10 + 0, patch ignored)
        "26.1.1"  -> "2610"   (26 + 1 + 0, patch ignored)
        "25.3.2"  -> "2530"   (25 + 3 + 0, patch ignored)
    """
    parts = version.split(".")
    if len(parts) >= 2:
        return parts[0] + parts[1] + "0"
    return version.replace(".", "")


def fetch_network_operator_components(network_operator_version: str) -> Dict[str, Optional[str]]:
    """Fetch DOCA container image and telemetry service tags from the Network Operator
    component matrix page.

    Source URL pattern:
        https://docs.nvidia.com/networking/display/kubernetes{VER}/platform-support.html

    Note: The NVIDIA docs page is JavaScript-rendered. This function attempts to extract
    data from the raw HTML using multiple patterns (both pipe-delimited text and HTML
    table formats). If the page renders client-side only, the values will be None and
    you should check the URL manually.

    Args:
        network_operator_version: e.g. "26.4.0"

    Returns:
        Dict with keys "DOCA OFED Driver Container" and "DOCA Telemetry Service",
        or None values if the page could not be fetched or parsed.
    """
    result: Dict[str, Optional[str]] = {
        "DOCA OFED Driver Container": None,
        "DOCA Telemetry Service": None,
    }
    ver_key = _network_operator_version_to_url_key(network_operator_version)
    # The component matrix (DOCA container tags) lives on the platform-support sub-page.
    # The index.html is the landing page shown to users; platform-support.html has the table.
    fetch_url = (
        f"https://docs.nvidia.com/networking/display/kubernetes{ver_key}"
        f"/platform-support.html"
    )
    display_url = (
        f"https://docs.nvidia.com/networking/display/kubernetes{ver_key}"
        f"/platform-support.html"
    )
    print(f"  Fetching Network Operator {network_operator_version} component matrix: {display_url}")
    try:
        req = urllib.request.Request(
            fetch_url, headers={"User-Agent": "Mozilla/5.0 (compatible; nvidia-matrix-script/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            content = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        print(f"  Warning: HTTP {e.code} fetching {fetch_url}", file=sys.stderr)
        return result
    except Exception as e:
        print(f"  Warning: Could not fetch {fetch_url}: {e}", file=sys.stderr)
        return result

    # Try multiple patterns for DOCA-OFED Driver Container tag.
    # Pattern 1: pipe-delimited text (rendered Markdown/text)
    # Pattern 2: HTML table cells (raw Confluence HTML)
    doca_patterns = [
        r"DOCA-OFED Driver Container[^\|]*\|[^\|]*\|[^\|]*\|[^\|]*\|\s*(doca[\d.]+[-\w.]+)\s*\|",
        r"DOCA-OFED Driver Container</td>(?:.*?<td[^>]*>){3}(doca[\d.]+[-\w.]+)</td>",
        r'doca-driver["\s]+\|[^|]*\|(doca[\d.]+[-\w.]+)',
        r'doca-driver.*?"tag":\s*"(doca[\d.]+[-\w.]+)"',
    ]
    for pattern in doca_patterns:
        m = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if m:
            result["DOCA OFED Driver Container"] = m.group(1).strip()
            break

    # Try multiple patterns for DOCA Telemetry Service (DTS) tag.
    dts_patterns = [
        r"DOCA Telemetry Service[^\|]*\|[^\|]*\|[^\|]*\|[^\|]*\|\s*([\d.]+-doca[\d.]+-host)\s*\|",
        r"DOCA Telemetry Service[^<]*</td>(?:.*?<td[^>]*>){3}([\d.]+-doca[\d.]+-host)</td>",
        r'doca_telemetry["\s]+\|[^|]*\|([\d.]+-doca[\d.]+-host)',
        r'doca_telemetry.*?"tag":\s*"([\d.]+-doca[\d.]+-host)"',
    ]
    for pattern in dts_patterns:
        m = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if m:
            result["DOCA Telemetry Service"] = m.group(1).strip()
            break

    if not result["DOCA OFED Driver Container"] and not result["DOCA Telemetry Service"]:
        print(
            f"  Note: Could not extract DOCA tags from the page (likely JS-rendered).\n"
            f"  Check manually: {display_url}",
            file=sys.stderr,
        )

    return result


def check_for_new_versions() -> List[str]:
    """Check NVIDIA AI Enterprise release notes pages for versions not in the local matrix.

    Only checks the highest known major version and the next one (e.g. 8.x and 9.x)
    since older major versions are already fully represented in the local matrix.
    Two HTTP requests total — fast enough for inline use.

    Returns:
        List of version strings (e.g. ["8.2", "9.0"]) not in NVIDIA_SUPPORT_MATRIX.
    """
    known_versions = set(NVIDIA_SUPPORT_MATRIX.keys())
    max_major = max(int(v.split(".")[0]) for v in known_versions)

    new_versions: List[str] = []

    # Only check the current highest major and the next one.
    # Older majors (7.x, etc.) are already fully known — no need to re-scan them.
    for major in range(max_major, max_major + 2):
        url = (
            f"https://docs.nvidia.com/ai-enterprise/release-{major}"
            f"/latest/overview/release-notes.html"
        )
        print(f"  Checking release notes: {url}")
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (compatible; nvidia-matrix-script/1.0)"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"  No release-{major} page found (404) — likely no {major}.x releases yet.")
            else:
                print(f"  Warning: HTTP {e.code} for {url}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"  Warning: Could not fetch {url}: {e}", file=sys.stderr)
            continue

        # Look for links like "8.2.html", "9.0.html" in the release notes index
        found = re.findall(
            rf'release-notes-{major}/({major}\.\d+(?:\.\d+)?)["\.]',
            content,
        )
        for ver in found:
            if ver not in known_versions:
                new_versions.append(ver)

    return sorted(set(new_versions))


def _check_for_new_versions_silent() -> List[str]:
    """Run check_for_new_versions() without any console output.

    Used for the inline check during normal report generation so that
    verbose progress messages don't clutter the report output. Any
    failure silently returns an empty list.
    """
    import io
    import contextlib

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            return check_for_new_versions()
    except Exception:
        return []


class NVIDIASupportMatrix:
    """Extract and process NVIDIA AI Enterprise support matrix data."""

    def __init__(self, variables_path: str = None):
        """
        Initialize the support matrix processor.

        Args:
            variables_path: Path to operators.ezai.yaml example file
        """
        self.variables_path = Path(variables_path or "examples/openshift/operators.ezai.yaml")
        self.example_data = {}
        # Overrides from --fetch-live: keyed by AE version
        self._live_doca_components: Dict[str, Dict[str, Optional[str]]] = {}

    def load_variables(self) -> None:
        """Load the YAML variables file."""
        if not self.variables_path.exists():
            print(f"Warning: Variables file not found: {self.variables_path}")
            return

        try:
            with open(self.variables_path, "r") as f:
                self.example_data = yaml.safe_load(f)
            print(f"✓ Loaded variables from {self.variables_path}")
        except yaml.YAMLError as e:
            print(f"Error parsing YAML: {e}")
            sys.exit(1)

    def extract_gpu_models(self) -> List[str]:
        """Extract GPU models from the example configuration."""
        gpu_models = []
        if self.example_data:
            gpu_models = (
                self.example_data.get("openshift", {}).get("gpu_models", [])
            )
        return gpu_models

    def extract_ai_enterprise_version(self) -> str:
        """Extract NVIDIA AI Enterprise version from the example configuration."""
        if self.example_data:
            return (
                self.example_data.get("openshift", {})
                .get("nvidia_ai_enterprise_version", "8.1")
            )
        return "8.1"

    def fetch_live_doca_components(self, ai_version: str) -> None:
        """Fetch DOCA container image tags live from the Network Operator docs and cache them.

        Only updates fields that are currently None in the static matrix.
        Static data (already set for e.g. 8.1) is preserved as authoritative.

        Args:
            ai_version: NVIDIA AI Enterprise version string (e.g. "8.1")
        """
        sw = NVIDIA_SUPPORT_MATRIX.get(ai_version, {}).get("infrastructure_software", {})
        no_version = sw.get("NVIDIA Network Operator")
        if not no_version:
            print(f"  Warning: No Network Operator version found for AE {ai_version}.", file=sys.stderr)
            return

        # If both DOCA fields already have static values, skip the live fetch
        static_doca = sw.get("DOCA OFED Driver Container")
        static_dts = sw.get("DOCA Telemetry Service")
        if static_doca and static_dts:
            print(
                f"  ✓ DOCA OFED Driver Container : {static_doca} (from static data)"
            )
            print(
                f"  ✓ DOCA Telemetry Service     : {static_dts} (from static data)"
            )
            return

        components = fetch_network_operator_components(no_version)
        # Merge: live fetch only fills in fields that are None in static data
        merged: Dict[str, Optional[str]] = {
            "DOCA OFED Driver Container": static_doca or components.get("DOCA OFED Driver Container"),
            "DOCA Telemetry Service": static_dts or components.get("DOCA Telemetry Service"),
        }
        self._live_doca_components[ai_version] = merged
        doca = merged.get("DOCA OFED Driver Container") or "not found"
        dts = merged.get("DOCA Telemetry Service") or "not found"
        print(f"  ✓ DOCA OFED Driver Container : {doca}")
        print(f"  ✓ DOCA Telemetry Service     : {dts}")

    def _get_doca_components(self, ai_version: str) -> Dict[str, Optional[str]]:
        """Return DOCA component versions for an AE version, preferring live-fetched data."""
        if ai_version in self._live_doca_components:
            return self._live_doca_components[ai_version]
        sw = NVIDIA_SUPPORT_MATRIX.get(ai_version, {}).get("infrastructure_software", {})
        return {
            "DOCA OFED Driver Container": sw.get("DOCA OFED Driver Container"),
            "DOCA Telemetry Service": sw.get("DOCA Telemetry Service"),
        }

    def get_compatibility_report(
        self, format_type: str = "table", ai_version: str = None
    ) -> str:
        """
        Generate a compatibility report for selected GPU models.

        Args:
            format_type: Output format ('table', 'json', or 'csv')
            ai_version: Override the AI Enterprise version (default: read from variables file)

        Returns:
            Formatted compatibility report

        Raises:
            ValueError: If GPU models or OpenShift are not supported for the selected version
        """
        self.load_variables()

        gpu_models = self.extract_gpu_models()
        # CLI --version takes precedence over the variables file
        if ai_version is None:
            ai_version = self.extract_ai_enterprise_version()

        available_versions = sorted(NVIDIA_SUPPORT_MATRIX.keys(), reverse=True)
        print(f"✓ NVIDIA AI Enterprise version : {ai_version}")
        print(f"✓ Local matrix versions        : {available_versions}")

        # Silently check online for versions not yet in the local matrix
        new_online = _check_for_new_versions_silent()
        if new_online:
            print(
                f"⚠️  New versions available online: {new_online}\n"
                f"   Add them to NVIDIA_SUPPORT_MATRIX, then run --fetch-live --version X.Y"
            )
        else:
            print("✓ Online version check         : up to date")

        print(f"✓ GPU models found             : {gpu_models}")

        ai_version = str(ai_version).strip()

        if ai_version not in NVIDIA_SUPPORT_MATRIX:
            print(f"Warning: Version '{ai_version}' not found in support matrix.")
            print(f"Available versions: {', '.join(available_versions)}")
            print("Tip: run --check-updates to see if a newer version has been published.")
            ai_version = "8.1"  # Default to latest

        version_data = NVIDIA_SUPPORT_MATRIX[ai_version]

        # Validate OpenShift support
        if not version_data.get("openshift_supported", False):
            raise ValueError(
                f"Error: NVIDIA AI Enterprise v{ai_version} does not support OpenShift.\n"
                f"Please choose a version with openshift_supported: true."
            )

        supported_software = version_data.get("infrastructure_software", {})

        if not gpu_models:
            return "No GPU models found in configuration."

        if not supported_software:
            return f"No support matrix data found for NVIDIA AI Enterprise version {ai_version}"

        # Validate GPU model support
        supported_gpu_models = set(version_data.get("gpu_models", {}).keys())
        selected_gpu_models = set(gpu_models)
        unsupported_models = selected_gpu_models - supported_gpu_models

        if unsupported_models:
            raise ValueError(
                f"Error: NVIDIA AI Enterprise v{ai_version} does not support the following GPU models:\n"
                f"  Unsupported: {', '.join(sorted(unsupported_models))}\n"
                f"  Supported for v{ai_version}: {', '.join(sorted(supported_gpu_models))}\n"
                f"\nPlease either:\n"
                f"  1. Update your GPU models to supported ones, or\n"
                f"  2. Change your NVIDIA AI Enterprise version"
            )

        doca_components = self._get_doca_components(ai_version)

        # Build report data
        report_data = []
        for gpu_model in gpu_models:
            gpu_info = version_data.get("gpu_models", {}).get(gpu_model, {})
            row = {
                "GPU Model": gpu_model,
                "Architecture": gpu_info.get("architecture", "N/A"),
                "Deployment Type": gpu_info.get("deployment", "N/A"),
                "OpenShift Kubernetes": "Supported",
                "Data Center GPU Driver": supported_software.get(
                    "NVIDIA Data Center GPU Driver", "N/A"
                ),
                "DOCA Driver for Networking": supported_software.get(
                    "NVIDIA DOCA Driver for Networking", "N/A"
                ),
                "GPU Operator": supported_software.get("NVIDIA GPU Operator", "N/A"),
                "Network Operator": supported_software.get("NVIDIA Network Operator", "N/A"),
                "NIM Operator": supported_software.get("NVIDIA NIM Operator", "N/A"),
                "Run:ai": supported_software.get("NVIDIA Run:ai", "N/A"),
                "DOCA OFED Driver Container": (
                    doca_components.get("DOCA OFED Driver Container") or "run --fetch-live"
                ),
                "DOCA Telemetry Service": (
                    doca_components.get("DOCA Telemetry Service") or "run --fetch-live"
                ),
            }
            report_data.append(row)

        if format_type == "json":
            return self._format_json(report_data, ai_version)
        elif format_type == "csv":
            return self._format_csv(report_data, ai_version)
        else:
            return self._format_table(report_data, ai_version)

    def _format_table(self, data: List[Dict], ai_version: str) -> str:
        """Format data as two human-readable tables: software versions + GPU models."""
        sw = NVIDIA_SUPPORT_MATRIX.get(ai_version, {}).get("infrastructure_software", {})
        no_version = sw.get("NVIDIA Network Operator", "")
        ver_key = _network_operator_version_to_url_key(no_version) if no_version else ""
        doca_components = self._get_doca_components(ai_version)

        separator = "=" * 100
        output = f"\n{separator}\n"
        output += f"NVIDIA AI Enterprise v{ai_version} — Bare Metal · Kubernetes · OpenShift\n"
        output += f"{separator}\n"

        # Table 1: Infrastructure software versions
        output += "\nInfrastructure Software Versions:\n"
        sw_table = [
            ["NVIDIA Data Center GPU Driver", sw.get("NVIDIA Data Center GPU Driver", "N/A")],
            ["NVIDIA DOCA Driver for Networking", sw.get("NVIDIA DOCA Driver for Networking", "N/A")],
            ["NVIDIA GPU Operator", sw.get("NVIDIA GPU Operator", "N/A")],
            ["NVIDIA Network Operator", sw.get("NVIDIA Network Operator", "N/A")],
            ["NVIDIA NIM Operator", sw.get("NVIDIA NIM Operator", "N/A")],
            ["NVIDIA Run:ai", sw.get("NVIDIA Run:ai", "N/A")],
            ["DOCA OFED Driver Container",
             doca_components.get("DOCA OFED Driver Container") or "run --fetch-live"],
            ["DOCA Telemetry Service",
             doca_components.get("DOCA Telemetry Service") or "run --fetch-live"],
        ]
        output += tabulate(sw_table, headers=["Component", "Version"], tablefmt="grid")

        # Table 2: Supported GPU models
        output += "\n\nSupported GPU Models (OpenShift: Supported):\n"
        gpu_table = [
            [row["GPU Model"], row["Architecture"], row["Deployment Type"]]
            for row in data
        ]
        output += tabulate(
            gpu_table,
            headers=["GPU Model", "Architecture", "Deployment Type"],
            tablefmt="grid",
        )

        output += "\n\nSources:\n"
        output += "  AI Enterprise Matrix : https://docs.nvidia.com/ai-enterprise/support-matrix/latest/index.html\n"
        if ver_key:
            output += (
                f"  DOCA Component Matrix: "
                f"https://docs.nvidia.com/networking/display/kubernetes{ver_key}/platform-support.html\n"
            )
        return output

    def _format_json(self, data: List[Dict], ai_version: str) -> str:
        """Format data as JSON with infrastructure versions at the top level (not per-GPU)."""
        sw = NVIDIA_SUPPORT_MATRIX.get(ai_version, {}).get("infrastructure_software", {})
        no_version = sw.get("NVIDIA Network Operator", "")
        ver_key = _network_operator_version_to_url_key(no_version) if no_version else ""
        doca_components = self._get_doca_components(ai_version)

        # GPU models: list of dicts with just model name, architecture, deployment type
        gpu_models = [
            {
                "gpu_model": row["GPU Model"],
                "architecture": row["Architecture"],
                "deployment_type": row["Deployment Type"],
            }
            for row in data
        ]

        output = {
            "nvidia_ai_enterprise_version": ai_version,
            "deployment": "Bare Metal - Kubernetes - OpenShift",
            "openshift_supported": True,
            "infrastructure_software": {
                "NVIDIA Data Center GPU Driver": sw.get("NVIDIA Data Center GPU Driver"),
                "NVIDIA DOCA Driver for Networking": sw.get("NVIDIA DOCA Driver for Networking"),
                "NVIDIA GPU Operator": sw.get("NVIDIA GPU Operator"),
                "NVIDIA Network Operator": sw.get("NVIDIA Network Operator"),
                "NVIDIA NIM Operator": sw.get("NVIDIA NIM Operator"),
                "NVIDIA Run:ai": sw.get("NVIDIA Run:ai"),
                "DOCA OFED Driver Container": (
                    doca_components.get("DOCA OFED Driver Container") or "run --fetch-live"
                ),
                "DOCA Telemetry Service": (
                    doca_components.get("DOCA Telemetry Service") or "run --fetch-live"
                ),
            },
            "gpu_models": gpu_models,
            "sources": {
                "support_matrix": (
                    "https://docs.nvidia.com/ai-enterprise/support-matrix/latest/index.html"
                ),
                "doca_component_matrix": (
                    f"https://docs.nvidia.com/networking/display/kubernetes{ver_key}/platform-support.html"
                ) if ver_key else None,
            },
        }
        return json.dumps(output, indent=2)

    def _format_csv(self, data: List[Dict], ai_version: str) -> str:
        """Format data as CSV."""
        import csv
        from io import StringIO

        output = StringIO()
        headers = [
            "GPU Model",
            "Architecture",
            "Deployment Type",
            "Platform",
            "GPU Driver",
            "DOCA Driver",
            "GPU Operator",
            "Network Operator",
            "Run:ai",
            "DOCA OFED Driver Container",
            "DOCA Telemetry Service",
        ]

        writer = csv.writer(output)
        writer.writerow(headers)

        for row in data:
            writer.writerow(
                [
                    row["GPU Model"],
                    row["Architecture"],
                    row["Deployment Type"],
                    row["OpenShift Kubernetes"],
                    row["Data Center GPU Driver"],
                    row["DOCA Driver for Networking"],
                    row["GPU Operator"],
                    row["Network Operator"],
                    row["Run:ai"],
                    row["DOCA OFED Driver Container"],
                    row["DOCA Telemetry Service"],
                ]
            )

        return output.getvalue()

    def get_version_info(self, ai_version: str = None) -> Dict[str, str]:
        """
        Get all software version information for a specific NVIDIA AI Enterprise version.

        Args:
            ai_version: NVIDIA AI Enterprise version (default: from examples)

        Returns:
            Dictionary of software versions
        """
        if ai_version is None:
            ai_version = self.extract_ai_enterprise_version()

        sw = NVIDIA_SUPPORT_MATRIX.get(ai_version, {}).get("infrastructure_software", {})
        # Overlay live-fetched DOCA component data if available
        if ai_version in self._live_doca_components:
            sw = dict(sw)
            sw.update(self._live_doca_components[ai_version])
        return sw

    def format_versions(self, ai_version: str, format_type: str = "table") -> str:
        """
        Format version information in the specified format.

        Args:
            ai_version: NVIDIA AI Enterprise version
            format_type: Output format (table, json, csv)

        Returns:
            Formatted version information
        """
        versions = self.get_version_info(ai_version)
        no_version = versions.get("NVIDIA Network Operator", "")
        ver_key = _network_operator_version_to_url_key(no_version) if no_version else ""

        if format_type == "json":
            output = {
                "nvidia_ai_enterprise_version": ai_version,
                "infrastructure_software": versions,
                "sources": {
                    "support_matrix": (
                        "https://docs.nvidia.com/ai-enterprise/support-matrix/latest/index.html"
                    ),
                    "doca_component_matrix": (
                        f"https://docs.nvidia.com/networking/display/kubernetes{ver_key}/platform-support.html"
                    ) if ver_key else None,
                },
            }
            return json.dumps(output, indent=2)

        elif format_type == "csv":
            import csv
            from io import StringIO

            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(["Software", "Version"])
            for software, version in versions.items():
                if version is not None:
                    writer.writerow([software, version])
            return output.getvalue()

        else:  # table format
            output = f"\nNVIDIA AI Enterprise {ai_version} - Software Versions:\n"
            output += "=" * 60 + "\n"
            for software, version in versions.items():
                val = version if version is not None else "(run --fetch-live)"
                output += f"  {software:<40} {val}\n"
            if ver_key:
                output += (
                    f"\nDOCA Component Matrix: "
                    f"https://docs.nvidia.com/networking/display/kubernetes{ver_key}/platform-support.html\n"
                )
            return output


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="NVIDIA AI Enterprise Support Matrix Tool"
    )
    parser.add_argument(
        "--format",
        choices=["table", "json", "csv"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--version",
        type=str,
        help="NVIDIA AI Enterprise version (default: from examples)",
    )
    parser.add_argument(
        "--variables",
        type=str,
        default="examples/openshift/operators.ezai.yaml",
        help="Path to variables file",
    )
    parser.add_argument(
        "--versions-only",
        action="store_true",
        help="Show only software versions for the selected AI Enterprise version",
    )
    parser.add_argument(
        "--fetch-live",
        action="store_true",
        help=(
            "Fetch DOCA OFED Driver Container and DOCA Telemetry Service image tags live "
            "from the NVIDIA Network Operator component matrix page. Use when the static "
            "data shows 'run --fetch-live' for those fields."
        ),
    )
    parser.add_argument(
        "--check-updates",
        action="store_true",
        help=(
            "Check NVIDIA AI Enterprise release notes pages for versions not yet in the "
            "local matrix. Use this to detect new releases like 8.2 or 9.0."
        ),
    )
    parser.add_argument(
        "--output-file",
        type=str,
        metavar="PATH",
        help=(
            "Write JSON output to this file instead of stdout. "
            "Status messages still go to stdout. "
            "Useful for Ansible integration (read file, then delete)."
        ),
    )

    args = parser.parse_args()

    if args.check_updates:
        print("Checking NVIDIA AI Enterprise release notes for new versions...")
        new_versions = check_for_new_versions()
        if new_versions:
            print("\n⚠️  New AI Enterprise versions found that are not in the local matrix:")
            for v in new_versions:
                print(f"  - {v}")
            print(
                "\nTo add a new version:\n"
                "  1. Look up component versions at:\n"
                "       https://docs.nvidia.com/ai-enterprise/support-matrix/latest/index.html\n"
                "  2. Add the version block to NVIDIA_SUPPORT_MATRIX in this script.\n"
                "  3. Run: python nvidia_support_matrix.py --fetch-live --version X.Y\n"
                "     to auto-populate DOCA container image tags."
            )
        else:
            print("✓ Local matrix is up to date — no new AI Enterprise versions detected.")
        return

    matrix = NVIDIASupportMatrix(args.variables)

    try:
        if args.versions_only:
            version = args.version or matrix.extract_ai_enterprise_version()
            if args.fetch_live:
                print(f"Fetching live DOCA component data for AI Enterprise {version}...")
                matrix.fetch_live_doca_components(version)
            output = matrix.format_versions(version, args.format)
            print(output)
        else:
            version = args.version
            if args.fetch_live:
                # Determine version for live fetch (from CLI or from variables file)
                matrix.load_variables()
                fetch_ver = version or matrix.extract_ai_enterprise_version()
                print(f"Fetching live DOCA component data for AI Enterprise {fetch_ver}...")
                matrix.fetch_live_doca_components(fetch_ver)
            # Pass --version explicitly so it overrides the variables file
            report = matrix.get_compatibility_report(args.format, ai_version=version)
            if args.output_file:
                output_path = Path(args.output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(report)
                print(f"✓ JSON written to {output_path}")
            else:
                print(report)
    except ValueError as e:
        print(f"\n❌ {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
