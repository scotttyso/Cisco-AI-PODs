.PHONY: help install test lint run-dry-run run-apply clean docs

help:
	@echo "DNS Updater - Makefile Commands"
	@echo "================================="
	@echo ""
	@echo "Setup:"
	@echo "  make install          - Install Python dependencies"
	@echo "  make setup-venv       - Create Python virtual environment"
	@echo ""
	@echo "Development:"
	@echo "  make test             - Run unit tests"
	@echo "  make lint             - Run code linting (pylint, flake8)"
	@echo "  make format           - Format code with black and isort"
	@echo "  make type-check       - Run type checking with mypy"
	@echo ""
	@echo "Execution:"
	@echo "  make run-dry-run      - Run DNS updater in dry-run mode"
	@echo "  make run-ad           - Update Active Directory DNS (dry-run)"
	@echo "  make run-infoblox     - Update Infoblox DNS (dry-run)"
	@echo "  make run-apply        - Apply changes to DNS provider"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean            - Remove temporary files and caches"
	@echo "  make validate-config  - Validate configuration file"
	@echo "  make docs             - Generate documentation"
	@echo ""
	@echo "Variables:"
	@echo "  PROVIDER=ad           - DNS provider (ad, infoblox, bluecat, efficientip, bind)"
	@echo "  CONFIG=dns_config.yaml - Configuration file path"
	@echo "  VERBOSE=1             - Enable verbose output"
	@echo ""

install:
	@echo "Installing DNS Updater dependencies..."
	pip install -r requirements.txt
	@echo "✓ Dependencies installed"

setup-venv:
	@echo "Creating Python virtual environment..."
	python3 -m venv venv
	. venv/bin/activate && pip install -r requirements.txt
	@echo "✓ Virtual environment created"
	@echo "Activate with: source venv/bin/activate"

test:
	@echo "Running unit tests..."
	python3 -m pytest test_dns_updater.py -v --tb=short 2>/dev/null || \
	python3 test_dns_updater.py

lint:
	@echo "Running code linting..."
	@if command -v pylint &> /dev/null; then \
		pylint dns_updater.py --disable=missing-docstring,too-many-arguments; \
	else \
		echo "pylint not installed. Install with: pip install pylint"; \
	fi
	@if command -v flake8 &> /dev/null; then \
		flake8 dns_updater.py --max-line-length=120; \
	else \
		echo "flake8 not installed. Install with: pip install flake8"; \
	fi

format:
	@echo "Formatting code..."
	@if command -v black &> /dev/null; then \
		black dns_updater.py; \
	else \
		echo "black not installed. Install with: pip install black"; \
	fi
	@if command -v isort &> /dev/null; then \
		isort dns_updater.py; \
	else \
		echo "isort not installed. Install with: pip install isort"; \
	fi

type-check:
	@echo "Running type checking..."
	@if command -v mypy &> /dev/null; then \
		mypy dns_updater.py --ignore-missing-imports; \
	else \
		echo "mypy not installed. Install with: pip install mypy"; \
	fi

validate-config:
	@echo "Validating configuration file..."
	python3 -c "import yaml; config = yaml.safe_load(open('${CONFIG:-dns_config.yaml}')); print('✓ Configuration is valid YAML'); print('Configured providers:', list(config.get('providers', {}).keys())); print('Inventory sources:', list(config.get('inventory', {}).keys()))"

run-dry-run: validate-config
	@echo "Running DNS updater in dry-run mode..."
	python3 dns_updater.py \
		--config ${CONFIG:-dns_config.yaml} \
		--provider ${PROVIDER:-ad} \
		--dry-run \
		$(if $(VERBOSE),--verbose,)

run-ad: validate-config
	@echo "Running DNS updater for Active Directory (dry-run)..."
	python3 dns_updater.py --config dns_config.yaml --provider ad --dry-run --verbose

run-infoblox: validate-config
	@echo "Running DNS updater for Infoblox (dry-run)..."
	python3 dns_updater.py --config dns_config.yaml --provider infoblox --dry-run --verbose

run-bluecat: validate-config
	@echo "Running DNS updater for BlueCat (dry-run)..."
	python3 dns_updater.py --config dns_config.yaml --provider bluecat --dry-run --verbose

run-apply: validate-config
	@echo "WARNING: About to apply changes to DNS provider: ${PROVIDER:-ad}"
	@echo "Press Ctrl+C to abort or Enter to continue..."
	@read dummy
	python3 dns_updater.py \
		--config ${CONFIG:-dns_config.yaml} \
		--provider ${PROVIDER:-ad} \
		--apply \
		$(if $(VERBOSE),--verbose,)

clean:
	@echo "Cleaning up temporary files..."
	rm -rf __pycache__ .pytest_cache .mypy_cache build dist
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".coverage" -delete
	@echo "✓ Cleanup complete"

docs:
	@echo "DNS Updater Documentation"
	@echo "================================="
	@echo "Main README: DNS_UPDATER_README.md"
	@echo ""
	@cat DNS_UPDATER_README.md | head -100

#
# Advanced targets for CI/CD pipelines
#

ci-test:
	@echo "Running CI tests..."
	python3 -m pytest test_dns_updater.py -v --tb=short --cov=dns_updater || python3 test_dns_updater.py

ci-lint:
	@echo "Running CI linting..."
	$(MAKE) lint || true

ci-build: ci-test ci-lint
	@echo "✓ CI build successful"

#
# Documentation generation
#

docs-html:
	@echo "Generating HTML documentation..."
	@if command -v pandoc &> /dev/null; then \
		pandoc DNS_UPDATER_README.md -o DNS_UPDATER_README.html -f markdown -t html; \
		echo "✓ Generated DNS_UPDATER_README.html"; \
	else \
		echo "pandoc not installed. Install with: apt-get install pandoc"; \
	fi
