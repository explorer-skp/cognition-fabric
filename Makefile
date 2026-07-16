.PHONY: setup test demo-smoke demo-ratchet demo-chaos demo-persist clean-state

# Python 3.11+ managed with uv; runs fully offline once deps are installed.
setup:
	uv venv --python 3.11
	uv pip install -e ".[dev]"

test:
	uv run pytest

demo-smoke:
	uv run python -m demo.demo_smoke

demo-ratchet:
	uv run python -m demo.demo_ratchet

demo-chaos:
	uv run python -m demo.demo_chaos

# Manual check for M2 persistence: crash a node store and reload it from the .state JSONL log.
demo-persist:
	uv run python -m demo.demo_persist

# Wipe per-node persistence and the event stream.
clean-state:
	rm -rf .state events.jsonl
