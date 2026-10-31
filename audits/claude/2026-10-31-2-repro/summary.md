requires-python: {'>=3.11'} (same)
ruff target-version=py311 mypy python_version=3.11
ci matrix python: ['"3.11", "3.13"']
console script invest-data -> invest_data.cli:main: ok
console script invest-mine -> invest_mining.cli:main: ok
console script invest-eval -> invest_evaluation.cli:main: ok
invest-data: third-party imports ['numpy', 'pandas', 'pyarrow']; declared ['numpy', 'pandas', 'pyarrow']; undeclared none; unused declared none
invest-mining: third-party imports ['invest_data', 'matplotlib', 'numpy', 'pandas']; declared ['invest-data', 'matplotlib', 'numpy', 'pandas']; undeclared none; unused declared none
invest-evaluation: third-party imports ['invest_data', 'matplotlib', 'numpy', 'pandas']; declared ['invest-data', 'matplotlib', 'numpy', 'pandas']; undeclared none; unused declared none
invest_mining references under strategy-evaluation: strategy-evaluation/src/invest_evaluation/strategies.py:75:    diagnostics in ``invest_mining.diagnostics``, so bucket portfolios hold exactly the
action actions/checkout@11d5960a3267 len=40 comment=# v4.4.0: pinned
action astral-sh/setup-uv@d0cc045d04cc len=40 comment=# v6.8.0: pinned
action actions/checkout@11d5960a3267 len=40 comment=# v4.4.0: pinned
action astral-sh/setup-uv@d0cc045d04cc len=40 comment=# v6.8.0: pinned
action actions/checkout@11d5960a3267 len=40 comment=# v4.4.0: pinned
action astral-sh/setup-uv@d0cc045d04cc len=40 comment=# v6.8.0: pinned
unpinned uses: none
permissions: contents: read
setup-uv pins uv version: yes
ci checks commands: uv sync --frozen | uv run ruff format --check . | uv run ruff check . | uv run mypy data-pipeline/data-preparation/src data-mining-framework/src strategy-evaluation/src | uv run pytest --cov=invest_data --cov=invest_mining --cov=invest_evaluation --cov-branch --cov-report=term-missing | uv run python scripts/check_markdown_links.py | uv build --all-packages --out-dir "$RUNNER_TEMP/dist"
  README.md:116 uv run ruff format --check . -> in ci.yml
  README.md:116 uv run ruff check . -> in ci.yml
  README.md:117 uv run mypy data-pipeline/data-preparation/src data-mining-framework/src strategy-evaluation/src -> in ci.yml
  README.md:118 uv run pytest --cov=invest_data --cov=invest_mining --cov=invest_evaluation --cov-branch -> DIFFERS from ci.yml
  README.md:119 uv run python scripts/check_markdown_links.py -> in ci.yml
  PYTHON_GUIDELINES.md:99 uv run ruff format --check . -> in ci.yml
  PYTHON_GUIDELINES.md:100 uv run ruff check . -> in ci.yml
  PYTHON_GUIDELINES.md:101 uv run mypy data-pipeline/data-preparation/src data-mining-framework/src strategy-evaluation/src -> in ci.yml
  PYTHON_GUIDELINES.md:102 uv run pytest --cov=invest_data --cov=invest_mining --cov=invest_evaluation --cov-branch --cov-report=term-missing -> in ci.yml
  PYTHON_GUIDELINES.md:103 uv run python scripts/check_markdown_links.py -> in ci.yml
  SKILL.md:75 uv run ruff format --check . -> in ci.yml
  SKILL.md:76 uv run ruff check . -> in ci.yml
  SKILL.md:77 uv run mypy data-pipeline/data-preparation/src data-mining-framework/src strategy-evaluation/src -> in ci.yml
  SKILL.md:78 uv run pytest --cov=invest_data --cov=invest_mining --cov=invest_evaluation --cov-branch --cov-report=term-missing -> in ci.yml
  SKILL.md:79 uv run python scripts/check_markdown_links.py -> in ci.yml
scripts/historical_workflow.sh: bash -n rc=0; set -euo pipefail: yes
scripts/synthetic_workflow.sh: bash -n rc=0; set -euo pipefail: yes
portability counts (all .py, 27 files): {'read_text_no_encoding': 109, 'write_text_no_encoding': 65, 'open_no_encoding': 4, 'os_rename': 1}
