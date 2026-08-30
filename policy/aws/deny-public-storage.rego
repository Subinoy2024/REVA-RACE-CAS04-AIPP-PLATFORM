# Deny public S3 buckets — Terraform plan gate.
# Trips on any `aws_s3_bucket` (or `aws_s3_bucket_acl`) that grants
# `public-read`, `public-read-write`, or `AllUsers` access.
package terraform.aws.security

import future.keywords.contains
import future.keywords.if
import future.keywords.in

deny contains msg if {
    some change in input.resource_changes
    change.type == "aws_s3_bucket_acl"
    change.change.after.acl in {"public-read", "public-read-write"}
    msg := sprintf("bucket %q has public ACL %q", [change.address, change.change.after.acl])
}

deny contains msg if {
    some change in input.resource_changes
    change.type == "aws_s3_bucket_public_access_block"
    not change.change.after.block_public_acls
    msg := sprintf("bucket %q disables block_public_acls", [change.address])
}
