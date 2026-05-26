# Build context: repository root with `-f runner/Dockerfile` and `docker build -f runner/Dockerfile runner` or from `runner/` as context.
FROM golang:1.22-bookworm AS build
WORKDIR /src
COPY go.mod .
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -ldflags "-X github.com/timothy-choi/cloud-networking-studio/runner/internal/buildinfo.Version=${RUNNER_VERSION:-dev} -X github.com/timothy-choi/cloud-networking-studio/runner/internal/buildinfo.GitSHA=${RUNNER_GIT_SHA:-unknown} -X github.com/timothy-choi/cloud-networking-studio/runner/internal/buildinfo.BuildTime=${RUNNER_BUILD_TIME:-unknown}" -o /out/cns-runner ./cmd/runner

FROM debian:bookworm-slim
ARG TARGETARCH
ARG TERRAFORM_VERSION=1.9.8
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget unzip ansible openssh-client \
  && rm -rf /var/lib/apt/lists/* \
  && case "${TARGETARCH}" in amd64) TF_ARCH=amd64 ;; arm64) TF_ARCH=arm64 ;; *) TF_ARCH=amd64 ;; esac \
  && wget -q "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${TF_ARCH}.zip" -O /tmp/terraform.zip \
  && unzip /tmp/terraform.zip -d /usr/local/bin \
  && rm /tmp/terraform.zip \
  && terraform version \
  && mkdir -p /opt/terraform/plugin-cache
ENV TF_PLUGIN_CACHE_DIR=/opt/terraform/plugin-cache
COPY --from=build /out/cns-runner /usr/local/bin/cns-runner
EXPOSE 8090
ENTRYPOINT ["/usr/local/bin/cns-runner"]
