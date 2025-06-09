#!/bin/bash
pip3 install --upgrade pip
pip3 install uv
uv venv
source .venv/bin/activate
uv sync --extra dev --extra test
