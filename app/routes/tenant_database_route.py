from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from uuid import uuid4

from app.core.db import get_db
from app.models.tenant_database import TenantDatabase
from app.services.auth_services.auth_service import require_admin
from app.services.tenant_database_service import CredentialManager, TenantDatabaseError, tenant_database_manager

router = APIRouter(prefix="/tenant/database", tags=["tenant-database"])


class DatabaseConnectRequest(BaseModel):
    database_type: str = Field(pattern="^(postgresql|mysql)$")
    host: str
    port: int = Field(gt=0, le=65535)
    database_name: str
    username: str
    password: str = Field(repr=False)
    default_schema: str | None = None
    ssl_enabled: bool = True
    ssl_mode: str = "require"
    connection_timeout: int = Field(default=10, ge=1, le=60)


def _error(exc: TenantDatabaseError):
    raise HTTPException(status_code=400, detail={"code": exc.code})


@router.post("/connect")
def connect(payload: DatabaseConnectRequest, admin=Depends(require_admin), db: Session = Depends(get_db)):
    existing = db.query(TenantDatabase).filter_by(tenant_id=str(admin.tenant_id)).one_or_none()
    config = existing or TenantDatabase(id=str(uuid4()), tenant_id=str(admin.tenant_id))
    for field in ("database_type", "host", "port", "database_name", "username", "default_schema", "ssl_enabled", "ssl_mode", "connection_timeout"):
        setattr(config, field, getattr(payload, field))
    try:
        config.encrypted_password = CredentialManager().encrypt(payload.password)
        config.enabled = True
        if not existing:
            db.add(config)
        # The Atlas session intentionally has autoflush disabled.  Persist the
        # new configuration before TenantDatabaseManager resolves it to test
        # the external connection in this same request.
        db.flush()
        tenant_database_manager.invalidate(str(admin.tenant_id))
        tenant_database_manager.test_connection(db, str(admin.tenant_id))
    except TenantDatabaseError as exc:
        db.rollback()
        _error(exc)
    except Exception:
        db.rollback(); raise HTTPException(status_code=400, detail={"code": "DATABASE_CONNECTION_FAILED"})
    return {"status": "connected", "database_type": config.database_type, "host_masked": "***", "database_name": config.database_name, "schema": config.default_schema}


@router.post("/test")
def test(admin=Depends(require_admin), db: Session = Depends(get_db)):
    try: return tenant_database_manager.test_connection(db, str(admin.tenant_id))
    except TenantDatabaseError as exc: _error(exc)
    except Exception: raise HTTPException(status_code=400, detail={"code": "DATABASE_CONNECTION_FAILED"})


@router.get("/status")
def status(admin=Depends(require_admin), db: Session = Depends(get_db)):
    config = db.query(TenantDatabase).filter_by(tenant_id=str(admin.tenant_id)).one_or_none()
    return {"connected": bool(config and config.enabled), "database_type": config.database_type if config else None, "host_masked": "***" if config else None, "database_name": config.database_name if config else None, "schema": config.default_schema if config else None, "last_tested_at": config.last_tested_at if config else None}


@router.post("/schema/refresh")
def refresh_schema(admin=Depends(require_admin), db: Session = Depends(get_db)):
    try: return tenant_database_manager.schema(db, str(admin.tenant_id), refresh=True)
    except TenantDatabaseError as exc: _error(exc)
    except Exception: raise HTTPException(status_code=400, detail={"code": "SCHEMA_INTROSPECTION_FAILED"})


@router.get("/schema")
def get_schema(admin=Depends(require_admin), db: Session = Depends(get_db)):
    try: return tenant_database_manager.schema(db, str(admin.tenant_id))
    except TenantDatabaseError as exc: _error(exc)
    except Exception: raise HTTPException(status_code=400, detail={"code": "SCHEMA_INTROSPECTION_FAILED"})


@router.delete("")
def disconnect(admin=Depends(require_admin), db: Session = Depends(get_db)):
    config = db.query(TenantDatabase).filter_by(tenant_id=str(admin.tenant_id)).one_or_none()
    if config: config.enabled = False; db.commit()
    tenant_database_manager.dispose(str(admin.tenant_id))
    return {"status": "disconnected"}
