from typing import List, Optional

from pydantic import BaseModel, Field


class RiskItem(BaseModel):
    facility_id: int
    product_id: int
    priority: str = Field(description="CRITICAL, HIGH, MEDIUM, or LOW")
    reason: str = Field(description="One or two sentences explaining the risk.")
    reason_amharic: str = Field(
        default="", description="Amharic (አማርኛ) translation of reason."
    )


class TransferRecommendationItem(BaseModel):
    source_facility_id: int
    destination_facility_id: int
    product_id: int
    quantity: int
    reason: str
    reason_amharic: str = Field(
        default="", description="Amharic (አማርኛ) translation of reason."
    )


class GapItem(BaseModel):
    facility_id: int
    product_id: int
    quantity: int


class InventoryAnalysisOutput(BaseModel):
    summary: str
    summary_amharic: str = Field(
        default="", description="Amharic (አማርኛ) translation of summary."
    )
    risks: List[RiskItem] = []
    transfer_recommendations: List[TransferRecommendationItem] = []
    unresolved_gaps: List[GapItem] = []
    missing_information: List[str] = []
    missing_information_amharic: List[str] = []


class GapPriorityItem(BaseModel):
    gap_id: int
    priority: str = Field(description="CRITICAL, HIGH, MEDIUM, or LOW")
    rank: int = Field(description="1 = most urgent. Must be unique.")
    reason: str
    reason_amharic: str = Field(
        default="", description="Amharic (አማርኛ) translation of reason."
    )


class SupplyGapPrioritizationOutput(BaseModel):
    summary: str
    summary_amharic: str = Field(
        default="", description="Amharic (አማርኛ) translation of summary."
    )
    ranked_gaps: List[GapPriorityItem] = []
    missing_information: List[str] = []
    missing_information_amharic: List[str] = []


class ProductDemandItem(BaseModel):
    product_id: int
    product_name: str
    open_follow_ups: int
    due_next_7_days: int
    due_next_30_days: int
    usable_stock: int
    projected_gap: Optional[int] = None
    comment: str = ""
    comment_amharic: str = Field(
        default="", description="Amharic (አማርኛ) translation of comment."
    )


class VaccinationDemandOutput(BaseModel):
    summary: str
    summary_amharic: str = Field(
        default="", description="Amharic (አማርኛ) translation of summary."
    )
    by_product: List[ProductDemandItem] = []
    priorities: List[str] = []
    priorities_amharic: List[str] = []
    missing_information: List[str] = []
    missing_information_amharic: List[str] = []


class TransferSourcingProposalItem(BaseModel):
    request_id: int
    source_facility_id: int
    product_id: int
    quantity: int
    reason: str = Field(description="One or two sentences explaining the choice of source.")
    reason_amharic: str = Field(
        default="", description="Amharic (አማርኛ) translation of reason."
    )


class TransferSourcingOutput(BaseModel):
    summary: str
    summary_amharic: str = Field(
        default="", description="Amharic (አማርኛ) translation of summary."
    )
    proposals: List[TransferSourcingProposalItem] = []
    missing_information: List[str] = []
    missing_information_amharic: List[str] = []


SCHEMA_BY_TYPE = {
    "INVENTORY_ANALYSIS": InventoryAnalysisOutput,
    "SUPPLY_GAP_PRIORITIZATION": SupplyGapPrioritizationOutput,
    "VACCINATION_DEMAND_SUMMARY": VaccinationDemandOutput,
    "TRANSFER_SOURCING": TransferSourcingOutput,
}