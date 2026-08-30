# Require encryption on GCS + Cloud SQL (customer-managed KMS preferred,
# but Google-managed keys are always on, so we just enforce Cloud SQL TDE).
package terraform.gcp.security

import future.keywords.contains
import future.keywords.if

deny contains msg if {
    some change in input.resource_changes
    change.type == "google_sql_database_instance"
    change.change.after.settings[0].disk_encryption_configuration == null
    change.change.after.encryption_key_name == null
    msg := sprintf("Cloud SQL instance %q has no encryption_key configuration", [change.address])
}
