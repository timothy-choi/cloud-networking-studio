# Build context: repository root with `-f runner/Dockerfile` and `docker build -f runner/Dockerfile runner` or from `runner/` as context.
FROM golang:1.22-bookworm AS build
WORKDIR /src
COPY go.mod .
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -ldflags "-X github.com/timothy-choi/cloud-networking-studio/runner/internal/buildinfo.Version=${RUNNER_VERSION:-dev} -X github.com/timothy-choi/cloud-networking-studio/runner/internal/buildinfo.GitSHA=${RUNNER_GIT_SHA:-unknown} -X github.com/timothy-choi/cloud-networking-studio/runner/internal/buildinfo.BuildTime=${RUNNER_BUILD_TIME:-unknown}" -o /out/cns-runner ./cmd/runner

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget ansible \
  && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/cns-runner /usr/local/bin/cns-runner
EXPOSE 8090
ENTRYPOINT ["/usr/local/bin/cns-runner"]
