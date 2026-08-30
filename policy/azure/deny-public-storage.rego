# Deny public Azure storage — Terraform plan gate.
# Blocks storage accounts and containers that allow anonymous public access.
package terraform.azure.security

import future.keywords.contains
import future.keywords.if

deny contains msg if {
    some change in input.resource_changes
    change.type == "azurerm_storage_account"
    change.change.after.allow_nested_items_to_be_public == true
    msg := sprintf("storage account %q allows public blobs", [change.address])
}

deny contains msg if {
    some change in input.resource_changes
    change.type == "azurerm_storage_container"
    change.change.after.container_access_type != "private"
    msg := sprintf("container %q access is %q (must be private)",
                   [change.address, change.change.after.container_access_type])
}
