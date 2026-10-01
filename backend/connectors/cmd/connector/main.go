// Kairos Go Connector Service
// Layer 5: Zero-Copy OT Virtualization Layer
// Provides: OT historian federation (PI Web API, OPC-UA), high-throughput ingestion
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/kr7shnasomani/kairos/connectors/internal/ot"
)

var (
	historian   ot.HistorianClient
	fastAPIURL  string
	internalKey string
	httpClient  = &http.Client{Timeout: 15 * time.Second}
)

func main() {
	port := getEnv("GO_CONNECTOR_PORT", "8090")
	fastAPIURL = getEnv("FASTAPI_URL", "http://kairos-backend-api:8000")
	internalKey = getEnv("INTERNAL_API_KEY", devInternalKey)
	secret := os.Getenv("CONNECTOR_SHARED_SECRET")
	if err := validateConfig(os.Getenv("APP_ENV"), secret, internalKey); err != nil {
		log.Fatalf("[kairos-connector] refusing to start: %v", err)
	}

	// Initialise historian: use PI Web API if configured, else mock
	piURL := os.Getenv("PI_WEBAPI_BASE_URL")
	if piURL != "" {
		historian = ot.NewPIWebAPIClient(piURL, os.Getenv("PI_WEBAPI_USERNAME"), os.Getenv("PI_WEBAPI_PASSWORD"))
		log.Println("[kairos-connector] Using PI Web API historian") // never log the URL: it may carry credentials
	} else {
		historian = &ot.MockHistorianClient{}
		log.Println("[kairos-connector] PI_WEBAPI_BASE_URL not set — using mock historian")
	}

	router := gin.Default()

	// Health: the only unauthenticated route (Docker healthcheck, no data)
	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok", "service": "kairos-connector"})
	})

	// OT Federation endpoints (Layer 5)
	ot_ := router.Group("/ot", requireSecret(secret))
	{
		ot_.GET("/query", queryHistorian)
		ot_.GET("/connectors", listConnectors)
	}

	// EAM ingestion endpoints (Layer 1 — MDM bootstrap)
	eam := router.Group("/eam", requireSecret(secret))
	{
		eam.POST("/sync", syncEAMAssets)
		eam.POST("/work-order", receiveWorkOrder)
	}

	srv := &http.Server{
		Addr:              fmt.Sprintf(":%s", port),
		Handler:           router,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      30 * time.Second,
	}

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		log.Printf("[kairos-connector] Listening on :%s\n", port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Server error: %v", err)
		}
	}()

	<-quit
	log.Println("[kairos-connector] Shutting down...")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := srv.Shutdown(ctx); err != nil {
		log.Fatalf("Forced shutdown: %v", err)
	}

	log.Println("[kairos-connector] Stopped.")
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// =============================================================================
// OT handlers
// =============================================================================

func queryHistorian(c *gin.Context) {
	assetID := c.Query("asset_id")
	tag := c.Query("tag")
	fromStr := c.Query("from")
	toStr := c.Query("to")

	if assetID == "" || tag == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "asset_id and tag are required"})
		return
	}

	from, err := parseTimeOrDefault(fromStr, time.Now().Add(-30*24*time.Hour))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid 'from': expected RFC3339"})
		return
	}
	to, err := parseTimeOrDefault(toStr, time.Now())
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "invalid 'to': expected RFC3339"})
		return
	}

	q := ot.TimeSeriesQuery{Tag: tag, AssetID: assetID, From: from, To: to, MaxPoints: 50}
	points, err := historian.Query(c.Request.Context(), q)
	if err != nil {
		log.Printf("[kairos-connector] historian query error: %v\n", err)
		c.JSON(http.StatusBadGateway, gin.H{"error": "historian query failed"})
		return
	}

	_, isMock := historian.(*ot.MockHistorianClient)
	c.JSON(http.StatusOK, gin.H{
		"asset_id": assetID,
		"tag":      tag,
		"from":     from.Format(time.RFC3339),
		"to":       to.Format(time.RFC3339),
		"data":     points,
		"mock":     isMock,
	})
}

// =============================================================================
// Connector registry (Layer 5)
//
// The architecture's Layer 5 claim is that "new connector types are added without changing the
// core layer". This makes that claim inspectable: every supported historian type is registered
// with its configuration state and the exact env var that would activate it.
//
// An unconfigured connector reports itself as unconfigured. It never fabricates a reading and
// never fails silently — the previous coverage handler did both, returning hardcoded sensor tags
// for every asset under a "knowledge_graph" source label.
// =============================================================================

