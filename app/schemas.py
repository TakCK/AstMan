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
    manager_dn: str | None = None
    user_dn: str | None = None
    object_guid: str | None = None
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
    manager_dn: str | None = Field(default=None, max_length=500)
    user_dn: str | None = Field(default=None, max_length=500)
    object_guid: str | None = Field(default=None, max_length=80)


class DirectoryUserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=120)
    manager_dn: str | None = Field(default=None, max_length=500)
    user_dn: str | None = Field(default=None, max_length=500)
    object_guid: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None


class DirectoryUserImportItem(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    display_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=120)
    manager_dn: str | None = Field(default=None, max_length=500)
    user_dn: str | None = Field(default=None, max_length=500)
    object_guid: str | None = Field(default=None, max_length=80)


class DirectoryUserBulkImportRequest(BaseModel):
    users: list[DirectoryUserImportItem] = Field(default_factory=list)


class DirectoryUserBulkImportResponse(BaseModel):
    ok: bool
    message: str
    result: dict[str, int]


class DirectoryUserAssignedAsset(BaseModel):
    id: int
    asset_code: str | None = None
    name: str
    category: str
    status: str


class DirectoryUserAssignedLicense(BaseModel):
    license_id: int
    license_name: str
    assignment_count: int = 1


class DirectoryUserDeactivationPreviewResponse(BaseModel):
    directory_user_id: int
    username: str
    display_name: str | None = None
    is_active: bool
    assigned_asset_count: int
    assigned_license_count: int
    assigned_assets: list[DirectoryUserAssignedAsset] = Field(default_factory=list)
    assigned_licenses: list[DirectoryUserAssignedLicense] = Field(default_factory=list)


class DirectoryUserDeactivateRequest(BaseModel):
    release_assets: bool = False
    asset_ids: list[int] = Field(default_factory=list)


class DirectoryUserDeactivateResponse(BaseModel):
    ok: bool
    message: str
    released_asset_count: int
    remaining_asset_count: int
    assigned_license_count: int
    user: DirectoryUserResponse

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
    user_department_attribute: str = Field(default="department", min_length=1, max_length=80)
    user_title_attribute: str = Field(default="title", min_length=1, max_length=80)
    manager_dn_attribute: str = Field(default="manager", min_length=1, max_length=80)
    user_dn_attribute: str = Field(default="distinguishedName", min_length=1, max_length=80)
    user_guid_attribute: str = Field(default="objectGUID", min_length=1, max_length=80)
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
    user_department_attribute: str
    user_title_attribute: str
    manager_dn_attribute: str
    user_dn_attribute: str
    user_guid_attribute: str
    size_limit: int
    has_runtime_password: bool
    has_stored_password: bool
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
    user_department_attribute: str = Field(default="department", min_length=1, max_length=80)
    user_title_attribute: str = Field(default="title", min_length=1, max_length=80)
    manager_dn_attribute: str = Field(default="manager", min_length=1, max_length=80)
    user_dn_attribute: str = Field(default="distinguishedName", min_length=1, max_length=80)
    user_guid_attribute: str = Field(default="objectGUID", min_length=1, max_length=80)
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


