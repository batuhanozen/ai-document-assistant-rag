.PHONY: install run test lint
install:
	python -m pip install --upgrade 'pip>=26.2'
	python -m pip install -e '.[dev]'
run:
	uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
test:
	pytest --cov=app --cov-report=term-missing
lint:
	ruff check app tests scripts
	ruff format --check app tests scripts
