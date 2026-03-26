from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

RoleType = Literal["admin", "user"]

AssetStatusType = Literal[
    "사용중",
    "대기",
    "폐기필요",
    "폐기완료",
    "assigned",
    "available",
    "maintenance",
    "retired",
    "disposed",
    "active",
    "in_use",
    "standby",
    "disposal_required",
    "disposal_done",
]

UsageType = Literal[
    "주장비",
    "대여장비",
    "프로젝트장비",
    "보조장비",
    "기타장비",
    "서버장비",
    "네트워크장비",
    "primary",
    "loaner",
    "project",
    "auxiliary",
    "other",
    "server",
    "network",
]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    role: RoleType = "user"


class UserResponse(BaseModel):
    id: int
    username: str
    role: RoleType
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}



class UserAdminUpdate(BaseModel):
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class DirectoryUserResponse(BaseModel):
    id: int
    username: str
    display_name: str | None = None
    email: str | None = None
    department: str | None = None
    title: str | None = None
    is_active: bool
    source: str
    synced_at: datetime

    model_config = {"from_attributes": True}



class DirectoryUserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    display_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=120)


class DirectoryUserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None


class DirectoryUserImportItem(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    display_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=120)


class DirectoryUserBulkImportRequest(BaseModel):
    users: list[DirectoryUserImportItem] = Field(default_factory=list)


class DirectoryUserBulkImportResponse(BaseModel):
    ok: bool
    message: str
    result: dict[str, int]


class LdapSyncScheduleRequest(BaseModel):
    enabled: bool = False
    interval_minutes: int = Field(default=60, ge=5, le=1440)
    server_url: str = Field(min_length=1, max_length=255)
    use_ssl: bool = False
    port: int | None = Field(default=None, ge=1, le=65535)
    bind_dn: str = Field(min_length=1, max_length=255)
    base_dn: str = Field(min_length=1, max_length=255)
    user_id_attribute: str = Field(default="sAMAccountName", min_length=1, max_length=80)
    user_name_attribute: str = Field(default="displayName", min_length=1, max_length=80)
    user_email_attribute: str = Field(default="mail", min_length=1, max_length=80)
    size_limit: int = Field(default=1000, ge=50, le=5000)
    bind_password: str | None = Field(default=None, min_length=1, max_length=255)


class LdapSyncScheduleResponse(BaseModel):
    enabled: bool
    interval_minutes: int
    server_url: str
    use_ssl: bool
    port: int | None = None
    bind_dn: str
    base_dn: str
    user_id_attribute: str
    user_name_attribute: str
    user_email_attribute: str
    size_limit: int
    has_runtime_password: bool
    last_synced_at: datetime | None = None
    last_error: str | None = None
    last_result: dict[str, int] | None = None


class LdapSyncNowRequest(BaseModel):
    server_url: str = Field(min_length=1, max_length=255)
    use_ssl: bool = False
    port: int | None = Field(default=None, ge=1, le=65535)
    bind_dn: str = Field(min_length=1, max_length=255)
    bind_password: str = Field(min_length=1, max_length=255)
    base_dn: str = Field(min_length=1, max_length=255)
    user_id_attribute: str = Field(default="sAMAccountName", min_length=1, max_length=80)
    user_name_attribute: str = Field(default="displayName", min_length=1, max_length=80)
    user_email_attribute: str = Field(default="mail", min_length=1, max_length=80)
    size_limit: int = Field(default=1000, ge=50, le=5000)
    save_for_schedule: bool = False


class LdapSyncNowResponse(BaseModel):
    ok: bool
    message: str
    result: dict[str, int]

class AssetBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    usage_type: UsageType = "기타장비"
    manufacturer: str | None = Field(default=None, max_length=120)
    model_name: str | None = Field(default=None, max_length=120)
    owner: str = Field(default="미지정", min_length=1, max_length=120)
    manager: str = Field(default="미지정", min_length=1, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    location: str = Field(default="미지정", min_length=1, max_length=120)
    status: AssetStatusType = "대기"
    serial_number: str | None = Field(default=None, max_length=120)
    asset_code: str | None = Field(default=None, min_length=1, max_length=50)
    vendor: str | None = Field(default=None, max_length=120)
    purchase_date: date | None = None
    purchase_cost: float | None = Field(default=None, ge=0)
    warranty_expiry: date | None = None
    rental_start_date: date | None = None
    rental_end_date: date | None = None
    notes: str | None = None


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    usage_type: UsageType | None = None
    manufacturer: str | None = Field(default=None, max_length=120)
    model_name: str | None = Field(default=None, max_length=120)
    owner: str | None = Field(default=None, min_length=1, max_length=120)
    manager: str | None = Field(default=None, min_length=1, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    status: AssetStatusType | None = None
    serial_number: str | None = Field(default=None, max_length=120)
    asset_code: str | None = Field(default=None, min_length=1, max_length=50)
    vendor: str | None = Field(default=None, max_length=120)
    purchase_date: date | None = None
    purchase_cost: float | None = Field(default=None, ge=0)
    warranty_expiry: date | None = None
    rental_start_date: date | None = None
    rental_end_date: date | None = None
    notes: str | None = None


class AssetResponse(AssetBase):
    id: int
    created_at: datetime
    updated_at: datetime
    disposed_at: datetime | None = None

    model_config = {"from_attributes": True}


class AssetAssignRequest(BaseModel):
    assignee: str = Field(min_length=1, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    location: str | None = Field(default=None, max_length=120)
    memo: str | None = Field(default=None, max_length=500)


class AssetReturnRequest(BaseModel):
    location: str | None = Field(default=None, max_length=120)
    memo: str | None = Field(default=None, max_length=500)


class AssetStatusChangeRequest(BaseModel):
    memo: str | None = Field(default=None, max_length=500)


class SoftwareLicenseBase(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    vendor: str | None = Field(default=None, max_length=120)
    license_type: str = Field(default="구독", min_length=1, max_length=30)
    total_quantity: int = Field(default=1, ge=1, le=100000)
    assignees: list[str] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    drafter: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class SoftwareLicenseCreate(SoftwareLicenseBase):
    pass


class SoftwareLicenseUpdate(BaseModel):
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    vendor: str | None = Field(default=None, max_length=120)
    license_type: str | None = Field(default=None, min_length=1, max_length=30)
    total_quantity: int | None = Field(default=None, ge=1, le=100000)
    assignees: list[str] | None = None
    start_date: date | None = None
    end_date: date | None = None
    drafter: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class SoftwareLicenseResponse(SoftwareLicenseBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DashboardSummaryResponse(BaseModel):
    total_assets: int
    total_hardware: int
    total_software: int
    expiring_warranty_30d: int
    overdue_warranty: int
    rental_expiring_7d: int
    software_expiring_30d: int
    software_expired: int
    status_counts: dict[str, int]
    usage_type_counts: dict[str, int]
    category_counts: dict[str, int]


class LdapTestRequest(BaseModel):
    server_url: str = Field(min_length=1, max_length=255)
    use_ssl: bool = False
    port: int | None = Field(default=None, ge=1, le=65535)
    bind_dn: str = Field(min_length=1, max_length=255)
    bind_password: str = Field(min_length=1, max_length=255)


class LdapSearchRequest(LdapTestRequest):
    base_dn: str = Field(min_length=1, max_length=255)
    query: str = Field(default="", max_length=120)
    user_id_attribute: str = Field(default="sAMAccountName", min_length=1, max_length=80)
    user_name_attribute: str = Field(default="displayName", min_length=1, max_length=80)
    user_email_attribute: str = Field(default="mail", min_length=1, max_length=80)
    size_limit: int = Field(default=1000, ge=50, le=5000)


class LdapUserResponse(BaseModel):
    dn: str
    username: str
    display_name: str | None = None
    email: str | None = None
    department: str | None = None
    title: str | None = None


class LdapSearchResponse(BaseModel):
    total: int
    users: list[LdapUserResponse]

class AssetHistoryResponse(BaseModel):
    id: int
    asset_id: int
    action: str
    actor_user_id: int | None
    actor_username: str
    changed_fields: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}










