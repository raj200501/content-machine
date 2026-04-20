PYTHON ?= python3

.PHONY: bootstrap init-db refresh plan render publish daily metrics smoke test

bootstrap:
	./scripts/bootstrap.sh

init-db:
	$(PYTHON) -m app.cli init-db

refresh:
	$(PYTHON) -m app.cli refresh-sources

plan:
	$(PYTHON) -m app.cli plan-day

render:
	$(PYTHON) -m app.cli render-batch --count 20

publish:
	$(PYTHON) -m app.cli publish-ready

daily:
	$(PYTHON) -m app.cli daily-run

metrics:
	$(PYTHON) -m app.cli metrics

smoke:
	$(PYTHON) -m app.cli smoke-test

test:
	pytest
