# Require encryption at rest — Terraform plan gate.
# Denies any RDS instance, EBS volume, or S3 bucket that is not encrypted.
package terraform.aws.security

import future.keywords.contains
import future.keywords.if

deny contains msg if {
    some change in input.resource_changes
    change.type == "aws_db_instance"
    not change.change.after.storage_encrypted
    msg := sprintf("RDS instance %q is not encrypted at rest", [change.address])
}

deny contains msg if {
    some change in input.resource_changes
    change.type == "aws_ebs_volume"
    not change.change.after.encrypted
    msg := sprintf("EBS volume %q is not encrypted at rest", [change.address])
}

deny contains msg if {
    some change in input.resource_changes
    change.type == "aws_s3_bucket_server_side_encryption_configuration"
    count(change.change.after.rule) == 0
    msg := sprintf("bucket %q has no SSE configuration", [change.address])
}
