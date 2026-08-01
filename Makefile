.PHONY: install-dev test check run

install-dev:
	python3 -m pip install -r requirements-dev.txt

test:
	PYTHONPATH=. pytest -q

check: test
	python3 -m compileall -q app
	bash -n scripts/*.sh

run:
	uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload
