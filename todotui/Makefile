PUBLISH_DIR ?= $(HOME)/docker/todo/data/downloads

# ── Linux aarch64 (Raspberry Pi) — static musl via cross ──────────────────────
PI_TARGET  := aarch64-unknown-linux-musl
PI_DIR     := target-linux-arm
PI_BIN     := $(PI_DIR)/$(PI_TARGET)/release/todotui

# ── Linux x86_64 — static musl ────────────────────────────────────────────────
X86_TARGET := x86_64-unknown-linux-musl
X86_DIR    := target-linux-x86
X86_BIN    := $(X86_DIR)/$(X86_TARGET)/release/todotui

# ── macOS aarch64 (Apple Silicon) — via cargo-zigbuild ────────────────────────
MACOS_ARM_TARGET := aarch64-apple-darwin
MACOS_ARM_DIR    := target-macos-arm
MACOS_ARM_BIN    := $(MACOS_ARM_DIR)/$(MACOS_ARM_TARGET)/release/todotui

# ── macOS x86_64 (Intel) — via cargo-zigbuild ─────────────────────────────────
MACOS_X86_TARGET := x86_64-apple-darwin
MACOS_X86_DIR    := target-macos-x86
MACOS_X86_BIN    := $(MACOS_X86_DIR)/$(MACOS_X86_TARGET)/release/todotui

PI_HOSTS ?= terminal pmb@192.168.1.84

.PHONY: build linux-arm linux-x86 macos-arm macos-x86 release push-pi

build:
	cargo build --release

linux-arm:
	cross build --release --target $(PI_TARGET) --target-dir $(PI_DIR)
	aarch64-linux-gnu-strip $(PI_BIN)
	@echo "linux-aarch64: $(PI_BIN) ($$(du -sh $(PI_BIN) | cut -f1))"

linux-x86:
	RUSTFLAGS="-C target-feature=+crt-static" \
	  cargo build --release --target $(X86_TARGET) --target-dir $(X86_DIR)
	strip $(X86_BIN)
	@echo "linux-x86_64: $(X86_BIN) ($$(du -sh $(X86_BIN) | cut -f1))"

macos-arm:
	cargo zigbuild --release --target $(MACOS_ARM_TARGET) --target-dir $(MACOS_ARM_DIR)
	@echo "macos-aarch64: $(MACOS_ARM_BIN) ($$(du -sh $(MACOS_ARM_BIN) | cut -f1))"

macos-x86:
	cargo zigbuild --release --target $(MACOS_X86_TARGET) --target-dir $(MACOS_X86_DIR)
	@echo "macos-x86_64: $(MACOS_X86_BIN) ($$(du -sh $(MACOS_X86_BIN) | cut -f1))"

# Build all archs and publish — clients self-update on next launch
release: linux-arm linux-x86 macos-arm macos-x86
	mkdir -p $(PUBLISH_DIR)
	cp $(PI_BIN)       $(PUBLISH_DIR)/todotui-linux-aarch64
	cp $(X86_BIN)      $(PUBLISH_DIR)/todotui-linux-x86_64
	cp $(MACOS_ARM_BIN) $(PUBLISH_DIR)/todotui-macos-aarch64
	cp $(MACOS_X86_BIN) $(PUBLISH_DIR)/todotui-macos-x86_64
	@for f in linux-aarch64 linux-x86_64 macos-aarch64 macos-x86_64; do \
	  sha256sum $(PUBLISH_DIR)/todotui-$$f | awk '{print $$1}' > $(PUBLISH_DIR)/todotui-$$f.sha256; \
	  echo "Published $$f: $$(cat $(PUBLISH_DIR)/todotui-$$f.sha256)"; \
	done

# Force-push aarch64 binary directly to Pi hosts (for initial install / migration)
push-pi: linux-arm
	@for host in $(PI_HOSTS); do \
		echo "→ $$host"; \
		scp $(PI_BIN) $$host:~/todotui; \
	done
