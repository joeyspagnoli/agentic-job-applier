# Phase 2: Agent Infrastructure for Job Application Workflow

## Overview

Set up the infrastructure to feed jobs from Phase 1 discovery into a multi-agent workflow. The implementation provides the plumbing - you'll define the agent architecture.

## What This Implementation Provides

1. **Pydantic models** for job data that agents can consume
2. **main.py orchestration** - fetches jobs, runs your agent, handles the loop
3. **Database schema** for storing agent decisions
4. **Clear integration points** where you plug in your agent

## What You'll Implement (After This)

- `root_agent` definition and workflow architecture
- Agent decision → database status mapping logic
- Sequential/conditional agent flow with tools

## Architecture

```
Every 30 min (systemd timer):
    ↓
main.py
    ↓
1. run_job_discovery() [Phase 1 - existing]
   └─ Fetches jobs → Stores with status='NEW'
    ↓
2. run_agent_workflow() [Phase 2 - NEW]
   ├─ Load NEW jobs from database
   ├─ Convert to Pydantic models
   ├─ For each job:
   │   ├─ Format job data
   │   ├─ Run YOUR root_agent
   │   └─ (You handle): Update DB based on agent result
   └─ Log summary
```

## Pydantic Models

### JobPosting (Already Exists)
Located in `src/models/job_posting.py` - no changes needed.

### JobBatch (NEW)
Wrapper for passing multiple jobs to agent if needed:

```python
# src/agents/models.py

from pydantic import BaseModel
from src.models.job_posting import JobPosting


class JobBatch(BaseModel):
    """Batch of jobs for agent processing."""
    jobs: list[JobPosting]
    total_count: int
    batch_number: int
```

For single job processing, just use `JobPosting` directly.

## Database Schema Changes

Add columns to track agent processing:

```sql
-- src/database/schema.sql

-- Add agent decision tracking
ALTER TABLE job_postings ADD COLUMN
  agent_processed_at TIMESTAMP;

ALTER TABLE job_postings ADD COLUMN
  agent_result TEXT;  -- JSON blob for whatever your agent returns

CREATE INDEX IF NOT EXISTS idx_agent_processed
  ON job_postings(agent_processed_at);
```

Migration happens automatically via `db_manager.migrate_agent_schema()`.

## main.py Structure

```python
"""Main entry point - job discovery + agent workflow."""

import asyncio
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from loguru import logger

from src.database.db_manager import DatabaseManager
from src.models.job_posting import JobPosting
from src.utils.logger import setup_logger


async def run_job_discovery():
    """Run Phase 1 job discovery (existing function)."""
    # ... existing implementation ...
    pass


async def run_agent_workflow(config: dict) -> dict:
    """Run agents on NEW jobs.

    This is the infrastructure - YOU define root_agent and handle results.
    """
    logger.info("=" * 60)
    logger.info("STARTING AGENT WORKFLOW")
    logger.info("=" * 60)

    db_path = os.getenv("DATABASE_PATH", "data/jobs.db")

    async with DatabaseManager(db_path) as db:
        # Ensure schema is migrated
        await db.migrate_agent_schema()

        # Get NEW jobs from database
        batch_size = config.get('processing', {}).get('batch_size', 100)
        new_jobs_data = await db.get_jobs_by_status("NEW", limit=batch_size)

        if not new_jobs_data:
            logger.info("No NEW jobs to process")
            return {"processed": 0}

        logger.info(f"Processing {len(new_jobs_data)} NEW jobs")

        # Convert to JobPosting models
        jobs = []
        for job_dict in new_jobs_data:
            job = JobPosting(
                source=job_dict['source'],
                source_url=job_dict['source_url'],
                company=job_dict['company'],
                title=job_dict['title'],
                location=job_dict.get('location'),
                is_remote=job_dict.get('is_remote'),
                salary_min=job_dict.get('salary_min'),
                salary_max=job_dict.get('salary_max'),
                description=job_dict.get('description', ''),
                requirements=job_dict.get('requirements', ''),
                # ... other fields
            )
            jobs.append(job)

        # ===================================================================
        # YOUR AGENT INTEGRATION POINT
        # ===================================================================

        # TODO: Define your root_agent here
        # from google.adk.agents import Agent
        # from google.adk import Runner
        #
        # root_agent = Agent(
        #     name="job_workflow",
        #     instruction="...",
        #     tools=[...],
        #     sub_agents=[...],
        # )
        #
        # runner = Runner(
        #     app_name="job_applier",
        #     agent=root_agent,
        #     session_service=InMemorySessionService(),
        # )

        processed_count = 0

        # Process each job
        for idx, job in enumerate(jobs, 1):
            logger.info(f"[{idx}/{len(jobs)}] Processing: {job.company} - {job.title}")

            # Format job for agent input
            job_input = format_job_for_agent(job)

            # TODO: Run your agent
            # async for event in runner.run_async(
            #     session_id=job.job_hash,
            #     user_input=job_input,
            # ):
            #     # Handle agent events
            #     # Check for exit/break conditions
            #     # Extract agent decision
            #     pass

            # TODO: Update database based on agent result
            # await db.update_job_status(job.job_hash, new_status)
            # await db.update_job_agent_result(job.job_hash, agent_output)

            processed_count += 1

        logger.info("=" * 60)
        logger.info(f"AGENT WORKFLOW COMPLETE - Processed {processed_count} jobs")
        logger.info("=" * 60)

        return {"processed": processed_count}


def format_job_for_agent(job: JobPosting) -> str:
    """Format job posting as text for agent consumption.

    Customize this format to match what your agent expects.
    """
    salary_str = "Not listed"
    if job.salary_min and job.salary_max:
        salary_str = f"${job.salary_min/100:,.0f} - ${job.salary_max/100:,.0f}"

    return f"""
JOB POSTING

Company: {job.company}
Title: {job.title}
Location: {job.location or 'Not specified'}
Remote: {'Yes' if job.is_remote else 'No'}
Salary: {salary_str}
Job Type: {job.job_type or 'Not specified'}

Description:
{job.description[:2000]}

Requirements:
{job.requirements[:1000] if job.requirements else 'Not specified'}

Source: {job.source}
URL: {job.source_url}
""".strip()


async def main():
    """Main entry point."""
    load_dotenv()
    setup_logger(
        log_file=os.getenv("LOG_FILE", "logs/job_monitor.log"),
        level=os.getenv("LOG_LEVEL", "INFO"),
    )

    # Load config
    config_dir = Path(__file__).parent / "config"
    search_criteria = yaml.safe_load(
        (config_dir / "search_criteria.yaml").read_text()
    )

    try:
        # Phase 1: Discover jobs
        await run_job_discovery()

        # Phase 2: Run agent workflow
        config = {"processing": {"batch_size": 100}}
        await run_agent_workflow(config)

    except KeyboardInterrupt:
        logger.info("Process interrupted")
    except Exception as e:
        logger.exception(f"Process failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
```

