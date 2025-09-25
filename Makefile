# ================================
# Photonest Makefile (stable build + show version + tar)
# ================================

.PHONY: build load run clean show-tar-version

IMAGE_NAME = photonest:latest
OUTPUT_TAR = photonest-latest.tar
PLATFORM   = linux/amd64

# Git情報（make 実行時に取得）
COMMIT_HASH      := $(shell git rev-parse --short HEAD)
COMMIT_HASH_FULL := $(shell git rev-parse HEAD)
BRANCH           := $(shell git rev-parse --abbrev-ref HEAD)
COMMIT_DATE      := $(shell git log -1 --format=%ci)
BUILD_DATE       := $(shell date -Iseconds)

# 1) 実行確認用に --load でローカルに取り込み
# 2) version.json を表示（ロードしたローカルイメージで確認）
# 3) 同じ内容で tar を作成（キャッシュ利用で高速）
# build: 最後に TAR から version.json を表示（--progress=plain は使わない）
# build: 最後に TAR から version.json を表示（--progress=plain は使わない）
build:
	@set -e; \
	echo "=== [1/4] Build & LOAD locally (for version check) ==="; \
	docker buildx build \
	  --platform $(PLATFORM) \
	  --build-arg COMMIT_HASH=$(COMMIT_HASH) \
	  --build-arg COMMIT_HASH_FULL=$(COMMIT_HASH_FULL) \
	  --build-arg BRANCH=$(BRANCH) \
	  --build-arg COMMIT_DATE="$(COMMIT_DATE)" \
	  --build-arg BUILD_DATE="$(BUILD_DATE)" \
	  -t $(IMAGE_NAME) . \
	  --load; \
	echo "=== [2/4] Show version.json (local image) ==="; \
	JSON=$$(docker run --rm $(IMAGE_NAME) cat /app/core/version.json); \
	echo "$$JSON"; \
	echo "=== [3/4] Export TAR artifact ==="; \
	docker buildx build \
	  --platform $(PLATFORM) \
	  --build-arg COMMIT_HASH=$(COMMIT_HASH) \
	  --build-arg COMMIT_HASH_FULL=$(COMMIT_HASH_FULL) \
	  --build-arg BRANCH=$(BRANCH) \
	  --build-arg COMMIT_DATE="$(COMMIT_DATE)" \
	  --build-arg BUILD_DATE="$(BUILD_DATE)" \
	  -t $(IMAGE_NAME) . \
	  --output type=tar,dest=$(OUTPUT_TAR); \
	echo "=== [4/4] FINAL: Same version.json (from step 2) ==="; \
	echo "$$JSON"; \
	echo "======================================"; \
	echo " Build finished!"; \
	echo " -> $(OUTPUT_TAR)"; \
	echo "======================================"

# TAR をロードしたイメージで version.json を表示（TAR 側の中身検証用）
show-tar-version:
	@echo "=== Verify version.json from TAR ==="
	# 既存の同名タグを消して、TARからロードしたものだけを参照
	-@docker image rm -f $(IMAGE_NAME) >/dev/null 2>&1 || true
	@IMG=$$(docker load -i $(OUTPUT_TAR) | awk -F': ' '/Loaded image:/ {print $$2}' | tail -n1); \
	  echo "Loaded: $$IMG"; \
	  docker run --rm $$IMG cat /app/core/version.json
	@echo "===================================="

load:
	docker load -i $(OUTPUT_TAR)

run:
	docker run --rm -p 5000:5000 $(IMAGE_NAME)

clean:
	rm -f $(OUTPUT_TAR)
	docker builder prune -f
