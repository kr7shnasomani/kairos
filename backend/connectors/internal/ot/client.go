// OT historian client interface and implementations
// Supports: OSIsoft PI Web API, OPC-UA, Honeywell Uniformance, Generic REST
package ot

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"time"
)

// TimeSeriesPoint is a single measurement from the historian
type TimeSeriesPoint struct {
	Timestamp time.Time   `json:"timestamp"`
	Value     interface{} `json:"value"`
	Quality   string      `json:"quality"` // Good, Bad, Uncertain
}

// TimeSeriesQuery defines a historian query (ephemeral — data never stored)
type TimeSeriesQuery struct {
	Tag       string    `json:"tag"`
	AssetID   string    `json:"asset_id"`
	From      time.Time `json:"from"`
	To        time.Time `json:"to"`
	MaxPoints int       `json:"max_points"`
}

// HistorianClient is the interface all historian connectors implement
type HistorianClient interface {
	Query(ctx context.Context, q TimeSeriesQuery) ([]TimeSeriesPoint, error)
	Health(ctx context.Context) error
}

// =============================================================================
// PI Web API Client (OSIsoft / AVEVA)
// IEC 62443 compliance required before activating any OT connection.
// =============================================================================

type PIWebAPIClient struct {
	BaseURL    string
	Username   string
	Password   string
	HTTPClient *http.Client
}

func NewPIWebAPIClient(baseURL, username, password string) *PIWebAPIClient {
	return &PIWebAPIClient{
		BaseURL:  baseURL,
		Username: username,
		Password: password,
		HTTPClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// piSearchResult is the shape of a PI Web API search response
type piSearchResult struct {
	Items []struct {
		WebID string `json:"WebId"`
	} `json:"Items"`
}

// piStreamValue is one recorded value from a PI stream
type piStreamValue struct {
	Timestamp string      `json:"Timestamp"`
	Value     interface{} `json:"Value"`
	Good      bool        `json:"Good"`
}

// piStreamRecorded is the shape of a PI Web API stream/recorded response
type piStreamRecorded struct {
	Items []piStreamValue `json:"Items"`
}

func (c *PIWebAPIClient) Query(ctx context.Context, q TimeSeriesQuery) ([]TimeSeriesPoint, error) {
	if c.BaseURL == "" {
		return nil, fmt.Errorf("PI Web API not configured: set PI_WEBAPI_BASE_URL in .env")
	}

	// Step 1: resolve WebID from tag name
	searchURL := fmt.Sprintf("%s/search?q=%s&scope=*&fields=WebId", c.BaseURL, q.Tag)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, searchURL, nil)
	if err != nil {
		return nil, fmt.Errorf("PI search request build: %w", err)
	}
	req.SetBasicAuth(c.Username, c.Password)
	req.Header.Set("X-Requested-With", "kairos")

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("PI search request: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()

	var searchResp piSearchResult
	if err := json.NewDecoder(resp.Body).Decode(&searchResp); err != nil {
		return nil, fmt.Errorf("PI search decode: %w", err)
	}
	if len(searchResp.Items) == 0 {
		return nil, fmt.Errorf("PI tag not found: %s", q.Tag)
	}
	webID := searchResp.Items[0].WebID

	// Step 2: query stream/recorded
	streamURL := fmt.Sprintf("%s/streams/%s/recorded?startTime=%s&endTime=%s&maxCount=%d",
		c.BaseURL, webID,
		q.From.UTC().Format(time.RFC3339),
		q.To.UTC().Format(time.RFC3339),
		max(q.MaxPoints, 50),
	)
	req2, err := http.NewRequestWithContext(ctx, http.MethodGet, streamURL, nil)
	if err != nil {
		return nil, fmt.Errorf("PI stream request build: %w", err)
	}
	req2.SetBasicAuth(c.Username, c.Password)
	req2.Header.Set("X-Requested-With", "kairos")

	resp2, err := c.HTTPClient.Do(req2)
	if err != nil {
		return nil, fmt.Errorf("PI stream request: %w", err)
	}
	defer func() { _ = resp2.Body.Close() }()

	var streamResp piStreamRecorded
	if err := json.NewDecoder(resp2.Body).Decode(&streamResp); err != nil {
		return nil, fmt.Errorf("PI stream decode: %w", err)
	}

	points := make([]TimeSeriesPoint, 0, len(streamResp.Items))
	for _, item := range streamResp.Items {
		ts, err := time.Parse(time.RFC3339, item.Timestamp)
		if err != nil {
			continue
		}
		quality := "Uncertain"
		if item.Good {
			quality = "Good"
		}
		points = append(points, TimeSeriesPoint{
			Timestamp: ts,
			Value:     item.Value,
			Quality:   quality,
		})
	}
	return points, nil
}

func (c *PIWebAPIClient) Health(ctx context.Context) error {
	if c.BaseURL == "" {
		return fmt.Errorf("PI Web API not configured")
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.BaseURL+"/system/userinfo", nil)
	if err != nil {
		return err
	}
	req.SetBasicAuth(c.Username, c.Password)
	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode >= 400 {
		return fmt.Errorf("PI Web API health check failed: %d", resp.StatusCode)
	}
	return nil
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

// =============================================================================
// Mock Historian Client
// Returns 50 realistic vibration points (sine-shaped, mean≈1.8 mm/s RMS, ±0.12)
// Values stay within 2σ of baseline so attribution telemetry check reports failed=false.
// ponytail: mock data, replace with real PI client when PI_WEBAPI_BASE_URL is set
// =============================================================================

type MockHistorianClient struct{}

func (c *MockHistorianClient) Query(ctx context.Context, q TimeSeriesQuery) ([]TimeSeriesPoint, error) {
	points := make([]TimeSeriesPoint, 50)
	base := time.Now().Add(-30 * 24 * time.Hour)
	for i := 0; i < 50; i++ {
		value := 1.8 + 0.12*math.Sin(float64(i)*0.4)
		points[i] = TimeSeriesPoint{
			Timestamp: base.Add(time.Duration(i) * 15 * time.Hour),
			Value:     math.Round(value*1000) / 1000,
			Quality:   "Good",
		}
	}
	return points, nil
}

func (c *MockHistorianClient) Health(ctx context.Context) error { return nil }

// =============================================================================
// OPC-UA Client
// =============================================================================

type OPCUAClient struct {
	EndpointURL string
}

func NewOPCUAClient(endpointURL string) *OPCUAClient {
	return &OPCUAClient{EndpointURL: endpointURL}
}

// Query always fails loudly. It previously returned an empty slice with a nil error once an
// endpoint was configured, which is indistinguishable from "the historian has no readings for
// this tag" — a caller would record an absence of data as evidence. An unimplemented connector
// must be impossible to mistake for a working one that found nothing.
//
// Implementing this for real needs the gopcua client plus an OPC-UA server to verify against;
// until then the honest answer is that this path does not serve data.
func (c *OPCUAClient) Query(ctx context.Context, q TimeSeriesQuery) ([]TimeSeriesPoint, error) {
	if c.EndpointURL == "" {
		return nil, fmt.Errorf("OPC-UA not configured: set OPCUA_ENDPOINT_URL in .env")
	}
	return nil, fmt.Errorf(
		"OPC-UA client is registered but not implemented in this build (endpoint %s); "+
			"no telemetry is served on this path", c.EndpointURL)
}

func (c *OPCUAClient) Health(ctx context.Context) error {
	if c.EndpointURL == "" {
		return fmt.Errorf("OPC-UA not configured")
	}
	return fmt.Errorf("OPC-UA client is registered but not implemented in this build")
}