## File Structure

```
agentic-job-applier/
├── src/
│   ├── agents/
│   │   ├── __init__.py
│   │   └── models.py           [NEW - JobBatch model if needed]
│   ├── database/
│   │   ├── schema.sql          [MODIFY - add agent columns]
│   │   └── db_manager.py       [MODIFY - add migration method]
│   └── [existing modules unchanged]
├── main.py                      [MODIFY - add agent workflow]
└── config/
    └── search_criteria.yaml     [existing - unchanged]
```

## Implementation Files

### 1. `src/agents/models.py` (NEW)

```python
"""Pydantic models for agent workflow."""

from pydantic import BaseModel
from src.models.job_posting import JobPosting


class JobBatch(BaseModel):
    """Batch of jobs for processing.

    Use this if you want to pass multiple jobs to your agent at once.
    Otherwise, just use JobPosting directly.
    """
    jobs: list[JobPosting]
    total_count: int
    batch_number: int = 1
```

### 2. `src/database/schema.sql` (MODIFY)

Add at the end:

```sql
-- Agent workflow tracking (Phase 2)
-- Note: Run migration via db_manager.migrate_agent_schema()

-- ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS
--   agent_processed_at TIMESTAMP;

-- ALTER TABLE job_postings ADD COLUMN IF NOT EXISTS
--   agent_result TEXT;  -- JSON blob for agent output

-- CREATE INDEX IF NOT EXISTS idx_agent_processed
--   ON job_postings(agent_processed_at);
```

### 3. `src/database/db_manager.py` (MODIFY)

Add method:

```python
async def migrate_agent_schema(self) -> None:
    """Add agent workflow columns if they don't exist."""
    try:
        # Check if columns exist
        cursor = await self.conn.execute("PRAGMA table_info(job_postings)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        # Add agent_processed_at if missing
        if 'agent_processed_at' not in column_names:
            await self.conn.execute(
                "ALTER TABLE job_postings ADD COLUMN agent_processed_at TIMESTAMP"
            )
            logger.info("Added agent_processed_at column")

        # Add agent_result if missing
        if 'agent_result' not in column_names:
            await self.conn.execute(
                "ALTER TABLE job_postings ADD COLUMN agent_result TEXT"
            )
            logger.info("Added agent_result column")

        # Create index if doesn't exist
        await self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_agent_processed
            ON job_postings(agent_processed_at)
            """
        )

        await self.conn.commit()
    except Exception as e:
        logger.warning(f"Schema migration warning: {e}")


async def update_job_agent_result(
    self,
    job_hash: str,
    agent_result: str,  # JSON string
) -> None:
    """Store agent processing result."""
    await self.conn.execute(
        """
        UPDATE job_postings
        SET agent_result = ?,
            agent_processed_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_hash = ?
        """,
        (agent_result, job_hash),
    )
    await self.conn.commit()
```

### 4. `main.py` (MODIFY)

