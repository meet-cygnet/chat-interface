# AI-Powered SAST — Implementation Plan

> **Scope boundary**: This is a standalone project, independent of `chat-interface`. It may *reuse patterns* (Pydantic settings, httpx pool, structured logging, retry) but ships as its own repository / package.

---

## Target Architecture (recap)

```
GitHub Actions
   ├── Semgrep ─► SARIF ─► Parser ─► Normalized JSON ─► Fresh Model A ─► Report A
   └── CodeQL  ─► SARIF ─► Parser ─► Normalized JSON ─► Fresh Model B ─► Report B
                                                            │
              ┌─────────────────────────────────────────────┤
              ▼                                             ▼
         Counter Model A (sees B + A + memory + CVE) ─► Refined Report B
         Counter Model B (sees A + B + memory + CVE) ─► Refined Report A
                                                            │
                                                            ▼
                                                   Final Model C (GPT-5.4)
                                                            │
                                                            ▼
                                                     Final Report (MD + JSON + SARIF)
```

All 5 model roles point to the **same Azure Foundry GPT-5.4 deployment** with different system prompts + temperatures.

---

## Phase 0 — Project Scaffolding *(half-day)*

**Goal**: Empty but runnable Python project, separate from `chat-interface`.

- [ ] Create new directory `ai-sast/` (or new repo `ai-sast`).
- [ ] `pyproject.toml` with package name `ai_sast`, Python ≥ 3.11.
- [ ] Dependencies:
  - `httpx[http2]`, `pydantic`, `pydantic-settings`, `python-dotenv`
  - `typer` (CLI), `rich` (pretty output)
  - `pytest`, `pytest-asyncio`, `ruff`, `mypy` (dev)
- [ ] Folder layout:
  ```
  ai-sast/
  ├── src/ai_sast/
  │   ├── __init__.py
  │   ├── cli.py              # typer entrypoint
  │   ├── config.py           # Settings (5 model roles + scanner paths)
  │   ├── logging_config.py
  │   ├── parser/             # Phase 2
  │   ├── ai/                 # Phase 3
  │   ├── memory/             # Phase 4
  │   ├── cve/                # Phase 4
  │   ├── orchestrator.py     # Phase 5
  │   └── report/             # Phase 6
  ├── tests/
  ├── prompts/                # *.md system prompts per role
  ├── samples/                # sample SARIF + normalized fixtures
  ├── .github/workflows/sast.yml
  ├── .env.example
  ├── pyproject.toml
  └── README.md
  ```
- [ ] CLI surface (drafted up front, implemented over phases):
  ```
  ai-sast parse   <sarif.json> -o normalized.json
  ai-sast analyze <normalized.json> --role fresh-a -o report.json
  ai-sast review  --primary B --secondary A -o refined.json
  ai-sast finalize --reports r1,r2,r3,r4 -o final.json
  ai-sast run     --semgrep s.sarif --codeql c.sarif -o final.json   # full pipeline
  ```

**Exit criteria**: `pip install -e .` works; `ai-sast --help` prints all subcommands as stubs.

---

## Phase 1 — Scanners in CI *(1 day)*

**Goal**: Both scanners run on every PR and upload SARIF artifacts.

- [ ] **Semgrep workflow** (`.github/workflows/semgrep.yml`):
  - `semgrep ci --sarif --output semgrep.sarif --config auto`
  - Upload as artifact `semgrep-sarif`.
- [ ] **CodeQL workflow** — already drafted (`.github/workflows/codeql.yml`). Modify to:
  - Add `upload: false` on `analyze@v4` and instead `output: codeql.sarif`.
  - Upload as artifact `codeql-sarif`.
- [ ] **Combine into one workflow** `sast.yml` with two parallel jobs (`semgrep`, `codeql`) feeding a downstream `ai-analysis` job (Phase 5).
- [ ] Pin tool versions for reproducibility.
- [ ] Verify SARIF files are valid (`jq '.runs[0].tool.driver.name'` smoke check in CI).

**Exit criteria**: A PR produces two downloadable SARIF artifacts; both validate against SARIF 2.1.0 schema.

---

## Phase 2 — SARIF Parser & Normalizer *(2 days)*

**Goal**: Convert any Semgrep or CodeQL SARIF into the unified `NormalizedReport` shape defined in `sast-cicd.md`.

- [ ] `src/ai_sast/parser/schema.py` — Pydantic models:
  - `ScanMeta`, `Location`, `DataFlowStep`, `Finding`, `NormalizedReport`.
- [ ] `src/ai_sast/parser/severity.py` — unified severity mapper:
  - Semgrep `ERROR/WARNING/INFO` + CodeQL `error/warning/note` + `security-severity` CVSS → `critical|high|medium|low|info`.
