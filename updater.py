"""
Запускается автоматически вместе с ботом.
Каждый час обновляет просмотры YouTube и TikTok роликов.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import get_conn, update_video_views
from handlers.videos import fetch_youtube_views, get_youtube_video_id, fetch_tiktok_views

logger = logging.getLogger(__name__)

async def update_all_views():
    logger.info("⏰ Обновляю просмотры всех роликов...")
    conn = get_conn()
    videos = conn.execute("SELECT * FROM videos WHERE platform IN ('youtube','tiktok')").fetchall()
    conn.close()

    for v in videos:
        try:
            if v["platform"] == "youtube":
                vid_id = get_youtube_video_id(v["url"])
                if vid_id:
                    _, views = fetch_youtube_views(vid_id)
                    if views is not None:
                        update_video_views(v["id"], views)
                        logger.info(f"YT обновлено: {v['url']} → {views}")

            elif v["platform"] == "tiktok":
                _, views = fetch_tiktok_views(v["url"])
                if views:
                    update_video_views(v["id"], views)
                    logger.info(f"TT обновлено: {v['url']} → {views}")
        except Exception as e:
            logger.error(f"Ошибка обновления {v['url']}: {e}")

def start_scheduler():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(update_all_views, "interval", hours=1, id="update_views")
    scheduler.start()
    logger.info("✅ Планировщик запущен (обновление каждый час)")
    return scheduler
