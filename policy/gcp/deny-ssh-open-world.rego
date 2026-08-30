# Deny SSH open to 0.0.0.0/0 on GCP firewall rules.
package terraform.gcp.security

import future.keywords.contains
import future.keywords.if
import future.keywords.in

deny contains msg if {
    some change in input.resource_changes
    change.type == "google_compute_firewall"
    "0.0.0.0/0" in change.change.after.source_ranges
    some allow in change.change.after.allow
    "22" in allow.ports
    msg := sprintf("firewall %q allows SSH from 0.0.0.0/0", [change.address])
}
