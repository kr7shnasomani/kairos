// OT historian client interface and implementations
// Supports: OSIsoft PI Web API and a mock historian (the default)
package ot

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"time"
)

// maxBodyBytes caps what we read back from a historian.
const maxBodyBytes = 4 << 20

// scrubURL drops the request URL from a transport error so logs never carry the PI base URL.
func scrubURL(err error) error {
	var ue *url.Error
	if errors.As(err, &ue) {
		return ue.Err
	}
	return err
}

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
	searchURL := fmt.Sprintf("%s/search?q=%s&scope=*&fields=WebId", c.BaseURL, url.QueryEscape(q.Tag))
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, searchURL, nil)
	if err != nil {
		return nil, fmt.Errorf("PI search request build: %w", err)
	}
	req.SetBasicAuth(c.Username, c.Password)
	req.Header.Set("X-Requested-With", "kairos")

	resp, err := c.HTTPClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("PI search request: %w", scrubURL(err))
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("PI search failed: HTTP %d", resp.StatusCode)
	}

	var searchResp piSearchResult
	if err := json.NewDecoder(io.LimitReader(resp.Body, maxBodyBytes)).Decode(&searchResp); err != nil {
		return nil, fmt.Errorf("PI search decode: %w", err)
	}
	if len(searchResp.Items) == 0 {
		return nil, fmt.Errorf("PI tag not found: %q", q.Tag)
	}
	webID := searchResp.Items[0].WebID

	// Step 2: query stream/recorded
	streamURL := fmt.Sprintf("%s/streams/%s/recorded?startTime=%s&endTime=%s&maxCount=%d",
		c.BaseURL, url.PathEscape(webID),
		url.QueryEscape(q.From.UTC().Format(time.RFC3339)),
		url.QueryEscape(q.To.UTC().Format(time.RFC3339)),
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
		return nil, fmt.Errorf("PI stream request: %w", scrubURL(err))
	}
	defer func() { _ = resp2.Body.Close() }()
	if resp2.StatusCode >= 400 {
		return nil, fmt.Errorf("PI stream failed: HTTP %d", resp2.StatusCode)
	}

	var streamResp piStreamRecorded
	if err := json.NewDecoder(io.LimitReader(resp2.Body, maxBodyBytes)).Decode(&streamResp); err != nil {
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
		return scrubURL(err)
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
