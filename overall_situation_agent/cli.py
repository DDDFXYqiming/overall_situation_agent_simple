from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="整体情况报告生成工具")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd(), help="项目目录（包含 .env）")

    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import", help="导入 Excel 到 Elasticsearch")
    import_parser.add_argument("--input", type=Path, required=True)
    import_parser.add_argument("--recreate-index", action="store_true")

    report_parser = subparsers.add_parser("report", help="生成 HTML 和 Markdown 报告")
    report_parser.add_argument("--output", type=Path, default=None)
    report_parser.add_argument("--start-date", type=str)
    report_parser.add_argument("--end-date", type=str)
    report_parser.add_argument("--schedule-input", type=Path, help="赛程文件")

    run_parser = subparsers.add_parser("run", help="导入数据并生成报告（一步完成）")
    run_parser.add_argument("--input", type=Path, required=True)
    run_parser.add_argument("--output", type=Path, default=None)
    run_parser.add_argument("--start-date", type=str)
    run_parser.add_argument("--end-date", type=str)
    run_parser.add_argument("--recreate-index", action="store_true")
    run_parser.add_argument("--schedule-input", type=Path)

    return parser


def main() -> None:
    args = build_parser().parse_args()

    try:
        from .agent import OverallSituationAgent
        from .config import load_settings
        from .logging_setup import setup_logging
        from .output_naming import normalize_report_path
    except ModuleNotFoundError as exc:
        missing = exc.name or "unknown"
        raise SystemExit(f"缺少依赖 [{missing}]。请执行: python -m pip install -r requirements.txt") from exc

    settings = load_settings(args.project_dir)
    setup_logging(settings.logs_dir)
    agent = OverallSituationAgent(settings)

    if args.command == "import":
        result = agent.import_data(args.input, recreate_index=args.recreate_index)
        print(result.message)
        return

    if args.command == "report":
        output_path = normalize_report_path(settings.outputs_dir, args.output, "整体情况报告")
        output = agent.generate_report(
            output_path,
            start_date=args.start_date,
            end_date=args.end_date,
            schedule_input=args.schedule_input,
        )
        print(f"HTML report generated: {output.resolve()}")
        print(f"Markdown report generated: {output.with_suffix('.md').resolve()}")
        return

    if args.command == "run":
        output_path = normalize_report_path(settings.outputs_dir, args.output, "整体情况报告")
        output = agent.run(
            input_path=args.input,
            output_path=output_path,
            start_date=args.start_date,
            end_date=args.end_date,
            recreate_index=args.recreate_index,
            schedule_input=args.schedule_input,
        )
        print(f"HTML report generated: {output.resolve()}")
        print(f"Markdown report generated: {output.with_suffix('.md').resolve()}")
        return


if __name__ == "__main__":
    main()
