# Convenience targets for the RAG project. The interesting one is `eval`, which
# runs the RAGAS evaluation against a running stack.
#
#   make eval-install   # create eval/.venv and install the eval dependencies
#   make eval-seed      # upload + index the test fixtures into the stack
#   make eval           # verify the stack is up, then run the RAGAS evaluation
#
# The stack must be running first:
#   docker-compose -f infra/docker-compose.yml up --build
#
# OPENAI_API_KEY (RAGAS judge) and ANTHROPIC_API_KEY (backend generation) are
# read from the repo-root .env automatically.

BASE_URL ?= http://localhost:8000
COMPOSE  ?= docker-compose -f infra/docker-compose.yml

# Use the eval virtualenv's python when it exists, otherwise the system python.
VENV_PY_UNIX := eval/.venv/bin/python
VENV_PY_WIN  := eval/.venv/Scripts/python.exe
PYTHON ?= $(or $(wildcard $(VENV_PY_UNIX)),$(wildcard $(VENV_PY_WIN)),python)

.PHONY: eval eval-install eval-seed seed-demo stack-up stack-down

## Create eval/.venv and install the evaluation dependencies.
eval-install:
	python -m venv eval/.venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r eval/requirements.txt

## Upload + index the test fixtures into the running stack (idempotent).
eval-seed:
	RAG_API_BASE_URL=$(BASE_URL) $(PYTHON) eval/index_fixtures.py

## Upload + index the demo documents in seed-data/ (idempotent). Use this to
## populate a fresh deployment (e.g. the public demo) with browsable content.
seed-demo:
	RAG_API_BASE_URL=$(BASE_URL) $(PYTHON) eval/seed_demo.py

## Run the RAGAS evaluation. Verifies the stack is reachable, seeds the
## fixtures, then scores the dataset and writes eval/results/report.{json,md}.
eval:
	@curl -fsS $(BASE_URL)/health >/dev/null 2>&1 \
		|| [ "$$(curl -s -o /dev/null -w '%{http_code}' $(BASE_URL)/health)" = "503" ] \
		|| { echo "ERROR: stack not reachable at $(BASE_URL). Run: $(COMPOSE) up --build"; exit 1; }
	RAG_API_BASE_URL=$(BASE_URL) $(PYTHON) eval/index_fixtures.py
	RAG_API_BASE_URL=$(BASE_URL) $(PYTHON) eval/run_ragas.py

## Bring the full stack up / down via docker-compose.
stack-up:
	$(COMPOSE) up --build -d --wait

stack-down:
	$(COMPOSE) down
