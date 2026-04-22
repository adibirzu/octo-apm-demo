package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"octo-drone-shop/services/workflow-gateway/internal/api"
	"octo-drone-shop/services/workflow-gateway/internal/config"
	"octo-drone-shop/services/workflow-gateway/internal/database"
	"octo-drone-shop/services/workflow-gateway/internal/telemetry"
	"octo-drone-shop/services/workflow-gateway/internal/workflows"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		panic(err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	tel, err := telemetry.New(ctx, telemetry.Config{
		ServiceName:       cfg.ServiceName,
		AppName:           cfg.AppName,
		Environment:       cfg.Environment,
		APMEndpoint:       cfg.APMEndpoint,
		APMPrivateDataKey: cfg.APMPrivateDataKey,
	})
	if err != nil {
		panic(err)
	}
	defer func() {
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = tel.Shutdown(shutdownCtx)
	}()

	store, err := database.New(cfg)
	if err != nil {
		panic(err)
	}
	defer func() {
		_ = store.Close()
	}()

	service := workflows.New(cfg, store, tel)
	service.StartScheduler(ctx)

	router := api.New(cfg, service, tel)
	server := &http.Server{
		Addr:              fmt.Sprintf(":%d", cfg.Port),
		Handler:           router.Handler(),
		ReadHeaderTimeout: 10 * time.Second,
	}

	go func() {
		telemetry.Log(ctx, "INFO", "workflow gateway listening", map[string]any{
			"service.name": cfg.ServiceName,
			"port":         cfg.Port,
		})
		if serveErr := server.ListenAndServe(); serveErr != nil && serveErr != http.ErrServerClosed {
			panic(serveErr)
		}
	}()

	<-ctx.Done()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = server.Shutdown(shutdownCtx)
}
