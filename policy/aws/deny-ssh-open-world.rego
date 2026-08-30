# Deny SSH open to the world — Terraform plan gate.
# Blocks any security-group rule that opens tcp/22 from 0.0.0.0/0.
package terraform.aws.security

import future.keywords.contains
import future.keywords.if
import future.keywords.in

deny contains msg if {
    some change in input.resource_changes
    change.type == "aws_security_group_rule"
    change.change.after.type == "ingress"
    change.change.after.from_port <= 22
    change.change.after.to_port >= 22
    "0.0.0.0/0" in change.change.after.cidr_blocks
    msg := sprintf("security group %q allows SSH from 0.0.0.0/0", [change.address])
}

deny contains msg if {
    some change in input.resource_changes
    change.type == "aws_security_group"
    some rule in change.change.after.ingress
    rule.from_port <= 22
    rule.to_port >= 22
    "0.0.0.0/0" in rule.cidr_blocks
    msg := sprintf("security group %q opens SSH from 0.0.0.0/0 (inline)", [change.address])
}