- [ ] `src/ai_sast/parser/fingerprint.py` — `sha256(tool|rule_id|file|normalized_snippet)`; snippet normalization strips whitespace + variable names (light AST-free heuristic).
- [ ] `src/ai_sast/parser/semgrep.py` — `parse_semgrep(sarif: dict) -> NormalizedReport`.
- [ ] `src/ai_sast/parser/codeql.py` — `parse_codeql(sarif: dict) -> NormalizedReport`:
  - Flatten `codeFlows[].threadFlows[].locations[]` into `data_flow` with `source/step/sink` roles (first = source, last = sink, middle = step).
  - Extract CWE from `rule.properties.tags` (entries starting with `external/cwe/cwe-`).
- [ ] `src/ai_sast/parser/__init__.py` — `parse(sarif: dict) -> NormalizedReport` autodetects driver name.
- [ ] CLI: `ai-sast parse` wired up.
- [ ] **Tests** (`tests/parser/`):
  - Golden-file tests with `samples/semgrep.sarif`, `samples/codeql.sarif` → expected normalized JSON.
  - Severity mapping edge cases (missing CVSS, unknown level).
  - Fingerprint stability across whitespace changes.

**Exit criteria**: `ai-sast parse samples/codeql.sarif` produces deterministic, schema-valid normalized JSON; tests pass.

---

## Phase 3 — AI Client + Role Configuration *(1.5 days)*

**Goal**: Single GPT-5.4 client with 5 role-configured "personas".

- [ ] `src/ai_sast/config.py` — Settings extending the chat-interface pattern:
  ```
  FOUNDRY_TARGET_URI=https://<res>.cognitiveservices.azure.com/openai/responses?api-version=2025-04-01-preview
  FOUNDRY_API_KEY=...
  FOUNDRY_DEPLOYMENT=gpt-5.4

  # Per-role temperature overrides (all share the deployment)
  ROLE_FRESH_A_TEMP=0.2
  ROLE_FRESH_B_TEMP=0.2
  ROLE_COUNTER_A_TEMP=0.1   # stricter when challenging
  ROLE_COUNTER_B_TEMP=0.1
  ROLE_FINAL_C_TEMP=0.0     # deterministic consolidation
  ```
- [ ] `src/ai_sast/ai/client.py` — async `FoundryClient` with:
  - Persistent `httpx.AsyncClient` (reuse chat-interface pool pattern).
  - Retry w/ exponential backoff on 429/5xx.
  - Structured request logging (role, tokens, latency).
- [ ] `src/ai_sast/ai/roles.py` — `Role` enum + `RoleConfig` (system prompt path, temperature, max output tokens).
- [ ] `prompts/` — one markdown file per role:
  - `fresh_a.md`, `fresh_b.md` — "You are reviewing a normalized SAST report from <tool>. Identify true positives, classify severity, suggest fixes…"
  - `counter_a.md`, `counter_b.md` — "You are an adversarial reviewer. The primary report below was generated from the *other* scanner. Challenge each finding…"
  - `final_c.md` — "You are the final consolidator. You receive 4 reports. Deduplicate by fingerprint, weigh refinements against originals, output the canonical report…"
- [ ] **Tests**: mock httpx transport, verify each role sends correct system prompt + temperature.

- [ ] **Report output is Markdown + YAML frontmatter** (see `sast-cicd.md` → *Report Format*). Every role — Fresh, Counter, Final — emits the same shape; prompts must instruct the model to follow it exactly.
- [ ] `src/ai_sast/report/markdown_io.py` — `parse_report(md: str) -> ParsedReport` and `render_report(data: ParsedReport) -> str` (~50 LOC, regex-based; YAML via `pyyaml`). Used by Counter and Final stages to read upstream reports.

**Exit criteria**: `ai-sast analyze samples/normalized.json --role fresh-a -o report_a.md` produces a valid Markdown report; `parse_report(open('report_a.md').read())` round-trips without loss of finding IDs / severities.

---

## Phase 4 — Memory + CVE Context *(1.5 days)*

**Goal**: Counter and Final models receive grounded context.

- [ ] **Memory store** (`src/ai_sast/memory/`):
  - SQLite file `.ai-sast/memory.db` committed *outside* the repo (uploaded as workflow artifact + restored per run).
  - Schema: `findings(fingerprint, last_verdict, last_seen_commit, false_positive_count, …)`.
  - On startup, query memory for fingerprints in the current report; inject prior verdicts as prompt context.
  - After Final Model output, persist new verdicts.
- [ ] **CVE context** (`src/ai_sast/cve/`):
  - For each finding with CWE → query NVD API (or local mirror) for recent related CVEs.
  - Cache responses for 24h (`.ai-sast/cve_cache.json`).
  - Inject top-N relevant CVE snippets into Counter + Final prompts.
- [ ] Both modules expose `enrich(report: NormalizedReport) -> EnrichedContext` so the orchestrator stays clean.
- [ ] **Tests**: memory roundtrip, CVE cache TTL, graceful degradation when NVD is unreachable.