See full implementation above - key changes:
1. Add `run_agent_workflow()` function
2. Add `format_job_for_agent()` helper
3. Call agent workflow after discovery in `main()`
4. Clear TODO comments where you plug in your agent

### 5. `.env.example` (MODIFY)

Add:

```bash
# Agent LLM Configuration
GOOGLE_API_KEY=your_google_api_key_here
# OR
OPENAI_API_KEY=your_openai_key_here
# OR
ANTHROPIC_API_KEY=your_anthropic_key_here

# Agent Processing
AGENT_BATCH_SIZE=100
```

## What You Need to Do After Implementation

### 1. Define Your Agent

In `main.py`, replace the TODO section:

```python
from google.adk.agents import Agent, SequentialAgent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool

def exit_workflow():
    """Tool for agent to exit if shouldn't apply."""
    return "EXIT"

root_agent = Agent(
    name="job_workflow",
    instruction="Evaluate if we should apply to this job...",
    tools=[FunctionTool(func=exit_workflow)],
    sub_agents=[
        SequentialAgent(
            name="application_pipeline",
            sub_agents=[
                # Your resume, cover letter, submit agents
            ]
        )
    ],
)

runner = Runner(
    app_name="job_applier",
    agent=root_agent,
    session_service=InMemorySessionService(),
)
```

### 2. Process Agent Events

```python
for idx, job in enumerate(jobs, 1):
    job_input = format_job_for_agent(job)

    should_exit = False
    agent_decision = None

    async for event in runner.run_async(
        session_id=job.job_hash,
        user_input=job_input,
    ):
        # Check if agent called exit tool
        if event.content:
            for call in event.get_function_calls():
                if call.name == "exit_workflow":
                    should_exit = True
                    break

        # Extract structured output if any
        # ... your logic ...

    if should_exit:
        # Agent decided not to apply
        await db.update_job_status(job.job_hash, "FILTERED")
        continue

    # Agent completed workflow
    await db.update_job_status(job.job_hash, "QUALIFIED")
```

### 3. Map Results to Database

Define how agent decisions update job status:

```python
# Example mapping
if agent_result.should_apply:
    await db.update_job_status(job.job_hash, "QUALIFIED")
else:
    await db.update_job_status(job.job_hash, "FILTERED")

# Store full agent output
import json
await db.update_job_agent_result(
    job.job_hash,
    json.dumps(agent_result.dict())
)
```

## Testing

### 1. Test Schema Migration

```bash
uv run python -c "
import asyncio
from src.database.db_manager import DatabaseManager

async def test():
    async with DatabaseManager('data/jobs.db') as db:
        await db.migrate_agent_schema()
        print('Migration complete')

asyncio.run(test())
"
```

### 2. Test Job Loading

```bash
uv run python -c "
import asyncio
from main import run_agent_workflow

async def test():
    config = {'processing': {'batch_size': 5}}
    result = await run_agent_workflow(config)
    print(f'Processed: {result}')

asyncio.run(test())
"
```

Should show jobs being loaded and formatted (agent calls will be TODOs).

### 3. Verify Pydantic Models

```bash
uv run python -c "
from src.models.job_posting import JobPosting
from src.agents.models import JobBatch

# Create test job
job = JobPosting(
    source='test',
    source_url='https://example.com',
    company='Test Co',
    title='Engineer',
    description='Test job',
)

print(f'Job hash: {job.job_hash}')
print(f'Job model: {job.model_dump_json(indent=2)}')

# Test batch
batch = JobBatch(jobs=[job], total_count=1)
print(f'Batch: {batch.model_dump_json(indent=2)}')
"
```

## Implementation Checklist

- [ ] Create `src/agents/__init__.py`
- [ ] Create `src/agents/models.py` (JobBatch)
- [ ] Modify `src/database/schema.sql` (add agent columns as comments)
- [ ] Modify `src/database/db_manager.py` (add migrate_agent_schema, update_job_agent_result)
- [ ] Modify `main.py` (add run_agent_workflow, format_job_for_agent, integrate into main)
- [ ] Modify `.env.example` (add agent API keys)
- [ ] Test schema migration
- [ ] Test job loading and formatting
- [ ] Verify jobs are converted to JobPosting models correctly

## After Implementation

You'll have:
- ✅ Jobs loading from database as JobPosting models
- ✅ Main loop ready to run your agent
- ✅ Database schema ready to store agent results
- ✅ Clear integration points marked with TODO comments

You can then focus entirely on:
- Defining your agent architecture
- Implementing the gate logic
- Handling agent events and results
- Mapping decisions to database updates

## Critical Files

**Must Create**:
1. `src/agents/models.py` - JobBatch model

**Must Modify**:
1. `src/database/db_manager.py` - Add migration and update methods
2. `main.py` - Add agent workflow function
3. `.env.example` - Add API key placeholders

**Reference (no changes)**:
- `src/models/job_posting.py` - Already has JobPosting model
- `src/database/schema.sql` - Schema comments for reference
