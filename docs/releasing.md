# Releases and Updates

## Publish a Release

Releases are created from version tags, not from every push to `main`. The
`Publish release` GitHub Actions workflow verifies that the tag uses
`vMAJOR.MINOR.PATCH` (optionally with a pre-release suffix such as `-rc.1`),
that `VERSION` matches the tag, and that the tagged commit is on `main`. It then
runs the appliance updater and WebUI tests and publishes a GitHub release with
generated notes. Tags with a suffix are published as pre-releases and are not
offered by the WebUI update check.

Before tagging, merge reviewed changes to `main`, run the tests, and set
`VERSION` to the exact tag you plan to publish:

```bash
printf '%s\n' v0.1.0 > VERSION
git add VERSION
git commit -m "Prepare v0.1.0 release"
git push origin main
git tag -a v0.1.0 -m "Cisco AI PODs v0.1.0"
git push origin v0.1.0
```

Use semantic versions: patch for fixes, minor for compatible features, and major
for incompatible behavior or state migrations. Never move or reuse a published
tag; appliances refuse to update when a local tag differs from GitHub. Confirm the
workflow succeeds before announcing a release.

## Install a Release

Any signed-in user can select the **Check for software updates** button in the
WebUI header. The dialog reads public GitHub release metadata (no token is stored
on the server) and shows the release notes. When a newer release exists, either:

- Select **Install vX.Y.Z now** (standard appliance and bare-metal installs, where
  `/usr/local/sbin/aipod-update` exists). The UI refuses while any automation job
  is running, asks you to type `UPDATE`, and asks for the local sudo password only
  when the service account does not have passwordless sudo (the password is used
  once and never saved). It starts the updater as its own transient systemd unit
  (`systemd-run --unit aipod-update-<version>-<timestamp>`) so it survives the UI
  service being stopped, and streams `/var/log/aipod-update/<unit>.log` until the
  UI restarts. The page reconnects when the service is back; the dialog's
  **Last update log** shows the result.
- Or run the displayed command from an administrative shell after finishing active
  playbooks, uploads, and terminal work in the repository:

```bash
sudo /usr/local/sbin/aipod-update --version vX.Y.Z
```

The updater:

1. Validates the standard installation (service user, repository location,
   official `origin`, and no local changes to tracked files).
2. Resolves the release tag on GitHub as root, downloads the root-executed files
   (updater, systemd unit, and `aipod-config` when installed) for that exact
   commit, and confirms the fetched tag matches GitHub and is on `main`.
3. Asks you to type `UPDATE` (the WebUI asks first and passes `--yes`), then stops
   `automation-ui.service`.
4. Backs up the previous commit ID, UI accounts/state, generated playbook
   variables, and system configuration to `/var/backups/aipod-update-*`. ISO
   media is not backed up.
5. Checks out the release, reruns `scripts/setup.sh --skip-apt --skip-iserver`,
   installs the WebUI requirements, verifies the application imports, installs
   the system files, and waits for the service to become healthy.

If any step fails after the outage starts, the service is left stopped and the
updater prints manual recovery commands. No automatic rollback is attempted.
Untracked files such as `.venv`, `LOGS`, and `assisted-installer` are preserved.

### Bootstrap Older Installations

Appliances built before the updater existed do not have
`/usr/local/sbin/aipod-update`. Install it once from the release you intend to
deploy, review it, then run it:

```bash
tag=v0.1.0
curl -fsSLo /tmp/aipod-update \
  "https://raw.githubusercontent.com/scotttyso/Cisco-AI-PODs/${tag}/automation-appliance/files/aipod-update"
less /tmp/aipod-update
sudo install -o root -g root -m 0755 /tmp/aipod-update /usr/local/sbin/aipod-update
sudo /usr/local/sbin/aipod-update --version "$tag"
```

Installations cloned from a fork, using a custom service user or path, or with a
non-default backend address must be updated manually.
