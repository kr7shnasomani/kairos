package ot

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestPIQueryEscapesTagAndScrubsURL(t *testing.T) {
	var gotRawQuery string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotRawQuery = r.URL.RawQuery
		_, _ = w.Write([]byte(`{"Items":[]}`))
	}))
	c := NewPIWebAPIClient(srv.URL, "u", "p")

	_, err := c.Query(context.Background(), TimeSeriesQuery{Tag: "T-1&scope=evil#x", From: time.Now(), To: time.Now()})
	if err == nil || !strings.Contains(err.Error(), "not found") {
		t.Fatalf("want tag-not-found error, got %v", err)
	}
	if !strings.HasPrefix(gotRawQuery, "q=T-1%26scope%3Devil%23x&") {
		t.Fatalf("tag not escaped: %q", gotRawQuery)
	}

	srv.Close() // transport failure: the error must not carry the base URL
	_, err = c.Query(context.Background(), TimeSeriesQuery{Tag: "T", From: time.Now(), To: time.Now()})
	if err == nil || strings.Contains(err.Error(), srv.URL) {
		t.Fatalf("error leaks PI URL: %v", err)
	}
}
