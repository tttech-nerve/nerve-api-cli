
DOCKER_IMG := tttech-nerve/nerve-cli:2.0.0
CLI_PROJECT_DIR := ./

SRC_FILES := $(shell find $(CLI_PROJECT_DIR) -type f -name "*.py")
POETRY_FILES := $(shell find $(CLI_PROJECT_DIR) -type f -name "pyproject.toml" -o -name "poetry.lock")

.DEFAULT_GOAL := help

.PHONY: help
help:  ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

.build: $(CLI_PROJECT_DIR)/Dockerfile $(SRC_FILES) $(POETRY_FILES)
	docker build \
		-t $(DOCKER_IMG) \
		-f $(CLI_PROJECT_DIR)/Dockerfile \
		$(CLI_PROJECT_DIR)
	
	@touch .build

build: .build	## Build the nerve-cli docker image

.PHONY: cleanup
cleanup:  ## Clean up build artifacts to ensure a clean build
	rm -rf .build