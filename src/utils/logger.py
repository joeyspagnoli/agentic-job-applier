"""Configure and standardize logging for the job discovery workflows."""

import sys
from pathlib import Path

from loguru import logger


def setup_logger(
    log_file: str = "logs/job_monitor.log",
    level: str = "INFO",
    rotation: str = "10 MB",
    retention: str = "1 week",
) -> None:
    """Configure the shared logger with console and file sinks.

    Purpose:
        Establish one consistent logging setup for interactive runs, scheduled
        discovery jobs, and script entrypoints.
    Args:
        log_file: Path to the rotating log file written on disk.
        level: Minimum log level that should be emitted by the logger.
        rotation: Rotation policy understood by Loguru for file rollover.
        retention: Retention policy describing how long old logs are kept.
    Output:
        Returns `None` after replacing the default logger configuration with the
        repository's console and file outputs.
    """
    # Loguru installs a default sink automatically, so it is removed first to
    # avoid duplicated log lines once the custom sinks are added.
    logger.remove()

    # The console sink favors readability during local runs by including color,
    # timestamps, and the function/line that emitted the message.
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

    # The file sink needs its parent directory to exist because scheduled runs
    # may execute in a fresh environment.
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # The file sink keeps a stable audit trail with rotation so long-running
    # deployments do not grow one unbounded logfile forever.
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
    """Log the summary for one source crawl.

    Purpose:
        Keep crawl-level metrics in a predictable format so individual source
        runs are easy to scan in logs and dashboards.
    Args:
        source: Source identifier that produced the crawl.
        company: Company or search label associated with the crawl.
        jobs_found: Total jobs returned before deduplication.
        jobs_new: Total jobs that remained after deduplication.
        duration_seconds: Crawl duration in seconds.
    Output:
        Returns `None` after writing the formatted summary to the logger.
    """
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
    """Log the summary for a full discovery cycle.

    Purpose:
        Emit the high-level metrics that describe the outcome of one full run
        across all configured sources.
    Args:
        total_discovered: Total jobs found before deduplication.
        total_new: Total jobs inserted as new records.
        total_duplicate: Total jobs skipped because they already existed.
        sources_success: Number of crawl units that completed successfully.
        sources_failed: Number of crawl units that failed.
        duration_seconds: Total cycle duration in seconds.
    Output:
        Returns `None` after logging the cycle summary banner and metrics.
    """
    # The surrounding divider lines make it easy to spot the end of a cycle in
    # a long log file with many individual crawl messages.
    logger.info("=" * 60)
    logger.info("DISCOVERY CYCLE COMPLETE")
    logger.info(f"  Total jobs discovered: {total_discovered}")
    logger.info(f"  New jobs: {total_new}")
    logger.info(f"  Duplicates: {total_duplicate}")
    logger.info(f"  Sources succeeded: {sources_success}")
    logger.info(f"  Sources failed: {sources_failed}")
    logger.info(f"  Total duration: {duration_seconds:.2f}s")
    logger.info("=" * 60)
