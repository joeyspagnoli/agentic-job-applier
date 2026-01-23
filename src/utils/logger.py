"""Logging configuration for job discovery system."""

import sys
from pathlib import Path

from loguru import logger


def setup_logger(
    log_file: str = "logs/job_monitor.log",
    level: str = "INFO",
    rotation: str = "10 MB",
    retention: str = "1 week",
) -> None:
    """Configure application logger with console and file outputs.

    Args:
        log_file: Path to log file
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR)
        rotation: When to rotate log file (e.g., "10 MB", "1 day")
        retention: How long to keep old logs (e.g., "1 week", "5 files")
    """
    # Remove default logger
    logger.remove()

    # Console logger (colored, human-readable)
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        level=level,
        colorize=True,
    )

    # Ensure log directory exists
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # File logger (with rotation)
    logger.add(
        log_file,
        rotation=rotation,
        retention=retention,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{name}:{function}:{line} - {message}"
        ),
        level=level,
    )

    logger.info(f"Logger initialized. Log file: {log_file}")


def log_crawl_summary(
    source: str,
    company: str,
    jobs_found: int,
    jobs_new: int,
    duration_seconds: float,
) -> None:
    """Log a structured crawl summary."""
    logger.info(
        f"Crawl complete: {source}/{company} | "
        f"Found: {jobs_found} | New: {jobs_new} | "
        f"Duration: {duration_seconds:.2f}s"
    )


def log_cycle_summary(
    total_discovered: int,
    total_new: int,
    total_duplicate: int,
    sources_success: int,
    sources_failed: int,
    duration_seconds: float,
) -> None:
    """Log a structured cycle summary."""
    logger.info("=" * 60)
    logger.info("DISCOVERY CYCLE COMPLETE")
    logger.info(f"  Total jobs discovered: {total_discovered}")
    logger.info(f"  New jobs: {total_new}")
    logger.info(f"  Duplicates: {total_duplicate}")
    logger.info(f"  Sources succeeded: {sources_success}")
    logger.info(f"  Sources failed: {sources_failed}")
    logger.info(f"  Total duration: {duration_seconds:.2f}s")
    logger.info("=" * 60)
