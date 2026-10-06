#!/usr/bin/env sh
# Starts the AIVA System A test application (Linux / macOS).  Edit .env first (copy .env.example).
cd "$(dirname "$0")" || exit 1
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
python -m pip install -q -r requirements.txt
python -m webapp check && python -m webapp serve
