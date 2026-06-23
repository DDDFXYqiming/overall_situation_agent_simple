# Overall Situation Agent (Simple)

A simplified and optimized local Python tool for turning spreadsheet records into a summarized HTML/Markdown report.

This edition keeps deterministic aggregation and report generation while removing interactive chat and API server layers.

## Features

- Import one spreadsheet file or a directory of spreadsheet files.
- Normalize tabular records into an Elasticsearch index.
- Generate local HTML and Markdown reports in a single run.
- Optionally apply OpenAI-compatible LLM wording enhancement for report narratives (disabled by default).
- Support date-range filtering and optional schedule-context annotation.

## Requirements

- Python 3.9+
- Local Elasticsearch instance
- Optional OpenAI-compatible LLM API key

## Setup

```powershell
python -m pip install -r requirements.txt
```

Create a local `.env` file based on `.env.example`:

```ini
ES_URL=http://localhost:9200
ES_INDEX=tagged_feedback
ES_VERIFY_CERTS=false

LLM_API_KEY=
```

## Usage

Import data:

```powershell
python -m overall_situation_agent.cli import --input "<spreadsheet-or-directory>" --recreate-index
```

Generate a report:

```powershell
python -m overall_situation_agent.cli report
```

Run import and report generation together:

```powershell
python -m overall_situation_agent.cli run --input "<spreadsheet-or-directory>"
```

Run with date filters and schedule input:

```powershell
python -m overall_situation_agent.cli run --input "<spreadsheet-or-directory>" --start-date 2026-01-01 --end-date 2026-01-31 --schedule-input "<schedule-file.xlsx>"
```

Generated files are written to `outputs/` by default.

## Configuration

Important environment variables:

- `ES_URL`, `ES_INDEX`, `ES_USERNAME`, `ES_PASSWORD`, `ES_VERIFY_CERTS`
- `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `DEEPSEEK_API_KEY`
- `LLM_REPORT_ENABLED`, `LLM_REPORT_TIMEOUT_SECONDS`, `LLM_REPORT_MAX_RETRIES`, `LLM_REPORT_MAX_TOKENS`
- `IMPORT_BATCH_SIZE`, `OUTPUTS_DIR`, `LOGS_DIR`
- `FOUR_DIM_MAPPING_FILE` for an optional local supplementary label mapping workbook; keep real local paths in `.env`, not in source code

## Differences From Full Edition

- Removed: interactive chat mode and query-builder conversation flow.
- Removed: API server dependencies and runtime path.
- Kept: import pipeline, deterministic aggregations, schedule-context support, report rendering, optional LLM narrative enhancement.
- Available commands: `import`, `report`, `run`.

## Repository Hygiene

This public repository intentionally excludes secrets, local environment files, generated outputs, private datasets, and internal working notes.

Examples, prompts, default report names, and descriptions use generic business terms to avoid exposing sensitive product, event, local-path, or source-data context.
