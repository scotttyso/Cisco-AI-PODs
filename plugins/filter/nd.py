"""Collection filters for ND inventory mapping and parity snapshots."""
from __future__ import annotations

from ansible_collections.cisco.aipod.plugins.module_utils.shared.lib.inventory import (
    inventory_from_merged_vars,
    resolve_nd_site_services,
)
from ansible_collections.cisco.aipod.plugins.module_utils.shared.lib.nd_baseline import (
    normalize_nd_baseline,
)
from ansible_collections.cisco.aipod.plugins.module_utils.shared.lib.nd_setup import (
    build_nd_setup_args,
)


def aipod_nd_setup_args(
    cluster_spec,
    nodes,
    runtime,
    admin_username,
    admin_pass_ref,
    serial_artifact,
    admin_password,
    cimc_passwords_by_ref,
):
    inv = inventory_from_merged_vars(
        cluster_spec,
        runtime,
        admin_username,
        admin_pass_ref,
        nodes,
    )

    def resolve_cimc(reference):
        try:
            return cimc_passwords_by_ref[reference]
        except KeyError as exc:
            raise ValueError(f"no vaulted CIMC value for {reference}") from exc

    return build_nd_setup_args(
        inv,
        serial_artifact,
        admin_password=admin_password,
        resolve_cimc_password=resolve_cimc,
    )


class FilterModule:
    def filters(self):
        return {
            "aipod_nd_cluster_spec": resolve_nd_site_services,
            "aipod_nd_setup_args": aipod_nd_setup_args,
            "aipod_nd_baseline": normalize_nd_baseline,
        }
