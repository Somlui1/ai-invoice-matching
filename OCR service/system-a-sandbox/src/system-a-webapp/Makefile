PY ?= python
export PYTHONPATH := .

install:   ; $(PY) -m pip install -r requirements.txt
check:     ; $(PY) -m webapp check          # read report.html and show what the app will see
serve:     ; $(PY) -m webapp serve
demo:      ; $(PY) -m webapp demo --out sample_batch
test:      ; $(PY) -m pytest -q             # needs SYSTEM_A_HOME
e2e:       ; $(PY) tests/e2e_browser.py     # needs playwright + chromium
