# Deny public GCS buckets — Terraform plan gate.
package terraform.gcp.security

import future.keywords.contains
import future.keywords.if
import future.keywords.in

deny contains msg if {
    some change in input.resource_changes
    change.type == "google_storage_bucket_iam_member"
    change.change.after.member in {"allUsers", "allAuthenticatedUsers"}
    msg := sprintf("bucket IAM %q grants access to %q",
                   [change.address, change.change.after.member])
}