type connectorInfo struct {
	Name       string `json:"name"`
	Protocol   string `json:"protocol"`
	Status     string `json:"status"`
	ConfigVar  string `json:"config_var"`
	Configured bool   `json:"configured"`
	Detail     string `json:"detail"`
}

func connectorRegistry() []connectorInfo {
	piConfigured := os.Getenv("PI_WEBAPI_BASE_URL") != ""
	opcConfigured := os.Getenv("OPCUA_ENDPOINT_URL") != ""
	uniConfigured := os.Getenv("UNIFORMANCE_BASE_URL") != ""
	gqlConfigured := os.Getenv("HISTORIAN_GRAPHQL_URL") != ""

	status := func(configured bool, implemented bool) (string, string) {
		switch {
		case configured && implemented:
			return "active", "Configured and serving queries."
		case !implemented:
			return "registered", "Registered in the connector layer; client not implemented in this build."
		default:
			return "not_configured", "Implemented, but no endpoint configured for this deployment."
		}
	}

	piStatus, piDetail := status(piConfigured, true)
	if !piConfigured {
		piStatus, piDetail = "not_configured", "Implemented. No endpoint set — the mock historian is serving telemetry, and every response is stamped mock:true."
	}
	opcStatus, opcDetail := status(opcConfigured, false)
	uniStatus, uniDetail := status(uniConfigured, false)
	gqlStatus, gqlDetail := status(gqlConfigured, false)

	return []connectorInfo{
		{"OSIsoft PI Web API", "REST", piStatus, "PI_WEBAPI_BASE_URL", piConfigured, piDetail},
		{"OPC-UA", "OPC-UA binary", opcStatus, "OPCUA_ENDPOINT_URL", opcConfigured, opcDetail},
		{"Honeywell Uniformance", "REST", uniStatus, "UNIFORMANCE_BASE_URL", uniConfigured, uniDetail},
		{"Generic GraphQL federation", "GraphQL", gqlStatus, "HISTORIAN_GRAPHQL_URL", gqlConfigured, gqlDetail},
	}
}

func listConnectors(c *gin.Context) {
	registry := connectorRegistry()
	active := 0
	for _, r := range registry {
		if r.Status == "active" {
			active++
		}
	}
	_, isMock := historian.(*ot.MockHistorianClient)
	c.JSON(http.StatusOK, gin.H{
		"connectors":   registry,
		"active_count": active,
		"serving_historian": map[string]any{
			"mock": isMock,
			"note": "Mock historian returns synthetic telemetry. Every /ot/query response carries mock:true.",
		},
	})
}

// =============================================================================
// EAM handlers
// =============================================================================

// eamAssetRecord matches fixtures/sample_assets.json
type eamAssetRecord struct {
	AssetID        string  `json:"asset_id"`
	TagNumber      string  `json:"tag_number"`
	Name           string  `json:"name"`
	EquipmentClass string  `json:"equipment_class"`
	Criticality    string  `json:"criticality"`
	SiteID         string  `json:"site_id"`
	FacilityID     string  `json:"facility_id"`
	ParentAssetID  *string `json:"parent_asset_id"`
	EAMSource      string  `json:"eam_source"`
}

func syncEAMAssets(c *gin.Context) {
	eamEndpoint := os.Getenv("EAM_ODS_ENDPOINT")

	var assets []eamAssetRecord

	if eamEndpoint == "" {
		// Load from bundled fixture
		fixturePath := getEnv("EAM_FIXTURE_PATH", "./fixtures/sample_assets.json")
		data, err := os.ReadFile(fixturePath)
		if err != nil {
			log.Printf("[kairos-connector] fixture read failed: %v\n", err)
			c.JSON(http.StatusInternalServerError, gin.H{"error": "fixture read failed"})
			return
		}
		if err := json.Unmarshal(data, &assets); err != nil {
			log.Printf("[kairos-connector] fixture parse failed: %v\n", err)
			c.JSON(http.StatusInternalServerError, gin.H{"error": "fixture parse failed"})
			return
		}
		log.Printf("[kairos-connector] EAM_ODS_ENDPOINT not set — loaded %d assets from fixture\n", len(assets))
	} else {
		// TODO: pull from SAP PM / Maximo ODS when EAM_ODS_ENDPOINT is configured
		c.JSON(http.StatusNotImplemented, gin.H{"error": "live EAM ODS sync not yet implemented"})
		return
	}

	results := make([]gin.H, 0, len(assets))
	for _, asset := range assets {
		result := postAssetToFastAPI(c.Request.Context(), asset)
		results = append(results, result)
	}

	synced := 0
	for _, r := range results {
		if r["status"] == "ok" || r["status"] == "exists" {
			synced++
		}
	}

	log.Printf("[kairos-connector] EAM sync complete: %d/%d assets synced\n", synced, len(assets))
	c.JSON(http.StatusOK, gin.H{
		"status":  "completed",
		"total":   len(assets),
		"synced":  synced,
		"results": results,
	})
}

