"""
Temporal activity worker for the Elicitation Engine (Layer 6).
Polls the kairos-elicitation task queue and runs MicroInterviewWorkflow activities.
"""

import asyncio
import os

import structlog
from temporalio.client import Client
from temporalio.worker import UnsandboxedWorkflowRunner, Worker

from workflows.elicitation_workflow import (
    MicroInterviewWorkflow,
    StoreElicitationResponseWorkflow,
    generate_interview_questions,
    store_elicitation_response,
)

log = structlog.get_logger(__name__)


async def main():
    temporal_address = os.environ.get("TEMPORAL_ADDRESS", "kairos-temporal:7233")
    task_queue = os.environ.get("TEMPORAL_TASK_QUEUE", "kairos-elicitation")

    log.info("elicitation_worker.connecting", address=temporal_address, queue=task_queue)

    client = await Client.connect(temporal_address)

    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[MicroInterviewWorkflow, StoreElicitationResponseWorkflow],
        activities=[generate_interview_questions, store_elicitation_response],
        workflow_runner=UnsandboxedWorkflowRunner(),
    )

    log.info("elicitation_worker.started", queue=task_queue)
    await worker.run()


if __name__ == "__main__":
    from api.services.http import run_with_client
    run_with_client(main())
