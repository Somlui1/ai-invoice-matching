PY ?= python
export PYTHONPATH := .

install:   ; $(PY) -m pip install -r requirements.txt
check:     ; $(PY) -m webapp check          # what System A (mode, Standard, models) and which DMS the app will see
serve:     ; $(PY) -m webapp serve
test:      ; $(PY) -m pytest -q             # needs SYSTEM_A_HOME - see README "How the tests run"
