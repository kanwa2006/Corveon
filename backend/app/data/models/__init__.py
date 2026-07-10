"""ORM models. Import every model module here so Alembic's autogenerate (and
the CI models↔migrations sync check, ADR-0002) sees the full metadata."""

from app.data.models.audit_log import AuditLog
from app.data.models.chat import Chat
from app.data.models.chunk import ChunkEmbedding, DocumentChunk
from app.data.models.document import Document, DocumentStatus
from app.data.models.evidence import (
    EvidenceCitation,
    EvidenceClaim,
    EvidenceSourceName,
    EvidenceVerification,
    SourceClass,
    VerificationStatus,
)
from app.data.models.job import Job, JobStatus, JobType
from app.data.models.medication import (
    DrugDataSnapshot,
    DrugInteraction,
    FindingSeverity,
    FindingType,
    InteractionSource,
    Medication,
    MedicationFinding,
)
from app.data.models.message import Message, MessageRole
from app.data.models.organization import Organization
from app.data.models.user import User, UserRole

__all__ = [
    "AuditLog",
    "Chat",
    "ChunkEmbedding",
    "Document",
    "DocumentChunk",
    "DocumentStatus",
    "DrugDataSnapshot",
    "DrugInteraction",
    "EvidenceCitation",
    "EvidenceClaim",
    "EvidenceSourceName",
    "EvidenceVerification",
    "FindingSeverity",
    "FindingType",
    "InteractionSource",
    "Job",
    "JobStatus",
    "JobType",
    "Medication",
    "MedicationFinding",
    "Message",
    "MessageRole",
    "Organization",
    "SourceClass",
    "User",
    "UserRole",
    "VerificationStatus",
]
