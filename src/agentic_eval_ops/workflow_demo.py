"""No-key deterministic pipeline demo; measured latencies vary by host."""
import argparse
import json
from pathlib import Path
import tempfile

from .workflow import Workflow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, help='Optional persistent SQLite file')
    parser.add_argument('--report', type=Path, help='Optional JSON evidence output')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        workflow = Workflow(args.database or Path(directory) / 'demo.db', 'synthetic-acme', clock=lambda: 1800000000)
        workflow.put_memory('case-policy', 1, 'prepare a local case note for review', 'synthetic://acme/policy/v1')
        job = workflow.request('demo-request-1', 'case-1', 'case-policy', 1)
        for _ in range(8):
            report = workflow.advance(job)
            if report['state'] == 'awaiting_approval':
                workflow.approve(job, report['action_digest'], expires_at=1800000100)
            if report['state'] in ('completed', 'failed'):
                break
        report = workflow.report(job)
        output = json.dumps(report, indent=2)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(output + '\n', encoding='utf-8')
        print(output)
        return 0 if report['state'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
