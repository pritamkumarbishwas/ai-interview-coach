from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.llm_usage import LlmUsage


class LlmUsageRepository:
    collection_name = "llm_usage"

    async def insert(self, db: AsyncIOMotorDatabase, usage: LlmUsage) -> str:
        doc = usage.model_dump(by_alias=True, exclude={"id"})
        result = await db[self.collection_name].insert_one(doc)
        return str(result.inserted_id)

    async def totals(self, db: AsyncIOMotorDatabase, since: datetime) -> dict:
        pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": None,
                    "calls": {"$sum": 1},
                    "prompt_tokens": {"$sum": "$prompt_tokens"},
                    "completion_tokens": {"$sum": "$completion_tokens"},
                    "cost_usd": {"$sum": "$cost_usd"},
                }
            },
        ]
        async for row in db[self.collection_name].aggregate(pipeline):
            return {
                "calls": int(row.get("calls", 0)),
                "prompt_tokens": int(row.get("prompt_tokens", 0)),
                "completion_tokens": int(row.get("completion_tokens", 0)),
                "cost_usd": round(float(row.get("cost_usd", 0.0)), 6),
            }
        return {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}

    async def by_model(self, db: AsyncIOMotorDatabase, since: datetime) -> list[dict]:
        pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": "$model",
                    "calls": {"$sum": 1},
                    "prompt_tokens": {"$sum": "$prompt_tokens"},
                    "completion_tokens": {"$sum": "$completion_tokens"},
                    "cost_usd": {"$sum": "$cost_usd"},
                }
            },
            {"$sort": {"cost_usd": -1}},
        ]
        rows: list[dict] = []
        async for row in db[self.collection_name].aggregate(pipeline):
            rows.append(
                {
                    "model": str(row["_id"]),
                    "calls": int(row.get("calls", 0)),
                    "prompt_tokens": int(row.get("prompt_tokens", 0)),
                    "completion_tokens": int(row.get("completion_tokens", 0)),
                    "cost_usd": round(float(row.get("cost_usd", 0.0)), 6),
                }
            )
        return rows


llm_usage_repository = LlmUsageRepository()
