from fastapi import APIRouter

from app.api.v1.routes import (
    accounts,
    analytics,
    categories,
    health,
    insights,
    plaid,
    transactions,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(users.router)
api_router.include_router(plaid.router)
api_router.include_router(accounts.router)
api_router.include_router(transactions.router)
api_router.include_router(categories.router)
api_router.include_router(analytics.router)
api_router.include_router(insights.router)
