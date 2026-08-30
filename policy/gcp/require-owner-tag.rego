# Require an `owner` label on every GCP resource.
package terraform.gcp.governance

import future.keywords.contains
import future.keywords.if

warn contains msg if {
    some change in input.resource_changes
    startswith(change.type, "google_")
    labels := object.get(change.change.after, "labels", {})
    not labels.owner
    msg := sprintf("resource %q is missing required `owner` label", [change.address])
}