class SoftwareLicenseAssigneeDetail(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    start_date: date | None = None
    end_date: date | None = None
    purchase_model: str | None = Field(default=None, min_length=1, max_length=30)


class SoftwareLicenseBase(BaseModel):
    product_name: str = Field(min_length=1, max_length=200)
    vendor: str | None = Field(default=None, max_length=120)
    license_category: str = Field(default="기타", min_length=1, max_length=40)
    license_scope: str = Field(default="일반", min_length=1, max_length=20)
    subscription_type: str = Field(default="연 구독", min_length=1, max_length=30)
    total_quantity: int = Field(default=1, ge=1, le=100000)
    allow_multiple_assignments: bool = False
    assignees: list[str] | None = Field(default_factory=list)
    assignee_details: list[SoftwareLicenseAssigneeDetail] | None = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    purchase_cost: float | None = Field(default=None, ge=0)
    purchase_currency: str = Field(default="원", min_length=1, max_length=10)
    drafter: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class SoftwareLicenseCreate(SoftwareLicenseBase):
    pass


class SoftwareLicenseUpdate(BaseModel):
    product_name: str | None = Field(default=None, min_length=1, max_length=200)
    vendor: str | None = Field(default=None, max_length=120)
    license_category: str | None = Field(default=None, min_length=1, max_length=40)
    license_scope: str | None = Field(default=None, min_length=1, max_length=20)
    subscription_type: str | None = Field(default=None, min_length=1, max_length=30)
    total_quantity: int | None = Field(default=None, ge=1, le=100000)
    allow_multiple_assignments: bool | None = None
    assignees: list[str] | None = None
    assignee_details: list[SoftwareLicenseAssigneeDetail] | None = None
    start_date: date | None = None
    end_date: date | None = None
    purchase_cost: float | None = Field(default=None, ge=0)
    purchase_currency: str | None = Field(default=None, min_length=1, max_length=10)
    drafter: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class SoftwareLicenseResponse(SoftwareLicenseBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SoftwareLicenseKeyUpdate(BaseModel):
    license_key: str | None = Field(default=None, max_length=4000)


class SoftwareLicenseKeyResponse(BaseModel):
    license_id: int
    license_key: str = ""
    has_license_key: bool = False



class CsvImportRowError(BaseModel):
    row: int
    kind: str | None = None
    message: str


class CsvHwSwImportResponse(BaseModel):
    ok: bool = True
    total_rows: int
    processed_rows: int
    created_hardware: int
    created_software: int
    failed_rows: int
    errors: list[CsvImportRowError] = Field(default_factory=list)
class DashboardHardwareHistoryPoint(BaseModel):
    key: str
    label: str
    period_cost: float
    cumulative_cost: float


class DashboardSoftwareProjectionPoint(BaseModel):
    key: str
    label: str
    actual_cost: float
    expected_cost: float
    total_cost: float
    is_forecast: bool


class DashboardSoftwareProjectionByScope(BaseModel):
    all: list[DashboardSoftwareProjectionPoint]
    required: list[DashboardSoftwareProjectionPoint]
    general: list[DashboardSoftwareProjectionPoint]


class DashboardCostTrendPeriod(BaseModel):
    hardware_history: list[DashboardHardwareHistoryPoint]
    software_projection: list[DashboardSoftwareProjectionPoint]
    software_projection_by_scope: DashboardSoftwareProjectionByScope


class DashboardCostTrendSet(BaseModel):
    month: DashboardCostTrendPeriod
    quarter: DashboardCostTrendPeriod
    year: DashboardCostTrendPeriod


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
    cost_trends: DashboardCostTrendSet


class DashboardSoftwareCostOverallSummary(BaseModel):
    team_count: int = 0
    user_count: int = 0
    assigned_license_count: int = 0
    monthly_cost: float = 0
    yearly_cost: float = 0
    license_type_count: int = 0


class DashboardSoftwareCostTeamSummaryItem(BaseModel):
    team_name: str
    user_count: int = 0
    assigned_license_count: int = 0
    monthly_cost: float = 0
    yearly_cost: float = 0
    license_type_count: int = 0


class DashboardSoftwareCostSummaryResponse(BaseModel):
    scope_filter: Literal["all", "general", "required"] = "all"
    overall_summary: DashboardSoftwareCostOverallSummary
    team_summary: list[DashboardSoftwareCostTeamSummaryItem] = Field(default_factory=list)


class SoftwareCostSnapshotCreateRequest(BaseModel):
    snapshot_month: date | None = None
    scope_filter: Literal["all", "general", "required"] = "all"
    overwrite: bool = False


class SoftwareCostSnapshotItem(BaseModel):
    id: int
    snapshot_month: date
    team_name: str
    scope: Literal["all", "general", "required"]
    user_count: int
    license_count: int
    monthly_cost: float
    annual_cost: float
    created_at: datetime

    model_config = {"from_attributes": True}


class SoftwareCostSnapshotCreateResponse(BaseModel):
    snapshot_month: date
    scope_filter: Literal["all", "general", "required"]
    overwritten: bool = False
    created_count: int = 0
    rows: list[SoftwareCostSnapshotItem] = Field(default_factory=list)


class SoftwareCostSnapshotListResponse(BaseModel):
    scope_filter: Literal["all", "general", "required"]
    snapshot_month_from: date | None = None
    snapshot_month_to: date | None = None
    total: int
    rows: list[SoftwareCostSnapshotItem] = Field(default_factory=list)


class ExchangeRateSettingResponse(BaseModel):
    usd_krw: float = Field(ge=0.0001)
    effective_date: date


class ExchangeRateSettingUpdate(BaseModel):
    usd_krw: float = Field(ge=0.0001)
    effective_date: date | None = None


class BrandingSettingsUpdate(BaseModel):
    service_title: str = Field(default="", max_length=200)
    service_subtitle: str = Field(default="", max_length=500)
    company_logo_path: str = Field(default="", max_length=500)
    footer_text: str = Field(default="", max_length=1000)


class BrandingSettingsResponse(BaseModel):
    service_title: str
    service_subtitle: str
    company_logo_path: str
    footer_text: str


class SystemInfoSslInfo(BaseModel):
    # Reserved for future SSL expiry integration.
    certificate_expires_at: datetime | None = None
    days_until_expiry: int | None = None


class SystemInfoResponse(BaseModel):
    service_name: str
    version: str
    external_access_url: str
    deployment_environment: str
    logo_configured: bool
    smtp_configured: bool
    ldap_configured: bool
    ssl_info: SystemInfoSslInfo = Field(default_factory=SystemInfoSslInfo)


class MailSmtpConfigUpdate(BaseModel):
    smtp_host: str = Field(default="", max_length=255)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    use_tls: bool = True
    use_ssl: bool = False
    smtp_username: str | None = Field(default=None, max_length=255)
    smtp_password: str | None = Field(default=None, min_length=1, max_length=255)
    from_email: str | None = Field(default=None, max_length=255)


class MailSmtpConfigResponse(BaseModel):
    smtp_host: str
    smtp_port: int
    use_tls: bool
    use_ssl: bool
    smtp_username: str
    from_email: str
    has_runtime_password: bool
    has_stored_password: bool


class MailAdminConfigUpdate(BaseModel):
    enabled: bool = False
    to_emails: list[str] = Field(default_factory=list)
    notify_days: int = Field(default=30, ge=1, le=365)
    schedule_hour: int = Field(default=9, ge=0, le=23)
    schedule_minute: int = Field(default=0, ge=0, le=59)
    include_expired: bool = True
    subject_template: str | None = Field(default=None, max_length=300)
    body_template: str | None = Field(default=None, max_length=20000)


class MailAdminConfigResponse(BaseModel):
    enabled: bool
    to_emails: list[str]
    notify_days: int
    schedule_hour: int
    schedule_minute: int
    include_expired: bool
    subject_template: str
    body_template: str
    last_sent_at: datetime | None = None
    last_error: str | None = None
    last_result: dict[str, int] | None = None


class MailUserConfigUpdate(BaseModel):
    enabled: bool = False
    notify_days: int = Field(default=30, ge=1, le=365)
    schedule_hour: int = Field(default=9, ge=0, le=23)
    schedule_minute: int = Field(default=0, ge=0, le=59)
    include_expired: bool = True
    only_active_users: bool = True
    subject_template: str | None = Field(default=None, max_length=300)
    body_template: str | None = Field(default=None, max_length=20000)


class MailUserConfigResponse(BaseModel):
    enabled: bool
    notify_days: int
    schedule_hour: int
    schedule_minute: int
    include_expired: bool
    only_active_users: bool
    subject_template: str
    body_template: str
    last_sent_at: datetime | None = None
    last_error: str | None = None
    last_result: dict[str, int] | None = None


class MailSendNowRequest(BaseModel):
    smtp_password: str | None = Field(default=None, min_length=1, max_length=255)


class MailSendNowResponse(BaseModel):
    ok: bool
    message: str
    result: dict[str, int]



class MailUserPreviewItem(BaseModel):
    username: str
    display_name: str
    email: str | None = None
    is_active: bool
    expiring_count: int
    expired_count: int
    expiring_license_names: list[str] = Field(default_factory=list)
    expired_license_names: list[str] = Field(default_factory=list)
    status: str
    sendable: bool


class MailUserPreviewResponse(BaseModel):
    checked_licenses: int
    target_users: int
    sendable_users: int
    skipped_no_email: int
    skipped_inactive: int
    expiring_count: int
    expired_count: int
    rows: list[MailUserPreviewItem] = Field(default_factory=list)

class SoftwareExpiryMailConfigUpdate(BaseModel):
    enabled: bool = False
    smtp_host: str = Field(default="", max_length=255)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    use_tls: bool = True
    use_ssl: bool = False
    smtp_username: str | None = Field(default=None, max_length=255)
    smtp_password: str | None = Field(default=None, min_length=1, max_length=255)
    from_email: str | None = Field(default=None, max_length=255)
    to_emails: list[str] = Field(default_factory=list)
    notify_days: int = Field(default=30, ge=1, le=365)
    schedule_hour: int = Field(default=9, ge=0, le=23)
    schedule_minute: int = Field(default=0, ge=0, le=59)
    include_expired: bool = True
    subject_template: str | None = Field(default=None, max_length=300)
    body_template: str | None = Field(default=None, max_length=20000)


class SoftwareExpiryMailConfigResponse(BaseModel):
    enabled: bool
    smtp_host: str
    smtp_port: int
    use_tls: bool
    use_ssl: bool
    smtp_username: str
    from_email: str
    to_emails: list[str]
    notify_days: int
    schedule_hour: int
    schedule_minute: int
    include_expired: bool
    subject_template: str
    body_template: str
    has_runtime_password: bool
    has_stored_password: bool
    last_sent_at: datetime | None = None
    last_error: str | None = None
    last_result: dict[str, int] | None = None


class SoftwareExpiryMailSendNowRequest(BaseModel):
    smtp_password: str | None = Field(default=None, min_length=1, max_length=255)


class SoftwareExpiryMailSendNowResponse(BaseModel):
    ok: bool
    message: str
    result: dict[str, int]


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
    user_department_attribute: str = Field(default="department", min_length=1, max_length=80)
    user_title_attribute: str = Field(default="title", min_length=1, max_length=80)
    manager_dn_attribute: str = Field(default="manager", min_length=1, max_length=80)
    user_dn_attribute: str = Field(default="distinguishedName", min_length=1, max_length=80)
    user_guid_attribute: str = Field(default="objectGUID", min_length=1, max_length=80)
    size_limit: int = Field(default=1000, ge=50, le=5000)


class LdapUserResponse(BaseModel):
    dn: str
    username: str
    display_name: str | None = None
    email: str | None = None
    department: str | None = None
    title: str | None = None
    manager_dn: str | None = None
    user_dn: str | None = None
    object_guid: str | None = None


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


class AssetLabelPreviewRequest(BaseModel):
    asset_ids: list[int] = Field(default_factory=list)


class AssetLabelExcludedItem(BaseModel):
    asset_id: int
    asset_name: str
    reason: str


class AssetLabelItem(BaseModel):
    asset_id: int
    asset_name: str
    asset_code: str
    owner: str = "미지정"
    purchase_date: date | None = None
    rental_start_date: date | None = None
    rental_end_date: date | None = None
    qr_code_data_url: str


class AssetLabelPreviewResponse(BaseModel):
    branding_logo_path: str = ""
    labels: list[AssetLabelItem] = Field(default_factory=list)
    excluded: list[AssetLabelExcludedItem] = Field(default_factory=list)































