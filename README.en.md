[简体中文](README.md) | English

# Overall Situation Agent (Simple)

**A streamlined, command-line pipeline for spreadsheet ingestion, Elasticsearch aggregations, and report generation.**

`Overall Situation Agent (Simple)` is an optimized edition of the situation analytics engine. By removing heavy frontend web workspaces, long-running daemon servers, and conversational chat interfaces, it isolates the essential operational pipeline: "batch spreadsheet ingestion → deterministic Elasticsearch aggregation → HTML/Markdown report compilation". It offers developers a robust, scriptable analytics runner.

---

## Key Highlights

* **Streamlined Pipeline**: Focuses purely on automated CLI execution with three intuitive commands: `import`, `report`, and the end-to-end `run`.
* **Deterministic Aggregations**: All calculated metrics, trend variations, and distributions are executed natively by Elasticsearch, guaranteeing verifiable and repeatable data summaries.
* **Optional LLM Narrative Synthesis**: Supports OpenAI-compatible endpoints (disabled by default) to optionally augment statistical reports with synthesized takeaways.
* **Minimal Footprint**: Operates without Node.js runtimes, web frameworks, or background workers; requires only standard Python dependencies.
* **Temporal Slicing & Context**: Natively filters arbitrary date ranges and overlays external milestones or operational schedules.

---

## Quick Start

### 1. Requirements & Setup

* **Python**: 3.9 or newer
* **Elasticsearch**: Local or networked cluster instance

```powershell
python -m pip install -r requirements.txt
```

### 2. Environment Configuration

Create a local `.env` configuration:

```ini
ES_URL=http://localhost:9200
ES_INDEX=tagged_feedback
ES_VERIFY_CERTS=false

# Optional LLM narrative enhancement (disabled by default)
LLM_API_KEY=
LLM_REPORT_ENABLED=false
```

### 3. CLI Invocations

```powershell
# Ingest spreadsheet data
python -m overall_situation_agent.cli import --input "./data/service_records.xlsx" --recreate-index

# Generate report from indexed data
python -m overall_situation_agent.cli report

# Combined execution (ingest + compile report)
python -m overall_situation_agent.cli run --input "./data/service_records.xlsx"

# Run with date window filtering and event schedule overlays
python -m overall_situation_agent.cli run --input "./data/records.xlsx" --start-date 2026-01-01 --end-date 2026-01-31 --schedule-input "./data/schedule.xlsx"
```

Compiled deliverables are saved to the `outputs/` directory in both HTML and Markdown formats.

---

## Comparison: Simple vs. Full Edition

| Feature | Full Edition | Simple Edition |
| :--- | :---: | :---: |
| **CLI Batch Commands (`import` / `report` / `run`)** | ✅ | ✅ |
| **Elasticsearch Aggregations & Preprocessing** | ✅ | ✅ |
| **Optional LLM Narrative Enhancements** | ✅ | ✅ |
| **Vue 3 Interactive Web Workspace** | ✅ | ❌ (Streamlined) |
| **HTTP API Server & Real-Time SSE Jobs** | ✅ | ❌ (Streamlined) |
| **Interactive Natural-Language Chat Interface** | ✅ | ❌ (Streamlined) |

---

## License

This project is open-sourced under the [MIT License](LICENSE).
