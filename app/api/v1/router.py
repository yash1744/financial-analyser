from fastapi import APIRouter

from app.api.v1.routes import (
    accounts,
    ai,
    analytics,
    auth,
    categories,
    health,
    insights,
    labels,
    plaid,
    transactions,
    user_categories,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(plaid.router)
api_router.include_router(accounts.router)
api_router.include_router(transactions.router)
api_router.include_router(categories.router)
api_router.include_router(labels.router)
api_router.include_router(user_categories.router)
api_router.include_router(analytics.router)
api_router.include_router(insights.router)
api_router.include_router(ai.router)
