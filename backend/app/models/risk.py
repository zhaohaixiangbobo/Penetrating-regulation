"""风险模块独立数据表：不可变版本、运行快照、预警及追加核查日志。"""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db.sqlite import Base
from app.models.clue import beijing_now


class RiskModel(Base):
    __tablename__ = 'risk_models'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)


class RiskVersion(Base):
    __tablename__ = 'risk_versions'
    __table_args__ = (UniqueConstraint('model_id', 'number'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(Integer, index=True)
    number: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict] = mapped_column(JSON)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)


class RiskRun(Base):
    __tablename__ = 'risk_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    model_id: Mapped[int] = mapped_column(Integer, index=True)
    version_id: Mapped[int] = mapped_column(Integer)
    model_name: Mapped[str] = mapped_column(String(100))
    version_number: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16))
    snapshot: Mapped[dict] = mapped_column(JSON)
    scope: Mapped[dict] = mapped_column(JSON)
    baseline: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default='queued', index=True)
    stage: Mapped[str] = mapped_column(String(100), default='等待执行')
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)


class RiskItem(Base):
    __tablename__ = 'risk_run_items'
    __table_args__ = (UniqueConstraint('run_id', 'event_key'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, index=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    event_key: Mapped[str] = mapped_column(String(300))
    outcome: Mapped[str] = mapped_column(String(16), index=True)
    baseline_outcome: Mapped[str | None] = mapped_column(String(16))
    evidence: Mapped[dict] = mapped_column(JSON)
    reasons: Mapped[list] = mapped_column(JSON)


class RiskAlert(Base):
    __tablename__ = 'risk_alerts'
    __table_args__ = (UniqueConstraint('model_version_id', 'event_key'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_id: Mapped[int] = mapped_column(Integer, index=True)
    model_version_id: Mapped[int] = mapped_column(Integer, index=True)
    model_name: Mapped[str] = mapped_column(String(100))
    event_key: Mapped[str] = mapped_column(String(300))
    first_item_id: Mapped[int] = mapped_column(Integer)
    latest_item_id: Mapped[int] = mapped_column(Integer)
    cust_code: Mapped[str | None] = mapped_column(String(40), index=True)
    cust_name: Mapped[str | None] = mapped_column(String(250))
    person_id: Mapped[str | None] = mapped_column(String(100))
    person_name: Mapped[str | None] = mapped_column(String(100))
    com_id: Mapped[str | None] = mapped_column(String(40), index=True)
    short_name: Mapped[str | None] = mapped_column(String(80))
    event_time: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(24), default='pending', index=True)
    conclusion: Mapped[str | None] = mapped_column(String(32))
    assigned_to: Mapped[str | None] = mapped_column(String(64))
    reviewed_by: Mapped[str | None] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    prior_alert_id: Mapped[int | None] = mapped_column(Integer)
    recurrence: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)


class RiskOccurrence(Base):
    __tablename__ = 'risk_occurrences'
    __table_args__ = (UniqueConstraint('alert_id', 'item_id'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(Integer, index=True)
    item_id: Mapped[int] = mapped_column(Integer)


class RiskAction(Base):
    __tablename__ = 'risk_actions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(30))
    from_status: Mapped[str] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24))
    conclusion: Mapped[str | None] = mapped_column(String(32))
    note: Mapped[str] = mapped_column(Text)
    measures: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)


class RiskClueLink(Base):
    __tablename__ = 'risk_clue_links'
    __table_args__ = (UniqueConstraint('alert_id', 'clue_id'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(Integer, index=True)
    clue_id: Mapped[int] = mapped_column(Integer, index=True)


class RiskAttachment(Base):
    __tablename__ = 'risk_attachments'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(Integer, index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(100), unique=True)
    size: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(64))


class RiskLease(Base):
    __tablename__ = 'risk_worker_lease'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner: Mapped[str] = mapped_column(String(36), default='')
    expires: Mapped[float] = mapped_column(Float, default=0)


class RiskSchedule(Base):
    """当前计划指向不可变修订；触发时间采用北京时间。"""
    __tablename__ = 'risk_schedules'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[dict] = mapped_column(JSON)
    next_fire: Mapped[datetime] = mapped_column(DateTime, index=True)
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)
    note: Mapped[str | None] = mapped_column(Text)


class RiskScheduleRevision(Base):
    __tablename__ = 'risk_schedule_revisions'
    __table_args__ = (UniqueConstraint('schedule_id', 'revision'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[int] = mapped_column(Integer, index=True)
    revision: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    actor: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)


class RiskTrigger(Base):
    __tablename__ = 'risk_triggers'
    __table_args__ = (UniqueConstraint('schedule_id', 'fire_at'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    schedule_id: Mapped[int] = mapped_column(Integer, index=True)
    revision: Mapped[int] = mapped_column(Integer)
    fire_at: Mapped[datetime] = mapped_column(DateTime)
    run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(24))
    note: Mapped[str | None] = mapped_column(Text)


class RiskBatch(Base):
    __tablename__ = 'risk_batches'
    __table_args__ = (UniqueConstraint('run_id', 'company', 'day', 'page'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    company: Mapped[str] = mapped_column(String(40))
    day: Mapped[str] = mapped_column(String(10))
    page: Mapped[int] = mapped_column(Integer, default=1)
    cursor: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default='queued', index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    token: Mapped[str | None] = mapped_column(String(36))
    retry_at: Mapped[float] = mapped_column(Float, default=0)
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)


class RiskBatchAttempt(Base):
    __tablename__ = 'risk_batch_attempts'
    __table_args__ = (UniqueConstraint('batch_id', 'number'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(Integer, index=True)
    number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default='running')
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=beijing_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
