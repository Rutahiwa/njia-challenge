.PHONY: install mock agent evals test

install:
	uv sync

mock:
	uv run uvicorn mock.app:app --port 9311

agent:
	uv run uvicorn app.server:app --port 9310 --reload

evals:
	uv run python -m evals.run_evals $(S)

test:
	uv run pytest -q

probe:
	uv run python -m evals.probe $(P)
