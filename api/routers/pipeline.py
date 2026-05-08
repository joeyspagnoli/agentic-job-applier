"""Pipeline progress SSE router."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


@router.get("/progress")
async def pipeline_progress_sse() -> StreamingResponse:
    """Server-sent events endpoint for real-time pipeline progress.

    Returns:
        Streaming SSE response with pipeline stage updates.
    """

    async def event_stream() -> AsyncIterator[str]:
        """Yield SSE-formatted pipeline progress events.

        Yields:
            SSE-formatted data strings.
        """
        yield f"data: {json.dumps({'stage': 'idle', 'source': '', 'progress': 0, 'jobsFound': 0, 'errors': []})}\n\n"

        heartbeat_interval_seconds = 30
        while True:
            await asyncio.sleep(heartbeat_interval_seconds)
            yield ": heartbeat\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
