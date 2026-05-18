FROM --platform=$BUILDPLATFORM golang:1.25 AS builder

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
ARG TARGETOS=linux
ARG TARGETARCH=amd64
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -o /out/workflow-gateway ./cmd/workflow-gateway

FROM gcr.io/distroless/base-debian12
WORKDIR /app
COPY --from=builder /out/workflow-gateway /app/workflow-gateway
USER 10001:10001
EXPOSE 8090
ENTRYPOINT ["/app/workflow-gateway"]
