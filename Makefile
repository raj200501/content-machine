PYTHON ?= python3

.PHONY: bootstrap init-db setup-status sync-env instagram-accounts refresh plan render publish daily metrics smoke test

bootstrap:
	./scripts/bootstrap.sh

init-db:
	$(PYTHON) -m app.cli init-db

setup-status:
	$(PYTHON) -m app.cli setup-status

sync-env:
	$(PYTHON) -m app.cli sync-env

instagram-accounts:
	$(PYTHON) -m app.cli instagram-accounts

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