func postAssetToFastAPI(ctx context.Context, asset eamAssetRecord) gin.H {
	// Map EAM record to FastAPI AssetCreate schema
	payload := map[string]interface{}{
		"asset_id":             asset.AssetID,
		"tag_number":           asset.TagNumber,
		"name":                 asset.Name,
		"equipment_class":      asset.EquipmentClass,
		"criticality":          asset.Criticality,
		"site_id":              asset.SiteID,
		"facility_id":          asset.FacilityID,
		"eam_source":           asset.EAMSource,
		"confirmed_by_user_id": "eam-sync-service",
	}
	if asset.ParentAssetID != nil {
		payload["parent_asset_id"] = *asset.ParentAssetID
	}

	body, _ := json.Marshal(payload)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, fastAPIURL+"/assets", bytes.NewReader(body))
	if err != nil {
		log.Printf("[kairos-connector] asset %s request build error: %v\n", asset.AssetID, err)
		return gin.H{"asset_id": asset.AssetID, "status": "error", "error": "request failed"}
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+internalKey)

	resp, err := httpClient.Do(req)
	if err != nil {
		log.Printf("[kairos-connector] asset %s forward error: %v\n", asset.AssetID, err)
		return gin.H{"asset_id": asset.AssetID, "status": "error", "error": "request failed"}
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode == http.StatusOK || resp.StatusCode == http.StatusCreated {
		return gin.H{"asset_id": asset.AssetID, "status": "ok"}
	}
	// 409 or similar = already exists (MERGE is idempotent)
	if resp.StatusCode == http.StatusConflict {
		return gin.H{"asset_id": asset.AssetID, "status": "exists"}
	}
	respBody, _ := io.ReadAll(io.LimitReader(resp.Body, maxResponseBytes))
	log.Printf("[kairos-connector] asset %s rejected by FastAPI: %d %s\n", asset.AssetID, resp.StatusCode, respBody)
	return gin.H{"asset_id": asset.AssetID, "status": "error", "code": resp.StatusCode}
}

func receiveWorkOrder(c *gin.Context) {
	// Forward raw JSON body to FastAPI /events/work-order
	body, err := io.ReadAll(http.MaxBytesReader(c.Writer, c.Request.Body, maxRequestBytes))
	if err != nil {
		var tooBig *http.MaxBytesError
		if errors.As(err, &tooBig) {
			c.JSON(http.StatusRequestEntityTooLarge, gin.H{"error": "request body too large"})
			return
		}
		c.JSON(http.StatusBadRequest, gin.H{"error": "failed to read body"})
		return
	}

	req, err := http.NewRequestWithContext(c.Request.Context(), http.MethodPost,
		fastAPIURL+"/events/work-order", bytes.NewReader(body))
	if err != nil {
		log.Printf("[kairos-connector] work-order request build error: %v\n", err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "internal error"})
		return
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+internalKey)

	resp, err := httpClient.Do(req)
	if err != nil {
		log.Printf("[kairos-connector] work-order forward error: %v\n", err)
		c.JSON(http.StatusBadGateway, gin.H{"error": "upstream unreachable"})
		return
	}
	defer func() { _ = resp.Body.Close() }()
	respBody, _ := io.ReadAll(io.LimitReader(resp.Body, maxResponseBytes))

	// Success bodies pass through; failure text from FastAPI is logged, never echoed.
	if resp.StatusCode >= http.StatusBadRequest {
		log.Printf("[kairos-connector] work-order rejected by FastAPI: %d %s\n", resp.StatusCode, respBody)
		c.JSON(resp.StatusCode, gin.H{"error": "upstream request failed"})
		return
	}
	c.Data(resp.StatusCode, "application/json", respBody)
}

// =============================================================================
// Helpers
// =============================================================================

func parseTimeOrDefault(s string, def time.Time) (time.Time, error) {
	if s == "" {
		return def, nil
	}
	t, err := time.Parse(time.RFC3339, s)
	if err != nil {
		return time.Time{}, err
	}
	return t, nil
}
