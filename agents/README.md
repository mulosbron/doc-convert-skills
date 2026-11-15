# Document Conversion Agents (`doc-convert-skills`)

Specialized agent roles for hardware-aware OCR and multi-document conversion pipelines.

## Execution Topology

```text
[1. doc-profiler-agent]  (Sequential: reads device specs + inspects docs + sets worker budget)
          │
          ▼
[2. batch-orchestrator-agent]
     ├── if orchestration.execution_mode == "sequential" (e.g. 8 GB GPU OCR):
     │      runs [ocr-conversion-worker] one file/chunk at a time
     └── if orchestration.execution_mode == "parallel_subagents" (CPU / API / vLLM):
            fans out up to `max_parallel_workers` [ocr-conversion-worker] subagents
          │
          ▼
[3. fidelity-validator-agent]  (Checks quality gates, repairs noise, triggers targeted retry)
```

## Agent Roster

| Agent Spec | Role | Parallelism |
|---|---|---|
| [doc-profiler-agent.md](./doc-profiler-agent.md) | Hardware probe, installed tool audit, PDF digital-vs-scanned classification, route recommendation | Single upfront pass |
| [batch-orchestrator-agent.md](./batch-orchestrator-agent.md) | Coordinates sequential vs hardware-bounded parallel subagent execution | Coordinator |
| [ocr-conversion-worker.md](./ocr-conversion-worker.md) | Executes the assigned conversion engine on 1 file or page range | Sequential (GPU) or Parallel (CPU/API) |
| [fidelity-validator-agent.md](./fidelity-validator-agent.md) | Verifies output completeness, tables, Turkish/UTF-8 diacritics, and triggers fallback retries | Per-output or parallel batch review |
