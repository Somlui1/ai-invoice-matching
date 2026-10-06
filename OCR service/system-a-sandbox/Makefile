PY ?= python
export PYTHONPATH := src
test:       ; $(PY) -m pytest -q
scenarios:  ; $(PY) -m system_a.cli scenarios
export:     ; $(PY) -m system_a.cli export
serve:      ; $(PY) -m system_a.cli serve --port 8080
docker:     ; docker compose -f docker/compose.yaml up --build
