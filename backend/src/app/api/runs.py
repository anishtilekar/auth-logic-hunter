import logging
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.events import publish, subscribe, unsubscribe
from app.api.schemas import RunCreate, RunDetail, RunSummary
from app.core.paths import resolve_target
from app.db.models import Invariant, Run, RunStatus
from app.db.session import async_session_factory, get_session
from app.pipeline.stage1_state_model.builder import build_application_model
from app.pipeline.stage2_invariants.extractor import extract_invariants

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunSummary, status_code=201)
async def create_run(
    body: RunCreate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> Run:
    run = Run(target_name=body.target_name, status=RunStatus.PENDING)
    session.add(run)
    await session.commit()
    await session.refresh(run)

    background_tasks.add_task(_execute_run, run.id)
    return run


@router.get("", response_model=list[RunSummary])
async def list_runs(session: AsyncSession = Depends(get_session)) -> list[Run]:
    result = await session.execute(select(Run).order_by(Run.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: int, session: AsyncSession = Depends(get_session)) -> RunDetail:
    run = await session.get(Run, run_id, options=[selectinload(Run.invariants)])
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunDetail(
        id=run.id,
        target_name=run.target_name,
        status=run.status,
        error=run.error,
        created_at=run.created_at,
        completed_at=run.completed_at,
        application_model=run.application_model,
        invariants=[inv.data for inv in run.invariants],
    )


@router.websocket("/{run_id}/events")
async def run_events(websocket: WebSocket, run_id: int) -> None:
    await websocket.accept()

    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            await websocket.close(code=4004, reason="Run not found")
            return
        await websocket.send_json(
            {"type": "status", "status": run.status.value, "error": run.error}
        )
        if run.status in (RunStatus.COMPLETED, RunStatus.FAILED):
            await websocket.close()
            return

    queue = subscribe(run_id)
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            if event.get("type") == "status" and event.get("status") in (
                RunStatus.COMPLETED.value,
                RunStatus.FAILED.value,
            ):
                break
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe(run_id, queue)


async def _execute_run(run_id: int) -> None:
    async with async_session_factory() as session:
        run = await session.get(Run, run_id)
        if run is None:
            return

        run.status = RunStatus.RUNNING
        await session.commit()
        publish(run_id, {"type": "status", "status": RunStatus.RUNNING.value})

        try:
            target_dir = resolve_target(run.target_name)
            model = build_application_model(target_dir)
            run.application_model = model.model_dump(mode="json")
            await session.commit()
            publish(run_id, {"type": "stage", "stage": "invariants"})

            invariants = extract_invariants(model)
            for inv in invariants:
                session.add(Invariant(run_id=run_id, data=inv.model_dump(mode="json")))

            run.status = RunStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
            await session.commit()
            publish(
                run_id,
                {
                    "type": "status",
                    "status": RunStatus.COMPLETED.value,
                    "summary": {
                        "resources": len(model.resources),
                        "endpoints": len(model.endpoints),
                        "transitions": len(model.transitions),
                        "invariants": len(invariants),
                    },
                },
            )
        except Exception as exc:  # noqa: BLE001 — surfaced to the run record, not swallowed
            logger.exception("Run %s failed", run_id)
            run.status = RunStatus.FAILED
            run.error = str(exc)
            run.completed_at = datetime.now(UTC)
            await session.commit()
            publish(run_id, {"type": "status", "status": RunStatus.FAILED.value, "error": str(exc)})
