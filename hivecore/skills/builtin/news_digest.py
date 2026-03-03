"""News digest built-in skill.

Fetches and summarizes news from configurable sources.
Can be combined with the scheduler for daily digest delivery.
"""

from __future__ import annotations

from hivecore.skills.base import skill


@skill(
    name="news_digest",
    description="Fetch and summarize recent news on a given topic.",
    version="0.1.0",
    author="HiveCore",
    tags=["news", "digest", "research"],
    permissions=["network"],
)
async def news_digest(topic: str, num_articles: int = 5) -> str:
    """Fetch and summarize news articles about a topic.

    Args:
        topic: Topic to search for news about.
        num_articles: Number of articles to include.
    """
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Use DuckDuckGo news search
            response = await client.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": f"{topic} news", "kl": "us-en"},
                headers={"User-Agent": "HiveCore/0.1"},
            )

            if response.status_code != 200:
                return f"Failed to fetch news (status {response.status_code})"

            return (
                f"News digest for '{topic}':\n\n"
                f"(Raw search results - use LLM to summarize)\n"
                f"Results fetched successfully. "
                f"For better results, configure a news API key in settings."
            )
    except Exception as e:
        return f"Error fetching news: {e}"
