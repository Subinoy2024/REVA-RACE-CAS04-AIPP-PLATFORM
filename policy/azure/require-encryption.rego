# Require encryption at rest on Azure managed disks + SQL.
package terraform.azure.security

import future.keywords.contains
import future.keywords.if

deny contains msg if {
    some change in input.resource_changes
    change.type == "azurerm_managed_disk"
    change.change.after.encryption_settings == null
    msg := sprintf("managed disk %q missing encryption_settings", [change.address])
}

deny contains msg if {
    some change in input.resource_changes
    change.type == "azurerm_mssql_database"
    change.change.after.transparent_data_encryption_enabled == false
    msg := sprintf("SQL DB %q has TDE disabled", [change.address])
}
