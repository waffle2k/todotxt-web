PI_TARGET := aarch64-unknown-linux-gnu
RELEASE_DIR := target/$(PI_TARGET)/release
PI_HOST    ?= terminal

.PHONY: build pi deploy-pi

build:
	cargo build --release

# Cross-compile for Raspberry Pi 4 (aarch64) using gcc-aarch64-linux-gnu
pi:
	cargo build --release --target $(PI_TARGET)
	@echo "Binary: $(RELEASE_DIR)/todotui"

deploy-pi: pi
	scp $(RELEASE_DIR)/todotui $(PI_HOST):~/todotui
