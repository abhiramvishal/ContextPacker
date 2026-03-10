.PHONY: test build ext-package ext-compile lint

test:
	pytest tests/ -v

build:
	python -m build

ext-package:
	cd vscode-extension && npm run package

ext-compile:
	cd vscode-extension && npm run compile

lint:
	@command -v ruff >/dev/null 2>&1 && ruff check . || flake8 .
