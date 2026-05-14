PUBLISH_DIR ?= $(HOME)/docker/todo/data/downloads

# aarch64 (Raspberry Pi) — static musl
PI_TARGET   := aarch64-unknown-linux-musl
PI_DIR      := target-pi
PI_BIN      := $(PI_DIR)/$(PI_TARGET)/release/todotui
PI_ARCH     := aarch64
PI_HOSTS    ?= terminal pmb@192.168.1.84

# x86_64 — static musl
X86_TARGET  := x86_64-unknown-linux-musl
X86_DIR     := target-x86
X86_BIN     := $(X86_DIR)/$(X86_TARGET)/release/todotui
X86_ARCH    := x86_64

.PHONY: build pi x86 release push-pi

build:
	cargo build --release

# Cross-compile for Raspberry Pi (aarch64, fully static musl)
pi:
	cross build --release --target $(PI_TARGET) --target-dir $(PI_DIR)
	aarch64-linux-gnu-strip $(PI_BIN)
	@echo "aarch64: $(PI_BIN) ($$(du -sh $(PI_BIN) | cut -f1))"

# Build for x86_64 (fully static musl)
x86:
	RUSTFLAGS="-C target-feature=+crt-static" cargo build --release --target $(X86_TARGET) --target-dir $(X86_DIR)
	strip $(X86_BIN)
	@echo "x86_64: $(X86_BIN) ($$(du -sh $(X86_BIN) | cut -f1))"

# Build all archs and publish to server — clients self-update on next launch
release: pi x86
	mkdir -p $(PUBLISH_DIR)
	cp $(PI_BIN)  $(PUBLISH_DIR)/todotui-$(PI_ARCH)
	cp $(X86_BIN) $(PUBLISH_DIR)/todotui-$(X86_ARCH)
	sha256sum $(PI_BIN)  | awk '{print $$1}' > $(PUBLISH_DIR)/todotui-$(PI_ARCH).sha256
	sha256sum $(X86_BIN) | awk '{print $$1}' > $(PUBLISH_DIR)/todotui-$(X86_ARCH).sha256
	@echo "Published aarch64: $$(cat $(PUBLISH_DIR)/todotui-$(PI_ARCH).sha256)"
	@echo "Published x86_64:  $$(cat $(PUBLISH_DIR)/todotui-$(X86_ARCH).sha256)"

# Force-push binaries directly to Pi hosts (bypass self-update, for initial installs)
push-pi: pi
	@for host in $(PI_HOSTS); do \
		echo "→ $$host"; \
		scp $(PI_BIN) $$host:~/todotui; \
	done
