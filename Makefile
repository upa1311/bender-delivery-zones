# Convenience wrappers around uv. Targets that touch the network (download,
# audit) are intentionally NOT part of `make check` and are never run in CI.

.PHONY: help sync lint fmt test check audit-help download audit

help:
	@echo "Targets:"
	@echo "  sync        uv sync (create venv, install deps + dev group)"
	@echo "  lint        uv run ruff check ."
	@echo "  fmt         uv run ruff format ."
	@echo "  test        uv run pytest"
	@echo "  check       lint + test + audit --help (offline quality gates)"
	@echo "  download    download the Moldova PBF (NETWORK; not in CI)"
	@echo "  audit       run the source audit (LOCAL; needs PBF + osmium-tool)"

sync:
	uv sync

lint:
	uv run ruff check .

fmt:
	uv run ruff format .

test:
	uv run pytest

audit-help:
	uv run python scripts/audit_osm.py --help

check: lint test audit-help

download:
	uv run python scripts/download_osm.py --source osm_moldova

audit:
	uv run python scripts/audit_osm.py --pbf data/raw/moldova-latest.osm.pbf
