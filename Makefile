# ================================
# Photonest Makefile (stable build + show version + docker-save tar)
# ================================

.PHONY: build load run clean show-tar-version

IMAGE_NAME = photonest:latest
OUTPUT_TAR = photonest-latest.tar
PLATFORM   = linux/amd64
DB_IMAGE_NAME = photonest-db:latest
DB_OUTPUT_TAR = photonest-db-latest.tar
DOCKER_API_VERSION ?= 1.43
DOCKER = DOCKER_API_VERSION=$(DOCKER_API_VERSION) docker

build-db:
	@echo "=== Build MariaDB with initial SQL ==="
	$(DOCKER) buildx build \
	  --platform linux/amd64 \
	  -t $(DB_IMAGE_NAME) ./db \
	  --load
	$(DOCKER) save $(DB_IMAGE_NAME) -o $(DB_OUTPUT_TAR)
	chmod 644 $(DB_OUTPUT_TAR)
	@echo "Build complete: $(DB_OUTPUT_TAR)"

# Git情報（make 実行時に取得）
COMMIT_HASH      := $(shell git rev-parse --short HEAD)
COMMIT_HASH_FULL := $(shell git rev-parse HEAD)
BRANCH           := $(shell git rev-parse --abbrev-ref HEAD)
COMMIT_DATE      := $(shell git log -1 --format=%ci)
BUILD_DATE       := $(shell date -Iseconds)

# 1) --load でローカルに取り込み
# 2) version.json を表示（ローカルイメージ）
# 3) docker save で互換性の高い tar を作成
# 4) 最後に同じ version.json を再表示
build:
	@set -e; \
	echo "=== [1/4] Build & LOAD locally (for version check) ==="; \
	$(DOCKER) buildx build \
      --network=host \
	  --platform $(PLATFORM) \
	  --build-arg COMMIT_HASH=$(COMMIT_HASH) \
	  --build-arg COMMIT_HASH_FULL=$(COMMIT_HASH_FULL) \
	  --build-arg BRANCH=$(BRANCH) \
	  --build-arg COMMIT_DATE="$(COMMIT_DATE)" \
	  --build-arg BUILD_DATE="$(BUILD_DATE)" \
	  -t $(IMAGE_NAME) . \
	  --load; \
	echo "=== [2/4] Show version.json (local image) ==="; \
	JSON=$$($(DOCKER) run --rm $(IMAGE_NAME) cat /app/core/version.json); \
	echo "$$JSON"; \
	echo "=== [3/4] Export TAR artifact (docker save) ==="; \
	$(DOCKER) save $(IMAGE_NAME) -o $(OUTPUT_TAR); \
	chmod 644 $(OUTPUT_TAR); \
	echo "=== [4/4] FINAL: Same version.json (from step 2) ==="; \
	echo "$$JSON"; \
	echo "======================================"; \
	echo " Build finished!"; \
	echo " -> $(OUTPUT_TAR)"; \
	echo "======================================"

# TAR をロードしたイメージで version.json を表示（TAR 側の中身検証用）
show-tar-version:
	@echo "=== Verify version.json from TAR ==="
	-@$(DOCKER) image rm -f $(IMAGE_NAME) >/dev/null 2>&1 || true
	@IMG=$$($(DOCKER) load -i $(OUTPUT_TAR) | awk -F': ' '/Loaded image:/ {print $$2}' | tail -n1); \
	  echo "Loaded: $$IMG"; \
	  $(DOCKER) run --rm $$IMG cat /app/core/version.json
	@echo "===================================="

load:
	docker load -i $(OUTPUT_TAR)

run:
	docker run --rm -p 5000:5000 $(IMAGE_NAME)

all: build build-db
	@echo "All builds complete."

clean:
	rm -f $(OUTPUT_TAR) $(DB_OUTPUT_TAR)
	$(DOCKER) builder prune -f
