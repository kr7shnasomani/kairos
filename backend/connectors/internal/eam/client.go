// EAM connector — SAP PM / IBM Maximo ingestion for MDM bootstrap
package eam

import "fmt"

// EAMConnector ingests asset master data from EAM/ERP systems
// for the Layer 1 MDM backbone bootstrap.
// CRITICAL: This must target a replicated ODS or data lake, NEVER the production ERP directly.
type EAMConnector interface {
	FetchAssets() ([]AssetRecord, error)
	FetchWorkOrders(since string) ([]WorkOrderRecord, error)
}

type AssetRecord struct {
	AssetID        string `json:"asset_id"`
	TagNumber      string `json:"tag_number"`
	Name           string `json:"name"`
	EquipmentClass string `json:"equipment_class"`
	Criticality    string `json:"criticality"`
	SiteID         string `json:"site_id"`
	FacilityID     string `json:"facility_id"`
	ParentAssetID  string `json:"parent_asset_id"`
	Source         string `json:"source"`
}

type WorkOrderRecord struct {
	WorkOrderID string `json:"work_order_id"`
	AssetID     string `json:"asset_id"`
	FailureCode string `json:"failure_code"`
	Description string `json:"description"`
	Status      string `json:"status"`
	CreatedAt   string `json:"created_at"`
}

// SAPPMConnector connects to a SAP SLT or ODS replication target (not production ERP)
type SAPPMConnector struct {
	ODSEndpoint string // SAP SLT / ODS replication endpoint — NOT production SAP ECC/S4
	Username    string
	Password    string
}

func (c *SAPPMConnector) FetchAssets() ([]AssetRecord, error) {
	if c.ODSEndpoint == "" {
		return nil, fmt.Errorf("SAP ODS endpoint not configured: set EAM_ODS_ENDPOINT in .env (never point it at the production ERP)")
	}
	// TODO: implement SAP ODS REST query for EQUI / IFLOT records
	return []AssetRecord{}, nil
}

func (c *SAPPMConnector) FetchWorkOrders(since string) ([]WorkOrderRecord, error) {
	// TODO: implement AUFK/AFKO work order pull from ODS
	return []WorkOrderRecord{}, nil
}
