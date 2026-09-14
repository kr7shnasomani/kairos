# syntax=docker/dockerfile:1
# =============================================================================
# Kairos Go OT Connector — multi-stage build
#   builder  → compiles the static binary (also used for `go run` in dev via
#              docker-compose.override.yml, target: builder)
#   release  → tiny non-root Alpine image with just the binary (default / AWS)
# =============================================================================

# ---- builder --------------------------------------------------------------
FROM golang:1.25-alpine AS builder
WORKDIR /app
COPY go.mod go.sum* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /kairos-connector ./cmd/connector/...

# ---- release --------------------------------------------------------------
FROM alpine:3.20 AS release
# hadolint ignore=DL3018
RUN apk --no-cache add ca-certificates wget \
    && addgroup -S -g 1001 kairos && adduser -S -u 1001 -G kairos kairos

WORKDIR /app
COPY --from=builder /kairos-connector .
# EAM sync reads fixtures/sample_assets.json (EAM_FIXTURE_PATH) at runtime.
COPY --chown=kairos:kairos fixtures ./fixtures

# Numeric uid:gid of the kairos user above — same as the backend image (hadolint DL3066).
USER 1001:1001
EXPOSE 8090

# JSON form (hadolint DL3025); `sh -c` keeps the `|| exit 1` so Docker still sees exit code 1.
# A real GET, not `--spider`: spider sends HEAD, `/health` is registered for GET only, so every
# probe 404'd and the release container was permanently reported unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["sh", "-c", "wget -q -O /dev/null http://localhost:8090/health || exit 1"]

CMD ["./kairos-connector"]
