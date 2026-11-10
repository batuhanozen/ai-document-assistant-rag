.PHONY: install run test lint audit docker
install:
	python -m pip install --upgrade 'pip>=26.2'
	python -m pip install -e '.[dev]'
run:
	uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8011 --workers 1 --no-access-log
test:
	pytest --cov=app --cov-report=term-missing
lint:
	ruff check app tests scripts
	ruff format --check app tests scripts
audit:
	python -m pip install pip-audit
	pip-audit
docker:
	docker build -t ai-document-assistant-rag .
