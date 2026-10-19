# Subsystem 01 — Lab deploy / validate

The **lab** deliverable for the Nexus Dashboard section. This is the third
deliverable that this section will eventually publish, alongside the docs
(`docs/`) and automation (`automation/`).

Today this directory is a placeholder. Once the section is exercised end-to-end
in lab, this is where the following will live:

* **Bring-up runbooks** — operator-facing scripts and checklists for spinning a
  3-node ND cluster from cold hardware in a lab pod (cabling, CIMC bootstrap,
  ISO staging on the lab HTTP server, etc.). These are *deploy* artifacts —
  one-shot scaffolding to get the section to a known starting state — and are
  intentionally separate from the repeatable, partner-facing automation under
  `automation/`.
* **Post-deploy validation** — smoke tests that assert the section's outcome
  was actually achieved. For ND: cluster status, node membership, persistent
  IP pool reachability, NTP sync, DNS resolution, NDFC service health.
* **Teardown** — recipes to safely return lab hardware to a re-imageable state
  (`acs reboot factory-reset`, BIOS reset, CIMC reset to factory).
* **Lab fixtures** — pinned credentials (referenced from the operator's secret
  manager, never inline), VLAN/IP plans, switch port mappings, jumbo-frame
  state for the lab pod the engineer is using.

The boundary with `automation/`:

* `automation/` is what a *partner* runs against *their* site. It validates
  inputs against the published JSON Schemas and assumes the site is already
  cabled / DNSed / firewalled.
* `lab/` is what a *Cisco engineer* runs against *their lab pod* to develop,
  reproduce a customer escalation, or regression-test the automation. It is
  free to assume Cisco-internal lab tooling, the macOS Keychain wrapper, and
  the AIPOD lab firewall ACLs.

The boundary with `docs/`:

* `docs/` is the customer-facing CVD chapter (the MOP). It is prose plus
  rendered figures.
* `lab/` is executable. If something here ever needs to be in the chapter, lift
  it into `docs/MOP-ND4-install.md` (with editorial polish), don't link to it.
