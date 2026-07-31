from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.analytics.popular_topics import popular_topic_store


router = APIRouter()


class SearchEvent(BaseModel):
    query: str = Field(min_length=1, max_length=200)


@router.get("/popular-searches")
def get_popular_searches():
    return {
        "window_days": popular_topic_store.window_days,
        "topics": popular_topic_store.ranked_topics(),
    }


@router.post("/search-events")
def record_search_event(event: SearchEvent):
    return {"recorded": popular_topic_store.record_query(event.query)}
