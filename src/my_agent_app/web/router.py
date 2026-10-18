import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from my_agent_app.models import queries
from my_agent_app.web.rendering import FIXABLE_STATUSES, STATUS_BADGES, extract_severity, render_markdown

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
templates.env.filters["badge_class"] = lambda status: STATUS_BADGES.get(status, "badge-incomplete")

DB_UNAVAILABLE_MESSAGE = "Banco de dados indisponível, tente novamente em instantes"


async def get_session(request: Request):
    async with request.app.state.sessionmaker() as session:
        yield session


def _error(request: Request, status_code: int, message: str, title: str, **extra):
    return templates.TemplateResponse(
        request, "error.html", {"status_code": status_code, "message": message, "title": title, **extra}, status_code=status_code
    )


def _db_unavailable(request: Request, exc: Exception):
    logger.error("Banco indisponivel ao atender %s: %s", request.url.path, exc)
    return _error(
        request, 503, DB_UNAVAILABLE_MESSAGE, "Indisponível", back_url=request.url.path, back_label="Tentar novamente"
    )


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "home.html")


@router.get("/reports", response_class=HTMLResponse)
async def list_reports(request: Request, session=Depends(get_session)):
    try:
        reports = await queries.list_reports(session)
    except (SQLAlchemyError, OSError) as exc:
        return _db_unavailable(request, exc)
    items = [
        {"id": r.id, "created_at": r.created_at, "status": r.status, "severity": extract_severity(r.markdown)}
        for r in reports
    ]
    return templates.TemplateResponse(request, "reports.html", {"reports": items})


async def render_report_detail(
    request: Request, session, report_id: uuid.UUID, message: str | None = None, status_code: int = 200
):
    """Detalhe do relatorio; tambem usado pela rota de correcao (PRD 004) para reexibir a pagina com uma mensagem."""
    try:
        report = await queries.get_report(session, report_id)
    except (SQLAlchemyError, OSError) as exc:
        return _db_unavailable(request, exc)
    if report is None:
        return _error(
            request, 404, "Relatório não encontrado", "Não encontrado", back_url="/reports", back_label="Voltar para relatórios"
        )
    context = {
        "report": report,
        "content": render_markdown(report.markdown),
        "can_fix": report.status in FIXABLE_STATUSES,
        "message": message,
    }
    return templates.TemplateResponse(request, "report_detail.html", context, status_code=status_code)


@router.get("/reports/{report_id}", response_class=HTMLResponse)
async def report_detail(request: Request, report_id: uuid.UUID, session=Depends(get_session)):
    return await render_report_detail(request, session, report_id)
