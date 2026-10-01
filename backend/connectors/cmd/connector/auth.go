package main

import (
	"crypto/sha256"
	"crypto/subtle"
	"errors"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
)

const (
	secretHeader     = "X-Connector-Secret"
	devConnectorKey  = "kairos-connector-dev-secret"
	devInternalKey   = "kairos-internal-dev-key"
	maxRequestBytes  = 1 << 20 // work-order bodies are small JSON documents
	maxResponseBytes = 4 << 20 // upstream replies we read into memory
)

// validateConfig refuses to start without a shared secret, and refuses the well-known development
// values unless APP_ENV is explicitly "development" (an unset or misspelled env counts as
// production, so a typo cannot silently weaken the check). Compose supplies the dev default.
func validateConfig(appEnv, secret, internalKey string) error {
	if secret == "" {
		return errors.New("CONNECTOR_SHARED_SECRET is not set")
	}
	if !strings.EqualFold(appEnv, "development") && (secret == devConnectorKey || internalKey == devInternalKey) {
		return errors.New("outside APP_ENV=development the development CONNECTOR_SHARED_SECRET and INTERNAL_API_KEY are refused")
	}
	return nil
}

// requireSecret rejects any request whose X-Connector-Secret header does not match. Both sides are
// hashed first so the comparison is constant-time regardless of length.
func requireSecret(secret string) gin.HandlerFunc {
	want := sha256.Sum256([]byte(secret))
	return func(c *gin.Context) {
		got := sha256.Sum256([]byte(c.GetHeader(secretHeader)))
		if subtle.ConstantTimeCompare(got[:], want[:]) != 1 {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "unauthorized"})
			return
		}
		c.Next()
	}
}
