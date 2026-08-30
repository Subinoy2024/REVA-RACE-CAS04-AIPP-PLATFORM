# Evaluation Corpus - "20+ Public Git Repositories"

This document explains what the "20+ public Git repositories" mentioned
in **Objective 4** of the proposal actually refers to, why we picked
that number, and how the evaluation is run.

---

## 1. What the "20+" refers to

It is the **evaluation dataset**. A curated set of real, open-source
GitHub repositories that we run AIPP on, so we can prove it actually
works and compare it against baseline systems.

We don't just claim "AIPP generates good pipelines". We prove it by
running AIPP plus two baseline systems on the same 20+ repos and
comparing the results side by side. This is what turns the project from
a demo into a research contribution.

The evaluation is run through `tests/research/run_batch.py`, and the
metrics per repo per variant are stored in the `research_experiments`
PostgreSQL table via `POST /api/research/experiments`.

---

## 2. Why 20, and not 5 or 100

| Reason | Explanation |
|--------|-------------|
| Statistical validity | Below 15 or 20 samples the results are anecdotal. Reviewers will say "you got lucky on those 5 repos". 20+ is the accepted minimum for a small-scale empirical software engineering study. |
| Diversity coverage | We need to cover different languages, sizes and architectures. 20 gives us roughly 3-4 repos per category. |
| Budget realism | Each repo runs through 3 variants (static / LLM-only / AIPP) which is 60 runs. At Claude Sonnet pricing that is about $10-15 total. 100 repos would need 300 runs and blow the student budget. |
| Thesis timeline | Manual labelling of ground truth (correct language, correct architecture, correct pipeline) for 20 repos takes about a weekend. 100 repos would take a month. |

---

## 3. What kind of repos are in the 20+

The idea is to pick a mix so the evaluation is fair across the kind of
projects we see in real work.

| # | Category | Example public repos |
|---|----------|----------------------|
| 1-4 | Python monoliths | `psf/requests`, `pallets/flask`, `tiangolo/fastapi`, `encode/django-rest-framework` |
| 5-8 | JS / TS frontend and backend | `expressjs/express`, `nestjs/nest`, `vercel/next.js`, `strapi/strapi` |
| 9-11 | Java Spring Boot | `spring-projects/spring-petclinic`, `spring-projects/spring-boot`, `Netflix/eureka` |
| 12-13 | Go services | `gin-gonic/gin`, `traefik/traefik` |
| 14-15 | Rust | `tokio-rs/tokio`, `actix/actix-web` |
| 16-17 | Microservices (multi-repo / mono-repo) | `GoogleCloudPlatform/microservices-demo`, `dotnet-architecture/eShopOnContainers` |
| 18 | Serverless (AWS Lambda / Azure Functions) | `aws-samples/serverless-patterns` |
| 19 | Repo with existing Dockerfile | Any of the above that already ships a Dockerfile |
| 20 | Repo without Dockerfile | A pure library repo. Tests whether AIPP can still generate a build pipeline. |
| 21+ | Buffer / edge cases | A monorepo, a repo with no tests, a repo with Helm charts |

---

## 4. What happens for each repo

For every one of the 20 repos, we run 3 variants side by side.

```
Repo: pallets/flask
  |
  |-- Variant A: static_template   -> uses a hard-coded YAML template
  |-- Variant B: generic_llm       -> sends one big prompt to Claude
  |-- Variant C: aipp              -> 8-agent workflow + validators + MCP
```

For each variant we measure the 7 metrics from Objective 4:

| Metric | What it measures | Example (Flask repo) |
|--------|------------------|----------------------|
| Language detection accuracy | Did the system correctly say Flask is Python? | Static = N/A, LLM = correct, AIPP = correct |
| YAML syntax validity | Does `yamllint` pass on the output? | Static = pass, LLM = fail, AIPP = pass |
| Platform validity | Does GitHub Actions accept the file? | Static = pass, LLM = fail (invented step), AIPP = pass |
| Environment trigger correctness | Is Production gated behind approval? | Static = missing, LLM = missing, AIPP = present |
| Generation time | Wall-clock seconds | Static = 0.5s, LLM = 8s, AIPP = 22s |
| Hallucination rate | Did the RCA cite log lines that don't exist? | Static = N/A, LLM = 3, AIPP = 0 |
| Manual corrections needed | Lines an engineer must fix by hand | Static = 15, LLM = 8, AIPP = 2 |

Then we aggregate across all 20 repos and get numbers like:

> *AIPP produces valid pipelines in 94% of cases, compared to 72% for
> single-prompt LLM and 58% for static templates. Average manual
> corrections per pipeline: 2.1 (AIPP), 8.4 (LLM), 15.3 (static).*

That table is the main thesis result. It is what the reviewer wants to
see.

---

## 5. Where this lives in the code

You already have most of the infrastructure in place:

- `tests/research/run_batch.py` - the batch runner (the corpus list is
  not fully populated yet).
- `research_experiments` PostgreSQL table - stores metrics per repo per
  variant.
- `POST /api/research/experiments` - writes results into the table.
- The **Compare Mode** tab in the Gradio UI - runs all 3 variants on
  any single repo interactively, so you can smoke-test the pipeline
  without needing to run the full batch.

The 20-repo batch itself is currently on the P1 backlog because it
needs an LLM budget to actually execute (60 LLM runs). Once we have
that budget, we fill in the repo list, run the batch script, and pandas
produces the comparison charts.

---

## 6. Common follow-up questions

**Can I use fewer than 20?**
Yes, but say so honestly in the thesis ("preliminary evaluation on N
repos") and mark it as a limitation. Reviewers accept smaller pilots
as long as they are transparent.

**Can I use private or internal repos?**
Better to stick to public ones so the study is reproducible. If you
must use a private one, at least redact the identifying details.

**What if my LLM budget runs out mid-way?**
Cache all LLM responses to disk on the first run. Reruns become free
after that. The `run_batch.py` script has a `--cache` flag for this.

**What if a repo already has a working CI/CD file?**
Even better. We can compare AIPP's generated YAML against the
hand-written one and use the hand-written one as ground truth.

---

## 7. Next step

The next task is to write the actual list of 20 repos into
`tests/research/corpus.yaml` so it is ready for the moment we have LLM
budget. That file will look roughly like this:

```yaml
corpus:
  - name: flask
    url: https://github.com/pallets/flask
    language: python
    architecture: library
    has_dockerfile: false
  - name: fastapi
    url: https://github.com/tiangolo/fastapi
    language: python
    architecture: library
    has_dockerfile: false
  # ... 18 more entries
```

Ping me when you want this file created and I will populate all 20
entries.
