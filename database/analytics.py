import logging
import motor.motor_asyncio
from datetime import datetime, timedelta
from info import MONGO_URI, DATABASE_NAME

logger = logging.getLogger(__name__)

class SearchAnalytics:
    def __init__(self):
        self.client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
        self.db = self.client[DATABASE_NAME]
        self.col = self.db["search_analytics"]

    async def ensure_indexes(self):
        # Performance ke liye indexes
        await self.col.create_index([("cleaned_query", 1)])
        await self.col.create_index([("timestamp", -1)])
        await self.col.create_index([("success", 1)])
        
    async def log_search(self, raw_query, cleaned_query, results_count, user_id, chat_id):
        try:
            doc = {
                "raw_query": raw_query,
                "cleaned_query": cleaned_query.lower().strip(),
                "results_count": results_count,
                "success": results_count > 0,
                "user_id": user_id,
                "chat_id": chat_id,
                "timestamp": datetime.utcnow()
            }
            await self.col.insert_one(doc)
        except Exception as e:
            logger.error(f"Analytics Log Error: {e}")

    async def get_top_searches(self, limit=10):
        pipeline = [
            {"$match": {"success": True}},
            {"$group": {"_id": "$cleaned_query", "hits": {"$sum": 1}}},
            {"$sort": {"hits": -1}},
            {"$limit": limit}
        ]
        return await self.col.aggregate(pipeline).to_list(None)

    async def get_failed_searches(self, limit=10):
        pipeline = [
            {"$match": {"success": False}},
            {"$group": {"_id": "$cleaned_query", "misses": {"$sum": 1}}},
            {"$sort": {"misses": -1}},
            {"$limit": limit}
        ]
        return await self.col.aggregate(pipeline).to_list(None)

    async def get_trending_searches(self, hours=24, limit=10):
        start_time = datetime.utcnow() - timedelta(hours=hours)
        pipeline = [
            {"$match": {"timestamp": {"$gte": start_time}}},
            {"$group": {"_id": "$cleaned_query", "hits": {"$sum": 1}}},
            {"$sort": {"hits": -1}},
            {"$limit": limit}
        ]
        return await self.col.aggregate(pipeline).to_list(None)

analytics = SearchAnalytics()
