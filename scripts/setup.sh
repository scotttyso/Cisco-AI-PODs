#!/usr/bin/env bash
set -euo pipefail

# Complete setup for Cisco AI PODs environment and iServer.
# This script prepares the development environment and downloads iServer for OpenShift assisted installer.

VENV_DIR_DEFAULT=".venv"
ISERVER_OUTPUT_DEFAULT="assisted-installer"

VENV_DIR="${VENV_DIR:-$VENV_DIR_DEFAULT}"
ISERVER_OUTPUT="${ISERVER_OUTPUT:-$ISERVER_OUTPUT_DEFAULT}"
GIT_USER_NAME="${GIT_USER_NAME:-}"
GIT_USER_EMAIL="${GIT_USER_EMAIL:-}"
SKIP_APT="${SKIP_APT:-0}"
SKIP_ENV_SETUP="${SKIP_ENV_SETUP:-0}"
SKIP_ISERVER="${SKIP_ISERVER:-0}"

GITHUB_API="https://api.github.com/repos/datacenter/iserver/releases/latest"

usage() {
    cat <<EOF
Usage: $0 [options]

This script performs a complete setup for Cisco AI PODs development environment
and downloads the latest iServer release.

Options:
  --git-name <name>         Configure git user.name
  --git-email <email>       Configure git user.email
  --venv-dir <path>         Virtual environment path (default: ${VENV_DIR_DEFAULT})
  --iserver-dir <path>      iServer output directory (default: ${ISERVER_OUTPUT_DEFAULT})
  --skip-apt                Skip apt-based package installation
  --skip-env-setup          Skip environment preparation (venv, ansible, dependencies)
  --skip-iserver            Skip iServer download
  -h, --help                Show this help

Environment variable equivalents:
  GIT_USER_NAME, GIT_USER_EMAIL, VENV_DIR, ISERVER_OUTPUT,
  SKIP_APT=1, SKIP_ENV_SETUP=1, SKIP_ISERVER=1

Optional GitHub authentication (to avoid rate limiting):
  GITHUB_TOKEN=<your-pat>   Personal Access Token for higher GitHub API rate limits
                            Generate at: https://github.com/settings/tokens
EOF
}

log() {
    printf "\n[INFO] %s\n" "$*"
}

warn() {
    printf "\n[WARN] %s\n" "$*"
}

die() {
    printf "\n[ERROR] %s\n" "$*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --git-name)
            GIT_USER_NAME="$2"
            shift 2
            ;;
        --git-email)
            GIT_USER_EMAIL="$2"
            shift 2
            ;;
        --venv-dir)
            VENV_DIR="$2"
            shift 2
            ;;
        --iserver-dir)
            ISERVER_OUTPUT="$2"
            shift 2
            ;;
        --skip-apt)
            SKIP_APT=1
            shift
            ;;
        --skip-env-setup)
            SKIP_ENV_SETUP=1
            shift
            ;;
        --skip-iserver)
            SKIP_ISERVER=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1"
            ;;
    esac
done

# ============================================================================
# ENVIRONMENT SETUP
# ============================================================================

