from typing import Annotated, Literal, Union

from pydantic import Field

from backend.app.schemas.common import ContractModel


class UiVariant(ContractModel):
    id: str
    minWidth: int = Field(ge=1, le=3840)
    maxWidth: int | None = Field(default=None, ge=1, le=3840)


class UiPressAction(ContractModel):
    action: Literal["press"]
    key: Literal["Control+k"]


class UiFillAction(ContractModel):
    action: Literal["fill"]
    role: Literal["searchbox"]
    name: str = Field(min_length=1)
    valueFrom: Literal["query"]


class UiExpectFocusedAction(ContractModel):
    action: Literal["expect-focused"]
    role: Literal["searchbox"]
    name: str = Field(min_length=1)


class UiExpectVisibleAction(ContractModel):
    action: Literal["expect-visible"]
    role: Literal["dialog", "option"]
    name: str | None = None
    textFrom: Literal["expectedHeadline"] | None = None


UiAction = Annotated[
    Union[UiPressAction, UiFillAction, UiExpectFocusedAction, UiExpectVisibleAction],
    Field(discriminator="action"),
]


class UiNoHorizontalOverflowAssertion(ContractModel):
    kind: Literal["no-horizontal-overflow"]


class UiOperationObservedAssertion(ContractModel):
    kind: Literal["operation-observed"]
    operationId: str


UiAssertion = Annotated[
    Union[UiNoHorizontalOverflowAssertion, UiOperationObservedAssertion],
    Field(discriminator="kind"),
]


class UiReadback(ContractModel):
    operationId: str
    queryFrom: Literal["query"]
    containsIdFrom: Literal["expectedNoteId"]
    limit: int = Field(default=8, ge=1, le=50)


class UiScenario(ContractModel):
    id: str
    title: str
    summary: str
    inputSchema: Literal["UiSearchScenarioInput"]
    targetState: str
    preconditions: list[str] = Field(default_factory=list)
    cleanup: Literal["none"] = "none"
    actions: list[UiAction] = Field(min_length=1)
    assertions: list[UiAssertion] = Field(min_length=1)
    readback: UiReadback


class UiContract(ContractModel):
    id: str
    featureId: str
    app: Literal["web"]
    route: str
    entryPoint: str
    dataCondition: str
    states: list[str] = Field(min_length=1)
    operationIds: list[str] = Field(min_length=1)
    sourcePaths: list[str] = Field(min_length=1)
    variants: list[UiVariant] = Field(min_length=1)
    scenarios: list[UiScenario] = Field(default_factory=list)
    manualReview: list[str] = Field(default_factory=list)
    mediaPolicy: Literal["none", "on-demand"] = "none"


class UiContractMap(ContractModel):
    schemaVersion: Literal[1]
    contracts: list[UiContract]


class UiSearchScenarioInput(ContractModel):
    query: str = Field(min_length=1, max_length=120)
    expectedNoteId: int = Field(gt=0)
    expectedHeadline: str = Field(min_length=1, max_length=255)
