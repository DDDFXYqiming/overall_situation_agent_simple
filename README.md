简体中文 | [English](README.en.md)

# Overall Situation Agent (Simple) · 全局态势轻量版

**精简高能的本地表格数据清洗、Elasticsearch 聚合与研报生成流水线**。

`Overall Situation Agent (Simple)` 是全局态势感知智能体的精简优化版。它去除了常驻 Web 前端与复杂交互服务器的重型依赖，聚焦于核心的“批量导入清洗 → 确定性聚合计算 → HTML/Markdown 研报生成”核心管线，以极简的命令行界面提供稳定、高效的离线自动化分析能力。

---

## 核心定位与精简优势

* **纯粹的管道化工作流**：专注于命令行批处理，通过 `import`、`report` 和一键直达的 `run` 指令，串联数据入库与报告产出。
* **确定性聚合与严谨数据**：报告中所有图表指标、多维分类与同比环比数据严格由 Elasticsearch 原生执行聚合，数据可重复、可验证。
* **可选大模型叙事增强**：支持接入 OpenAI 兼容端点（默认静默关闭），仅在需要时为研报中的异动分析与结论提供自然的文本归纳。
* **轻量级零包袱**：无需启动 Node.js、Vue 前端或额外后台守护进程，单 Python 环境即开即跑。
* **时序与业务排期上下文**：原生支持时间段精确切片与外部日程排期（如重大节点/赛程活动）对比分析。

---

## 快速开始

### 1. 环境依赖与安装

* **Python**：3.9 或更高版本
* **Elasticsearch**：本地或局域网 Elasticsearch 实例

```powershell
python -m pip install -r requirements.txt
```

### 2. 配置环境变量

从示例创建 `.env` 文件：

```ini
ES_URL=http://localhost:9200
ES_INDEX=tagged_feedback
ES_VERIFY_CERTS=false

# 可选的大模型叙事生成（默认关闭）
LLM_API_KEY=
LLM_REPORT_ENABLED=false
```

### 3. 命令行调用

```powershell
# 仅导入数据
python -m overall_situation_agent.cli import --input "./data/service_records.xlsx" --recreate-index

# 基于已有数据生成研报
python -m overall_situation_agent.cli report

# 一键执行导入与报告生成
python -m overall_situation_agent.cli run --input "./data/service_records.xlsx"

# 带时间区间过滤与外部排期文件联动
python -m overall_situation_agent.cli run --input "./data/records.xlsx" --start-date 2026-01-01 --end-date 2026-01-31 --schedule-input "./data/schedule.xlsx"
```

生成结果默认输出至 `outputs/` 目录（包含 HTML 与 Markdown 双版本）。

---

## 与全功能版的区别

| 特性维度 | 全功能完整版 (Full Edition) | 精简版 (Simple Edition) |
| :--- | :---: | :---: |
| **命令行批处理 (`import` / `report` / `run`)** | ✅ | ✅ |
| **底层 Elasticsearch 聚合与数据清洗** | ✅ | ✅ |
| **可选大模型叙事润色** | ✅ | ✅ |
| **Vue 3 交互式 Web 桌面工作台** | ✅ | ❌（已精简剥离） |
| **常驻 HTTP API 与 SSE 实时作业流** | ✅ | ❌（已精简剥离） |
| **交互式自然语言问数终端 (Chat)** | ✅ | ❌（已精简剥离） |

---

## 许可证

本项目基于 [MIT License](LICENSE) 开源。
