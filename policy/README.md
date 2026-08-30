# AIPP · OPA Policy Starter Bundle

Drop the files from this directory into your target repo's `./policy/`
folder to make the AIPP-generated **Terraform pipelines** actually enforce
policy in the `policy` stage (stage 3 of 5).

## What's in here

```
policy/
├── README.md
├── aws/     ← AWS-specific Rego rules
├── azure/   ← Azure-specific Rego rules
└── gcp/     ← GCP-specific Rego rules
```

Every `.rego` file targets `data.terraform.plan.resource_changes` — the
JSON shape produced by `terraform show -json` and consumed by
[`conftest`](https://www.conftest.dev/).

## How it's wired

Every AIPP-generated **infra** pipeline (Azure DevOps, GitHub Actions,
GitLab CI, Harness, Tekton) has a **stage 3 · policy** step that:

1. Downloads and installs `conftest`.
2. Runs `conftest test plan.json` **only if** `./policy/*.rego` exists in
   the repo.
3. Fails the build on any `deny` rule match.

If your repo does not ship any `.rego` file, the step logs
*"no policy dir — skipping"* and moves on. Copying this bundle **turns
on** the gate.

## Recommended starter set

Every cloud folder ships four rules that cover the OWASP-style basics:

| Rule | Effect |
|------|--------|
| `deny-public-storage.rego` | Block `public-read` / `AllUsers` buckets |
| `deny-ssh-open-world.rego` | Block security-group ingress on port 22 from `0.0.0.0/0` |
| `require-encryption.rego` | Require storage encryption at rest |
| `require-owner-tag.rego`   | Every resource must carry an `owner` tag |

These are **defaults, not commandments** — override or extend them for
your organisation. Rego files are plain text; keep them under version
control alongside your `.tf` code.

## Reference

- Terraform plan JSON schema: <https://developer.hashicorp.com/terraform/internals/json-format>
- conftest: <https://www.conftest.dev/>
- OPA / Rego language: <https://www.openpolicyagent.org/docs/latest/policy-language/>
