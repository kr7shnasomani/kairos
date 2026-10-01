package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestRequireSecret(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.GET("/health", func(c *gin.Context) { c.String(http.StatusOK, "ok") })
	r.Group("/ot", requireSecret("s3cret")).GET("/query", func(c *gin.Context) { c.String(http.StatusOK, "data") })

	tests := []struct {
		name   string
		path   string
		header string
		want   int
	}{
		{"health needs no secret", "/health", "", http.StatusOK},
		{"missing header", "/ot/query", "", http.StatusUnauthorized},
		{"wrong secret", "/ot/query", "nope", http.StatusUnauthorized},
		{"prefix of secret", "/ot/query", "s3", http.StatusUnauthorized},
		{"correct secret", "/ot/query", "s3cret", http.StatusOK},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest(http.MethodGet, tt.path, nil)
			if tt.header != "" {
				req.Header.Set(secretHeader, tt.header)
			}
			w := httptest.NewRecorder()
			r.ServeHTTP(w, req)
			if w.Code != tt.want {
				t.Fatalf("status = %d, want %d", w.Code, tt.want)
			}
		})
	}
}

func TestValidateConfig(t *testing.T) {
	tests := []struct {
		name        string
		env         string
		secret      string
		internalKey string
		wantErr     bool
	}{
		{"no secret", "development", "", "k", true},
		{"dev with dev defaults", "development", devConnectorKey, devInternalKey, false},
		{"production real values", "production", "long-random", "other-random", false},
		{"production dev secret", "production", devConnectorKey, "other-random", true},
		{"production dev internal key", "production", "long-random", devInternalKey, true},
		{"typo env is not development", "prod", devConnectorKey, "other-random", true},
		{"unset env is not development", "", devConnectorKey, "other-random", true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateConfig(tt.env, tt.secret, tt.internalKey)
			if (err != nil) != tt.wantErr {
				t.Fatalf("err = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestReceiveWorkOrderBodyLimit(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.POST("/eam/work-order", receiveWorkOrder)

	req := httptest.NewRequest(http.MethodPost, "/eam/work-order", strings.NewReader(strings.Repeat("a", maxRequestBytes+1)))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)
	if w.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf("status = %d, want 413", w.Code)
	}
}

func TestReceiveWorkOrderDoesNotEchoUpstream(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusUnprocessableEntity)
		_, _ = w.Write([]byte(`{"detail":"secret internal stack trace"}`))
	}))
	defer upstream.Close()
	fastAPIURL = upstream.URL

	gin.SetMode(gin.TestMode)
	r := gin.New()
	r.POST("/eam/work-order", receiveWorkOrder)
	req := httptest.NewRequest(http.MethodPost, "/eam/work-order", strings.NewReader(`{}`))
	w := httptest.NewRecorder()
	r.ServeHTTP(w, req)

	if w.Code != http.StatusUnprocessableEntity {
		t.Fatalf("status = %d, want 422", w.Code)
	}
	if strings.Contains(w.Body.String(), "stack trace") {
		t.Fatalf("upstream text leaked: %s", w.Body.String())
	}
}
