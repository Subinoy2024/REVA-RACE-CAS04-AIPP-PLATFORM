# Require an owner tag on every Azure resource for cost + incident ownership.
package terraform.azure.governance

import future.keywords.contains
import future.keywords.if

warn contains msg if {
    some change in input.resource_changes
    startswith(change.type, "azurerm_")
    tags := object.get(change.change.after, "tags", {})
    not tags.owner
    msg := sprintf("resource %q is missing required `owner` tag", [change.address])
}
