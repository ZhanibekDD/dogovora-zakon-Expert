from __future__ import annotations

import asyncio
from pathlib import Path

from redis import Redis
from rq import Queue
from rq.job import Job

from app.core.config import get_settings

QUEUE_NAME = "pdf_conversion"


def get_redis_connection() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url)


def get_queue() -> Queue:
    return Queue(QUEUE_NAME, connection=get_redis_connection())


def convert_docx_to_pdf_job(input_path: str, output_path: str) -> str:
    """The actual unit of work executed by the RQ worker process (app/worker.py)."""
    from app.services.pdf_service import convert_docx_to_pdf

    convert_docx_to_pdf(Path(input_path), Path(output_path))
    return output_path


def enqueue_pdf_conversion(input_path: Path, output_path: Path) -> Job:
    queue = get_queue()
    return queue.enqueue(
        convert_docx_to_pdf_job, str(input_path), str(output_path), job_timeout=120
    )


async def wait_for_job(job: Job, *, timeout_seconds: float = 100.0, poll_interval: float = 0.5) -> str:
    """Poll an RQ job from async code until it finishes, fails, or times out."""
    elapsed = 0.0
    while elapsed < timeout_seconds:
        job.refresh()
        if job.is_finished:
            return str(job.return_value())
        if job.is_failed:
            raise RuntimeError(f"Задача конвертации PDF завершилась с ошибкой: {job.exc_info}")
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    raise TimeoutError("Превышено время ожидания конвертации PDF из очереди задач")
