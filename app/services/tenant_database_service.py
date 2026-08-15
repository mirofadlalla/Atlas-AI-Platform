"""Tenant external database security boundary; never expose credentials to agents."""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from datetime import datetime

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.tenant_database import TenantDatabase

logger = logging.getLogger(__name__)


class TenantDatabaseError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class CredentialManager:
    def _fernet(self) -> Fernet:
        key = settings.credential_encryption_key
        if not key:
            raise TenantDatabaseError("CREDENTIAL_ENCRYPTION_NOT_CONFIGURED")
        try:
            return Fernet(key.encode())
        except ValueError as exc:
            raise TenantDatabaseError("CREDENTIAL_ENCRYPTION_KEY_INVALID") from exc

    def encrypt(self, value: str) -> str:
        return self._fernet().encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self._fernet().decrypt(value.encode()).decode()

    def rotate(self, value: str) -> str:
        return self.encrypt(self.decrypt(value))


class TenantDatabaseManager:
    _engines: dict[str, Engine] = {}
    _lock = threading.Lock()

    def _configuration(self, db: Session, tenant_id: str) -> TenantDatabase:
        config = (
            db.query(TenantDatabase)
            .filter_by(tenant_id=str(tenant_id), enabled=True)
            .one_or_none()
        )
        if not config:
            raise TenantDatabaseError("TENANT_DATABASE_NOT_CONFIGURED")
        return config

    def _url(self, config: TenantDatabase) -> URL:
        drivers = {"postgresql": "postgresql+psycopg2", "mysql": "mysql+pymysql"}
        driver = drivers.get(config.database_type)
        if not driver:
            raise TenantDatabaseError("DATABASE_TYPE_NOT_SUPPORTED")
        password = CredentialManager().decrypt(config.encrypted_password)
        return URL.create(
            driver,
            username=config.username,
            password=password,
            host=config.host,
            port=config.port,
            database=config.database_name,
        )

    def get_engine(self, db: Session, tenant_id: str) -> Engine:
        key = str(tenant_id)
        with self._lock:
            if key in self._engines:
                return self._engines[key]
            config = self._configuration(db, key)
            engine = create_engine(
                self._url(config),
                pool_size=settings.tenant_db_pool_size,
                max_overflow=settings.tenant_db_max_overflow,
                pool_pre_ping=True,
                connect_args={"connect_timeout": config.connection_timeout},
            )
            self._engines[key] = engine
            return engine

    @contextmanager
    def get_connection(self, db: Session, tenant_id: str):
        engine = self.get_engine(db, tenant_id)
        with engine.connect() as connection:
            yield connection

    def test_connection(self, db: Session, tenant_id: str) -> dict:
        with self.get_connection(db, tenant_id) as connection:
            connection.execute(text("SELECT 1"))
        config = self._configuration(db, tenant_id)
        config.last_tested_at = datetime.utcnow()
        db.commit()
        return {
            "status": "connected",
            "database_type": config.database_type,
            "database": config.database_name,
            "read_only": True,
        }

    def dispose(self, tenant_id: str) -> None:
        engine = self._engines.pop(str(tenant_id), None)
        if engine:
            engine.dispose()

    invalidate = dispose

    def schema(self, db: Session, tenant_id: str, refresh: bool = False) -> dict:
        config = self._configuration(db, tenant_id)
        if config.schema_metadata and not refresh:
            import json

            return json.loads(config.schema_metadata)
        with self.get_connection(db, tenant_id) as connection:
            inspector = inspect(connection)
            schema = config.default_schema or inspector.default_schema_name
            tables = {}
            relationships = []
            for table in inspector.get_table_names(schema=schema):
                foreign_keys = inspector.get_foreign_keys(table, schema=schema)
                tables[table] = {
                    "columns": [
                        {
                            "name": c["name"],
                            "type": str(c["type"]),
                            "nullable": c.get("nullable", True),
                        }
                        for c in inspector.get_columns(table, schema=schema)
                    ],
                    "primary_key": inspector.get_pk_constraint(
                        table, schema=schema
                    ).get("constrained_columns", []),
                    "foreign_keys": foreign_keys,
                    "indexes": inspector.get_indexes(table, schema=schema),
                }
                for foreign_key in foreign_keys:
                    relationships.append(
                        {
                            "from_table": table,
                            "from_columns": foreign_key.get("constrained_columns", []),
                            "to_schema": foreign_key.get("referred_schema") or schema,
                            "to_table": foreign_key.get("referred_table"),
                            "to_columns": foreign_key.get("referred_columns", []),
                            "name": foreign_key.get("name"),
                        }
                    )
        import json

        payload = {"schema": schema, "tables": tables, "relationships": relationships}
        config.schema_metadata, config.schema_updated_at = (
            json.dumps(payload),
            datetime.utcnow(),
        )
        db.commit()
        return payload


tenant_database_manager = TenantDatabaseManager()
