import asyncio
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
from app.core.config import settings
from app.core.paths import resolve_target
from app.db.models import Finding, Hypothesis, Invariant, Run, RunStatus
from app.db.session import async_session_factory, get_session
from app.pipeline.stage1_state_model.builder import build_application_model
from app.pipeline.stage2_invariants.extractor import extract_invariants
from app.pipeline.stage3_hypotheses.generator import generate_hypotheses
from app.pipeline.stage5_solver.schema import Verdict
from app.pipeline.stage5_solver.solver import prove_all, refutation_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])

REFUTED = {Verdict.UNSAT, Verdict.INVALID}


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
    run = await session.get(
        Run,
        run_id,
        options=[
            selectinload(Run.invariants),
            selectinload(Run.hypotheses),
            selectinload(Run.findings),
        ],
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    # Findings pair with hypotheses by position, so both lists must come back in
    # insertion order — relationships don't guarantee that on their own.
    return RunDetail(
        id=run.id,
        target_name=run.target_name,
        status=run.status,
        error=run.error,
        created_at=run.created_at,
        completed_at=run.completed_at,
        application_model=run.application_model,
        invariants=[inv.data for inv in sorted(run.invariants, key=lambda x: x.id)],
        hypotheses=[h.data for h in sorted(run.hypotheses, key=lambda x: x.id)],
        findings=[f.data for f in sorted(run.findings, key=lambda x: x.id)],
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

            # The LLM stages are correctly synchronous (same functions the CLI
            # calls directly), but a blocking network call straight inside this
            # async task would freeze the whole event loop for its duration.
            # Offload to a thread; Z3 is CPU-bound, offloaded for the same reason.
            invariants = await asyncio.to_thread(extract_invariants, model)
            for inv in invariants:
                session.add(Invariant(run_id=run_id, data=inv.model_dump(mode="json")))
            await session.commit()
            publish(run_id, {"type": "stage", "stage": "hypotheses"})

            hypotheses = await asyncio.to_thread(generate_hypotheses, model, invariants)
            for hyp in hypotheses:
                session.add(Hypothesis(run_id=run_id, data=hyp.model_dump(mode="json")))
            await session.commit()
            publish(run_id, {"type": "stage", "stage": "solving"})

            results = await asyncio.to_thread(prove_all, model, hypotheses, invariants)
            for res in results:
                session.add(Finding(run_id=run_id, data=res.model_dump(mode="json")))
            await session.commit()

            # Counterexample feedback loop: refuted chains from the latest round
            # (cumulative history in the prompt) drive another Stage 3 round,
            # bounded by settings.hypothesis_rounds. Stops early once a round
            # produces nothing new to refute.
            latest_refuted = [
                (h, r) for h, r in zip(hypotheses, results, strict=True) if r.verdict in REFUTED
            ]
            for round_no in range(2, settings.hypothesis_rounds + 1):
                if not latest_refuted:
                    break
                feedback = [
                    refutation_summary(h, r)
                    for h, r in zip(hypotheses, results, strict=True)
                    if r.verdict in REFUTED
                ]
                publish(run_id, {"type": "stage", "stage": "refining", "round": round_no})
                more = await asyncio.to_thread(
                    generate_hypotheses, model, invariants, refuted=feedback
                )
                for hyp in more:
                    session.add(Hypothesis(run_id=run_id, data=hyp.model_dump(mode="json")))
                await session.commit()
                publish(run_id, {"type": "stage", "stage": "solving"})

                more_results = await asyncio.to_thread(
                    prove_all, model, more, invariants, index_offset=len(hypotheses)
                )
                for res in more_results:
                    session.add(Finding(run_id=run_id, data=res.model_dump(mode="json")))
                await session.commit()

                latest_refuted = [
                    (h, r) for h, r in zip(more, more_results, strict=True) if r.verdict in REFUTED
                ]
                hypotheses += more
                results += more_results

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
                        "hypotheses": len(hypotheses),
                        "findings": len(results),
                        "proven": sum(r.verdict == Verdict.SAT for r in results),
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
