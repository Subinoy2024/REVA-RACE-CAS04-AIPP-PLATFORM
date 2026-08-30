# AIPP Research Methodology

This document describes the evaluation protocol that ships with AIPP.

## 1. Research questions

1. Does repository-aware, multi-agent pipeline generation produce more accurate
   pipelines than static templates or single-prompt LLM generation?
2. Does an evidence-grounded RCA agent reduce hallucination compared with a
   naïve "explain this log" prompt?

## 2. Comparison groups

Three variants are stored side-by-side in `research_experiments`:

- `static_template` — hand-authored templates only
- `generic_llm` — single-prompt LLM generation, no repository scan, no validators
- `aipp` — the full AIPP workflow

Add an experiment result via:

```
POST /api/research/experiments
{
  "experiment_type": "aipp",
  "ci_platform": "github_actions",
  "repository_url": "https://github.com/foo/bar",
  "metrics": {
      "language_detection_correct": true,
      "yaml_syntax_valid": true,
      "platform_schema_valid": true,
      "env_trigger_correct": true,
      "manual_corrections": 1,
      "generation_seconds": 27.6,
      "user_effort_delta_minutes": -35
   },
   "notes": "SonarQube + Trivy requested via custom requirement"
}
```

## 3. Metrics captured

| Metric                                   | Where                              |
|------------------------------------------|------------------------------------|
| Repository technology-detection accuracy | Agent output vs ground truth       |
| Pipeline syntax-validity rate            | `YAMLValidator`                    |
| Pipeline platform validity               | `PlatformValidator`                |
| Pipeline completeness                    | Manual review                      |
| Env-trigger accuracy                     | `EnvironmentValidator` + review    |
| Manual corrections                       | Recorded per experiment            |
| Generation time                          | `PipelineRun.generation_seconds`   |
| RCA accuracy                             | Manual review + confidence         |
| RCA evidence quality                     | Evidence lines vs log              |
| Hallucination rate                       | Inferences without evidence anchor |
| User effort reduction                    | Delta vs `static_template`         |

## 4. Evaluation dataset

Use a curated set of at least 20 Git repositories covering:

- Language: Python, JavaScript/TypeScript, Java, Go, Rust
- Architecture: monolith, microservice, library, serverless
- Container-readiness: with and without a Dockerfile
- IaC: with Terraform, Pulumi, or none
- Existing CI: fresh repositories and repositories with prior CI

Group results by these dimensions to see where AIPP wins or loses.

## 5. Running an evaluation batch

```
python -m tests.research.run_batch --input repos.csv --variant aipp
```

The runner iterates the CSV, calls the API for each variant, and inserts
records into `research_experiments`. Downstream analysis lives in
`tests/research/analyze.ipynb` (not committed).

## 6. Reporting

Query aggregate metrics via:

```
GET /api/research/experiments
GET /api/research/metrics
```

or pull directly from PostgreSQL for offline notebooks.
