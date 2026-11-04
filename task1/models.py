"""Strict input contracts for the Task 1 MCP tools."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictStr


CustomerId = Annotated[StrictStr, Field(pattern=r"^CUST-[0-9]{5}$")]
PositiveAmount = Annotated[StrictFloat, Field(gt=0)]
RefundReason = Annotated[StrictStr, Field(min_length=10, max_length=1000)]


class StrictToolInput(BaseModel):
    """Reject coercion and fields that are not part of a tool contract."""

    model_config = ConfigDict(extra="forbid", strict=True)


class GetCustomerRecordInput(StrictToolInput):
    customer_id: CustomerId


class TriggerRefundInput(StrictToolInput):
    customer_id: CustomerId
    amount: PositiveAmount
    reason: RefundReason