if [[ "$SKIP_ENV_SETUP" != "1" ]]; then
    log "=== ENVIRONMENT SETUP ==="

    if [[ "$SKIP_APT" != "1" ]]; then
        if command -v apt >/dev/null 2>&1; then
            log "Installing Git and Python system packages with apt"
            sudo apt update
            sudo apt install -y git python3 python3-pip python3-venv
        elif command -v dnf >/dev/null 2>&1; then
            log "Installing Git and Python system packages with dnf"
            sudo dnf install -y git python3 python3-pip python3-venv
        elif command -v yum >/dev/null 2>&1; then
            log "Installing Git and Python system packages with yum"
            sudo yum install -y git python3 python3-pip python3-venv
        else
            warn "No supported package manager found (apt, dnf, or yum); skipping OS package install"
        fi
    else
        log "Skipping package manager installation"
    fi

    log "Validating Git and Python availability"
    command -v git >/dev/null 2>&1 || die "git is not installed or not in PATH"
    command -v python3 >/dev/null 2>&1 || die "python3 is not installed or not in PATH"

    git --version
    python3 --version

    if [[ -n "$GIT_USER_NAME" ]]; then
        log "Configuring git user.name"
        git config --global user.name "$GIT_USER_NAME"
    fi

    if [[ -n "$GIT_USER_EMAIL" ]]; then
        log "Configuring git user.email"
        git config --global user.email "$GIT_USER_EMAIL"
    fi

    if [[ -d "$PWD/.git" && -f "$PWD/requirements.txt" && -f "$PWD/requirements.yaml" ]]; then
        WORKDIR="$PWD"
    else
        die "Run this script from the Cisco-AI-PODs repository root (where requirements.txt and requirements.yaml exist)"
    fi

    log "Using repository directory: ${WORKDIR}"

    # Resolve venv path relative to repository root when a relative path is provided.
    if [[ "$VENV_DIR" != /* ]]; then
        VENV_DIR="${WORKDIR}/${VENV_DIR}"
    fi

    # Normalize possible trailing slash for safe path comparisons.
    WORKDIR_NORMALIZED="${WORKDIR%/}"
    VENV_DIR_NORMALIZED="${VENV_DIR%/}"
    if [[ "$VENV_DIR_NORMALIZED" == "$WORKDIR_NORMALIZED" ]]; then
        warn "--venv-dir points to repository root; using ${WORKDIR}/.venv instead"
        VENV_DIR="${WORKDIR}/.venv"
    fi

    TOOLING_CONSTRAINTS_FILE="${WORKDIR}/constraints/python-tooling.txt"

    log "Creating virtual environment at ${VENV_DIR}"
    python3 -m venv "$VENV_DIR"

    # shellcheck disable=SC1090
    source "${VENV_DIR}/bin/activate"

    log "Upgrading pip tooling"
    python3 -m pip install --upgrade pip setuptools wheel

    # Remove meta-package ansible if present to avoid ansible-core pin conflicts on Python 3.14.
    if python3 -m pip show ansible >/dev/null 2>&1; then
        log "Removing ansible meta-package to prevent ansible-core version conflicts"
        python3 -m pip uninstall -y ansible
    fi

    if [[ -f "$TOOLING_CONSTRAINTS_FILE" ]]; then
        log "Installing Ansible tooling with constraints from ${TOOLING_CONSTRAINTS_FILE}"
        python3 -m pip install -c "$TOOLING_CONSTRAINTS_FILE" ansible-core ansible-lint tox
    else
        warn "Constraints file not found at ${TOOLING_CONSTRAINTS_FILE}; using fallback ranges"
        python3 -m pip install "ansible-core>=2.20,<2.21" "ansible-lint>=26,<27" tox
    fi

    log "Installing Python dependencies"
    python3 -m pip install -r "${WORKDIR}/requirements.txt"

    log "Verifying key Python dependencies"
    python3 -m pip show purestorage py-pure-client kubernetes openshift >/dev/null
    python3 -m pip show purestorage py-pure-client kubernetes openshift | awk '/^Name:|^Version:/{print}'

    log "Installing Ansible collections"
    ansible-galaxy collection install -r "${WORKDIR}/requirements.yaml"

    log "Verifying installed collections"
    ansible-galaxy collection list | grep -E "kubernetes.core|purestorage.flasharray|purestorage.flashblade|ansible.posix" || true

    log "Ansible version"
    ansible --version
    
    cat <<EOF

================================
Environment setup complete
================================
To reactivate this virtual environment later:
source "${VENV_DIR}/bin/activate"

EOF

fi

# ============================================================================
# iSERVER DOWNLOAD AND SETUP
# ============================================================================

if [[ "$SKIP_ISERVER" != "1" ]]; then
    log "=== iSERVER DOWNLOAD AND SETUP ==="

    # Ensure output directory exists
    if [[ ! -d "$ISERVER_OUTPUT" ]]; then
        log "Creating iServer output directory: ${ISERVER_OUTPUT}"
        mkdir -p "$ISERVER_OUTPUT"
    fi

    log "Checking for existing iServer Linux archive in ${ISERVER_OUTPUT}"
    existing_archive=""
    if [[ -d "$ISERVER_OUTPUT" ]]; then
        for archive in "$ISERVER_OUTPUT"/*.tar.gz; do
            if [[ -f "$archive" ]]; then
                archive_lower=$(echo "$archive" | tr '[:upper:]' '[:lower:]')
                if [[ "$archive_lower" == *"iserver"* ]] && [[ "$archive_lower" == *"linux"* ]]; then
                    existing_archive="$archive"
                    break
                fi
            fi
        done
    fi

    if [[ -n "$existing_archive" ]]; then
        log "Using existing iServer Linux archive: ${existing_archive}"
        archive_path="$existing_archive"
    else
        log "Fetching latest iServer release metadata from GitHub"

        curl_headers=(
            -H "Accept: application/vnd.github+json"
            -H "User-Agent: iserver-installer-downloader"
        )
        if [[ -n "${GITHUB_TOKEN:-}" ]]; then
            curl_headers+=( -H "Authorization: token ${GITHUB_TOKEN}" )
        fi

        release_data="$(curl -sS "${curl_headers[@]}" "$GITHUB_API" 2>&1 || true)"
        [[ -n "$release_data" ]] || die "Failed to fetch latest release metadata from ${GITHUB_API}"

        # Debug output
        resp_length=${#release_data}
        resp_first_50="${release_data:0:50}"
        resp_last_50="${release_data:$((resp_length-50)):50}"
        log "DEBUG: Response length=$resp_length | First 50: $resp_first_50 | Last 50: $resp_last_50"

        # Debug: check if response looks like JSON
        if [[ ! "$release_data" =~ ^\{ ]]; then
            response_preview="${release_data:0:300}"
            die "GitHub API response is not JSON. First 300 chars: ${response_preview}"
        fi

        # Use temp file for Python script to avoid stdin issues with heredoc in command substitution
        python_script=$(mktemp)
        cat > "$python_script" <<'PYSCRIPT'
import json, sys
try:
    raw = sys.stdin.read()
    if not raw.strip():
        print("json-error:empty stdin")
        sys.exit(0)
    payload = json.loads(raw)
except json.JSONDecodeError as e:
    print(f"json-error:JSONDecodeError at {e.pos}: {str(e)}")
    sys.exit(0)
except Exception as e:
    print(f"json-error:{str(e)}")
    sys.exit(0)
msg = payload.get("message", "") if isinstance(payload, dict) else ""
print(msg)
PYSCRIPT

        api_error_message="$(printf '%s' "$release_data" | python3 "$python_script")"
        rm -f "$python_script"

        if [[ "$api_error_message" == json-error:* ]]; then
            error_detail="${api_error_message#json-error:}"
            response_preview="${release_data:0:500}"
            die "GitHub API JSON parse error: ${error_detail}. Full response: ${response_preview}"
        fi

        if [[ -n "$api_error_message" ]]; then
            if [[ "$api_error_message" == *"API rate limit exceeded"* ]]; then
                die "GitHub API rate limit exceeded. Export GITHUB_TOKEN with a GitHub PAT and re-run setup.sh"
            fi
            die "Failed to fetch latest release metadata: ${api_error_message}"
        fi

        # Use temp file for Python script to extract asset URL from release data
        python_script=$(mktemp)
        cat > "$python_script" <<'PYSCRIPT'
import json, sys
try:
    payload = json.load(sys.stdin)
    assets = payload.get("assets", []) if isinstance(payload, dict) else []
    preferred = []
    fallback = []
    for asset in assets:
        name = str(asset.get("name", ""))
        url = str(asset.get("browser_download_url", ""))
        low = name.lower()
        if not url or not low.endswith(".tar.gz"):
            continue
        if "linux" in low:
            preferred.append((url, name))
        elif all(token not in low for token in ("windows", "darwin", "mac", "osx")):
            fallback.append((url, name))
    selected = preferred[0] if preferred else (fallback[0] if fallback else None)
    if not selected:
        sys.exit(1)
    print(f"{selected[0]}\t{selected[1]}")
except Exception as e:
    print(f"Asset extraction failed: {str(e)}", file=sys.stderr)
    sys.exit(1)
PYSCRIPT

        release_asset="$(printf '%s' "$release_data" | python3 "$python_script")" || die "No suitable .tar.gz asset found in latest datacenter/iserver release"
        rm -f "$python_script"

        IFS=$'\t' read -r download_url asset_name <<< "$release_asset"
        [[ -n "$download_url" && -n "$asset_name" ]] || die "Failed to parse iServer release asset metadata"

        archive_path="${ISERVER_OUTPUT}/${asset_name}"
        log "Downloading iServer release from: ${download_url}"

        if ! curl -fL -sS "${curl_headers[@]}" -o "$archive_path" "$download_url"; then
            die "Failed to download ${asset_name}"
        fi

        log "Downloaded: ${archive_path}"
    fi

    log "Extracting iServer archive to: ${ISERVER_OUTPUT}"
    if ! tar -xzf "$archive_path" -C "$ISERVER_OUTPUT"; then
        die "Failed to extract ${archive_path}"
    fi

    log "iServer setup complete!"
    log "Output directory: ${ISERVER_OUTPUT}"
    log ""
    log "Next steps:"
    log "1. Review the iServer documentation: https://github.com/datacenter/iserver/blob/main/doc/ocp/Console.md"
    log "2. Configure iServer for OpenShift assisted installer deployment"

fi

# ============================================================================
# SUMMARY
# ============================================================================

cat <<EOF

================================
Setup Complete
================================

Virtual environment (if enabled):
  source "${VENV_DIR}/bin/activate"

iServer directory (if enabled):
  ${ISERVER_OUTPUT}/

Environment preparation is complete.

Manual steps from the guide that remain:
1. iServer Setup:
    - After setup completes, follow the iServer Console configuration guide:
      https://github.com/datacenter/iserver/blob/main/doc/ocp/Console.md
2. Install Visual Studio Code (if not installed): https://code.visualstudio.com/Download
3. Install VS Code extensions:
   - GitHub Pull Requests and Issues (GitHub)
   - Pylance (Microsoft)
   - Python (Microsoft)
   - YAML (Red Hat)
4. Add YAML schema mapping in VS Code settings.json:
   "yaml.schemas": {
     "https://raw.githubusercontent.com/scotttyso/Cisco-AI-PODs/main/schema/cisco-ai-pods.json": "*.ezai.yaml"
   }

EOF
