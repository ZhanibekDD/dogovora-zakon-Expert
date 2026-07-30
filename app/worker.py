from __future__ import annotations

from rq import Worker

from app.core.logging import configure_logging, get_logger
from app.tasks.pdf_tasks import QUEUE_NAME, get_queue, get_redis_connection

logger = get_logger(__name__)


def main() -> None:
    configure_logging()
    connection = get_redis_connection()
    worker = Worker([get_queue()], connection=connection)
    logger.info("worker_starting", queue=QUEUE_NAME)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
