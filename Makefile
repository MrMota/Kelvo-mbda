VENV ?= .venv
PY := $(VENV)/bin/python

.PHONY: install build run dev-backend dev-frontend test e2e fake-ollama

install:            ## install backend (editable) and frontend deps
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -e "backend[dev]"
	cd frontend && npm ci

build:              ## build the UI into the Python package
	cd frontend && npm run build

run: build          ## run MBDAflow on http://127.0.0.1:7860
	$(VENV)/bin/mbdaflow run

dev-backend:        ## API with auto-reload
	$(VENV)/bin/mbdaflow run --reload

dev-frontend:       ## Vite dev server on :5173, proxies /api to :7860
	cd frontend && npm run dev

fake-ollama:        ## a stand-in Ollama on :11435 for demos/tests without a GPU
	$(PY) -m mbdaflow.fake_ollama

test:               ## backend tests (spin up the fake Ollama themselves)
	cd backend && ../$(PY) -m pytest -q

e2e:                ## browser click-through; needs a running server
	node e2e/smoke.mjs http://127.0.0.1:7860
