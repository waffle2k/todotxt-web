PI_TARGET  := aarch64-unknown-linux-musl
TARGET_DIR := target-pi
RELEASE_DIR := $(TARGET_DIR)/$(PI_TARGET)/release
PI_HOSTS   ?= terminal pmb@192.168.1.84

.PHONY: build pi deploy-pi

build:
	cargo build --release

# Cross-compile for Raspberry Pi (aarch64, fully static musl binary)
pi:
	cross build --release --target $(PI_TARGET) --target-dir $(TARGET_DIR)
	aarch64-linux-gnu-strip $(RELEASE_DIR)/todotui
	@echo "Binary: $(RELEASE_DIR)/todotui ($$(du -sh $(RELEASE_DIR)/todotui | cut -f1))"

deploy-pi: pi
	@for host in $(PI_HOSTS); do \
		echo "→ $$host"; \
		scp $(RELEASE_DIR)/todotui $$host:~/todotui; \
	done
