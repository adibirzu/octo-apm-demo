FROM golang:1.25 AS builder

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/workflow-gateway ./cmd/workflow-gateway

FROM gcr.io/distroless/base-debian12
WORKDIR /app
COPY --from=builder /out/workflow-gateway /app/workflow-gateway
EXPOSE 8090
ENTRYPOINT ["/app/workflow-gateway"]
