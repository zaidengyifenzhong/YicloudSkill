# Yicloud skill evaluation

From the repository root, use the development environment:

```bash
.venv/bin/python tools/evaluate_skill.py > /tmp/yicloud-evaluation.json
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python tools/validate_skill.py
```

`evaluate_skill.py` emits one JSON report and exits 0 only when all contracts and local reference checks pass. It uses temporary configuration, removes inherited `YICLOUD_*` variables, runs the current source CLI in isolated Python subprocesses, and blocks socket operations with an audit hook. The guard is checked before any cases run. No platform requests, credentials, resources, or persistent test files are required. This is an offline regression guard, not a sandbox for arbitrary hostile Python code.

The report counts help checks for every root command and the direct children of workspace, job, ray, serving, skill, api, and context. The initial baseline has 113 help cases; discovery includes future additions automatically. Ten JSON cases cover argument conflicts, unknown commands/operations, time boundaries, missing scope, invalid request shapes, and valid Job/Workspace dry-runs. The report also measures UTF-8 bytes, characters, scenario reading sizes, and broken local references. Context size is not a token count; speed measurements are descriptive and have no fixed performance threshold.

For before/after comparisons, retain reports from the corresponding commits and compare case IDs, pass counts, links, and context sizes. New cases increase the denominator. Run the same interpreter and host when comparing elapsed times. The script requires the repository fixtures and dependencies; wheel/install behavior is checked separately by `tools/verify_wheel.py`.

CI also runs the full test suite, CLI evaluator and catalog/skill validators on Python 3.10 with the declared dependency floors, Click 8.1.0 and HTTPX 0.27.0, across Linux, macOS and Windows. To reproduce the dependency selection in a disposable Python 3.10 environment, install `-e ".[dev]" "click==8.1.0" "httpx==0.27.0"` before running the commands above. This complements the existing matrix using newer dependencies; a configured matrix is not evidence of a completed run.

`scenarios.json` contains 12 positive, negative, and boundary requests with review criteria. Give an independent evaluator the request and skill without the criteria when measuring behavior, then review its actions against the criteria. Use permitted isolated resources, and record actual tool evidence and limitations. These scenarios are currently a manual/agent assessment set; neither their presence nor a desktop routing review establishes production trigger accuracy, task completion rate, or live-platform reliability. Report those only after running a suitable selector or complete task evaluation.
