# Build context: repository root with `-f runner/Dockerfile` and `docker build -f runner/Dockerfile runner` or from `runner/` as context.
FROM golang:1.22-bookworm AS build
WORKDIR /src
COPY go.mod .
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /out/cns-runner ./cmd/runner

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget \
  && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/cns-runner /usr/local/bin/cns-runner
EXPOSE 8090
ENTRYPOINT ["/usr/local/bin/cns-runner"]
