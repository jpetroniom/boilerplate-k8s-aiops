import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from my_agent_app.database import Base


class ReportStatus(str, enum.Enum):
    EM_ANALISE = "EM_ANALISE"
    COMPLETO = "COMPLETO"
    INCOMPLETO = "INCOMPLETO"
    CORRIGINDO = "CORRIGINDO"
    CORRIGIDO = "CORRIGIDO"
    FALHA_CORRECAO = "FALHA_CORRECAO"


# Status que indicam evento em tratamento (nao reanalisar).
ACTIVE_STATUSES = (
    ReportStatus.EM_ANALISE,
    ReportStatus.COMPLETO,
    ReportStatus.CORRIGINDO,
    ReportStatus.FALHA_CORRECAO,
)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (Index("ix_reports_event_uids", "event_uids", postgresql_using="gin"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    markdown: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), index=True)
    event_uids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
