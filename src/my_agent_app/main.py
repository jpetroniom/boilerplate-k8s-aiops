import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from my_agent_app.api.router import router as api_router
from my_agent_app.collector.handler import EventHandler
from my_agent_app.collector.loop import EventCollector
from my_agent_app.database import get_database_url
from my_agent_app.models import queries
from my_agent_app.web.router import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(get_database_url())
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    app.state.sessionmaker = sessionmaker

    try:
        async with sessionmaker() as session:
            recovered = await queries.recover_orphans(session)
        if recovered:
            logger.warning("%d relatorio(s) EM_ANALISE orfao(s) marcado(s) como INCOMPLETO", recovered)
    except Exception:
        logger.exception("Nao foi possivel recuperar relatorios EM_ANALISE orfaos no startup")

    collector_task = asyncio.create_task(EventCollector(handler=EventHandler(sessionmaker)).run())

    yield

    collector_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await collector_task
    await engine.dispose()


app = FastAPI(title="My Agent App", lifespan=lifespan)
app.include_router(api_router)
app.include_router(web_router)
