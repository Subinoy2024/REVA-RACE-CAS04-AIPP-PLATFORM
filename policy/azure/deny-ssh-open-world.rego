# Deny SSH open to the world on Azure NSGs.
package terraform.azure.security

import future.keywords.contains
import future.keywords.if

deny contains msg if {
    some change in input.resource_changes
    change.type == "azurerm_network_security_rule"
    change.change.after.access == "Allow"
    change.change.after.direction == "Inbound"
    change.change.after.destination_port_range == "22"
    change.change.after.source_address_prefix == "*"
    msg := sprintf("NSG rule %q allows SSH from *", [change.address])
}
