from datetime import datetime

from pydantic import BaseModel


class AccountCoverage(BaseModel):
    earliest: datetime
    newest: datetime


class AccountImportResult(BaseModel):
    account_id: str
    added: int
    replaced: int
    skipped: int
    coverage: AccountCoverage
    message: str
    warnings: list[str]


class ImportResult(BaseModel):
    accounts: list[AccountImportResult]


class ResetResult(BaseModel):
    account_id: str
    deleted: int
