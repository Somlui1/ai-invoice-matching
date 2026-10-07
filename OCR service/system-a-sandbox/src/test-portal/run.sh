#!/usr/bin/env sh
# Starts the AIVA System A test application (Linux / macOS).  Edit .env first (copy .env.example).
cd "$(dirname "$0")" || exit 1
# The interpreter is used by path on purpose: ". .venv/bin/activate" exports a VIRTUAL_ENV that was fixed when
# the venv was created, so after the folder is moved "python" falls back to another interpreter.
[ -d .venv ] || python3 -m venv .venv
PY=.venv/bin/python
[ -x "$PY" ] || PY=.venv/bin/python3
if [ ! -x "$PY" ]; then echo "cannot find .venv/bin/python - create it with: python3 -m venv .venv"; exit 2; fi
"$PY" -m pip install -q -r requirements.txt
"$PY" -m webapp check && "$PY" -m webapp serve
