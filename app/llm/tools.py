"""LLM tool wrappers over the finance services.

Deliberately thin: every tool validates its arguments with the same
Pydantic params model the REST layer uses, calls the same service method,
and returns the service's response DTO as JSON-ready dicts. No business
logic lives here — REST, LLM, and scheduled jobs all share the services.

Security boundary: user_id is bound at construction (from the caller's
auth context), never exposed in a tool schema — the model can only read
the data of the user the toolset was built for.

The definitions are provider-agnostic {name, description, input_schema}
dicts; input_schema is JSON Schema, which the Anthropic Messages API
accepts as-is.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.insights import (
    CompareSpendingParams,
    RecurringTransactionsParams,
    SpendingSummaryParams,
)
from app.schemas.transaction import TransactionListQuery, TransactionSearchParams
from app.services.analytics import AnalyticsService
from app.services.insights import InsightsService
from app.services.queries import TransactionQueryService


class UnknownToolError(ValueError):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    params_model: type[BaseModel]
    handler: Callable[[Any], Awaitable[BaseModel]]

    def definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.params_model.model_json_schema(),
        }


class FinanceToolset:
    """One user's finance tools, ready for an LLM tool-use loop."""

    def __init__(
        self,
        user_id: uuid.UUID,
        insights: InsightsService,
        analytics: AnalyticsService,
        transactions: TransactionQueryService,
    ) -> None:
        self._user_id = user_id
        self._insights = insights
        self._analytics = analytics
        self._transactions = transactions
        self._specs = {spec.name: spec for spec in self._build_specs()}

    def definitions(self) -> list[dict[str, Any]]:
        """Tool definitions to pass to the LLM provider."""
        return [spec.definition() for spec in self._specs.values()]

    async def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Validate arguments, run the tool, return a JSON-ready dict.

        Raises UnknownToolError / pydantic.ValidationError; the chat loop
        decides how to surface those back to the model.
        """
        spec = self._specs.get(name)
        if spec is None:
            raise UnknownToolError(f"unknown tool: {name}")
        params = spec.params_model.model_validate(arguments)
        response = await spec.handler(params)
        return response.model_dump(mode="json")

    def _build_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="get_spending_summary",
                description=(
                    "Headline finance numbers for a date range: total spending, "
                    "income, net, transaction count, averages, and the top "
                    "category and merchant. Use for questions like 'how much "
                    "did I spend last month?'. Omit dates for all history."
                ),
                params_model=SpendingSummaryParams,
                handler=lambda p: self._insights.get_spending_summary(
                    self._user_id, p
                ),
            ),
            ToolSpec(
                name="get_spending_by_category",
                description=(
                    "Spending broken down by category for a date range, with "
                    "each category's share of the total. Use for 'where does "
                    "my money go?' or 'how much on groceries?'."
                ),
                params_model=SpendingSummaryParams,  # same shape: range + account
                handler=lambda p: self._analytics.category_breakdown(
                    self._user_id, p.start_date, p.end_date, p.account_id
                ),
            ),
            ToolSpec(
                name="search_transactions",
                description=(
                    "Find individual transactions with filters (merchant text, "
                    "date range, amount range, account, category) and "
                    "sorting/pagination. Use when specific transactions are "
                    "asked about, e.g. 'my latest Starbucks charges'. Amounts "
                    "are positive for money out, negative for money in."
                ),
                params_model=TransactionSearchParams,
                handler=lambda p: self._transactions.list_transactions(
                    TransactionListQuery(user_id=self._user_id, **p.model_dump())
                ),
            ),
            ToolSpec(
                name="compare_spending",
                description=(
                    "Compare spending between two periods (baseline vs "
                    "comparison), overall and per category. Omit all dates to "
                    "compare last month against the current month to date. Use "
                    "for 'am I spending more than last month?'."
                ),
                params_model=CompareSpendingParams,
                handler=lambda p: self._insights.compare_spending(self._user_id, p),
            ),
            ToolSpec(
                name="get_recurring_transactions",
                description=(
                    "Detect subscription-like recurring charges (same merchant, "
                    "steady amount and cadence) with their cadence, average "
                    "amount, and next expected date. Use for 'what "
                    "subscriptions am I paying for?'."
                ),
                params_model=RecurringTransactionsParams,
                handler=lambda p: self._insights.get_recurring_transactions(
                    self._user_id, p
                ),
            ),
        ]


def build_finance_toolset(session: AsyncSession, user_id: uuid.UUID) -> FinanceToolset:
    """Compose a toolset from a session — for chat endpoints and jobs alike."""
    return FinanceToolset(
        user_id=user_id,
        insights=InsightsService(session),
        analytics=AnalyticsService(session),
        transactions=TransactionQueryService(session),
    )
