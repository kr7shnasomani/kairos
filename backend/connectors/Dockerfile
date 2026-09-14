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
    && addgroup -S kairos && adduser -S kairos -G kairos

WORKDIR /app
COPY --from=builder /kairos-connector .
# EAM sync reads fixtures/sample_assets.json (EAM_FIXTURE_PATH) at runtime.
COPY --chown=kairos:kairos fixtures ./fixtures

USER kairos
EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://localhost:8090/health || exit 1

CMD ["./kairos-connector"]
