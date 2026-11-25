import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from . import db
from .model import Fixture, ModelUnavailable, Ollama
from .service import ask
from .snapshot import PASSAGES, SNAPSHOT, SOURCES, lookup
from .types import Lookup, Question, Reply, Review, Status

bearer = HTTPBearer(
    auto_error=False,
    description="Paste the generated REVIEWER_TOKEN or VISITOR_TOKEN from .env.",
)


def reviewer(auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    token = auth.credentials.encode() if auth else b""
    if hmac.compare_digest(token, os.environ["REVIEWER_TOKEN"].encode()):
        return os.environ["REVIEWER_ID"]
    if hmac.compare_digest(token, os.environ["VISITOR_TOKEN"].encode()):
        raise HTTPException(403, "Reviewer access is required.")
    raise HTTPException(
        401,
        "Supply a valid reviewer bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_app(model=None):
    @asynccontextmanager
    async def lifespan(app):
        review, visitor = (
            os.environ.get("REVIEWER_TOKEN", ""),
            os.environ.get("VISITOR_TOKEN", ""),
        )
        if (
            not review
            or not visitor
            or review == visitor
            or not os.environ.get("REVIEWER_ID", "").strip()
        ):
            raise RuntimeError(
                "Configure a reviewer identity and two distinct, nonempty access tokens."
            )
        db.initialize()
        provider = os.environ.get("MODEL_PROVIDER", "fixture")
        if model is None and provider not in ("fixture", "ollama"):
            raise RuntimeError("MODEL_PROVIDER must be fixture or ollama.")
        app.state.model = model or (Ollama() if provider == "ollama" else Fixture())
        yield

    api = FastAPI(
        title="Country Park Visitor Centre Assistant",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        description="Published guidance for Sai Kung, Shing Mun and Tai Mo Shan. Reviewer decisions create local simulated records.",
    )
    api.mount(
        "/ui",
        StaticFiles(directory=Path(__file__).resolve().parents[1] / "ui"),
        name="swagger-assets",
    )

    @api.get("/docs", include_in_schema=False)
    def docs():
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title=api.title,
            swagger_js_url="/ui/swagger-ui-bundle.js",
            swagger_css_url="/ui/swagger-ui.css",
            swagger_favicon_url="/ui/favicon-32x32.png",
            swagger_ui_parameters={"validatorUrl": None},
        )

    @api.get("/health", tags=["Service"])
    def health():
        with db.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ready", "model_adapter": type(api.state.model).__name__}

    @api.get("/snapshot", tags=["Sources"])
    def snapshot():
        return {
            k: SNAPSHOT[k]
            for k in ("snapshot_date", "timezone", "calendar_range", "notices")
        }

    @api.get("/sources", tags=["Sources"])
    def sources():
        return SOURCES

    @api.get("/sources/{source_id}", tags=["Sources"])
    def source(source_id: str):
        if source_id not in SOURCES:
            raise HTTPException(404, "Source not found.")
        return {
            "id": source_id,
            **SOURCES[source_id],
            "passages": [
                {k: p[k] for k in ("id", "locator", "text")}
                for p in PASSAGES.values()
                if p["source_id"] == source_id
            ],
        }

    @api.get("/status", response_model=Status, tags=["Visitors"])
    def read_status(args: Annotated[Lookup, Query()]):
        """Resolve a centre and Hong Kong date. This endpoint is read-only."""
        return lookup(args)

    @api.post("/ask", response_model=Reply, tags=["Visitors"])
    def answer(question: Question):
        """Ask about a visit, check a date or request one staff follow-up draft."""
        try:
            return ask(question, api.state.model)
        except ModelUnavailable as error:
            raise HTTPException(503, str(error)) from error

    @api.get("/review/proposals", tags=["Review"])
    def proposals(
        actor: Annotated[str, Depends(reviewer)],
        state: Literal["pending", "approved", "rejected"] = "pending",
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        with db.connect() as conn:
            return conn.execute(
                "SELECT * FROM proposals WHERE state=%s ORDER BY created_at DESC,id LIMIT %s OFFSET %s",
                (state, limit, offset),
            ).fetchall()

    @api.post("/review/proposals/{proposal_id}/decision", tags=["Review"])
    def review(
        proposal_id: UUID, body: Review, actor: Annotated[str, Depends(reviewer)]
    ):
        """Approve or reject a pending draft. Replaying the same decision returns the original record."""
        return db.decide(proposal_id, body.decision, actor)

    @api.get("/review/requests/{request_id}/audit", tags=["Review"])
    def audit(request_id: UUID, actor: Annotated[str, Depends(reviewer)]):
        with db.connect() as conn:
            if not conn.execute(
                "SELECT id FROM requests WHERE id=%s", (request_id,)
            ).fetchone():
                raise HTTPException(404, "Request not found.")
            return conn.execute(
                "SELECT * FROM audit WHERE request_id=%s ORDER BY seq", (request_id,)
            ).fetchall()

    return api


app = create_app()