**Exit criteria**: A second run of the pipeline on unchanged code reuses memory verdicts and skips re-prompting unchanged fingerprints (optional optimization).

---

## Phase 5 — Orchestrator *(1 day)*

**Goal**: Wire all phases into the dual-track flow.

- [ ] `src/ai_sast/orchestrator.py`:
  ```python
  async def run_pipeline(semgrep_sarif, codeql_sarif) -> FinalReport:
      norm_a, norm_b = parse(semgrep_sarif), parse(codeql_sarif)
      ctx_a = enrich(norm_a)
      ctx_b = enrich(norm_b)

      report_a, report_b = await asyncio.gather(
          analyze(norm_a, Role.FRESH_A, ctx_a),
          analyze(norm_b, Role.FRESH_B, ctx_b),
      )
      refined_b, refined_a = await asyncio.gather(
          review(primary=report_b, secondary=report_a, role=Role.COUNTER_A, ctx=ctx_a),
          review(primary=report_a, secondary=report_b, role=Role.COUNTER_B, ctx=ctx_b),
      )
      final = await finalize([report_a, report_b, refined_b, refined_a], Role.FINAL_C)
      return final
  ```
- [ ] Strict JSON-schema validation on every model output; one retry with "your previous output was invalid JSON, here is the schema, try again" on parse failure.
- [ ] Token + latency metrics emitted per stage.
- [ ] CLI: `ai-sast run --semgrep s.sarif --codeql c.sarif -o final.json`.

**Exit criteria**: End-to-end run on `samples/` produces a valid `FinalReport` in under N minutes.

---

## Phase 6 — Reporting & PR Integration *(1 day)*

**Goal**: Output is consumable by humans and GitHub.

- [ ] `src/ai_sast/report/`:
  - `markdown_io.py` already exists from Phase 3 — reused here.
  - `pr_comment.py` — wraps the **Final Report markdown** with a collapsible per-severity layout suitable for a long PR comment (`<details>` blocks for LOW/INFO).
  - `sarif.py` — convert the parsed final markdown back to **SARIF** so findings show up in GitHub's **Security → Code scanning** tab.
- [ ] **Artifacts uploaded per run** (all 5 markdown files, downloadable from the workflow run):
  - `report_a.md`, `report_b.md`, `refined_a.md`, `refined_b.md`, `final.md`
- [ ] GH Actions `ai-analysis` job:
  - Download both SARIF artifacts.
  - Run `ai-sast run …` (outputs all 5 markdown reports + `final.sarif`).
  - Post the **Final Report markdown** as a sticky PR comment via `actions/github-script` (updated on each push).
  - Optionally post the four intermediate reports as collapsed `<details>` sections under the final one, so reviewers can audit the adversarial chain.
  - Upload `final.sarif` via `github/codeql-action/upload-sarif`.
  - Fail the job if any CRITICAL findings with confidence ≥ 0.8.

**Exit criteria**: A PR shows (a) a sticky AI-SAST comment and (b) findings in the Security tab.

---

## Phase 7 — Hardening & Rollout *(ongoing)*

- [ ] Secrets in GitHub Actions: `FOUNDRY_API_KEY` (never echoed).
- [ ] Budget guardrails: per-run token cap; abort if exceeded.
- [ ] Cost telemetry: log estimated cost per PR.
- [ ] Golden-set regression: a fixed `samples/` repo with known vulnerabilities + expected final report; CI fails if AI output drifts beyond a tolerance.
- [ ] Prompt versioning: each prompt file gets a header `# version: 3` recorded in the final report for reproducibility.
- [ ] Docs: README with diagram (copy from `sast-cicd.md`), env var reference, troubleshooting.

---

## Effort Summary

| Phase | Deliverable | Est. effort |
|------:|-------------|-------------|
| 0 | Scaffolding | 0.5 d |
| 1 | Scanners in CI | 1 d |
| 2 | SARIF parser | 2 d |
| 3 | AI client + roles | 1.5 d |
| 4 | Memory + CVE | 1.5 d |
| 5 | Orchestrator | 1 d |
| 6 | Reporting + PR | 1 d |
| 7 | Hardening | ongoing |
| **Total to MVP** | Phases 0–6 | **~8.5 days** |

---

## Open Decisions (need your input before Phase 0)

1. **Repo strategy** — new repo `ai-sast`, or subfolder `ai-sast/` inside this workspace?
2. **CVE source** — NVD public API (rate-limited, free) or a paid feed (Vulners, Snyk DB)?
3. **Memory persistence** — workflow artifact (simple, ephemeral-ish) or a GitHub-hosted branch / external storage?
4. **Failure policy** — should AI-SAST *block* merges on CRITICAL, or always advisory?
5. **Languages** — Python only for now (matches your CodeQL workflow), or multi-language from day 1?
