# Require owner tag on every resource — Terraform plan gate.
# Every taggable AWS resource must carry an `owner` tag so cost + incident
# ownership can be tracked. Warn (not deny) so the pipeline can still ship.
package terraform.aws.governance

import future.keywords.contains
import future.keywords.if

warn contains msg if {
    some change in input.resource_changes
    startswith(change.type, "aws_")
    tags := object.get(change.change.after, "tags", {})
    not tags.owner
    msg := sprintf("resource %q is missing required `owner` tag", [change.address])
}
