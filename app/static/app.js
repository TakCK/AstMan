const STORAGE_KEYS = {
  token: "token",
  codeTemplate: "setting.asset_code_template",
  defaultOwner: "setting.default_owner",
  defaultManager: "setting.default_manager",
  categories: "setting.asset_categories",
  seq: "asset_code_seq",
  ldapConfig: "setting.ldap_config",
  softwareLicenseCategories: "setting.software_license_categories",
};

const TODAY_ISO = new Date().toISOString().slice(0, 10);

const DEFAULTS = {
  codeTemplate: "{CAT}-{YYYY}-{SEQ4}",
  defaultOwner: "미지정",
  defaultManager: "미지정",
  categories: [
    { name: "노트북", token: "NB" },
    { name: "데스크탑", token: "DT" },
    { name: "모니터", token: "MON" },
    { name: "서버", token: "SRV" },
    { name: "네트워크", token: "NET" },
  ],
  ldapConfig: {
    server_url: "",
    use_ssl: false,
    port: "",
    bind_dn: "",
    base_dn: "",
    user_id_attribute: "sAMAccountName",
    user_name_attribute: "displayName",
    user_email_attribute: "mail",
    user_department_attribute: "department",
    user_title_attribute: "title",
    manager_dn_attribute: "manager",
    user_dn_attribute: "distinguishedName",
    user_guid_attribute: "objectGUID",
    size_limit: 1000,
  },
  softwareLicenseCategories: ["생산성&협업", "개발", "디자인", "API", "클라우드&인프라", "생성형AI", "기타"],
  exchangeRate: {
    usd_krw: 1350,
    effective_date: TODAY_ISO,
  },
  mailSmtp: {
    smtp_host: "",
    smtp_port: 587,
    use_tls: true,
    use_ssl: false,
    smtp_username: "",
    from_email: "",
    has_runtime_password: false,
    has_stored_password: false,
  },
  mailAdmin: {
    enabled: false,
    to_emails: [],
    notify_days: 30,
    schedule_hour: 9,
    schedule_minute: 0,
    include_expired: true,
    subject_template: "[ITAM] 소프트웨어 만료 알림 ({DATE})",
    body_template: "소프트웨어 만료 알림 ({DATE})\n\n- 조회 라이선스: {CHECKED_LICENSES}건\n- 만료 예정({NOTIFY_DAYS}일 이내): {EXPIRING_COUNT}건\n- 이미 만료: {EXPIRED_COUNT}건\n\n[만료 예정 목록]\n{EXPIRING_ITEMS}\n\n[만료 목록]\n{EXPIRED_ITEMS}",
    last_sent_at: null,
    last_error: null,
    last_result: null,
  },
  mailUser: {
    enabled: false,
    notify_days: 30,
    schedule_hour: 9,
    schedule_minute: 0,
    include_expired: true,
    only_active_users: true,
    subject_template: "[ITAM] {USER_NAME}님 소프트웨어 만료 알림 ({DATE})",
    body_template: "안녕하세요 {USER_NAME}님,\n\n소프트웨어 라이선스 만료 안내입니다. ({DATE})\n\n- 만료 예정({NOTIFY_DAYS}일 이내): {USER_EXPIRING_COUNT}건\n- 이미 만료: {USER_EXPIRED_COUNT}건\n\n[내 만료 예정 목록]\n{EXPIRING_ITEMS}\n\n[내 만료 목록]\n{EXPIRED_ITEMS}",
    last_sent_at: null,
    last_error: null,
    last_result: null,
  },
};

function cloneDefaultCategories() {
  return DEFAULTS.categories.map((item) => ({ ...item }));
}

function sanitizeCategorySetting(item) {
  const name = String(item?.name || "").trim();
  if (!name) return null;

  const rawToken = String(item?.token || "").trim();
  return {
    name,
    token: sanitizeTokenValue(rawToken || name, "CAT"),
  };
}

function normalizeCategorySettings(source) {
  const rows = Array.isArray(source) ? source : [];
  const seen = new Set();
  const normalized = [];

  rows.forEach((row) => {
    const item = sanitizeCategorySetting(row);
    if (!item) return;

    const key = item.name.toLocaleLowerCase();
    if (seen.has(key)) return;

    seen.add(key);
    normalized.push(item);
  });

  return normalized.length ? normalized : cloneDefaultCategories();
}

function loadCategorySettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.categories);
    if (!raw) return cloneDefaultCategories();
    return normalizeCategorySettings(JSON.parse(raw));
  } catch {
    return cloneDefaultCategories();
  }
}

function normalizeSoftwareMetaList(source, fallback = []) {
  const rows = Array.isArray(source) ? source : [];
  const normalized = [];
  const seen = new Set();

  rows.forEach((value) => {
    const text = String(value || "").trim();
    if (!text) return;
    const key = text.toLocaleLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    normalized.push(text);
  });

  if (normalized.length) return normalized;
  return Array.isArray(fallback) ? fallback.map((value) => String(value || "").trim()).filter(Boolean) : [];
}

function loadSoftwareMetaList(key, fallback = []) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return normalizeSoftwareMetaList(fallback, fallback);
    return normalizeSoftwareMetaList(JSON.parse(raw), fallback);
  } catch {
    return normalizeSoftwareMetaList(fallback, fallback);
  }
}
function loadLdapConfig() {
  try {
    const raw = localStorage.getItem(STORAGE_KEYS.ldapConfig);
    if (!raw) return { ...DEFAULTS.ldapConfig };
    const parsed = JSON.parse(raw);
    return {
      ...DEFAULTS.ldapConfig,
      ...(parsed || {}),
    };
  } catch {
    return { ...DEFAULTS.ldapConfig };
  }
}
function normalizeExchangeRateSetting(source) {
  const rawRate = Number(source?.usd_krw);
  const usdKrw = Number.isFinite(rawRate) && rawRate > 0 ? rawRate : Number(DEFAULTS.exchangeRate.usd_krw);

  const rawDate = String(source?.effective_date || "").trim();
  const effectiveDate = /^\d{4}-\d{2}-\d{2}$/.test(rawDate) ? rawDate : TODAY_ISO;

  return {
    usd_krw: usdKrw,
    effective_date: effectiveDate,
  };
}

function getUsdKrwRate() {
  return Number(normalizeExchangeRateSetting(state.settings.exchangeRate).usd_krw || DEFAULTS.exchangeRate.usd_krw);
}

function isUsdCurrency(currency) {
  const key = String(currency || "").trim().toLowerCase();
  return ["usd", "달러", "$", "us$", "dollar", "미국달러"].includes(key);
}

function toKrwByCurrency(amount, currency) {
  const base = Number(amount);
  if (!Number.isFinite(base) || base < 0) return NaN;
  if (!isUsdCurrency(currency)) return base;
  return base * getUsdKrwRate();
}

function formatWon(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "-";
  return `${Math.round(num).toLocaleString("ko-KR")}원`;
}

function applyExchangeRateInputs() {
  const rateInput = document.getElementById("settingUsdKrwRate");
  const dateInput = document.getElementById("settingExchangeRateDate");
  if (!rateInput || !dateInput) return;

  const normalized = normalizeExchangeRateSetting(state.settings.exchangeRate);
  state.settings.exchangeRate = normalized;
  rateInput.value = String(normalized.usd_krw);
  dateInput.value = normalized.effective_date;
}

async function loadExchangeRateSetting() {
  if (!state.token) return;
  const setting = await api("/settings/exchange-rate");
  state.settings.exchangeRate = normalizeExchangeRateSetting(setting);
  applyExchangeRateInputs();
}

function parseMailEmailList(raw) {
  const text = String(raw || "").replaceAll(";", ",").replaceAll("\n", ",");
  return [...new Set(text.split(",").map((v) => v.trim()).filter(Boolean))];
}

function normalizeMailSmtpSetting(source) {
  const base = source || {};
  const smtpPort = Number(base.smtp_port);

  return {
    smtp_host: String(base.smtp_host || "").trim(),
    smtp_port: Number.isFinite(smtpPort) ? Math.min(65535, Math.max(1, smtpPort)) : 587,
    use_tls: Boolean(base.use_tls),
    use_ssl: Boolean(base.use_ssl),
    smtp_username: String(base.smtp_username || "").trim(),
    from_email: String(base.from_email || "").trim(),
    has_runtime_password: Boolean(base.has_runtime_password),
    has_stored_password: Boolean(base.has_stored_password),
  };
}

function normalizeMailAdminSetting(source) {
  const base = source || {};
  const notifyDays = Number(base.notify_days);
  const scheduleHour = Number(base.schedule_hour);
  const scheduleMinute = Number(base.schedule_minute);

  return {
    enabled: Boolean(base.enabled),
    to_emails: Array.isArray(base.to_emails)
      ? [...new Set(base.to_emails.map((v) => String(v || "").trim()).filter(Boolean))]
      : [],
    notify_days: Number.isFinite(notifyDays) ? Math.min(365, Math.max(1, notifyDays)) : 30,
    schedule_hour: Number.isFinite(scheduleHour) ? Math.min(23, Math.max(0, scheduleHour)) : 9,
    schedule_minute: Number.isFinite(scheduleMinute) ? Math.min(59, Math.max(0, scheduleMinute)) : 0,
    include_expired: base.include_expired === undefined ? true : Boolean(base.include_expired),
    subject_template: String(base.subject_template || DEFAULTS.mailAdmin.subject_template || "").slice(0, 300),
    body_template: String(base.body_template || DEFAULTS.mailAdmin.body_template || "").slice(0, 20000),
    last_sent_at: base.last_sent_at ? String(base.last_sent_at) : null,
    last_error: base.last_error ? String(base.last_error) : null,
    last_result: base.last_result && typeof base.last_result === "object" ? base.last_result : null,
  };
}

function normalizeMailUserSetting(source) {
  const base = source || {};
  const notifyDays = Number(base.notify_days);
  const scheduleHour = Number(base.schedule_hour);
  const scheduleMinute = Number(base.schedule_minute);

  return {
    enabled: Boolean(base.enabled),
    notify_days: Number.isFinite(notifyDays) ? Math.min(365, Math.max(1, notifyDays)) : 30,
    schedule_hour: Number.isFinite(scheduleHour) ? Math.min(23, Math.max(0, scheduleHour)) : 9,
    schedule_minute: Number.isFinite(scheduleMinute) ? Math.min(59, Math.max(0, scheduleMinute)) : 0,
    include_expired: base.include_expired === undefined ? true : Boolean(base.include_expired),
    only_active_users: base.only_active_users === undefined ? true : Boolean(base.only_active_users),
    subject_template: String(base.subject_template || DEFAULTS.mailUser.subject_template || "").slice(0, 300),
    body_template: String(base.body_template || DEFAULTS.mailUser.body_template || "").slice(0, 20000),
    last_sent_at: base.last_sent_at ? String(base.last_sent_at) : null,
    last_error: base.last_error ? String(base.last_error) : null,
    last_result: base.last_result && typeof base.last_result === "object" ? base.last_result : null,
  };
}

function applyMailSmtpInputs() {
  const config = normalizeMailSmtpSetting(state.settings.mailSmtp);
  state.settings.mailSmtp = config;

  const host = document.getElementById("smtpHost");
  if (!host) return;

  const port = document.getElementById("smtpPort");
  const useTls = document.getElementById("smtpUseTls");
  const useSsl = document.getElementById("smtpUseSsl");
  const username = document.getElementById("smtpUsername");
  const fromEmail = document.getElementById("smtpFromEmail");
  const passwordInput = document.getElementById("smtpPassword");

  host.value = config.smtp_host;
  port.value = String(config.smtp_port || 587);
  useTls.checked = config.use_tls;
  useSsl.checked = config.use_ssl;
  username.value = config.smtp_username;
  fromEmail.value = config.from_email;
  if (passwordInput) passwordInput.value = "";

  renderMailSmtpStatus();
}

function applyMailAdminInputs() {
  const config = normalizeMailAdminSetting(state.settings.mailAdmin);
  state.settings.mailAdmin = config;

  const enabled = document.getElementById("adminMailEnabled");
  if (!enabled) return;

  document.getElementById("adminMailEnabled").checked = config.enabled;
  document.getElementById("adminMailToEmails").value = (config.to_emails || []).join(", ");
  document.getElementById("adminMailNotifyDays").value = String(config.notify_days || 30);
  document.getElementById("adminMailScheduleHour").value = String(config.schedule_hour ?? 9);
  document.getElementById("adminMailScheduleMinute").value = String(config.schedule_minute ?? 0);
  document.getElementById("adminMailIncludeExpired").checked = config.include_expired;
  document.getElementById("adminMailSubjectTemplate").value = config.subject_template || "";
  document.getElementById("adminMailBodyTemplate").value = config.body_template || "";

  renderAdminMailStatus();
}

function applyMailUserInputs() {
  const config = normalizeMailUserSetting(state.settings.mailUser);
  state.settings.mailUser = config;

  const enabled = document.getElementById("userMailEnabled");
  if (!enabled) return;

  document.getElementById("userMailEnabled").checked = config.enabled;
  document.getElementById("userMailNotifyDays").value = String(config.notify_days || 30);
  document.getElementById("userMailScheduleHour").value = String(config.schedule_hour ?? 9);
  document.getElementById("userMailScheduleMinute").value = String(config.schedule_minute ?? 0);
  document.getElementById("userMailIncludeExpired").checked = config.include_expired;
  document.getElementById("userMailOnlyActiveUsers").checked = config.only_active_users;
  document.getElementById("userMailSubjectTemplate").value = config.subject_template || "";
  document.getElementById("userMailBodyTemplate").value = config.body_template || "";

  renderUserMailStatus();
}

function renderMailSmtpStatus() {
  if (!smtpConfigStatus) return;
  const config = normalizeMailSmtpSetting(state.settings.mailSmtp);
  const passwordStatus = config.has_stored_password
    ? "설정됨(서버 암호화 저장)"
    : config.has_runtime_password
      ? "설정됨(현재 서버 메모리)"
      : "미설정";
  smtpConfigStatus.textContent = `SMTP 비밀번호: ${passwordStatus}`;
}

function renderAdminMailStatus() {
  if (!adminMailStatus) return;
  const config = normalizeMailAdminSetting(state.settings.mailAdmin);
  const lastSent = config.last_sent_at ? new Date(config.last_sent_at).toLocaleString() : "없음";
  const result = config.last_result || {};
  const resultText = config.last_result
    ? ` / 최근 결과: 만료예정 ${Number(result.expiring_count || 0)}건, 만료 ${Number(result.expired_count || 0)}건`
    : "";
  const lastError = config.last_error ? ` / 최근 오류: ${config.last_error}` : "";
  adminMailStatus.textContent = `최근 발송: ${lastSent}${resultText}${lastError}`;
}

function renderUserMailStatus() {
  if (!userMailStatus) return;
  const config = normalizeMailUserSetting(state.settings.mailUser);
  const lastSent = config.last_sent_at ? new Date(config.last_sent_at).toLocaleString() : "없음";
  const result = config.last_result || {};
  const resultText = config.last_result
    ? ` / 최근 결과: 대상 ${Number(result.target_users || 0)}명, 발송 ${Number(result.sent_users || 0)}명, 실패 ${Number(result.failed_users || 0)}명`
    : "";
  const lastError = config.last_error ? ` / 최근 오류: ${config.last_error}` : "";
  userMailStatus.textContent = `최근 발송: ${lastSent}${resultText}${lastError}`;
}

function applyMailSettingInputs() {
  applyMailSmtpInputs();
  applyMailAdminInputs();
  applyMailUserInputs();
}

function readMailSmtpForm() {
  const smtpPort = Number(document.getElementById("smtpPort")?.value || 587);
  const payload = {
    smtp_host: String(document.getElementById("smtpHost")?.value || "").trim(),
    smtp_port: smtpPort,
    use_tls: Boolean(document.getElementById("smtpUseTls")?.checked),
    use_ssl: Boolean(document.getElementById("smtpUseSsl")?.checked),
    smtp_username: String(document.getElementById("smtpUsername")?.value || "").trim() || null,
    smtp_password: String(document.getElementById("smtpPassword")?.value || "").trim() || null,
    from_email: String(document.getElementById("smtpFromEmail")?.value || "").trim() || null,
  };

  if (!Number.isInteger(payload.smtp_port) || payload.smtp_port < 1 || payload.smtp_port > 65535) {
    throw new Error("SMTP 포트는 1~65535 범위의 숫자여야 합니다.");
  }

  if (payload.use_ssl && payload.use_tls) {
    throw new Error("SSL과 TLS는 동시에 선택할 수 없습니다.");
  }

  if (!payload.smtp_host) {
    throw new Error("SMTP 서버 주소를 입력해주세요.");
  }

  return payload;
}

function readAdminMailForm() {
  const notifyDays = Number(document.getElementById("adminMailNotifyDays")?.value || 30);
  const scheduleHour = Number(document.getElementById("adminMailScheduleHour")?.value || 9);
  const scheduleMinute = Number(document.getElementById("adminMailScheduleMinute")?.value || 0);

  const payload = {
    enabled: Boolean(document.getElementById("adminMailEnabled")?.checked),
    to_emails: parseMailEmailList(document.getElementById("adminMailToEmails")?.value || ""),
    notify_days: notifyDays,
    schedule_hour: scheduleHour,
    schedule_minute: scheduleMinute,
    include_expired: Boolean(document.getElementById("adminMailIncludeExpired")?.checked),
    subject_template: String(document.getElementById("adminMailSubjectTemplate")?.value || "").trim() || null,
    body_template: String(document.getElementById("adminMailBodyTemplate")?.value || "").trim() || null,
  };

  if (!Number.isInteger(payload.notify_days) || payload.notify_days < 1 || payload.notify_days > 365) {
    throw new Error("알림 기준 일수는 1~365 범위여야 합니다.");
  }
  if (!Number.isInteger(payload.schedule_hour) || payload.schedule_hour < 0 || payload.schedule_hour > 23) {
    throw new Error("발송 시(0~23)를 확인해주세요.");
  }
  if (!Number.isInteger(payload.schedule_minute) || payload.schedule_minute < 0 || payload.schedule_minute > 59) {
    throw new Error("발송 분(0~59)을 확인해주세요.");
  }

  if (payload.enabled && !payload.to_emails.length) {
    throw new Error("관리자 수신 이메일 주소를 1개 이상 입력해주세요.");
  }

  if (payload.subject_template && payload.subject_template.length > 300) {
    throw new Error("메일 제목 템플릿은 최대 300자까지 입력할 수 있습니다.");
  }

  if (payload.body_template && payload.body_template.length > 20000) {
    throw new Error("메일 본문 템플릿은 최대 20000자까지 입력할 수 있습니다.");
  }

  return payload;
}

function readUserMailForm() {
  const notifyDays = Number(document.getElementById("userMailNotifyDays")?.value || 30);
  const scheduleHour = Number(document.getElementById("userMailScheduleHour")?.value || 9);
  const scheduleMinute = Number(document.getElementById("userMailScheduleMinute")?.value || 0);

  const payload = {
    enabled: Boolean(document.getElementById("userMailEnabled")?.checked),
    notify_days: notifyDays,
    schedule_hour: scheduleHour,
    schedule_minute: scheduleMinute,
    include_expired: Boolean(document.getElementById("userMailIncludeExpired")?.checked),
    only_active_users: Boolean(document.getElementById("userMailOnlyActiveUsers")?.checked),
    subject_template: String(document.getElementById("userMailSubjectTemplate")?.value || "").trim() || null,
    body_template: String(document.getElementById("userMailBodyTemplate")?.value || "").trim() || null,
  };

  if (!Number.isInteger(payload.notify_days) || payload.notify_days < 1 || payload.notify_days > 365) {
    throw new Error("알림 기준 일수는 1~365 범위여야 합니다.");
  }
  if (!Number.isInteger(payload.schedule_hour) || payload.schedule_hour < 0 || payload.schedule_hour > 23) {
    throw new Error("발송 시(0~23)를 확인해주세요.");
  }
  if (!Number.isInteger(payload.schedule_minute) || payload.schedule_minute < 0 || payload.schedule_minute > 59) {
    throw new Error("발송 분(0~59)을 확인해주세요.");
  }

  if (payload.subject_template && payload.subject_template.length > 300) {
    throw new Error("메일 제목 템플릿은 최대 300자까지 입력할 수 있습니다.");
  }

  if (payload.body_template && payload.body_template.length > 20000) {
    throw new Error("메일 본문 템플릿은 최대 20000자까지 입력할 수 있습니다.");
  }

  return payload;
}

async function loadMailSmtpSetting() {
  if (!state.user || state.user.role !== "admin") return;
  const setting = await api("/settings/mail/smtp");
  state.settings.mailSmtp = normalizeMailSmtpSetting(setting);
  applyMailSmtpInputs();
}

async function loadMailAdminSetting() {
  if (!state.user || state.user.role !== "admin") return;
  const setting = await api("/settings/mail/admin");
  state.settings.mailAdmin = normalizeMailAdminSetting(setting);
  applyMailAdminInputs();
}

async function loadMailUserSetting() {
  if (!state.user || state.user.role !== "admin") return;
  const setting = await api("/settings/mail/user");
  state.settings.mailUser = normalizeMailUserSetting(setting);
  applyMailUserInputs();
}

async function loadMailSettingsAll() {
  if (!state.user || state.user.role !== "admin") return;
  await Promise.all([loadMailSmtpSetting(), loadMailAdminSetting(), loadMailUserSetting()]);
}

function applySoftwareMailInputs() {
  applyMailSettingInputs();
}

async function loadSoftwareExpiryMailSetting() {
  await loadMailSettingsAll();
}
const state = {
  token: localStorage.getItem(STORAGE_KEYS.token) || "",
  user: null,
  assets: [],
  disposedAssets: [],
  softwareLicenses: [],
  softwareLicensesAll: [],
  currentAssetId: null,
  directoryUsers: [],
  lastLdapSearchUsers: [],
  managedUsers: [],
  managedAdmins: [],
  ldapSession: {
    bindPassword: "",
  },
  ldapSchedule: {
    enabled: false,
    interval_minutes: 60,
    has_runtime_password: false,
    has_stored_password: false,
    last_synced_at: null,
    last_error: null,
    last_result: null,
  },
  activeMainTab: "dashboard",
  hardwareSubtab: "assets",
  softwareSubtab: "list",
  softwareAssignedSort: { key: "expiry_key", direction: "asc" },
  pagination: {
    page: 1,
    pageSize: 50,
    hasNext: false,
  },
  dashboardDrilldown: null,
  dashboardSummary: null,
  dashboardCostPeriod: "month",
  dashboardCostScope: "all",
  settingsSubtab: "hardware",
  settingsAccountsSubtab: "users",
  orgChartShowInactive: false,
  orgChartDeptExpanded: false,
  settingsMiscSubtab: "ldap",
  settingsMailSubtab: "smtp",
  settings: {
    codeTemplate: localStorage.getItem(STORAGE_KEYS.codeTemplate) || DEFAULTS.codeTemplate,
    defaultOwner: localStorage.getItem(STORAGE_KEYS.defaultOwner) || DEFAULTS.defaultOwner,
    defaultManager: localStorage.getItem(STORAGE_KEYS.defaultManager) || DEFAULTS.defaultManager,
    categories: loadCategorySettings(),
    ldapConfig: loadLdapConfig(),
    softwareLicenseCategories: loadSoftwareMetaList(STORAGE_KEYS.softwareLicenseCategories, DEFAULTS.softwareLicenseCategories),
    exchangeRate: { ...DEFAULTS.exchangeRate },
    mailSmtp: { ...DEFAULTS.mailSmtp },
    mailAdmin: { ...DEFAULTS.mailAdmin },
    mailUser: { ...DEFAULTS.mailUser },
  },
};

const statusValues = ["사용중", "대기", "폐기필요", "폐기완료"];
const nonInUseStatuses = new Set(["대기", "폐기필요", "폐기완료"]);
const usageTypeValues = [
  "주장비",
  "대여장비",
  "프로젝트장비",
  "보조장비",
  "기타장비",
  "서버장비",
  "네트워크장비",
];

const softwareSubscriptionTypeValues = ["영구 구매", "연 구독", "월 구독", "사용량만큼 지불"];

function normalizeSoftwareLicenseScope(value) {
  const key = String(value || "").trim().toLocaleLowerCase();
  if (["필수", "required", "mandatory", "critical"].includes(key)) return "필수";
  return "일반";
}

const usageShortMap = {
  주장비: "PRI",
  대여장비: "LON",
  프로젝트장비: "PRJ",
  보조장비: "AUX",
  기타장비: "ETC",
  서버장비: "SRV",
  네트워크장비: "NET",
};

const actionLabelMap = {
  created: "등록",
  updated: "수정",
  deleted: "삭제",
  assigned: "할당",
  returned: "반납",
  marked_disposal_required: "폐기필요 처리",
  marked_disposed: "폐기완료 처리",
};

const fieldLabelMap = {
  name: "자산명",
  category: "카테고리",
  usage_type: "사용 분류",
  status: "상태",
  owner: "사용자",
  manager: "담당자",
  department: "부서",
  location: "위치",
  manufacturer: "제조사",
  model_name: "모델명",
  serial_number: "시리얼번호",
  asset_code: "자산코드",
  vendor: "구매처",
  purchase_date: "구매일",
  purchase_cost: "구매금액",
  warranty_expiry: "보증만료일",
  rental_start_date: "대여 시작일자",
  rental_end_date: "대여 만료일자",
  notes: "메모",
};

const loginPanel = document.getElementById("loginPanel");
const appPanel = document.getElementById("appPanel");
const userInfo = document.getElementById("userInfo");
const tabs = document.getElementById("tabs");
const hardwareSubtabs = document.getElementById("hardwareSubtabs");
const softwareSubtabs = document.getElementById("softwareSubtabs");
const settingsSubtabs = document.getElementById("settingsSubtabs");
const settingsAccountsSubtabs = document.getElementById("settingsAccountsSubtabs");
const settingsMiscSubtabs = document.getElementById("settingsMiscSubtabs");
const settingsMailSubtabs = document.getElementById("settingsMailSubtabs");
const toast = document.getElementById("toast");
const summaryCards = document.getElementById("summaryCards");
const softwareSummaryCards = document.getElementById("softwareSummaryCards");
const statusBoard = document.getElementById("statusBoard");
const usageBoard = document.getElementById("usageBoard");
const categoryBoard = document.getElementById("categoryBoard");
const dashboardCostPeriodTabs = document.getElementById("dashboardCostPeriodTabs");
const dashboardCostScopeTabs = document.getElementById("dashboardCostScopeTabs");
const dashboardCostChart = document.getElementById("dashboardCostChart");
const dashboardCostLegend = document.getElementById("dashboardCostLegend");
const assetTableBody = document.getElementById("assetTableBody");
const disposedTableBody = document.getElementById("disposedTableBody");
const softwareTableBody = document.getElementById("softwareTableBody");
const softwareAssignUserTableBody = document.getElementById("softwareAssignUserTableBody");
const softwareCategoryTableBody = document.getElementById("softwareCategoryTableBody");
const assetsPrevPageBtn = document.getElementById("assetsPrevPageBtn");
const assetsNextPageBtn = document.getElementById("assetsNextPageBtn");
const assetsPageInfo = document.getElementById("assetsPageInfo");
const editModal = document.getElementById("editModal");
const editHistoryBox = document.getElementById("editHistoryBox");
const ldapResultBody = document.getElementById("ldapResultBody");
const ldapResultInfo = document.getElementById("ldapResultInfo");
const ldapPasswordStatus = document.getElementById("ldapPasswordStatus");
const ldapScheduleInfo = document.getElementById("ldapScheduleInfo");
const smtpConfigStatus = document.getElementById("smtpConfigStatus");
const adminMailStatus = document.getElementById("adminMailStatus");
const userMailStatus = document.getElementById("userMailStatus");
const userMailPreviewModal = document.getElementById("userMailPreviewModal");
const userMailPreviewSummary = document.getElementById("userMailPreviewSummary");
const userMailPreviewTableBody = document.getElementById("userMailPreviewTableBody");
const directoryUserDatalist = document.getElementById("directoryUserDatalist");
const adminUserDatalist = document.getElementById("adminUserDatalist");
const softwareLicenseDatalist = document.getElementById("softwareLicenseDatalist");
const usersTableBody = document.getElementById("usersTableBody");
const inactiveUsersTableBody = document.getElementById("inactiveUsersTableBody");
const adminsTableBody = document.getElementById("adminsTableBody");
const orgChartBoard = document.getElementById("orgChartBoard");
const orgChartSummary = document.getElementById("orgChartSummary");
const orgChartShowInactiveInput = document.getElementById("orgChartShowInactive");
const orgChartToggleDeptExpandBtn = document.getElementById("orgChartToggleDeptExpandBtn");
const ownerAssignModal = document.getElementById("ownerAssignModal");
const ownerAssignInput = document.getElementById("ownerAssignInput");
const addOwnerInput = document.getElementById("addOwner");
const editOwnerInput = document.getElementById("editOwner");
const ldapPasswordModal = document.getElementById("ldapPasswordModal");
const ldapSessionPasswordInput = document.getElementById("ldapSessionPasswordInput");

const ownerLookupState = {
  menu: null,
  input: null,
  candidates: [],
  activeIndex: -1,
};

const ownerLookupInputIds = ["addOwner", "editOwner", "ownerAssignInput"];

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2200);
}

function authHeaders() {
  return state.token ? { Authorization: `Bearer ${state.token}` } : {};
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function makeOptions(values, selected) {
  return values
    .map((value) => {
      const isSelected = value === selected ? "selected" : "";
      return `<option value="${escapeHtml(value)}" ${isSelected}>${escapeHtml(value)}</option>`;
    })
    .join("");
}


function toLookupDisplay(username, displayName) {
  const idText = String(username || "").trim();
  const nameText = String(displayName || "").trim();
  if (!idText) return "";
  if (!nameText || nameText === idText) return idText;
  return `${idText} | ${nameText}`;
}

function extractLookupUsername(rawValue) {
  const text = String(rawValue || "").trim();
  if (!text) return "";
  const pipeIndex = text.indexOf("|");
  if (pipeIndex < 0) return text;
  return text.slice(0, pipeIndex).trim();
}

function renderDirectoryUserDatalist() {
  if (!directoryUserDatalist) return;

  const rows = Array.isArray(state.directoryUsers) ? state.directoryUsers : [];
  directoryUserDatalist.innerHTML = rows
    .map((row) => `<option value="${escapeHtml(toLookupDisplay(row.username, row.display_name))}"></option>`)
    .join("");

  refreshOwnerLookupIfNeeded();
  renderSoftwareAssigneeOptions();
}

function renderSoftwareAssigneeOptions(selectedValues = null) {
  const select = document.getElementById("swAssignees");
  if (!select) return;

  const selected = new Set(
    Array.isArray(selectedValues)
      ? selectedValues.map((v) => String(v || "").trim()).filter(Boolean)
      : [...select.selectedOptions].map((option) => option.value),
  );

  const rows = Array.isArray(state.directoryUsers) ? state.directoryUsers : [];
  select.innerHTML = rows
    .map((row) => {
      const username = String(row.username || "").trim();
      if (!username) return "";
      const display = String(row.display_name || "").trim();
      const label = display ? `${display} (${username})` : username;
      const isSelected = selected.has(username) ? "selected" : "";
      return `<option value="${escapeHtml(username)}" ${isSelected}>${escapeHtml(label)}</option>`;
    })
    .join("");
}

function renderAdminUserDatalist() {
  if (!adminUserDatalist) return;

  const rows = Array.isArray(state.managedAdmins) ? state.managedAdmins : [];
  adminUserDatalist.innerHTML = rows
    .map((row) => `<option value="${escapeHtml(toLookupDisplay(row.username, row.username))}"></option>`)
    .join("");
}

function findDirectoryUserByUsername(username) {
  const key = String(username || "").trim();
  if (!key || key === "미지정") return null;
  return state.directoryUsers.find((row) => String(row.username || "").trim() === key) || null;
}

function getOwnerDisplayName(username) {
  const key = String(username || "").trim();
  if (!key || key === "미지정") return "미지정";

  const found = findDirectoryUserByUsername(key);
  const displayName = String(found?.display_name || "").trim();
  return displayName || key;
}

function getOwnerDepartment(username) {
  const found = findDirectoryUserByUsername(username);
  const department = String(found?.department || "").trim();
  return department || "";
}

function syncDepartmentByOwner(prefix, options = {}) {
  const { preserveWhenUnknown = true } = options;
  const ownerInput = document.getElementById(`${prefix}Owner`);
  const departmentInput = document.getElementById(`${prefix}Department`);
  if (!ownerInput || !departmentInput) return;

  const ownerKey = extractLookupUsername(ownerInput.value).trim();
  if (!ownerKey || ownerKey === "미지정") {
    departmentInput.value = "";
    return;
  }

  const department = getOwnerDepartment(ownerKey);
  if (department) {
    departmentInput.value = department;
    return;
  }

  if (!preserveWhenUnknown) {
    departmentInput.value = "";
  }
}

function bindOwnerDepartmentSync(prefix) {
  const ownerInput = document.getElementById(`${prefix}Owner`);
  if (!ownerInput || ownerInput.dataset.departmentSyncBound === "1") return;

  ownerInput.dataset.departmentSyncBound = "1";
  const onSync = () => syncDepartmentByOwner(prefix, { preserveWhenUnknown: false });
  ownerInput.addEventListener("change", onSync);
  ownerInput.addEventListener("blur", onSync);
}

function setOwnerInputValue(id, username) {
  const input = document.getElementById(id);
  if (!input) return;

  const key = String(username || "").trim();
  if (!key || key === "미지정") {
    input.value = "미지정";
    return;
  }

  const found = findDirectoryUserByUsername(key);
  input.value = found ? toLookupDisplay(found.username, found.display_name) : key;
}

function setManagerInputValue(id, username) {
  const input = document.getElementById(id);
  if (!input) return;

  const key = String(username || "").trim();
  if (!key || key === "미지정") {
    input.value = "미지정";
    return;
  }

  const found = state.managedAdmins.find((row) => row.username === key);
  input.value = found ? toLookupDisplay(found.username, found.username) : key;
}

function getOwnerLookupCandidates(rawQuery = "") {
  const rows = Array.isArray(state.directoryUsers) ? state.directoryUsers : [];
  const query = extractLookupUsername(rawQuery).toLocaleLowerCase();

  const filtered = !query
    ? rows
    : rows.filter((row) => {
        const username = String(row.username || "").toLocaleLowerCase();
        const displayName = String(row.display_name || "").toLocaleLowerCase();
        return username.includes(query) || displayName.includes(query);
      });

  return filtered.slice(0, 12);
}

function ensureOwnerLookupMenu() {
  if (ownerLookupState.menu) return ownerLookupState.menu;

  const menu = document.createElement("div");
  menu.className = "lookup-menu hidden";
  menu.setAttribute("role", "listbox");
  document.body.appendChild(menu);

  menu.addEventListener("mousedown", (event) => {
    event.preventDefault();
  });

  menu.addEventListener("click", (event) => {
    const option = event.target.closest(".lookup-option");
    if (!option) return;
    selectOwnerLookupCandidate(Number(option.dataset.index || 0));
  });

  document.addEventListener("mousedown", (event) => {
    if (!ownerLookupState.menu || ownerLookupState.menu.classList.contains("hidden")) return;
    if (event.target === ownerLookupState.input || ownerLookupState.menu.contains(event.target)) return;
    closeOwnerLookupMenu();
  });

  window.addEventListener("resize", () => {
    if (!ownerLookupState.menu?.classList.contains("hidden")) positionOwnerLookupMenu();
  });

  window.addEventListener(
    "scroll",
    () => {
      if (!ownerLookupState.menu?.classList.contains("hidden")) positionOwnerLookupMenu();
    },
    true,
  );

  ownerLookupState.menu = menu;
  return menu;
}

function positionOwnerLookupMenu() {
  if (!ownerLookupState.menu || !ownerLookupState.input) return;

  const rect = ownerLookupState.input.getBoundingClientRect();
  ownerLookupState.menu.style.left = `${window.scrollX + rect.left}px`;
  ownerLookupState.menu.style.top = `${window.scrollY + rect.bottom + 4}px`;
  ownerLookupState.menu.style.width = `${rect.width}px`;
}

function closeOwnerLookupMenu() {
  if (!ownerLookupState.menu) return;
  ownerLookupState.menu.classList.add("hidden");
  ownerLookupState.menu.innerHTML = "";
  ownerLookupState.input = null;
  ownerLookupState.candidates = [];
  ownerLookupState.activeIndex = -1;
}

function renderOwnerLookupMenu() {
  const menu = ensureOwnerLookupMenu();
  if (!ownerLookupState.input || !ownerLookupState.candidates.length) {
    closeOwnerLookupMenu();
    return;
  }

  menu.innerHTML = ownerLookupState.candidates
    .map((row, index) => {
      const isActive = index === ownerLookupState.activeIndex ? "active" : "";
      const display = toLookupDisplay(row.username, row.display_name);
      return `<button type="button" class="lookup-option ${isActive}" data-index="${index}">${escapeHtml(display)}</button>`;
    })
    .join("");

  menu.classList.remove("hidden");
  positionOwnerLookupMenu();
}

function openOwnerLookupMenu(input) {
  if (!input) return;

  ownerLookupState.input = input;
  ownerLookupState.candidates = getOwnerLookupCandidates(input.value);
  ownerLookupState.activeIndex = ownerLookupState.candidates.length ? 0 : -1;
  renderOwnerLookupMenu();
}

function moveOwnerLookupActive(step) {
  if (!ownerLookupState.candidates.length) return;

  if (ownerLookupState.activeIndex < 0) {
    ownerLookupState.activeIndex = 0;
  } else {
    ownerLookupState.activeIndex = (ownerLookupState.activeIndex + step + ownerLookupState.candidates.length) % ownerLookupState.candidates.length;
  }

  renderOwnerLookupMenu();
}

function selectOwnerLookupCandidate(index = 0) {
  if (!ownerLookupState.input || !ownerLookupState.candidates.length) return;

  const safeIndex = Math.max(0, Math.min(index, ownerLookupState.candidates.length - 1));
  const row = ownerLookupState.candidates[safeIndex];
  ownerLookupState.input.value = toLookupDisplay(row.username, row.display_name);
  ownerLookupState.input.dispatchEvent(new Event("change", { bubbles: true }));
  closeOwnerLookupMenu();
}

function setupOwnerLookupInputs() {
  ownerLookupInputIds.forEach((id) => {
    const input = document.getElementById(id);
    if (!input || input.dataset.lookupBound === "1") return;

    input.dataset.lookupBound = "1";

    input.addEventListener("focus", () => {
      openOwnerLookupMenu(input);
    });

    input.addEventListener("input", () => {
      openOwnerLookupMenu(input);
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (!ownerLookupState.menu || ownerLookupState.menu.classList.contains("hidden") || ownerLookupState.input !== input) {
          openOwnerLookupMenu(input);
          return;
        }
        moveOwnerLookupActive(1);
        return;
      }

      if (event.key === "ArrowUp") {
        event.preventDefault();
        if (!ownerLookupState.menu || ownerLookupState.menu.classList.contains("hidden") || ownerLookupState.input !== input) {
          openOwnerLookupMenu(input);
          moveOwnerLookupActive(-1);
          return;
        }
        moveOwnerLookupActive(-1);
        return;
      }

      if (event.key === "Enter") {
        const menuHidden = !ownerLookupState.menu || ownerLookupState.menu.classList.contains("hidden") || ownerLookupState.input !== input;
        if (menuHidden) {
          openOwnerLookupMenu(input);
        }

        if (ownerLookupState.candidates.length) {
          event.preventDefault();
          const targetIndex = ownerLookupState.activeIndex >= 0 ? ownerLookupState.activeIndex : 0;
          selectOwnerLookupCandidate(targetIndex);
        }
        return;
      }

      if (event.key === "Escape") {
        closeOwnerLookupMenu();
      }
    });

    input.addEventListener("blur", () => {
      setTimeout(() => {
        if (!ownerLookupState.menu || ownerLookupState.menu.contains(document.activeElement)) return;
        closeOwnerLookupMenu();
      }, 100);
    });
  });
}

function refreshOwnerLookupIfNeeded() {
  if (!ownerLookupState.input || ownerLookupState.menu?.classList.contains("hidden")) return;
  openOwnerLookupMenu(ownerLookupState.input);
}
function updateLdapPasswordStatus() {
  if (!ldapPasswordStatus) return;
  ldapPasswordStatus.textContent = state.ldapSession.bindPassword ? "비밀번호 입력됨(현재 브라우저 세션)" : "비밀번호 미입력";
}

function renderUsersTable(view = "user") {
  const key = String(view || "user");
  const isAdminView = key === "admin";
  const isInactiveView = key === "user-inactive";

  const tableBody = isAdminView ? adminsTableBody : isInactiveView ? inactiveUsersTableBody : usersTableBody;
  if (!tableBody) return;

  if (isAdminView) {
    const rows = state.managedAdmins;
    if (!rows.length) {
      tableBody.innerHTML = '<tr><td colspan="5">등록된 관리자가 없습니다.</td></tr>';
      return;
    }

    tableBody.innerHTML = rows
      .map(
        (row) => `
          <tr>
            <td>${escapeHtml(row.username)}</td>
            <td>${escapeHtml(row.role || "admin")}</td>
            <td>${row.is_active ? "활성" : "비활성"}</td>
            <td>${new Date(row.created_at).toLocaleString()}</td>
            <td>
              <button type="button" class="mini-btn user-toggle-btn" data-id="${row.id}" data-role="admin" data-active="${row.is_active ? "1" : "0"}">
                ${row.is_active ? "비활성" : "활성"} 전환
              </button>
            </td>
          </tr>
        `,
      )
      .join("");
    return;
  }

  const rows = (state.managedUsers || []).filter((row) => (isInactiveView ? !row.is_active : row.is_active));
  if (!rows.length) {
    tableBody.innerHTML = `<tr><td colspan="7">${isInactiveView ? "비활성 사용자" : "활성 사용자"}가 없습니다.</td></tr>`;
    return;
  }

  tableBody.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.username)}</td>
          <td>${escapeHtml(row.display_name || "-")}</td>
          <td>${escapeHtml(row.email || "-")}</td>
          <td>${escapeHtml(row.department || "-")}</td>
          <td>${row.is_active ? "활성" : "비활성"}</td>
          <td>${escapeHtml(row.source || "manual")}</td>
          <td>
            <button type="button" class="mini-btn user-toggle-btn" data-id="${row.id}" data-role="user" data-active="${row.is_active ? "1" : "0"}">
              ${row.is_active ? "비활성" : "활성"} 전환
            </button>
          </td>
        </tr>
      `,
    )
    .join("");
}

function getOrgChartDepartmentName(row) {
  const department = String(row?.department || "").trim();
  return department || "\uBBF8\uC9C0\uC815";
}

function updateOrgChartDeptToggleButton() {
  if (!orgChartToggleDeptExpandBtn) return;
  orgChartToggleDeptExpandBtn.textContent = state.orgChartDeptExpanded ? "\uBD80\uC11C \uC804\uCCB4 \uC811\uAE30" : "\uBD80\uC11C \uC804\uCCB4 \uD3BC\uCE68";
}

function renderOrgChart(rows = state.managedUsers || []) {
  if (!orgChartBoard || !orgChartSummary) return;

  if (orgChartShowInactiveInput) {
    orgChartShowInactiveInput.checked = Boolean(state.orgChartShowInactive);
  }
  updateOrgChartDeptToggleButton();

  const sourceRows = Array.isArray(rows) ? rows.filter((row) => String(row?.username || "").trim()) : [];
  const activeCount = sourceRows.filter((row) => Boolean(row?.is_active)).length;
  const inactiveCount = sourceRows.length - activeCount;
  const filteredRows = sourceRows.filter((row) => state.orgChartShowInactive || Boolean(row?.is_active));

  if (!filteredRows.length) {
    orgChartSummary.textContent = sourceRows.length
      ? "\uBE44\uD65C\uC131 \uC0AC\uC6A9\uC790 \uC228\uAE40 \uC0C1\uD0DC\uC785\uB2C8\uB2E4. '\uBE44\uD65C\uC131 \uC0AC\uC6A9\uC790 \uD3EC\uD568'\uC744 \uCF1C\uBA74 \uD45C\uC2DC\uB429\uB2C8\uB2E4."
      : "\uD45C\uC2DC\uD560 \uC0AC\uC6A9\uC790 \uB370\uC774\uD130\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.";
    orgChartBoard.innerHTML = '<p class="muted">\uD45C\uC2DC\uD560 \uC0AC\uC6A9\uC790 \uB370\uC774\uD130\uAC00 \uC5C6\uC2B5\uB2C8\uB2E4.</p>';
    return;
  }

  const normalize = (value) => String(value || "").trim().toLowerCase();
  const nodes = [];
  const aliasMap = new Map();

  filteredRows.forEach((row, index) => {
    const username = String(row?.username || "").trim();
    const userDn = normalize(row?.user_dn);
    const objectGuid = normalize(row?.object_guid);
    const uidKey = normalize(username);

    const baseKey = userDn ? `dn:${userDn}` : objectGuid ? `guid:${objectGuid}` : `uid:${uidKey || `row-${index}`}`;
    let key = baseKey;
    let seq = 2;
    while (nodes.some((node) => node.key === key)) {
      key = `${baseKey}#${seq++}`;
    }

    const node = {
      key,
      row,
      managerKey: normalize(row?.manager_dn),
      children: [],
      parent: null,
      hasParent: false,
      orphan: false,
    };

    nodes.push(node);

    if (userDn && !aliasMap.has(`dn:${userDn}`)) aliasMap.set(`dn:${userDn}`, node);
    if (objectGuid && !aliasMap.has(`guid:${objectGuid}`)) aliasMap.set(`guid:${objectGuid}`, node);
    if (uidKey && !aliasMap.has(`uid:${uidKey}`)) aliasMap.set(`uid:${uidKey}`, node);
  });

  nodes.forEach((node) => {
    if (!node.managerKey) return;

    const parent = aliasMap.get(`dn:${node.managerKey}`);
    if (!parent || parent === node) {
      node.orphan = true;
      return;
    }

    parent.children.push(node);
    node.parent = parent;
    node.hasParent = true;
  });

  const sortNodes = (list) => {
    list.sort((a, b) => {
      const an = String(a?.row?.display_name || a?.row?.username || "");
      const bn = String(b?.row?.display_name || b?.row?.username || "");
      return an.localeCompare(bn, "ko");
    });
    list.forEach((node) => sortNodes(node.children));
  };

  const roots = nodes.filter((node) => !node.hasParent);
  if (!roots.length && nodes.length) {
    roots.push(nodes[0]);
  }

  const reachable = new Set();
  const collectReachable = (node) => {
    if (!node || reachable.has(node.key)) return;
    reachable.add(node.key);
    node.children.forEach(collectReachable);
  };

  roots.forEach(collectReachable);
  nodes.forEach((node) => {
    if (!reachable.has(node.key)) {
      roots.push(node);
      collectReachable(node);
    }
  });

  sortNodes(roots);

  const linkedCount = nodes.filter((node) => node.hasParent).length;
  const orphanCount = nodes.filter((node) => node.orphan).length;
  const visibleActiveCount = nodes.filter((node) => Boolean(node?.row?.is_active)).length;

  orgChartSummary.textContent = `\uD45C\uC2DC ${nodes.length}\uBA85 (\uD65C\uC131 ${visibleActiveCount}\uBA85) / \uC804\uCCB4 ${sourceRows.length}\uBA85 (\uD65C\uC131 ${activeCount}\uBA85, \uBE44\uD65C\uC131 ${inactiveCount}\uBA85) / \uD2B8\uB9AC \uC5F0\uACB0 ${linkedCount}\uBA85 / \uB8E8\uD2B8 ${roots.length}\uBA85 / \uC0C1\uC704DN \uBBF8\uB9E4\uD551 ${orphanCount}\uBA85`;

  const renderNode = (node, visited = new Set()) => {
    const display = String(node?.row?.display_name || node?.row?.username || "-");
    const username = String(node?.row?.username || "-");
    const department = getOrgChartDepartmentName(node?.row);

    if (visited.has(node.key)) {
      return `
        <li class="org-tree-node">
          <article class="org-node-card cycle">
            <div class="org-node-name">${escapeHtml(display)}</div>
            <div class="org-node-meta">ID: ${escapeHtml(username)}</div>
            <div class="org-node-meta">\uBD80\uC11C: ${escapeHtml(department)}</div>
          </article>
        </li>
      `;
    }

    const nextVisited = new Set(visited);
    nextVisited.add(node.key);

    const childNodes = node.children.map((child) => renderNode(child, nextVisited)).filter(Boolean);
    const childrenHtml = childNodes.length ? `<ul class="org-tree-list">${childNodes.join("")}</ul>` : "";

    return `
      <li class="org-tree-node">
        <article class="org-node-card">
          <div class="org-node-name">${escapeHtml(display)}</div>
          <div class="org-node-meta">ID: ${escapeHtml(username)}</div>
          <div class="org-node-meta">\uBD80\uC11C: ${escapeHtml(department)}</div>
        </article>
        ${childrenHtml}
      </li>
    `;
  };

  const byDeptRoots = new Map();
  roots.forEach((root) => {
    const department = getOrgChartDepartmentName(root.row);
    const list = byDeptRoots.get(department) || [];
    list.push(root);
    byDeptRoots.set(department, list);
  });

  const departmentNames = [...byDeptRoots.keys()].sort((a, b) => a.localeCompare(b, "ko"));
  const countSubtree = (node, seen = new Set()) => {
    if (!node || seen.has(node.key)) return 0;
    seen.add(node.key);
    return 1 + node.children.reduce((acc, child) => acc + countSubtree(child, seen), 0);
  };

  const deptHtml = departmentNames
    .map((department) => {
      const deptRoots = byDeptRoots.get(department) || [];
      sortNodes(deptRoots);
      const treeRows = deptRoots.map((node) => renderNode(node)).filter(Boolean);
      const deptCount = deptRoots.reduce((acc, root) => acc + countSubtree(root, new Set()), 0);
      const openAttr = state.orgChartDeptExpanded ? " open" : "";

      return `
        <details class="org-dept-tree"${openAttr}>
          <summary>${escapeHtml(department)} <span>${deptCount}\uBA85</span></summary>
          <div class="org-dept-tree-body">
            <ul class="org-tree-list root">
              ${treeRows.join("")}
            </ul>
          </div>
        </details>
      `;
    })
    .join("");

  orgChartBoard.innerHTML = `
    <div class="org-tree-wrap">
      ${deptHtml}
    </div>
  `;
}

async function loadManagedUsers(role, q = "") {
  const targetRole = role === "admin" ? "admin" : "user";

  if (targetRole === "admin") {
    const params = new URLSearchParams();
    params.set("role", "admin");
    params.set("limit", "500");
    if (q.trim()) params.set("q", q.trim());

    const rows = await api(`/users?${params.toString()}`);
    state.managedAdmins = rows;
    renderUsersTable("admin");
    renderAdminUserDatalist();
    return;
  }

  const params = new URLSearchParams();
  params.set("limit", "5000");
  params.set("include_inactive", "true");
  if (q.trim()) params.set("q", q.trim());

  const rows = await api(`/directory-users?${params.toString()}`);
  state.managedUsers = rows;
  renderUsersTable("user");
  renderUsersTable("user-inactive");
  renderOrgChart(rows);
}

async function loadDirectoryUsers(q = "") {
  const params = new URLSearchParams();
  params.set("limit", "5000");
  if (q.trim()) params.set("q", q.trim());

  state.directoryUsers = await api(`/directory-users?${params.toString()}`);
  renderDirectoryUserDatalist();
  syncDepartmentByOwner("add", { preserveWhenUnknown: true });
  syncDepartmentByOwner("edit", { preserveWhenUnknown: true });
  if (state.assets.length) renderAssetRows();
}


function renderLdapScheduleInfo() {
  if (!ldapScheduleInfo) return;

  const schedule = state.ldapSchedule;
  const lastSynced = schedule.last_synced_at ? new Date(schedule.last_synced_at).toLocaleString() : "없음";
  const runtimePassword = schedule.has_stored_password
    ? "설정됨(서버 암호화 저장)"
    : schedule.has_runtime_password
      ? "설정됨(현재 서버 메모리)"
      : "미설정";
  const lastError = schedule.last_error ? ` / 최근 오류: ${schedule.last_error}` : "";

  ldapScheduleInfo.textContent = `최근 동기화: ${lastSynced} / 스케줄 비밀번호: ${runtimePassword}${lastError}`;
}

async function loadLdapSchedule() {
  if (!state.user || state.user.role !== "admin") return;

  const schedule = await api("/ldap/sync-schedule");
  state.ldapSchedule = {
    ...state.ldapSchedule,
    ...(schedule || {}),
  };

  const scheduleConfigKeys = [
    "server_url",
    "use_ssl",
    "port",
    "bind_dn",
    "base_dn",
    "user_id_attribute",
    "user_name_attribute",
    "user_email_attribute",
    "user_department_attribute",
    "user_title_attribute",
    "manager_dn_attribute",
    "user_dn_attribute",
    "user_guid_attribute",
    "size_limit",
  ];
  const nextConfig = { ...(state.settings.ldapConfig || DEFAULTS.ldapConfig) };
  let configChanged = false;

  scheduleConfigKeys.forEach((key) => {
    if (!(key in state.ldapSchedule)) return;
    const value = state.ldapSchedule[key];
    const normalizedValue = key === "port" ? (value ?? "") : value;
    if (nextConfig[key] !== normalizedValue) {
      nextConfig[key] = normalizedValue;
      configChanged = true;
    }
  });

  if (configChanged) {
    state.settings.ldapConfig = nextConfig;
    persistSettings();
    applyLdapInputs({ resetResults: false });
  }

  document.getElementById("ldapScheduleEnabled").checked = Boolean(state.ldapSchedule.enabled);
  document.getElementById("ldapScheduleInterval").value = state.ldapSchedule.interval_minutes || 60;
  renderLdapScheduleInfo();
}

async function refreshUserDataSources() {
  await loadDirectoryUsers();
  if (isAdminUser()) {
    await Promise.all([loadManagedUsers("user"), loadManagedUsers("admin")]);
  }
}

const publicSettingsTabs = new Set(["hardware", "software"]);
const adminSettingsTabs = new Set(["accounts", "misc"]);

function isAdminUser() {
  return String(state.user?.role || "").trim().toLowerCase() === "admin";
}

function activateSettingsAccountsSubtab(subtabName = "users") {
  let target = String(subtabName || "users");
  const allowed = new Set(["users", "users-inactive", "admins", "orgchart"]);

  if (!allowed.has(target)) {
    target = "users";
  }

  state.settingsAccountsSubtab = target;

  document.querySelectorAll(".subtab-btn[data-settings-accounts-tab]").forEach((button) => {
    const isActive = button.dataset.settingsAccountsTab === target;
    button.classList.toggle("active", isActive);
  });

  document.querySelectorAll(".settings-accounts-subtab-section").forEach((section) => {
    section.classList.toggle("active", section.id === `settings-accounts-subtab-${target}`);
  });
}

function activateSettingsMailSubtab(subtabName = "smtp") {
  const isAdmin = isAdminUser();
  let target = String(subtabName || "smtp");
  const allowed = new Set(["smtp", "admin", "user"]);

  if (!allowed.has(target)) {
    target = "smtp";
  }

  if (!isAdmin) {
    target = "smtp";
  }

  state.settingsMailSubtab = target;

  document.querySelectorAll(".subtab-btn[data-settings-mail-tab]").forEach((button) => {
    const isActive = button.dataset.settingsMailTab === target;
    button.classList.toggle("active", isActive);
  });

  document.querySelectorAll(".settings-mail-subtab-section").forEach((section) => {
    section.classList.toggle("active", section.id === `settings-mail-subtab-${target}`);
  });
}

function activateSettingsMiscSubtab(subtabName = "ldap") {
  const isAdmin = isAdminUser();
  let target = String(subtabName || "ldap");
  const allowed = new Set(["ldap", "mail"]);

  if (!allowed.has(target)) {
    target = "ldap";
  }

  if (!isAdmin) {
    target = "ldap";
  }

  state.settingsMiscSubtab = target;

  document.querySelectorAll(".subtab-btn[data-settings-misc-tab]").forEach((button) => {
    const isActive = button.dataset.settingsMiscTab === target;
    button.classList.toggle("active", isActive);
  });

  document.querySelectorAll(".settings-misc-subtab-section").forEach((section) => {
    section.classList.toggle("active", section.id === `settings-misc-subtab-${target}`);
  });

  if (target === "mail") {
    activateSettingsMailSubtab(state.settingsMailSubtab || "smtp");
  }
}

function activateSettingsSubtab(subtabName = "hardware") {
  const isAdmin = isAdminUser();
  const requested = String(subtabName || "hardware");
  let target = requested;

  if (!publicSettingsTabs.has(target) && !adminSettingsTabs.has(target)) {
    target = "hardware";
  }

  if (!isAdmin && adminSettingsTabs.has(target)) {
    target = "hardware";
  }

  state.settingsSubtab = target;

  document.querySelectorAll(".subtab-btn[data-settings-tab]").forEach((button) => {
    const isActive = button.dataset.settingsTab === target;
    button.classList.toggle("active", isActive);
  });

  document.querySelectorAll(".settings-subtab-section").forEach((section) => {
    section.classList.toggle("active", section.id === `settings-subtab-${target}`);
  });

  if (target === "accounts") {
    activateSettingsAccountsSubtab(state.settingsAccountsSubtab || "users");
  }
  if (target === "misc") {
    activateSettingsMiscSubtab(state.settingsMiscSubtab || "ldap");
  }
}

async function loadSettingsSubtabData(subtabName = "hardware") {
  if (!state.token) return;
  const target = String(subtabName || "hardware");

  if (target === "software") {
    await loadExchangeRateSetting();
    return;
  }

  if (target === "accounts") {
    if (!isAdminUser()) return;
    const accountSubtab = String(state.settingsAccountsSubtab || "users");
    if (accountSubtab === "admins") {
      await loadManagedUsers("admin", document.getElementById("adminSearchQ")?.value || "");
    } else if (accountSubtab === "users-inactive") {
      await loadManagedUsers("user", document.getElementById("inactiveUserSearchQ")?.value || "");
    } else if (accountSubtab === "orgchart") {
      await loadManagedUsers("user", document.getElementById("orgChartSearchQ")?.value || "");
    } else {
      await loadManagedUsers("user", document.getElementById("userSearchQ")?.value || "");
    }
    return;
  }

  if (target === "misc") {
    if (!isAdminUser()) return;
    const miscSubtab = String(state.settingsMiscSubtab || "ldap");
    if (miscSubtab === "mail") {
      await loadMailSettingsAll();
      return;
    }
    await loadLdapSchedule();
  }
}

function applyRoleTabVisibility() {
  const isAdmin = isAdminUser();

  document.querySelectorAll("[data-admin-only]").forEach((el) => {
    el.classList.toggle("hidden", !isAdmin);
  });

  if (!isAdmin && adminSettingsTabs.has(state.settingsSubtab)) {
    state.settingsSubtab = "hardware";
  }

  activateSettingsSubtab(state.settingsSubtab || "hardware");
}

function openOwnerAssignModal() {
  return new Promise((resolve) => {
    if (!ownerAssignModal || !ownerAssignInput) {
      resolve(null);
      return;
    }

    ownerAssignInput.value = "";
    ownerAssignModal.classList.remove("hidden");
    ownerAssignInput.focus();

    const cleanup = () => {
      ownerAssignModal.classList.add("hidden");
      confirmBtn.removeEventListener("click", onConfirm);
      cancelBtn.removeEventListener("click", onCancel);
      ownerAssignModal.removeEventListener("click", onBackdrop);
    };

    const confirmBtn = document.getElementById("ownerAssignConfirmBtn");
    const cancelBtn = document.getElementById("ownerAssignCancelBtn");

    const onConfirm = () => {
      const username = extractLookupUsername(ownerAssignInput.value);
      if (!username || username === "미지정") {
        showToast("사용중 상태는 사용자 지정이 필요합니다.");
        return;
      }
      cleanup();
      resolve(username);
    };

    const onCancel = () => {
      cleanup();
      resolve(null);
    };

    const onBackdrop = (event) => {
      if (event.target !== ownerAssignModal) return;
      onCancel();
    };

    confirmBtn.addEventListener("click", onConfirm);
    cancelBtn.addEventListener("click", onCancel);
    ownerAssignModal.addEventListener("click", onBackdrop);
  });
}

function openLdapPasswordModal() {
  if (!ldapPasswordModal || !ldapSessionPasswordInput) return;
  ldapSessionPasswordInput.value = "";
  ldapPasswordModal.classList.remove("hidden");
  ldapSessionPasswordInput.focus();
}

function closeLdapPasswordModal() {
  if (!ldapPasswordModal) return;
  ldapPasswordModal.classList.add("hidden");
}

function closeUserMailPreviewModal() {
  if (!userMailPreviewModal) return;
  userMailPreviewModal.classList.add("hidden");
}

function renderUserMailPreviewModal(data) {
  if (!userMailPreviewSummary || !userMailPreviewTableBody) return;

  const checkedLicenses = Number(data?.checked_licenses || 0);
  const targetUsers = Number(data?.target_users || 0);
  const sendableUsers = Number(data?.sendable_users || 0);
  const skippedNoEmail = Number(data?.skipped_no_email || 0);
  const skippedInactive = Number(data?.skipped_inactive || 0);
  const expiringCount = Number(data?.expiring_count || 0);
  const expiredCount = Number(data?.expired_count || 0);
  const rows = Array.isArray(data?.rows) ? data.rows : [];

  userMailPreviewSummary.textContent =
    `확인 라이선스 ${checkedLicenses}건 / 대상 ${targetUsers}명 / 발송 가능 ${sendableUsers}명` +
    ` / 이메일 없음 ${skippedNoEmail}명 / 비활성 제외 ${skippedInactive}명` +
    ` / 만료예정 ${expiringCount}건 / 만료 ${expiredCount}건`;

  if (!rows.length) {
    userMailPreviewTableBody.innerHTML = '<tr><td colspan="5">대상자가 없습니다.</td></tr>';
    return;
  }

  userMailPreviewTableBody.innerHTML = rows
    .map((row) => {
      const expiringNames = Array.isArray(row?.expiring_license_names) ? row.expiring_license_names : [];
      const expiredNames = Array.isArray(row?.expired_license_names) ? row.expired_license_names : [];
      const expiringText = expiringNames.length ? expiringNames.map((name) => escapeHtml(name)).join("<br>") : "-";
      const expiredText = expiredNames.length ? expiredNames.map((name) => escapeHtml(name)).join("<br>") : "-";
      return `
        <tr>
          <td>${row?.is_active ? "활성" : "비활성"}</td>
          <td>${escapeHtml(row?.display_name || "-")}</td>
          <td>${escapeHtml(row?.email || "-")}</td>
          <td>${expiringText}</td>
          <td>${expiredText}</td>
        </tr>
      `;
    })
    .join("");
}

function applyLdapSessionPassword() {
  const pwd = String(ldapSessionPasswordInput?.value || "").trim();
  if (!pwd) {
    showToast("Bind 비밀번호를 입력해주세요.");
    return false;
  }
  state.ldapSession.bindPassword = pwd;
  updateLdapPasswordStatus();
  closeLdapPasswordModal();
  return true;
}

async function api(path, options = {}) {
  const customHeaders = { ...(options.headers || {}) };
  const hasContentTypeHeader = Object.keys(customHeaders).some((key) => key.toLowerCase() === "content-type");
  const isFormDataBody = typeof FormData !== "undefined" && options.body instanceof FormData;

  const headers = {
    ...authHeaders(),
    ...customHeaders,
  };

  if (!isFormDataBody && !hasContentTypeHeader) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    let detail = "요청 처리에 실패했습니다";
    try {
      const errorData = await response.json();
      if (errorData.detail) detail = errorData.detail;
    } catch {
      // ignore parse
    }
    throw new Error(detail);
  }

  if (response.status === 204) return null;
  return response.json();
}

function updateAuthView() {
  const loggedIn = Boolean(state.token && state.user);
  loginPanel.classList.toggle("hidden", loggedIn);
  appPanel.classList.toggle("hidden", !loggedIn);

  if (loggedIn) {
    const roleLabel = state.user.role === "admin" ? "관리자" : "사용자";
    userInfo.textContent = `${state.user.username} (${roleLabel})`;
  } else {
    userInfo.textContent = "로그인 필요";
  }
}

const hardwareTabKeys = new Set(["assets", "add", "addcsv", "disposed"]);
const softwareTabKeys = new Set(["list", "assigned", "assignment", "editor", "import"]);
const mainTabKeys = new Set(["dashboard", "hardware", "software", "settings"]);

function setSectionActive(tabName) {
  document.querySelectorAll(".tab-section").forEach((section) => {
    section.classList.toggle("active", section.id === `tab-${tabName}`);
  });
}

function activateHardwareSubtab(subtabName = "assets") {
  const target = hardwareTabKeys.has(subtabName) ? subtabName : "assets";

  state.activeMainTab = "hardware";
  state.hardwareSubtab = target;

  document.querySelectorAll(".tab-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === "hardware");
  });

  hardwareSubtabs?.classList.remove("hidden");
  softwareSubtabs?.classList.add("hidden");

  hardwareSubtabs?.querySelectorAll("[data-hardware-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.hardwareTab === target);
  });

  setSectionActive(target);
}

function activateSoftwareSubtab(subtabName = "list") {
  const target = softwareTabKeys.has(subtabName) ? subtabName : "list";
  const previous = state.softwareSubtab;

  state.activeMainTab = "software";
  state.softwareSubtab = target;

  document.querySelectorAll(".tab-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === "software");
  });

  hardwareSubtabs?.classList.add("hidden");
  softwareSubtabs?.classList.remove("hidden");

  softwareSubtabs?.querySelectorAll("[data-software-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.softwareTab === target);
  });

  setSectionActive("software");

  document.querySelectorAll(".software-subtab-section").forEach((section) => {
    section.classList.toggle("active", section.id === `software-subtab-${target}`);
  });

  if (target === "assignment" && previous !== "assignment") {
    const assignmentSearchField = document.getElementById("softwareAssignSearchField");
    const assignmentSearch = document.getElementById("softwareAssignSearch");
    if (assignmentSearchField) assignmentSearchField.value = "username";
    if (assignmentSearch) assignmentSearch.value = "";
  }
}

function activateTab(tabName) {
  if (hardwareTabKeys.has(tabName)) {
    activateHardwareSubtab(tabName);
    return;
  }

  if (softwareTabKeys.has(tabName)) {
    activateSoftwareSubtab(tabName);
    return;
  }

  const target = mainTabKeys.has(tabName) ? tabName : "dashboard";
  state.activeMainTab = target;

  if (target === "hardware") {
    activateHardwareSubtab(state.hardwareSubtab || "assets");
    return;
  }

  if (target === "software") {
    activateSoftwareSubtab(state.softwareSubtab || "list");
    return;
  }

  document.querySelectorAll(".tab-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === target);
  });

  hardwareSubtabs?.classList.add("hidden");
  softwareSubtabs?.classList.add("hidden");
  setSectionActive(target);
}

function renderSummary(summary) {
  const cards = [
    { title: "전체 자산(통합)", value: summary.total_assets ?? 0, key: "total" },
    { title: "하드웨어", value: summary.total_hardware ?? 0, key: "hardware_total" },
    { title: "소프트웨어", value: summary.total_software ?? 0, key: "software_total" },
    { title: "보증 30일 내 만료", value: summary.expiring_warranty_30d ?? 0, key: "warranty_30d" },
    { title: "보증 만료 지남", value: summary.overdue_warranty ?? 0, key: "warranty_overdue" },
    { title: "대여 만료 7일 내", value: summary.rental_expiring_7d ?? 0, key: "rental_7d" },
    { title: "SW 만료 30일 내", value: summary.software_expiring_30d ?? 0, key: "software_30d" },
    { title: "SW 만료 지남", value: summary.software_expired ?? 0, key: "software_expired" },
  ];

  summaryCards.innerHTML = cards
    .map(
      (item) => `
        <article class="summary-card">
          <div class="summary-title">${escapeHtml(item.title)}</div>
          <button type="button" class="summary-value metric-link" data-dashboard-kind="summary" data-dashboard-value="${escapeHtml(item.key)}">${item.value}</button>
        </article>
      `,
    )
    .join("");

  statusBoard.innerHTML = statusValues
    .map(
      (key) => `
        <div class="k-chip">
          <div class="k">${key}</div>
          <button type="button" class="v metric-link" data-dashboard-kind="status" data-dashboard-value="${escapeHtml(key)}">${summary.status_counts?.[key] ?? 0}</button>
        </div>
      `,
    )
    .join("");

  usageBoard.innerHTML = usageTypeValues
    .map(
      (key) => `
        <div class="k-chip">
          <div class="k">${key}</div>
          <button type="button" class="v metric-link" data-dashboard-kind="usage" data-dashboard-value="${escapeHtml(key)}">${summary.usage_type_counts?.[key] ?? 0}</button>
        </div>
      `,
    )
    .join("");

  const categoryEntries = Object.entries(summary.category_counts || {});
  if (!categoryEntries.length) {
    categoryBoard.innerHTML = '<div class="k-chip"><div class="k">카테고리</div><div class="v">데이터 없음</div></div>';
  } else {
    categoryBoard.innerHTML = categoryEntries
      .map(
        ([key, value]) => `
          <div class="k-chip">
            <div class="k">${escapeHtml(key)}</div>
            <button type="button" class="v metric-link" data-dashboard-kind="category" data-dashboard-value="${escapeHtml(key)}">${value}</button>
          </div>
        `,
      )
      .join("");
  }

  renderSoftwareSummary(summary);
  renderDashboardCostTrend(summary);
  requestAnimationFrame(syncDashboardCardsHeight);
}

function renderSoftwareSummary(summary = state.dashboardSummary || {}) {
  if (!softwareSummaryCards) return;

  const softwareTotalQuantity = (Array.isArray(state.softwareLicensesAll) ? state.softwareLicensesAll : (Array.isArray(state.softwareLicenses) ? state.softwareLicenses : []))
    .reduce((acc, row) => acc + Math.max(0, Number(row?.total_quantity || 0)), 0);

  const cards = [
    { title: "총 보유 수량", value: summary.total_software ?? softwareTotalQuantity },
    { title: "만료 30일 내", value: summary.software_expiring_30d ?? 0 },
    { title: "만료됨", value: summary.software_expired ?? 0 },
  ];

  softwareSummaryCards.innerHTML = cards
    .map(
      (item) => `
        <article class="summary-card">
          <div class="summary-title">${escapeHtml(item.title)}</div>
          <div class="summary-value">${item.value}</div>
        </article>
      `,
    )
    .join("");
}
const dashboardCostPeriodLabels = {
  month: "월 단위 (소프트웨어: 현재 기준 앞뒤 3개월)",
  quarter: "분기 단위 (소프트웨어: 현재 기준 앞뒤 3분기)",
  year: "연 단위 (소프트웨어: 현재 기준 앞뒤 3년)",
};

const dashboardCostScopeLabels = {
  all: "전체 라이선스",
  required: "필수 라이선스",
  general: "일반 라이선스",
};

function toCostNumber(value) {
  const num = Number(value);
  return Number.isFinite(num) && num > 0 ? num : 0;
}

function formatCostDisplay(value) {
  const num = toCostNumber(value);
  return `${Math.round(num).toLocaleString("ko-KR")}원`;
}

function formatCostCompact(value) {
  const num = toCostNumber(value);
  if (num >= 100000000) {
    return `${(num / 100000000).toFixed(1)}억`;
  }
  if (num >= 10000) {
    return `${Math.round(num / 10000).toLocaleString("ko-KR")}만`;
  }
  return `${Math.round(num).toLocaleString("ko-KR")}원`;
}

function normalizeDashboardHardwareHistory(points) {
  if (!Array.isArray(points)) return [];

  return points.map((point) => ({
    key: String(point?.key || ""),
    label: String(point?.label || "-"),
    period_cost: toCostNumber(point?.period_cost),
    cumulative_cost: toCostNumber(point?.cumulative_cost),
  }));
}

function normalizeDashboardSoftwareProjection(points) {
  if (!Array.isArray(points)) return [];

  return points.map((point) => ({
    key: String(point?.key || ""),
    label: String(point?.label || "-"),
    actual_cost: toCostNumber(point?.actual_cost),
    expected_cost: toCostNumber(point?.expected_cost),
    total_cost: toCostNumber(point?.total_cost),
    is_forecast: Boolean(point?.is_forecast),
  }));
}

function buildChartTickIndexes(length) {
  if (length <= 0) return [];
  if (length <= 8) return Array.from({ length }, (_, index) => index);

  const step = length <= 16 ? 2 : length <= 28 ? 3 : Math.ceil(length / 10);
  const result = new Set([0, length - 1]);
  for (let index = 0; index < length; index += step) {
    result.add(index);
  }

  return [...result].sort((a, b) => a - b);
}

function buildLineGeometry(values, options = {}) {
  const normalized = Array.isArray(values) ? values.map((value) => toCostNumber(value)) : [];
  const length = normalized.length;
  const width = Math.max(Number(options.width) || 700, Math.max(length, 1) * 82);
  const height = Number(options.height) || 220;
  const padLeft = Number(options.padLeft) || 42;
  const padRight = Number(options.padRight) || 20;
  const padTop = Number(options.padTop) || 14;
  const padBottom = Number(options.padBottom) || 40;
  const maxValue = Math.max(1, ...normalized);
  const plotWidth = Math.max(1, width - padLeft - padRight);
  const plotHeight = Math.max(1, height - padTop - padBottom);

  const coords = normalized.map((value, index) => {
    const ratio = length <= 1 ? 0.5 : index / (length - 1);
    const x = padLeft + plotWidth * ratio;
    const y = padTop + plotHeight - (value / maxValue) * plotHeight;
    return { x, y, value, index };
  });

  const baselineY = padTop + plotHeight;
  return {
    width,
    height,
    padLeft,
    padRight,
    padTop,
    padBottom,
    maxValue,
    coords,
    baselineY,
  };
}

function buildPathD(points) {
  if (!Array.isArray(points) || points.length === 0) return "";
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
}

let dashboardCostTooltipEl = null;

function ensureDashboardCostTooltip() {
  if (dashboardCostTooltipEl && document.body.contains(dashboardCostTooltipEl)) {
    return dashboardCostTooltipEl;
  }

  const el = document.createElement("div");
  el.className = "cost-point-tooltip hidden";
  document.body.appendChild(el);
  dashboardCostTooltipEl = el;
  return el;
}

function hideDashboardCostTooltip() {
  if (!dashboardCostTooltipEl) return;
  dashboardCostTooltipEl.classList.add("hidden");
}

function showDashboardCostTooltip(text, clientX, clientY) {
  const message = String(text || "").trim();
  if (!message) {
    hideDashboardCostTooltip();
    return;
  }

  const el = ensureDashboardCostTooltip();
  el.textContent = message;
  el.classList.remove("hidden");

  const tooltipWidth = el.offsetWidth || 180;
  const tooltipHeight = el.offsetHeight || 32;

  let left = Number(clientX || 0) + 14;
  let top = Number(clientY || 0) + 14;

  if (left + tooltipWidth > window.innerWidth - 8) {
    left = Math.max(8, window.innerWidth - tooltipWidth - 8);
  }
  if (top + tooltipHeight > window.innerHeight - 8) {
    top = Math.max(8, Number(clientY || 0) - tooltipHeight - 14);
  }

  el.style.left = `${left}px`;
  el.style.top = `${top}px`;
}

function attachDashboardCostPointTooltips() {
  if (!dashboardCostChart) return;

  const dots = dashboardCostChart.querySelectorAll(".cost-line-dot[data-tip]");
  if (!dots.length) {
    hideDashboardCostTooltip();
    return;
  }

  dots.forEach((dot) => {
    const getTip = () => String(dot.getAttribute("data-tip") || "");

    dot.addEventListener("mouseenter", (event) => {
      showDashboardCostTooltip(getTip(), event.clientX, event.clientY);
    });

    dot.addEventListener("mousemove", (event) => {
      showDashboardCostTooltip(getTip(), event.clientX, event.clientY);
    });

    dot.addEventListener("mouseleave", hideDashboardCostTooltip);

    dot.addEventListener("focus", () => {
      const rect = dot.getBoundingClientRect();
      showDashboardCostTooltip(getTip(), rect.left + rect.width / 2, rect.top);
    });

    dot.addEventListener("blur", hideDashboardCostTooltip);
  });
}

function renderHardwareCostLineChart(points) {
  const rows = normalizeDashboardHardwareHistory(points);
  if (!rows.length) {
    return '<p class="cost-line-empty">하드웨어 비용 데이터가 없습니다.</p>';
  }

  const values = rows.map((row) => row.cumulative_cost);
  const geometry = buildLineGeometry(values);
  const pathD = buildPathD(geometry.coords);
  const tickIndexes = buildChartTickIndexes(rows.length);

  const tickLabels = tickIndexes
    .map((index) => {
      const point = geometry.coords[index];
      const label = rows[index]?.label || "";
      return `<text x="${point.x.toFixed(2)}" y="${(geometry.height - 12).toFixed(2)}" text-anchor="middle" class="cost-line-tick">${escapeHtml(label)}</text>`;
    })
    .join("");

  const dots = geometry.coords
    .map((point, index) => {
      const row = rows[index];
      const tip = `${row.label || ""} / 누적 ${formatCostDisplay(row.cumulative_cost)}`;
      return `<circle cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="4.2" class="cost-line-dot hw" data-tip="${escapeHtml(tip)}" tabindex="0"></circle>`;
    })
    .join("");

  const lastValue = rows[rows.length - 1]?.cumulative_cost || 0;

  return `
    <div class="cost-line-panel">
      <div class="cost-line-head">
        <h4>하드웨어 누적 비용</h4>
        <span class="cost-line-caption">과거 ~ 현재</span>
      </div>
      <div class="cost-line-wrap">
        <svg viewBox="0 0 ${geometry.width} ${geometry.height}" class="cost-line-svg" role="img" aria-label="하드웨어 누적 비용 추이">
          <line x1="${geometry.padLeft}" y1="${geometry.baselineY.toFixed(2)}" x2="${(geometry.width - geometry.padRight).toFixed(2)}" y2="${geometry.baselineY.toFixed(2)}" class="cost-line-axis"></line>
          <path d="${pathD}" class="cost-line-path hw"></path>
          ${dots}
          ${tickLabels}
        </svg>
      </div>
      <p class="cost-line-summary">현재 누적 비용: ${escapeHtml(formatCostDisplay(lastValue))}</p>
    </div>
  `;
}

function renderSoftwareCostLineChart(points, scope = "all") {
  const rows = normalizeDashboardSoftwareProjection(points);
  if (!rows.length) {
    return '<p class="cost-line-empty">소프트웨어 비용 데이터가 없습니다.</p>';
  }

  const values = rows.map((row) => row.total_cost);
  const geometry = buildLineGeometry(values);
  const tickIndexes = buildChartTickIndexes(rows.length);
  const firstForecastIndex = rows.findIndex((row) => row.is_forecast);

  const actualPoints = firstForecastIndex >= 0
    ? geometry.coords.slice(0, Math.max(firstForecastIndex, 0) + 1)
    : geometry.coords;

  const forecastPoints = firstForecastIndex > 0
    ? geometry.coords.slice(firstForecastIndex - 1)
    : firstForecastIndex === 0
      ? geometry.coords
      : [];

  const actualPath = buildPathD(actualPoints);
  const forecastPath = buildPathD(forecastPoints);

  const tickLabels = tickIndexes
    .map((index) => {
      const point = geometry.coords[index];
      const label = rows[index]?.label || "";
      return `<text x="${point.x.toFixed(2)}" y="${(geometry.height - 12).toFixed(2)}" text-anchor="middle" class="cost-line-tick">${escapeHtml(label)}</text>`;
    })
    .join("");

  const dots = geometry.coords
    .map((point, index) => {
      const row = rows[index];
      const modeText = row.is_forecast ? "예상" : "실제";
      const tip = `${row.label || ""} / ${formatCostDisplay(row.total_cost)} (${modeText})`;
      const cls = row.is_forecast ? "cost-line-dot forecast" : "cost-line-dot actual";
      return `<circle cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="4.2" class="${cls}" data-tip="${escapeHtml(tip)}" tabindex="0"></circle>`;
    })
    .join("");

  const actualTotal = rows.reduce((sum, row) => sum + row.actual_cost, 0);
  const expectedTotal = rows.reduce((sum, row) => sum + row.expected_cost, 0);
  const scopeLabel = dashboardCostScopeLabels[scope] || dashboardCostScopeLabels.all;

  return `
    <div class="cost-line-panel">
      <div class="cost-line-head">
        <h4>소프트웨어 비용 추이 (꺾은선)</h4>
        <span class="cost-line-caption">현재 기준 앞뒤 3단위 / ${escapeHtml(scopeLabel)}</span>
      </div>
      <div class="cost-line-wrap">
        <svg viewBox="0 0 ${geometry.width} ${geometry.height}" class="cost-line-svg" role="img" aria-label="소프트웨어 과거 및 예상 비용 추이">
          <line x1="${geometry.padLeft}" y1="${geometry.baselineY.toFixed(2)}" x2="${(geometry.width - geometry.padRight).toFixed(2)}" y2="${geometry.baselineY.toFixed(2)}" class="cost-line-axis"></line>
          <path d="${actualPath}" class="cost-line-path sw-actual"></path>
          <path d="${forecastPath}" class="cost-line-path sw-forecast"></path>
          ${dots}
          ${tickLabels}
        </svg>
      </div>
      <p class="cost-line-summary">과거 비용 합계: ${escapeHtml(formatCostDisplay(actualTotal))} / 예상 비용 합계: ${escapeHtml(formatCostDisplay(expectedTotal))}</p>
    </div>
  `;
}

function renderDashboardCostTrend(summary = state.dashboardSummary || {}) {
  if (!dashboardCostChart || !dashboardCostLegend || !dashboardCostPeriodTabs) return;

  const trends = summary.cost_trends || {};
  const validPeriods = ["month", "quarter", "year"];
  let period = String(state.dashboardCostPeriod || "month");
  if (!validPeriods.includes(period)) period = "month";
  state.dashboardCostPeriod = period;

  const validScopes = ["all", "required", "general"];
  let scope = String(state.dashboardCostScope || "all");
  if (!validScopes.includes(scope)) scope = "all";
  state.dashboardCostScope = scope;

  dashboardCostPeriodTabs.querySelectorAll(".period-tab-btn[data-period]").forEach((button) => {
    button.classList.toggle("active", button.dataset.period === period);
  });

  dashboardCostScopeTabs?.querySelectorAll(".period-tab-btn[data-scope]").forEach((button) => {
    button.classList.toggle("active", button.dataset.scope === scope);
  });

  const periodData = trends?.[period] || {};
  const softwareProjectionByScope = periodData.software_projection_by_scope || {};
  const hardwareHistory = normalizeDashboardHardwareHistory(periodData.hardware_history);
  const softwareProjection = normalizeDashboardSoftwareProjection(softwareProjectionByScope?.[scope] || periodData.software_projection);

  if (!hardwareHistory.length && !softwareProjection.length) {
    dashboardCostChart.innerHTML = '<p class="cost-line-empty">표시할 비용 데이터가 없습니다.</p>';
    dashboardCostLegend.innerHTML = "";
    hideDashboardCostTooltip();
    return;
  }

  dashboardCostChart.innerHTML = `
    <div class="cost-line-grid">
      ${renderHardwareCostLineChart(hardwareHistory)}
      ${renderSoftwareCostLineChart(softwareProjection, scope)}
    </div>
  `;

  attachDashboardCostPointTooltips();

  const hwCurrentCumulative = hardwareHistory.length ? hardwareHistory[hardwareHistory.length - 1].cumulative_cost : 0;
  const swPastTotal = softwareProjection.reduce((sum, row) => sum + row.actual_cost, 0);
  const swExpectedTotal = softwareProjection.reduce((sum, row) => sum + row.expected_cost, 0);
  const caption = dashboardCostPeriodLabels[period] || "";
  const scopeLabel = dashboardCostScopeLabels[scope] || dashboardCostScopeLabels.all;
  const usdKrw = getUsdKrwRate();

  dashboardCostLegend.innerHTML = `
    <span class="cost-legend-item">${escapeHtml(caption)}</span>
    <span class="cost-legend-item">집계 기준: ${escapeHtml(scopeLabel)}</span>
    <span class="cost-legend-item"><span class="cost-legend-swatch hw"></span>하드웨어 누적 ${escapeHtml(formatCostDisplay(hwCurrentCumulative))}</span>
    <span class="cost-legend-item"><span class="cost-legend-swatch sw"></span>소프트웨어 과거 ${escapeHtml(formatCostDisplay(swPastTotal))}</span>
    <span class="cost-legend-item"><span class="cost-legend-swatch forecast"></span>소프트웨어 예상 ${escapeHtml(formatCostDisplay(swExpectedTotal))}</span>
    <span class="cost-legend-item">환율 기준: 1$ = ${escapeHtml(Math.round(usdKrw).toLocaleString("ko-KR"))}원</span>
  `;
}

function updateAssetsPagination() {
  assetsPageInfo.textContent = `${state.pagination.page} 페이지`;
  assetsPrevPageBtn.disabled = state.pagination.page <= 1;
  assetsNextPageBtn.disabled = !state.pagination.hasNext;
}

function getCategoryOptionValues(currentValue = "") {
  const values = state.settings.categories.map((item) => item.name);
  if (currentValue && !values.includes(currentValue)) {
    values.push(currentValue);
  }
  return values;
}

function makeCategoryOptions(currentValue = "") {
  return makeOptions(getCategoryOptionValues(currentValue), currentValue);
}

function syncDashboardCardsHeight() {
  const statusCard = statusBoard?.closest(".card");
  const usageCard = usageBoard?.closest(".card");
  if (!statusCard || !usageCard) return;

  statusCard.style.minHeight = "";
  usageCard.style.minHeight = "";

  const maxHeight = Math.max(statusCard.offsetHeight, usageCard.offsetHeight);
  statusCard.style.minHeight = `${maxHeight}px`;
  usageCard.style.minHeight = `${maxHeight}px`;
}

async function applyDashboardDrilldown(filter) {
  const filterQ = document.getElementById("filterQ");
  const filterStatus = document.getElementById("filterStatus");
  const filterUsageType = document.getElementById("filterUsageType");
  const filterCategory = document.getElementById("filterCategory");
  const filterDepartment = document.getElementById("filterDepartment");

  state.dashboardDrilldown = filter.mode || null;

  filterQ.value = "";
  filterDepartment.value = "";
  filterStatus.value = filter.status || "";
  filterUsageType.value = filter.usageType || "";

  const categoryValue = filter.category || "";
  syncFilterCategorySelect(categoryValue);
  filterCategory.value = categoryValue;

  activateTab("assets");
  state.pagination.page = 1;
  await loadAssets(1);
}

async function applySoftwareDrilldown(mode = "") {
  const isAssignedMode = mode === "software_30d" || mode === "software_expired";

  if (isAssignedMode) {
    const assignedFilterExpiring = document.getElementById("softwareAssignedFilterExpiring");
    const assignedFilterQ = document.getElementById("softwareAssignedFilterQ");
    const assignedFilterField = document.getElementById("softwareAssignedFilterField");
    const assignedFilterCategory = document.getElementById("softwareAssignedFilterCategory");

    if (assignedFilterExpiring) {
      assignedFilterExpiring.value = mode === "software_30d" ? "30" : "expired";
    }
    if (assignedFilterQ) assignedFilterQ.value = "";
    if (assignedFilterField) assignedFilterField.value = "all";
    if (assignedFilterCategory) assignedFilterCategory.value = "";

    activateTab("software");
    activateSoftwareSubtab("assigned");
    await loadSoftwareLicenses();
    return;
  }

  const filterField = document.getElementById("softwareFilterField");
  const filterExpiring = document.getElementById("softwareFilterExpiring");
  const filterCategory = document.getElementById("softwareFilterCategory");
  const filterSubscription = document.getElementById("softwareFilterSubscription");

  if (filterField) filterField.value = "all";
  if (filterExpiring) filterExpiring.value = "";
  if (filterCategory) filterCategory.value = "";
  if (filterSubscription) filterSubscription.value = "";

  activateTab("software");
  activateSoftwareSubtab("list");
  await loadSoftwareLicenses();
}
function handleDashboardMetricClick(kind, value) {
  const v = String(value || "");

  if (kind === "summary") {
    if (v === "total" || v === "hardware_total") {
      return applyDashboardDrilldown({ mode: null, status: "", usageType: "", category: "" });
    }
    if (v === "software_total" || v === "software_30d" || v === "software_expired") {
      return applySoftwareDrilldown(v);
    }
    if (v === "warranty_30d") {
      return applyDashboardDrilldown({ mode: "warranty_30d", status: "", usageType: "", category: "" });
    }
    if (v === "warranty_overdue") {
      return applyDashboardDrilldown({ mode: "warranty_overdue", status: "", usageType: "", category: "" });
    }
    if (v === "rental_7d") {
      return applyDashboardDrilldown({ mode: "rental_7d", status: "", usageType: "대여장비", category: "" });
    }
  }

  if (kind === "status") {
    if (v === "폐기완료") {
      state.dashboardDrilldown = null;
      activateTab("disposed");
      return loadDisposedAssets();
    }
    return applyDashboardDrilldown({ mode: null, status: v, usageType: "", category: "" });
  }

  if (kind === "usage") {
    return applyDashboardDrilldown({ mode: null, status: "", usageType: v, category: "" });
  }

  if (kind === "category") {
    return applyDashboardDrilldown({ mode: null, status: "", usageType: "", category: v });
  }

  return Promise.resolve();
}

function toggleRentalFields(prefix, usageTypeValue = null) {
  const usageType = usageTypeValue || document.getElementById(`${prefix}UsageType`)?.value || "";
  const rentalFields = document.getElementById(`${prefix}RentalFields`);
  const rentalStartDate = document.getElementById(`${prefix}RentalStartDate`);
  const rentalEndDate = document.getElementById(`${prefix}RentalEndDate`);

  if (!rentalFields || !rentalStartDate || !rentalEndDate) return;

  const isLoaner = usageType === "대여장비";
  rentalFields.classList.toggle("hidden", !isLoaner);

  if (!isLoaner) {
    rentalStartDate.value = "";
    rentalEndDate.value = "";
  }
}

function renderAssetRows() {
  if (!state.assets.length) {
    assetTableBody.innerHTML = '<tr><td colspan="10">조건에 맞는 자산이 없습니다.</td></tr>';
    return;
  }

  assetTableBody.innerHTML = state.assets
    .map((asset) => {
      const status = asset.status || "대기";
      const usageType = asset.usage_type || "기타장비";
      const ownerId = asset.owner || "미지정";
      const ownerDisplay = getOwnerDisplayName(ownerId);
      const category = asset.category || "";

      return `
      <tr data-id="${asset.id}" data-status="${escapeHtml(status)}" data-owner="${escapeHtml(ownerId)}" data-category="${escapeHtml(category)}">
        <td>${escapeHtml(asset.asset_code || "-")}</td>
        <td>${escapeHtml(asset.name)}</td>
        <td>${escapeHtml(category || "-")}</td>
        <td>${escapeHtml(usageType)}</td>
        <td><span class="status-tag status-${escapeHtml(status)}">${escapeHtml(status)}</span></td>
        <td>${escapeHtml(ownerDisplay)}</td>
        <td>${escapeHtml(asset.department || "-")}</td>
        <td>${escapeHtml(asset.location || "-")}</td>
        <td>
          <div class="inline-edit" data-id="${asset.id}">
            <select class="inline-status" data-id="${asset.id}">${makeOptions(statusValues, status)}</select>
            <select class="inline-usage" data-id="${asset.id}">${makeOptions(usageTypeValues, usageType)}</select>
            <button type="button" class="mini-btn apply-inline-btn" data-id="${asset.id}">반영</button>
          </div>
        </td>
        <td><button type="button" class="mini-btn history-btn" data-id="${asset.id}">이력/수정</button></td>
      </tr>
    `;
    })
    .join("");
}

function renderDisposedRows() {
  if (!disposedTableBody) return;

  if (!state.disposedAssets.length) {
    disposedTableBody.innerHTML = '<tr><td colspan="5">폐기 완료 자산이 없습니다.</td></tr>';
    return;
  }

  disposedTableBody.innerHTML = state.disposedAssets
    .map((asset) => {
      const disposedAt = asset.disposed_at || asset.updated_at;
      return `
        <tr>
          <td>${escapeHtml(asset.asset_code || "-")}</td>
          <td>${escapeHtml(asset.name || "-")}</td>
          <td>${escapeHtml(asset.category || "-")}</td>
          <td>
            <div class="disposed-status-cell">
              <span class="status-tag status-${escapeHtml(asset.status || "폐기완료")}">${escapeHtml(asset.status || "폐기완료")}</span>
              <button type="button" class="mini-btn undispose-btn" data-id="${asset.id}">폐기취소</button>
              <button type="button" class="mini-btn danger delete-disposed-btn" data-id="${asset.id}">삭제</button>
            </div>
          </td>
          <td>${disposedAt ? new Date(disposedAt).toLocaleString() : "-"}</td>
        </tr>
      `;
    })
    .join("");
}

async function loadDisposedAssets() {
  const rows = [];
  const limit = 200;
  let skip = 0;

  for (let i = 0; i < 100; i += 1) {
    const page = await api(`/assets?status=폐기완료&skip=${skip}&limit=${limit}`);
    if (!Array.isArray(page) || page.length === 0) break;

    rows.push(...page);
    if (page.length < limit) break;
    skip += limit;
  }

  state.disposedAssets = rows;
  renderDisposedRows();
}


function getSoftwareRowsForSelection() {
  const rows = Array.isArray(state.softwareLicensesAll) && state.softwareLicensesAll.length
    ? state.softwareLicensesAll
    : state.softwareLicenses;
  return Array.isArray(rows) ? rows : [];
}

function findSoftwareLicenseById(licenseId) {
  const id = Number(licenseId || 0);
  if (!id) return null;
  return getSoftwareRowsForSelection().find((row) => Number(row.id) === id) || null;
}

function makeSoftwareLicenseLookupLabel(row) {
  const id = Number(row?.id || 0);
  const name = String(row?.product_name || `라이선스#${id || ""}`).trim();
  const category = String(row?.license_category || "기타").trim();
  if (!id) return name;
  return `${id} | ${name} (${category})`;
}

function makeSoftwareAssignmentLookupLabel(row) {
  const id = Number(row?.id || 0);
  return String(row?.product_name || `라이선스#${id || ""}`).trim();
}

function getSoftwareAssignees(row) {
  const direct = Array.isArray(row?.assignees)
    ? row.assignees.map((v) => String(v || "").trim()).filter(Boolean)
    : [];
  if (direct.length) return [...new Set(direct)];

  const fromDetails = Array.isArray(row?.assignee_details)
    ? row.assignee_details.map((item) => String(item?.username || "").trim()).filter(Boolean)
    : [];
  return [...new Set(fromDetails)];
}

function getSoftwareAssigneeDetails(row) {
  const defaultPurchaseModel = String(row?.subscription_type || "연 구독").trim() || "연 구독";
  const defaultStartDate = String(row?.start_date || "").trim() || null;
  const defaultEndDate = String(row?.end_date || "").trim() || null;

  const normalized = Array.isArray(row?.assignee_details)
    ? row.assignee_details
      .map((item) => {
        const username = String(item?.username || "").trim();
        if (!username) return null;
        const startDate = String(item?.start_date || "").trim();
        const endDate = String(item?.end_date || "").trim();
        return {
          username,
          start_date: startDate || null,
          end_date: endDate || null,
          purchase_model: String(item?.purchase_model || "").trim() || defaultPurchaseModel,
        };
      })
      .filter(Boolean)
    : [];

  const detailMap = new Map();
  normalized.forEach((item) => {
    if (!detailMap.has(item.username)) detailMap.set(item.username, item);
  });

  return getSoftwareAssignees(row).map((username) => {
    const current = detailMap.get(username);
    if (current) return current;
    return {
      username,
      start_date: defaultStartDate,
      end_date: defaultEndDate,
      purchase_model: defaultPurchaseModel,
    };
  });
}
function getSoftwareAssigneeDetailMap(row) {
  const map = new Map();
  getSoftwareAssigneeDetails(row).forEach((item) => {
    map.set(item.username, { ...item });
  });
  return map;
}

function buildSoftwareAssigneePayload(license, assignees, detailMap) {
  const defaultPurchaseModel = String(license?.subscription_type || "연 구독").trim() || "연 구독";

  return assignees.map((username) => {
    const current = detailMap.get(username) || {};
    const startDate = String(current.start_date || "").trim();
    const endDate = String(current.end_date || "").trim();

    if (startDate && endDate && endDate < startDate) {
      throw new Error("사용자별 만료일은 시작일보다 빠를 수 없습니다.");
    }

    return {
      username,
      start_date: startDate || null,
      end_date: endDate || null,
      purchase_model: String(current.purchase_model || "").trim() || defaultPurchaseModel,
    };
  });
}
function getSoftwareAssignedQuantity(row) {
  return getSoftwareAssignees(row).length;
}

function getSoftwareUnassignedQuantity(row) {
  const total = Math.max(1, Number(row?.total_quantity || 1));
  return Math.max(total - getSoftwareAssignedQuantity(row), 0);
}

function getSoftwareCategoryOptions() {
  const base = normalizeSoftwareMetaList(state.settings.softwareLicenseCategories, DEFAULTS.softwareLicenseCategories);
  const seen = new Set(base.map((value) => value.toLocaleLowerCase()));

  getSoftwareRowsForSelection().forEach((row) => {
    const value = String(row.license_category || "").trim();
    if (!value) return;
    const key = value.toLocaleLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    base.push(value);
  });

  return base;
}

function getSoftwareSubscriptionOptions() {
  const base = [...softwareSubscriptionTypeValues];
  const seen = new Set(base.map((value) => value.toLocaleLowerCase()));

  getSoftwareRowsForSelection().forEach((row) => {
    const value = String(row.subscription_type || "").trim();
    if (!value) return;
    const key = value.toLocaleLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    base.push(value);
  });

  return base;
}

function renderSoftwareMetaTables() {
  if (!softwareCategoryTableBody) return;

  const rows = getSoftwareCategoryOptions();
  softwareCategoryTableBody.innerHTML = rows
    .map(
      (value) => `
        <tr>
          <td>${escapeHtml(value)}</td>
          <td>
            <button type="button" class="mini-btn danger software-meta-remove-btn" data-kind="category" data-value="${escapeHtml(value)}">삭제</button>
          </td>
        </tr>
      `,
    )
    .join("");
}

function syncSoftwareMetaControls() {
  state.settings.softwareLicenseCategories = normalizeSoftwareMetaList(
    state.settings.softwareLicenseCategories,
    DEFAULTS.softwareLicenseCategories,
  );

  const categoryOptions = getSoftwareCategoryOptions();
  const subscriptionOptions = getSoftwareSubscriptionOptions();

  const swCategory = document.getElementById("swCategory");
  if (swCategory) {
    const current = swCategory.value || "기타";
    swCategory.innerHTML = makeOptions(categoryOptions, current);
    if (![...swCategory.options].some((option) => option.value === current)) {
      swCategory.value = categoryOptions[0] || "기타";
    }
  }

  const filterCategory = document.getElementById("softwareFilterCategory");
  if (filterCategory) {
    const current = filterCategory.value || "";
    filterCategory.innerHTML = `<option value="">전체 구분</option>${makeOptions(categoryOptions, current)}`;
    filterCategory.value = current;
  }

  const swSubscriptionType = document.getElementById("swSubscriptionType");
  if (swSubscriptionType) {
    const current = swSubscriptionType.value || "연 구독";
    swSubscriptionType.innerHTML = makeOptions(subscriptionOptions, current);
    if (![...swSubscriptionType.options].some((option) => option.value === current)) {
      swSubscriptionType.value = subscriptionOptions[0] || "연 구독";
    }
  }

  const filterSubscription = document.getElementById("softwareFilterSubscription");
  if (filterSubscription) {
    const current = filterSubscription.value || "";
    filterSubscription.innerHTML = `<option value="">전체 구독 형태</option>${makeOptions(subscriptionOptions, current)}`;
    filterSubscription.value = current;
  }

  renderSoftwareMetaTables();
}

function renderSoftwareEditTargetOptions(selectedId = "") {
  const select = document.getElementById("swEditTarget");
  if (!select) return;

  const current = String(selectedId || select.value || "");
  const options = getSoftwareRowsForSelection()
    .map((row) => `<option value="${row.id}">${escapeHtml(makeSoftwareLicenseLookupLabel(row))}</option>`)
    .join("");

  select.innerHTML = `<option value="">신규 라이선스 등록</option>${options}`;
  select.value = current;
}

function setSoftwareAssignmentLicenseById(licenseId, syncInput = true) {
  const id = Number(licenseId || 0);
  const hidden = document.getElementById("softwareAssignLicenseId");
  const input = document.getElementById("softwareAssignLicenseInput");
  if (hidden) hidden.value = id > 0 ? String(id) : "";

  if (!syncInput || !input) return;
  if (!id) {
    input.value = "";
    return;
  }

  const row = findSoftwareLicenseById(id);
  input.value = row ? makeSoftwareAssignmentLookupLabel(row) : String(id);
}

function resolveSoftwareAssignmentLicenseIdFromInput(rawValue, preferFirstMatch = false) {
  const text = String(rawValue || "").trim();
  if (!text) return 0;

  const byPrefix = text.match(/^(\d+)\s*\|/);
  if (byPrefix) {
    return Number(byPrefix[1]);
  }

  const rows = getSoftwareRowsForSelection();
  const exact = rows.find((row) => makeSoftwareAssignmentLookupLabel(row) === text || makeSoftwareLicenseLookupLabel(row) === text);
  if (exact) return Number(exact.id || 0);

  if (!preferFirstMatch) return 0;

  const q = text.toLocaleLowerCase();
  const found = rows.find((row) => {
    const name = String(row.product_name || "").toLocaleLowerCase();
    const category = String(row.license_category || "").toLocaleLowerCase();
    return name.includes(q) || category.includes(q) || makeSoftwareAssignmentLookupLabel(row).toLocaleLowerCase().includes(q) || makeSoftwareLicenseLookupLabel(row).toLocaleLowerCase().includes(q);
  });
  return Number(found?.id || 0);
}

function renderSoftwareAssignmentLicenseOptions(selectedId = "") {
  if (softwareLicenseDatalist) {
    softwareLicenseDatalist.innerHTML = getSoftwareRowsForSelection()
      .map((row) => `<option value="${escapeHtml(makeSoftwareAssignmentLookupLabel(row))}"></option>`)
      .join("");
  }

  const id = Number(selectedId || document.getElementById("softwareAssignLicenseId")?.value || 0);
  setSoftwareAssignmentLicenseById(id, true);
}

function readSoftwareFormPayload() {
  const productName = document.getElementById("swProductName")?.value.trim() || "";
  if (!productName) {
    throw new Error("라이선스명을 입력해주세요.");
  }

  const totalQuantity = Number(document.getElementById("swTotalQuantity")?.value || 1);
  if (!Number.isFinite(totalQuantity) || totalQuantity < 1) {
    throw new Error("총 수량은 1 이상이어야 합니다.");
  }

  const startDate = document.getElementById("swStartDate")?.value || null;
  const endDate = document.getElementById("swEndDate")?.value || null;
  if (startDate && endDate && endDate < startDate) {
    throw new Error("만료일은 시작일보다 빠를 수 없습니다.");
  }

  const purchaseCostRaw = document.getElementById("swPurchaseCost")?.value;
  const purchaseCost = purchaseCostRaw === "" || purchaseCostRaw === null || purchaseCostRaw === undefined
    ? null
    : Number(purchaseCostRaw);
  if (purchaseCost !== null && (!Number.isFinite(purchaseCost) || purchaseCost < 0)) {
    throw new Error("구매 비용은 0 이상이어야 합니다.");
  }

  const currentId = Number(document.getElementById("swId")?.value || 0);
  const assignedCount = getSoftwareAssignedQuantity(findSoftwareLicenseById(currentId));
  if (Math.floor(totalQuantity) < assignedCount) {
    throw new Error(`현재 할당(${assignedCount})보다 총 수량을 작게 설정할 수 없습니다.`);
  }

  return {
    product_name: productName,
    license_category: document.getElementById("swCategory")?.value || "기타",
    license_scope: document.getElementById("swLicenseScope")?.value || "일반",
    subscription_type: document.getElementById("swSubscriptionType")?.value || "연 구독",
    total_quantity: Math.floor(totalQuantity),
    start_date: startDate,
    end_date: endDate,
    purchase_cost: purchaseCost,
    purchase_currency: document.getElementById("swPurchaseCurrency")?.value || "원",
    drafter: extractLookupUsername(document.getElementById("swDrafter")?.value || "") || null,
    notes: document.getElementById("swNotes")?.value.trim() || null,
  };
}

function updateSoftwareQuantityFields(assignedCount = null) {
  const total = Math.max(1, Number(document.getElementById("swTotalQuantity")?.value || 1));
  const currentId = Number(document.getElementById("swId")?.value || 0);
  const fallbackAssigned = getSoftwareAssignedQuantity(findSoftwareLicenseById(currentId));
  const assigned = Math.max(0, Number.isFinite(Number(assignedCount)) ? Number(assignedCount) : fallbackAssigned);
  const unassigned = Math.max(total - assigned, 0);

  const assignedInput = document.getElementById("swAssignedQuantity");
  const unassignedInput = document.getElementById("swUnassignedQuantity");
  if (assignedInput) assignedInput.value = String(assigned);
  if (unassignedInput) unassignedInput.value = String(unassigned);
}

function resetSoftwareForm() {
  const form = document.getElementById("softwareForm");
  if (!form) return;

  form.reset();
  document.getElementById("swId").value = "";
  const swEditTarget = document.getElementById("swEditTarget");
  if (swEditTarget) swEditTarget.value = "";

  syncSoftwareMetaControls();
  document.getElementById("swTotalQuantity").value = "1";
  document.getElementById("swPurchaseCurrency").value = "원";
  document.getElementById("swLicenseScope").value = "일반";
  updateSoftwareQuantityFields(0);

  const saveBtn = document.getElementById("saveSoftwareBtn");
  if (saveBtn) saveBtn.textContent = "라이선스 저장";
}

function fillSoftwareForm(row) {
  document.getElementById("swId").value = String(row.id || "");
  const swEditTarget = document.getElementById("swEditTarget");
  if (swEditTarget) swEditTarget.value = String(row.id || "");

  document.getElementById("swProductName").value = row.product_name || "";

  syncSoftwareMetaControls();
  document.getElementById("swCategory").value = row.license_category || "기타";
  document.getElementById("swLicenseScope").value = normalizeSoftwareLicenseScope(row.license_scope);
  document.getElementById("swSubscriptionType").value = row.subscription_type || "연 구독";

  document.getElementById("swTotalQuantity").value = String(row.total_quantity || 1);
  document.getElementById("swStartDate").value = row.start_date || "";
  document.getElementById("swEndDate").value = row.end_date || "";
  document.getElementById("swPurchaseCost").value = row.purchase_cost ?? "";
  document.getElementById("swPurchaseCurrency").value = row.purchase_currency || "원";

  const drafter = String(row.drafter || "").trim();
  const drafterUser = findDirectoryUserByUsername(drafter);
  document.getElementById("swDrafter").value = drafterUser
    ? toLookupDisplay(drafter, drafterUser.display_name || "")
    : drafter;
  document.getElementById("swNotes").value = row.notes || "";

  updateSoftwareQuantityFields(getSoftwareAssignedQuantity(row));

  const saveBtn = document.getElementById("saveSoftwareBtn");
  if (saveBtn) saveBtn.textContent = "라이선스 수정 저장";
}

function renderSoftwareRows() {
  if (!softwareTableBody) return;

  if (!state.softwareLicenses.length) {
    softwareTableBody.innerHTML = '<tr><td colspan="13">등록된 라이선스가 없습니다.</td></tr>';
    return;
  }

  const today = new Date();
  const todayKey = new Date(today.getFullYear(), today.getMonth(), today.getDate()).toISOString().slice(0, 10);

  softwareTableBody.innerHTML = state.softwareLicenses
    .map((row) => {
      const totalQty = Math.max(1, Number(row.total_quantity || 1));
      const assignedQty = getSoftwareAssignedQuantity(row);
      const unassignedQty = Math.max(totalQty - assignedQty, 0);
      const endDate = row.end_date || "";
      const expired = Boolean(endDate && endDate < todayKey);
      const endDateText = `${escapeHtml(endDate || "-")} <span class="muted">(${expired ? "만료" : "사용중"})</span>`;
      const costNumber = Number(row.purchase_cost);
      const convertedCost = toKrwByCurrency(costNumber, row.purchase_currency);
      const isDollar = isUsdCurrency(row.purchase_currency);
      const costText = Number.isFinite(convertedCost) ? formatWon(convertedCost) : "-";
      const sourceCostText = Number.isFinite(costNumber)
        ? (isDollar ? `${costNumber.toLocaleString("en-US")} USD` : `${costNumber.toLocaleString("ko-KR")} KRW`)
        : "-";
      const currencyText = isDollar
        ? `달러(환산 1$=${Math.round(getUsdKrwRate()).toLocaleString("ko-KR")}원)`
        : "원";
      const drafterDisplay = row.drafter ? getOwnerDisplayName(row.drafter) : "-";

      return `
        <tr data-license-id="${row.id}">
          <td>${escapeHtml(row.product_name || "-")}</td>
          <td>${escapeHtml(row.license_category || "기타")}</td>
          <td>${escapeHtml(row.subscription_type || "연 구독")}</td>
          <td>${escapeHtml(normalizeSoftwareLicenseScope(row.license_scope))}</td>
          <td>${escapeHtml(row.start_date || "-")}</td>
          <td>${endDateText}</td>
          <td>${escapeHtml(costText)}<br><span class="muted">입력값: ${escapeHtml(sourceCostText)}</span></td>
          <td>${escapeHtml(currencyText)}</td>
          <td>${totalQty}</td>
          <td>${assignedQty}</td>
          <td>${unassignedQty}</td>
          <td>${escapeHtml(drafterDisplay)}</td>
          <td>
            <button type="button" class="mini-btn software-edit-btn" data-id="${row.id}">수정</button>
            <button type="button" class="mini-btn danger software-delete-btn" data-id="${row.id}">삭제</button>
          </td>
        </tr>
      `;
    })
    .join("");
}

function normalizeSearchValue(value) {
  return String(value ?? "").trim().toLocaleLowerCase();
}

function getSoftwareLicenseSearchValues(row, field = "all") {
  const drafterId = String(row?.drafter || "").trim();
  const drafterName = drafterId ? getOwnerDisplayName(drafterId) : "";

  const map = {
    product_name: [row?.product_name],
    license_category: [row?.license_category],
    subscription_type: [row?.subscription_type],
    license_scope: [row?.license_scope],
    drafter: [drafterId, drafterName],
    all: [row?.product_name, row?.license_category, row?.subscription_type, row?.license_scope, drafterId, drafterName],
  };

  return (map[field] || map.all)
    .map((value) => normalizeSearchValue(value))
    .filter(Boolean);
}

function matchesSoftwareLicenseSearch(row, field, queryLower) {
  const needle = normalizeSearchValue(queryLower);
  if (!needle) return true;
  return getSoftwareLicenseSearchValues(row, field).some((value) => value.includes(needle));
}

function getSoftwareAssignedSearchValues(row, field = "all") {
  const map = {
    username: [row?.username],
    display_name: [row?.display_name],
    department: [row?.department],
    license_name: [row?.license_name],
    category: [row?.category],
    purchase_model: [row?.purchase_model],
    all: [row?.username, row?.display_name, row?.department, row?.license_name, row?.category, row?.purchase_model],
  };

  return (map[field] || map.all)
    .map((value) => normalizeSearchValue(value))
    .filter(Boolean);
}

function matchesSoftwareAssignedSearch(row, field, queryLower) {
  const needle = normalizeSearchValue(queryLower);
  if (!needle) return true;
  return getSoftwareAssignedSearchValues(row, field).some((value) => value.includes(needle));
}

function compareSoftwareAssignedRows(a, b, sortKey = "expiry_key") {
  const textCompare = (va, vb) => String(va || "").localeCompare(String(vb || ""), "ko");

  if (sortKey === "expiry_key") {
    const rank = { expired: 0, soon: 1, active: 2, unknown: 3 };
    const ra = rank[String(a.expiry_key || "unknown")] ?? 99;
    const rb = rank[String(b.expiry_key || "unknown")] ?? 99;
    if (ra !== rb) return ra - rb;
    return textCompare(a.end_date || "9999-12-31", b.end_date || "9999-12-31");
  }

  if (sortKey === "start_date" || sortKey === "end_date") {
    const da = String(a[sortKey] || "9999-12-31");
    const db = String(b[sortKey] || "9999-12-31");
    if (da !== db) return da.localeCompare(db);
    return textCompare(a.display_name, b.display_name);
  }

  const primary = textCompare(a[sortKey], b[sortKey]);
  if (primary !== 0) return primary;

  const secondary = textCompare(a.license_name, b.license_name);
  if (secondary !== 0) return secondary;

  return textCompare(a.display_name, b.display_name);
}

function sortSoftwareAssignedRows(rows) {
  const sort = state.softwareAssignedSort || { key: "expiry_key", direction: "asc" };
  const direction = sort.direction === "desc" ? -1 : 1;

  return [...rows].sort((a, b) => compareSoftwareAssignedRows(a, b, sort.key) * direction);
}

function updateSoftwareAssignedSortButtons() {
  const buttons = document.querySelectorAll("#softwareAssignedTable .table-sort-btn[data-sort-key]");
  if (!buttons.length) return;

  const sort = state.softwareAssignedSort || { key: "expiry_key", direction: "asc" };

  buttons.forEach((button) => {
    const key = String(button.dataset.sortKey || "");
    const baseLabel = button.dataset.baseLabel || button.textContent.trim();
    button.dataset.baseLabel = baseLabel;

    const active = key === sort.key;
    button.classList.toggle("sorted", active);
    button.dataset.direction = active ? sort.direction : "";
    button.textContent = active ? `${baseLabel} ${sort.direction === "asc" ? "▲" : "▼"}` : baseLabel;
  });
}

function toggleSoftwareAssignedSort(sortKey) {
  const key = String(sortKey || "").trim();
  if (!key) return;

  const current = state.softwareAssignedSort || { key: "expiry_key", direction: "asc" };
  if (current.key === key) {
    current.direction = current.direction === "asc" ? "desc" : "asc";
  } else {
    current.key = key;
    current.direction = "asc";
  }

  state.softwareAssignedSort = current;
}
function getDayDiffFromToday(dateText) {
  const text = String(dateText || "").trim();
  if (!text) return null;

  const target = new Date(`${text}T00:00:00`);
  if (Number.isNaN(target.getTime())) return null;

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.floor((target.getTime() - today.getTime()) / 86400000);
}

function getSoftwareAssignedOverviewRows() {
  const licenses = getSoftwareRowsForSelection();
  const rows = [];

  licenses.forEach((license) => {
    const details = getSoftwareAssigneeDetails(license);
    details.forEach((detail) => {
      const username = String(detail?.username || "").trim();
      if (!username) return;

      const user = findDirectoryUserByUsername(username);
      const displayName = String(user?.display_name || "").trim() || username;
      const department = String(user?.department || "").trim() || "-";
      const licenseName = String(license?.product_name || `라이선스 #${license?.id || ""}`).trim();
      const category = String(license?.license_category || "기타").trim() || "기타";
      const purchaseModel = String(detail?.purchase_model || license?.subscription_type || "-").trim() || "-";
      const startDate = String(detail?.start_date || license?.start_date || "").trim() || null;
      const endDate = String(detail?.end_date || license?.end_date || "").trim() || null;
      const dayDiff = getDayDiffFromToday(endDate);

      let expiryKey = "unknown";
      let expiryText = "만료일 미지정";

      if (dayDiff !== null) {
        if (dayDiff < 0) {
          expiryKey = "expired";
          expiryText = `만료 (${Math.abs(dayDiff)}일 경과)`;
        } else if (dayDiff <= 30) {
          expiryKey = "soon";
          expiryText = `${dayDiff}일 후 만료`;
        } else {
          expiryKey = "active";
          expiryText = `${dayDiff}일 남음`;
        }
      }

      rows.push({
        license_id: Number(license?.id || 0),
        license_name: licenseName,
        category,
        username,
        display_name: displayName,
        department,
        purchase_model: purchaseModel,
        start_date: startDate,
        end_date: endDate,
        expiry_key: expiryKey,
        expiry_text: expiryText,
      });
    });
  });

  const rank = { expired: 0, soon: 1, active: 2, unknown: 3 };
  rows.sort((a, b) => {
    const ra = rank[a.expiry_key] ?? 99;
    const rb = rank[b.expiry_key] ?? 99;
    if (ra !== rb) return ra - rb;

    const ad = a.end_date || "9999-12-31";
    const bd = b.end_date || "9999-12-31";
    if (ad !== bd) return ad.localeCompare(bd);

    if (a.license_name !== b.license_name) return a.license_name.localeCompare(b.license_name, "ko");
    return a.display_name.localeCompare(b.display_name, "ko");
  });

  return rows;
}

function syncSoftwareAssignedFilterOptions() {
  const categorySelect = document.getElementById("softwareAssignedFilterCategory");
  if (!categorySelect) return;

  const current = String(categorySelect.value || "").trim();
  categorySelect.innerHTML = `<option value="">전체 구분</option>${makeOptions(getSoftwareCategoryOptions(), current)}`;
  categorySelect.value = current;
}

function renderSoftwareAssignedRows() {
  if (!softwareAssignedTableBody) return;

  const query = String(document.getElementById("softwareAssignedFilterQ")?.value || "").trim().toLocaleLowerCase();
  const searchField = String(document.getElementById("softwareAssignedFilterField")?.value || "all").trim();
  const expiringFilter = String(document.getElementById("softwareAssignedFilterExpiring")?.value || "").trim();
  const categoryFilter = String(document.getElementById("softwareAssignedFilterCategory")?.value || "").trim();

  let rows = getSoftwareAssignedOverviewRows();

  if (query) {
    rows = rows.filter((row) => matchesSoftwareAssignedSearch(row, searchField, query));
  }

  if (categoryFilter) {
    rows = rows.filter((row) => String(row.category || "") === categoryFilter);
  }

  if (expiringFilter === "30") {
    rows = rows.filter((row) => row.expiry_key === "soon");
  } else if (expiringFilter === "expired") {
    rows = rows.filter((row) => row.expiry_key === "expired");
  }

  rows = sortSoftwareAssignedRows(rows);
  updateSoftwareAssignedSortButtons();

  if (!rows.length) {
    softwareAssignedTableBody.innerHTML = '<tr><td colspan="9">조건에 맞는 할당 데이터가 없습니다.</td></tr>';
    return;
  }

  softwareAssignedTableBody.innerHTML = rows
    .map((row) => {
      return `
        <tr data-license-id="${row.license_id}">
          <td>${escapeHtml(row.username)}</td>
          <td>${escapeHtml(row.display_name)}</td>
          <td>${escapeHtml(row.department)}</td>
          <td>${escapeHtml(row.license_name)}</td>
          <td>${escapeHtml(row.category)}</td>
          <td>${escapeHtml(row.purchase_model)}</td>
          <td>${escapeHtml(row.start_date || "-")}</td>
          <td>${escapeHtml(row.end_date || "-")}</td>
          <td><span class="software-expiry-status ${escapeHtml(row.expiry_key)}">${escapeHtml(row.expiry_text)}</span></td>
        </tr>
      `;
    })
    .join("");
}
function buildSoftwareQueryParams() {
  const params = new URLSearchParams();

  const expiring = document.getElementById("softwareFilterExpiring")?.value || "";
  if (expiring === "30") {
    params.set("expiring_days", "30");
  } else if (expiring === "expired") {
    params.set("expired_only", "true");
  }

  params.set("skip", "0");
  params.set("limit", "1000");
  return params;
}

function renderSoftwareAssignmentPanel() {
  if (!softwareAssignUserTableBody) return;

  const input = document.getElementById("softwareAssignLicenseInput");
  const summary = document.getElementById("softwareAssignSummary");
  const query = String(document.getElementById("softwareAssignSearch")?.value || "").trim().toLocaleLowerCase();
  const searchField = String(document.getElementById("softwareAssignSearchField")?.value || "username").trim();

  const selectedId = Number(document.getElementById("softwareAssignLicenseId")?.value || 0)
    || resolveSoftwareAssignmentLicenseIdFromInput(input?.value || "", false);
  if (selectedId) setSoftwareAssignmentLicenseById(selectedId, true);

  const license = findSoftwareLicenseById(selectedId);
  if (!license) {
    softwareAssignUserTableBody.innerHTML = '<tr><td colspan="8">라이선스를 선택해주세요.</td></tr>';
    if (summary) summary.textContent = "라이선스를 선택하면 사용자 할당 상태를 관리할 수 있습니다.";
    return;
  }

  const assignees = getSoftwareAssignees(license);
  const assignedSet = new Set(assignees);
  const assigneeDetailMap = getSoftwareAssigneeDetailMap(license);
  const totalQuantity = Math.max(1, Number(license.total_quantity || 1));
  const unassignedQuantity = Math.max(totalQuantity - assignees.length, 0);
  const purchaseOptions = getSoftwareSubscriptionOptions();

  if (summary) {
    summary.textContent = `${license.product_name || `라이선스 #${license.id}`} - 할당 ${assignees.length}/${totalQuantity} (미할당 ${unassignedQuantity})`;
  }

  let users = Array.isArray(state.directoryUsers) ? [...state.directoryUsers] : [];
  if (query) {
    users = users.filter((user) => {
      const username = String(user.username || "").toLocaleLowerCase();
      const displayName = String(user.display_name || "").toLocaleLowerCase();
      const department = String(user.department || "").toLocaleLowerCase();
      const fieldMap = {
        username,
        display_name: displayName,
        department,
      };
      const target = fieldMap[searchField] ?? username;
      return target.includes(query);
    });
  }

  users.sort((a, b) => {
    const aAssigned = assignedSet.has(String(a.username || "").trim()) ? 0 : 1;
    const bAssigned = assignedSet.has(String(b.username || "").trim()) ? 0 : 1;
    if (aAssigned !== bAssigned) return aAssigned - bAssigned;

    const aLabel = String(a.display_name || a.username || "");
    const bLabel = String(b.display_name || b.username || "");
    return aLabel.localeCompare(bLabel, "ko");
  });

  if (!users.length) {
    softwareAssignUserTableBody.innerHTML = '<tr><td colspan="8">검색 조건에 맞는 사용자가 없습니다.</td></tr>';
    return;
  }

  softwareAssignUserTableBody.innerHTML = users
    .map((user) => {
      const username = String(user.username || "").trim();
      const isAssigned = assignedSet.has(username);
      const atCapacity = assignees.length >= totalQuantity;
      const canAssign = !isAssigned && !atCapacity;
      const defaultPurchaseModel = String(license.subscription_type || "연 구독").trim() || "연 구독";
      const defaultStartDate = String(license.start_date || "").trim() || null;
      const defaultEndDate = String(license.end_date || "").trim() || null;
      const detail = assigneeDetailMap.get(username) || {
        username,
        start_date: defaultStartDate,
        end_date: defaultEndDate,
        purchase_model: defaultPurchaseModel,
      };

      const actionCell = isAssigned
        ? `
            <div class="software-assignment-actions">
              <button
                type="button"
                class="mini-btn software-assignment-save-btn"
                data-license-id="${license.id}"
                data-username="${escapeHtml(username)}"
              >
                저장
              </button>
              <button
                type="button"
                class="mini-btn danger software-assignment-action-btn"
                data-license-id="${license.id}"
                data-username="${escapeHtml(username)}"
                data-action="remove"
              >
                할당 해제
              </button>
            </div>
          `
        : `
            <button
              type="button"
              class="mini-btn software-assignment-action-btn"
              data-license-id="${license.id}"
              data-username="${escapeHtml(username)}"
              data-action="assign"
              ${canAssign ? "" : "disabled"}
            >
              ${canAssign ? "할당" : "수량초과"}
            </button>
          `;

      return `
        <tr>
          <td>${escapeHtml(username || "-")}</td>
          <td>${escapeHtml(user.display_name || "-")}</td>
          <td>${escapeHtml(user.department || "-")}</td>
          <td>
            ${isAssigned
    ? `<input type="date" class="software-assignee-date software-assignee-start" value="${escapeHtml(detail.start_date || "")}" />`
    : '<span class="muted">-</span>'}
          </td>
          <td>
            ${isAssigned
    ? `<input type="date" class="software-assignee-date software-assignee-end" value="${escapeHtml(detail.end_date || "")}" />`
    : '<span class="muted">-</span>'}
          </td>
          <td>
            ${isAssigned
    ? `<select class="software-assignee-purchase">${makeOptions(purchaseOptions, detail.purchase_model || defaultPurchaseModel)}</select>`
    : '<span class="muted">-</span>'}
          </td>
          <td><span class="software-assign-status ${isAssigned ? "" : "off"}">${isAssigned ? "할당됨" : "미할당"}</span></td>
          <td>${actionCell}</td>
        </tr>
      `;
    })
    .join("");
}

async function toggleSoftwareAssignment(licenseId, username, action) {
  const license = findSoftwareLicenseById(licenseId);
  if (!license) throw new Error("라이선스를 찾을 수 없습니다.");

  const userKey = String(username || "").trim();
  if (!userKey) throw new Error("사용자 정보가 올바르지 않습니다.");

  const assignees = getSoftwareAssignees(license);
  const detailMap = getSoftwareAssigneeDetailMap(license);
  const totalQuantity = Math.max(1, Number(license.total_quantity || 1));
  const defaultPurchaseModel = String(license.subscription_type || "연 구독").trim() || "연 구독";
  let next = [...assignees];

  if (action === "assign") {
    if (next.includes(userKey)) return;
    if (next.length >= totalQuantity) {
      throw new Error("총 수량을 초과하여 할당할 수 없습니다.");
    }
    next.push(userKey);
    if (!detailMap.has(userKey)) {
      detailMap.set(userKey, {
        username: userKey,
        start_date: license.start_date || null,
        end_date: license.end_date || null,
        purchase_model: defaultPurchaseModel,
      });
    }
  } else {
    next = next.filter((value) => value !== userKey);
    detailMap.delete(userKey);
  }

  const nextDetails = buildSoftwareAssigneePayload(license, next, detailMap);

  await api(`/software-licenses/${license.id}`, {
    method: "PUT",
    body: JSON.stringify({ assignees: next, assignee_details: nextDetails }),
  });

  await Promise.all([loadSoftwareLicenses(), loadDashboard()]);
}
async function saveSoftwareAssigneeDetail(licenseId, username, rowElement) {
  const license = findSoftwareLicenseById(licenseId);
  if (!license) throw new Error("라이선스를 찾을 수 없습니다.");

  const userKey = String(username || "").trim();
  if (!userKey) throw new Error("사용자 정보가 올바르지 않습니다.");

  const assignees = getSoftwareAssignees(license);
  if (!assignees.includes(userKey)) {
    throw new Error("할당된 사용자만 수정할 수 있습니다.");
  }

  const startDate = rowElement?.querySelector(".software-assignee-start")?.value || null;
  const endDate = rowElement?.querySelector(".software-assignee-end")?.value || null;
  const purchaseModel = rowElement?.querySelector(".software-assignee-purchase")?.value || license.subscription_type || "연 구독";

  if (startDate && endDate && endDate < startDate) {
    throw new Error("사용자별 만료일은 시작일보다 빠를 수 없습니다.");
  }

  const detailMap = getSoftwareAssigneeDetailMap(license);
  detailMap.set(userKey, {
    username: userKey,
    start_date: startDate,
    end_date: endDate,
    purchase_model: purchaseModel,
  });

  const nextDetails = buildSoftwareAssigneePayload(license, assignees, detailMap);

  await api(`/software-licenses/${license.id}`, {
    method: "PUT",
    body: JSON.stringify({ assignees, assignee_details: nextDetails }),
  });

  await Promise.all([loadSoftwareLicenses(), loadDashboard()]);
}
function openSoftwareAssignmentForLicense(licenseId) {
  const id = Number(licenseId || 0);
  if (!id) return;

  activateTab("software");
  activateSoftwareSubtab("assignment");
  setSoftwareAssignmentLicenseById(id, true);
  renderSoftwareAssignmentLicenseOptions(id);
  renderSoftwareAssignmentPanel();
}

async function loadSoftwareLicenses() {
  if (!state.token) return;

  const prevEditId = document.getElementById("swEditTarget")?.value || "";
  const prevAssignId = Number(document.getElementById("softwareAssignLicenseId")?.value || 0)
    || resolveSoftwareAssignmentLicenseIdFromInput(document.getElementById("softwareAssignLicenseInput")?.value || "", false);

  const params = buildSoftwareQueryParams();
  const rows = await api(`/software-licenses?${params.toString()}`);
  let filtered = Array.isArray(rows) ? rows : [];

  const searchField = String(document.getElementById("softwareFilterField")?.value || "all").trim();
  const searchQuery = String(document.getElementById("softwareFilterQ")?.value || "").trim().toLocaleLowerCase();
  if (searchQuery) {
    filtered = filtered.filter((row) => matchesSoftwareLicenseSearch(row, searchField, searchQuery));
  }

  const categoryFilter = String(document.getElementById("softwareFilterCategory")?.value || "").trim();
  if (categoryFilter) {
    filtered = filtered.filter((row) => String(row.license_category || "").trim() === categoryFilter);
  }

  const subscriptionFilter = String(document.getElementById("softwareFilterSubscription")?.value || "").trim();
  if (subscriptionFilter) {
    filtered = filtered.filter((row) => String(row.subscription_type || "").trim() === subscriptionFilter);
  }

  state.softwareLicenses = filtered;

  const allRows = await api("/software-licenses?skip=0&limit=1000");
  state.softwareLicensesAll = Array.isArray(allRows) ? allRows : [];

  renderSoftwareRows();
  renderSoftwareSummary();
  syncSoftwareMetaControls();
  syncSoftwareAssignedFilterOptions();
  renderSoftwareAssignedRows();
  renderSoftwareEditTargetOptions(prevEditId);
  renderSoftwareAssignmentLicenseOptions(prevAssignId);
  renderSoftwareAssignmentPanel();
  updateSoftwareQuantityFields();
}
function buildAssetQueryParams() {
  const params = new URLSearchParams();
  const q = document.getElementById("filterQ").value.trim();
  const status = document.getElementById("filterStatus").value;
  const usageType = document.getElementById("filterUsageType").value;
  const category = document.getElementById("filterCategory").value;
  const department = document.getElementById("filterDepartment").value.trim();

  if (q) params.set("q", q);
  if (status) params.set("status", status);
  if (usageType) params.set("usage_type", usageType);
  if (category) params.set("category", category);
  if (department) params.set("department", department);

  params.set("exclude_disposed", "true");

  if (state.dashboardDrilldown === "warranty_30d") {
    params.set("warranty_expiring_days", "30");
  } else if (state.dashboardDrilldown === "warranty_overdue") {
    params.set("warranty_overdue", "true");
  } else if (state.dashboardDrilldown === "rental_7d") {
    params.set("rental_expiring_days", "7");
  }

  return params;
}

async function loadDashboard() {
  const summary = await api("/dashboard/summary");
  state.dashboardSummary = summary;
  renderSummary(summary);
}

async function loadAssets(page = state.pagination.page) {
  const targetPage = Math.max(1, Number(page) || 1);
  const params = buildAssetQueryParams();
  params.set("skip", String((targetPage - 1) * state.pagination.pageSize));
  params.set("limit", String(state.pagination.pageSize + 1));

  const rows = await api(`/assets?${params.toString()}`);
  state.pagination.page = targetPage;
  state.pagination.hasNext = rows.length > state.pagination.pageSize;
  state.assets = rows.slice(0, state.pagination.pageSize);

  if (!state.assets.length && targetPage > 1) {
    return loadAssets(targetPage - 1);
  }

  renderAssetRows();
  updateAssetsPagination();
}

function csvEscape(value) {
  const text = String(value ?? "").replace(/\r?\n/g, " ").trim();
  const escaped = text.replace(/"/g, '""');
  if (/[",\r\n]/.test(escaped)) {
    return `"${escaped}"`;
  }
  return escaped;
}

function buildCsvFilename() {
  const now = new Date();
  const pad = (num) => String(num).padStart(2, "0");
  const stamp = `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  return `자산리스트_${stamp}.csv`;
}

async function fetchAllAssetsForCurrentFilter() {
  const rows = [];
  const seen = new Set();
  const limit = 200;
  let skip = 0;

  for (let i = 0; i < 2000; i += 1) {
    const params = buildAssetQueryParams();
    params.set("skip", String(skip));
    params.set("limit", String(limit));

    const page = await api(`/assets?${params.toString()}`);
    if (!Array.isArray(page) || page.length === 0) break;

    let added = 0;
    page.forEach((asset) => {
      const key = String(asset.id ?? `${asset.asset_code || ""}|${asset.name || ""}|${asset.updated_at || ""}`);
      if (seen.has(key)) return;
      seen.add(key);
      rows.push(asset);
      added += 1;
    });

    if (added === 0) break;
    skip += page.length;
  }

  return rows;
}

function convertAssetsToCsvText(assets) {
  const headers = ["자산코드", "자산명", "카테고리", "사용 분류", "상태", "사용자", "담당자", "부서", "위치"];

  const lines = [headers.map(csvEscape).join(",")];
  assets.forEach((asset) => {
    const row = [
      asset.asset_code || "",
      asset.name || "",
      asset.category || "",
      asset.usage_type || "",
      asset.status || "",
      asset.owner || "",
      asset.manager || "",
      asset.department || "",
      asset.location || "",
    ];
    lines.push(row.map(csvEscape).join(","));
  });

  return `\uFEFF${lines.join("\r\n")}`;
}

async function exportAssetsCsv() {
  const exportBtn = document.getElementById("exportAssetsCsvBtn");
  if (exportBtn) exportBtn.disabled = true;

  try {
    showToast("CSV 파일을 생성 중입니다...");
    const assets = await fetchAllAssetsForCurrentFilter();

    if (!assets.length) {
      showToast("내보낼 자산이 없습니다.");
      return;
    }

    const csvText = convertAssetsToCsvText(assets);
    const blob = new Blob([csvText], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);

    const link = document.createElement("a");
    link.href = url;
    link.download = buildCsvFilename();
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);

    showToast(`CSV 다운로드 준비 완료 (${assets.length}건)`);
  } catch (error) {
    showToast(error.message || "CSV 다운로드에 실패했습니다.");
  } finally {
    if (exportBtn) exportBtn.disabled = false;
  }
}

function downloadCsvFile(filename, csvText) {
  const blob = new Blob([csvText], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function buildHardwareImportTemplateCsv() {
  const headers = [
    "자산명", "카테고리", "사용분류", "상태", "담당자", "사용자", "부서", "위치",
    "제조사", "모델명", "시리얼번호", "자산코드", "구매처", "구매일", "보증만료일", "구매금액", "대여시작일", "대여만료일", "메모",
  ];

  const sample = [
    "개발용 노트북", "노트북", "주장비", "대기", "admin", "미지정", "개발팀", "본사 3층",
    "Lenovo", "ThinkPad X1", "SN-001", "NB-26-00001", "공식총판", "2026-03-01", "2029-03-01", "2300000", "", "", "HW 예시",
  ];

  return `\uFEFF${[headers, sample].map((row) => row.map(csvEscape).join(",")).join("\r\n")}`;
}

function buildSoftwareImportTemplateCsv() {
  const headers = [
    "라이선스명", "라이선스구분", "라이선스성격", "구독형태", "라이선스시작일", "라이선스만료일", "라이선스구매비용", "통화", "총수량", "공급사", "기안자", "메모",
  ];

  const sample = [
    "Microsoft 365 E3", "생산성&협업", "필수", "연 구독", "2026-01-01", "2026-12-31", "1200000", "원", "50", "Microsoft", "admin", "SW 예시",
  ];

  return `\uFEFF${[headers, sample].map((row) => row.map(csvEscape).join(",")).join("\r\n")}`;
}

function downloadHardwareImportTemplate() {
  downloadCsvFile("HW_업로드_양식.csv", buildHardwareImportTemplateCsv());
}

function downloadSoftwareImportTemplate() {
  downloadCsvFile("SW_업로드_양식.csv", buildSoftwareImportTemplateCsv());
}

function formatHwSwImportResult(result) {
  const lines = [
    `총 데이터 행: ${result.total_rows ?? 0}`,
    `성공: ${result.processed_rows ?? 0}건 (HW ${result.created_hardware ?? 0} / SW ${result.created_software ?? 0})`,
    `실패: ${result.failed_rows ?? 0}건`,
  ];

  const errors = Array.isArray(result.errors) ? result.errors : [];
  if (errors.length) {
    lines.push("", "실패 상세:");
    errors.slice(0, 100).forEach((item) => {
      const kind = item.kind ? `[${item.kind}] ` : "";
      lines.push(`- ${item.row}행 ${kind}${item.message}`);
    });
    if (errors.length > 100) {
      lines.push(`- ...외 ${errors.length - 100}건`);
    }
  }

  return lines.join("\n");
}

async function uploadCsvToEndpoint(file, endpoint) {
  const formData = new FormData();
  formData.append("file", file);

  return api(endpoint, {
    method: "POST",
    body: formData,
  });
}

function setFieldValue(id, value) {
  document.getElementById(id).value = value ?? "";
}

function sanitizeTokenValue(text, fallback = "AST") {
  const cleaned = String(text || "")
    .toUpperCase()
    .replace(/[\s_\-]+/g, "")
    .replace(/[^\p{L}\p{N}]/gu, "")
    .slice(0, 6);
  return cleaned || fallback;
}

function getCategoryToken(categoryName) {
  const category = String(categoryName || "").trim();
  if (!category) return "AST";

  const found = state.settings.categories.find((item) => item.name.toLocaleLowerCase() === category.toLocaleLowerCase());
  if (found) {
    return sanitizeTokenValue(found.token, sanitizeTokenValue(category, "AST"));
  }
  return sanitizeTokenValue(category, "AST");
}

function fillCategorySelect(select, selectedValue = "") {
  if (!select) return;

  const prev = String(selectedValue || select.value || "").trim();
  select.innerHTML = "";

  state.settings.categories.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.name;
    option.textContent = item.name;
    select.appendChild(option);
  });

  if (prev && !state.settings.categories.some((item) => item.name === prev)) {
    const legacyOption = document.createElement("option");
    legacyOption.value = prev;
    legacyOption.textContent = `${prev} (기존값)`;
    select.appendChild(legacyOption);
  }

  if (prev) {
    select.value = prev;
  }
  if (!select.value && select.options.length) {
    select.value = select.options[0].value;
  }
}

function syncCategorySelects(addSelected = "", editSelected = "") {
  fillCategorySelect(document.getElementById("addCategory"), addSelected);
  fillCategorySelect(document.getElementById("editCategory"), editSelected);
}

function syncFilterCategorySelect(selectedValue = "") {
  const filter = document.getElementById("filterCategory");
  if (!filter) return;

  const selected = String(selectedValue || filter.value || "").trim();
  filter.innerHTML = '<option value="">전체 카테고리</option>';

  const names = getCategoryOptionValues(selected).sort((a, b) => a.localeCompare(b, "ko"));
  names.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    filter.appendChild(option);
  });

  filter.value = selected;
}

function setCategorySettingInputs(name = "", token = "") {
  document.getElementById("settingCategoryName").value = name;
  document.getElementById("settingCategoryToken").value = token;
}

function renderCategorySettingTable() {
  const tableBody = document.getElementById("settingCategoryTableBody");
  if (!state.settings.categories.length) {
    tableBody.innerHTML = '<tr><td colspan="3">등록된 카테고리가 없습니다.</td></tr>';
    return;
  }

  tableBody.innerHTML = state.settings.categories
    .map(
      (item, index) => `
        <tr>
          <td>${escapeHtml(item.name)}</td>
          <td><code>${escapeHtml(item.token)}</code></td>
          <td>
            <div class="table-actions">
              <button type="button" class="mini-btn" data-action="edit" data-index="${index}">불러오기</button>
              <button type="button" class="mini-btn danger" data-action="delete" data-index="${index}">삭제</button>
            </div>
          </td>
        </tr>
      `,
    )
    .join("");
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function resolveCodeTokens(category, usageType) {
  const now = new Date();
  return {
    CAT: getCategoryToken(category),
    USG: usageShortMap[usageType] || "ETC",
    YYYY: String(now.getFullYear()),
    YY: String(now.getFullYear()).slice(-2),
    MM: String(now.getMonth() + 1).padStart(2, "0"),
    DD: String(now.getDate()).padStart(2, "0"),
    RAND4: Math.floor(Math.random() * 10000).toString().padStart(4, "0"),
  };
}

function applyNonSeqTokens(template, tokens) {
  let code = String(template || DEFAULTS.codeTemplate).trim();
  code = code
    .replaceAll("{CAT}", tokens.CAT)
    .replaceAll("{USG}", tokens.USG)
    .replaceAll("{YYYY}", tokens.YYYY)
    .replaceAll("{YY}", tokens.YY)
    .replaceAll("{MM}", tokens.MM)
    .replaceAll("{DD}", tokens.DD)
    .replaceAll("{RAND4}", tokens.RAND4);
  return code;
}

async function fetchAllAssetCodes() {
  const codes = [];
  const limit = 200;
  let skip = 0;

  for (let i = 0; i < 100; i += 1) {
    const rows = await api(`/assets?skip=${skip}&limit=${limit}`);
    if (!Array.isArray(rows) || rows.length === 0) break;

    rows.forEach((asset) => {
      const code = String(asset.asset_code || "").trim();
      if (code) codes.push(code);
    });

    if (rows.length < limit) break;
    skip += limit;
  }

  return codes;
}

function replaceSeqWithFixedValue(code, length, value) {
  const replacement = String(value).padStart(length, "0");
  return code.replace(/\{SEQ\d*\}/g, replacement);
}

function findNextSequence(codeTemplateWithTokens, existingCodes) {
  const seqMatch = codeTemplateWithTokens.match(/\{SEQ(\d*)\}/);
  if (!seqMatch) return codeTemplateWithTokens;

  const seqLength = Number(seqMatch[1] || "4");
  const seqPlaceholder = "__SEQ__";
  const matchingTemplate = codeTemplateWithTokens.replace(/\{SEQ\d*\}/g, seqPlaceholder);
  const pattern = `^${escapeRegExp(matchingTemplate).replaceAll(seqPlaceholder, `(\\d{${seqLength}})`)}$`;
  const regex = new RegExp(pattern);

  let maxValue = 0;
  existingCodes.forEach((code) => {
    const matched = regex.exec(code);
    if (!matched) return;

    const value = Number(matched[1]);
    if (Number.isFinite(value) && value > maxValue) {
      maxValue = value;
    }
  });

  return matchingTemplate.replaceAll(seqPlaceholder, String(maxValue + 1).padStart(seqLength, "0"));
}

async function buildCodeFromTemplate(template, category, usageType) {
  const tokens = resolveCodeTokens(category, usageType);
  const codeWithTokens = applyNonSeqTokens(template, tokens);

  if (!/\{SEQ\d*\}/.test(codeWithTokens)) {
    return codeWithTokens;
  }

  const existingCodes = await fetchAllAssetCodes();
  return findNextSequence(codeWithTokens, existingCodes);
}

function buildPreviewCodeFromTemplate(template, category, usageType) {
  const tokens = resolveCodeTokens(category, usageType);
  const codeWithTokens = applyNonSeqTokens(template, tokens);

  if (!/\{SEQ\d*\}/.test(codeWithTokens)) {
    return codeWithTokens;
  }

  const seqMatch = codeWithTokens.match(/\{SEQ(\d*)\}/);
  const seqLength = Number(seqMatch?.[1] || "4");
  return replaceSeqWithFixedValue(codeWithTokens, seqLength, 1);
}

async function generateAssetCode(prefix) {
  const category = document.getElementById(`${prefix}Category`).value;
  const usageType = document.getElementById(`${prefix}UsageType`).value;
  const generated = await buildCodeFromTemplate(state.settings.codeTemplate, category, usageType);
  document.getElementById(`${prefix}AssetCode`).value = generated;
  showToast("자산코드를 생성했습니다.");
}

async function normalizeOwnerByStatus(status, ownerCandidate, contextLabel) {
  const ownerText = extractLookupUsername(ownerCandidate || "").trim();

  if (nonInUseStatuses.has(status)) {
    if (ownerText && ownerText !== "미지정") {
      showToast(`${contextLabel}: ${status} 상태로 변경되어 사용자 할당이 해제됩니다.`);
    }
    return "미지정";
  }

  if (status === "사용중" && (!ownerText || ownerText === "미지정")) {
    const assigned = await openOwnerAssignModal();
    if (!assigned) return null;
    return assigned;
  }

  return ownerText || "미지정";
}

function readCommonForm(prefix) {
  const pick = (id) => document.getElementById(`${prefix}${id}`).value;
  const trimOrNull = (value) => {
    const v = value.trim();
    return v ? v : null;
  };

  const usageType = pick("UsageType");
  const rentalStartDate = pick("RentalStartDate") || null;
  const rentalEndDate = pick("RentalEndDate") || null;

  if (usageType === "대여장비" && rentalStartDate && rentalEndDate && rentalEndDate < rentalStartDate) {
    throw new Error("대여 만료일자는 대여 시작일자보다 빠를 수 없습니다.");
  }

  const owner = extractLookupUsername(pick("Owner")) || "미지정";
  const manager = extractLookupUsername(pick("Manager")) || "미지정";
  const autoDepartment = owner === "미지정" ? null : getOwnerDepartment(owner) || trimOrNull(pick("Department"));
  const payload = {
    name: pick("Name").trim(),
    usage_type: usageType,
    status: pick("Status"),
    owner,
    manager,
    department: autoDepartment,
    location: pick("Location").trim() || "미지정",
    manufacturer: trimOrNull(pick("Manufacturer")),
    model_name: trimOrNull(pick("ModelName")),
    serial_number: trimOrNull(pick("SerialNumber")),
    asset_code: trimOrNull(pick("AssetCode")),
    vendor: trimOrNull(pick("Vendor")),
    purchase_date: pick("PurchaseDate") || null,
    warranty_expiry: pick("WarrantyExpiry") || null,
    rental_start_date: usageType === "대여장비" ? rentalStartDate : null,
    rental_end_date: usageType === "대여장비" ? rentalEndDate : null,
    purchase_cost: pick("PurchaseCost") ? Number(pick("PurchaseCost")) : null,
    notes: trimOrNull(pick("Notes")),
  };

  if (prefix === "add") {
    payload.category = pick("Category").trim();
  }

  return payload;
}

function applyLdapInputs(options = {}) {
  const resetResults = options.resetResults !== false;
  const config = state.settings.ldapConfig || { ...DEFAULTS.ldapConfig };

  const serverUrl = document.getElementById("ldapServerUrl");
  const useSsl = document.getElementById("ldapUseSsl");
  const port = document.getElementById("ldapPort");
  const bindDn = document.getElementById("ldapBindDn");
  const baseDn = document.getElementById("ldapBaseDn");
  const userIdAttr = document.getElementById("ldapUserIdAttr");
  const userNameAttr = document.getElementById("ldapUserNameAttr");
  const userEmailAttr = document.getElementById("ldapUserEmailAttr");
  const userDepartmentAttr = document.getElementById("ldapUserDepartmentAttr");
  const userTitleAttr = document.getElementById("ldapUserTitleAttr");
  const managerDnAttr = document.getElementById("ldapManagerDnAttr");
  const userDnAttr = document.getElementById("ldapUserDnAttr");
  const userGuidAttr = document.getElementById("ldapUserGuidAttr");
  const sizeLimit = document.getElementById("ldapSizeLimit");

  if (!serverUrl) return;

  serverUrl.value = config.server_url || "";
  useSsl.checked = Boolean(config.use_ssl);
  port.value = config.port || "";
  bindDn.value = config.bind_dn || "";
  baseDn.value = config.base_dn || "";
  userIdAttr.value = config.user_id_attribute || "sAMAccountName";
  userNameAttr.value = config.user_name_attribute || "displayName";
  userEmailAttr.value = config.user_email_attribute || "mail";
  userDepartmentAttr.value = config.user_department_attribute || "department";
  userTitleAttr.value = config.user_title_attribute || "title";
  managerDnAttr.value = config.manager_dn_attribute || "manager";
  userDnAttr.value = config.user_dn_attribute || "distinguishedName";
  userGuidAttr.value = config.user_guid_attribute || "objectGUID";
  sizeLimit.value = config.size_limit || 1000;

  if (resetResults) {
    if (ldapResultInfo) ldapResultInfo.textContent = "검색 결과가 없습니다.";
    if (ldapResultBody) ldapResultBody.innerHTML = "";
    state.lastLdapSearchUsers = [];
    const importBtn = document.getElementById("ldapImportSearchResultBtn");
    if (importBtn) importBtn.disabled = true;
  }

  updateLdapPasswordStatus();
  renderLdapScheduleInfo();
}

function readLdapForm(includePassword = false, requireBaseDn = true) {
  const payload = {
    server_url: document.getElementById("ldapServerUrl").value.trim(),
    use_ssl: document.getElementById("ldapUseSsl").checked,
    port: document.getElementById("ldapPort").value ? Number(document.getElementById("ldapPort").value) : null,
    bind_dn: document.getElementById("ldapBindDn").value.trim(),
    bind_password: state.ldapSession.bindPassword || "",
    base_dn: document.getElementById("ldapBaseDn").value.trim(),
    user_id_attribute: document.getElementById("ldapUserIdAttr").value.trim() || "sAMAccountName",
    user_name_attribute: document.getElementById("ldapUserNameAttr").value.trim() || "displayName",
    user_email_attribute: document.getElementById("ldapUserEmailAttr").value.trim() || "mail",
    user_department_attribute: document.getElementById("ldapUserDepartmentAttr").value.trim() || "department",
    user_title_attribute: document.getElementById("ldapUserTitleAttr").value.trim() || "title",
    manager_dn_attribute: document.getElementById("ldapManagerDnAttr").value.trim() || "manager",
    user_dn_attribute: document.getElementById("ldapUserDnAttr").value.trim() || "distinguishedName",
    user_guid_attribute: document.getElementById("ldapUserGuidAttr").value.trim() || "objectGUID",
    size_limit: Number(document.getElementById("ldapSizeLimit").value || 1000),
  };

  if (!payload.server_url) throw new Error("LDAP 서버 주소를 입력해주세요.");
  if (!payload.bind_dn) throw new Error("Bind DN을 입력해주세요.");
  if (requireBaseDn && !payload.base_dn) throw new Error("Base DN을 입력해주세요.");

  if (includePassword && !payload.bind_password) {
    openLdapPasswordModal();
    throw new Error("Bind 비밀번호를 먼저 팝업에서 입력해주세요.");
  }

  return payload;
}

function renderLdapResults(users) {
  if (!ldapResultBody || !ldapResultInfo) return;

  const rows = Array.isArray(users) ? users : [];
  state.lastLdapSearchUsers = rows
    .map((row) => ({
      username: String(row.username || "").trim(),
      display_name: row.display_name || null,
      email: row.email || null,
      department: row.department || null,
      title: row.title || null,
      manager_dn: row.manager_dn || null,
      user_dn: row.user_dn || null,
      object_guid: row.object_guid || null,
    }))
    .filter((row) => row.username);

  const importBtn = document.getElementById("ldapImportSearchResultBtn");
  if (importBtn) importBtn.disabled = state.lastLdapSearchUsers.length === 0;

  ldapResultInfo.textContent = `검색 결과: ${rows.length}건`;

  if (!rows.length) {
    ldapResultBody.innerHTML = '<tr><td colspan="9">검색 결과가 없습니다.</td></tr>';
    return;
  }

  ldapResultBody.innerHTML = rows
    .map(
      (user) => `
        <tr>
          <td>${escapeHtml(user.username || "-")}</td>
          <td>${escapeHtml(user.display_name || "-")}</td>
          <td>${escapeHtml(user.email || "-")}</td>
          <td>${escapeHtml(user.department || "-")}</td>
          <td>${escapeHtml(user.title || "-")}</td>
          <td>${escapeHtml(user.manager_dn || "-")}</td>
          <td>${escapeHtml(user.object_guid || "-")}</td>
          <td>${escapeHtml(user.user_dn || "-")}</td>
          <td><button type="button" class="mini-btn ldap-apply-btn" data-username="${escapeHtml(user.username || "")}">사용자 적용</button></td>
        </tr>
      `,
    )
    .join("");
}
function applyLdapUserToForm(username) {
  const user = String(username || "").trim();
  if (!user) return;

  if (!editModal.classList.contains("hidden") && state.currentAssetId) {
    setOwnerInputValue("editOwner", user);
    showToast(`LDAP 사용자(${user})를 수정 팝업 사용자에 적용했습니다.`);
    return;
  }

  setOwnerInputValue("addOwner", user);
  activateTab("add");
  showToast(`LDAP 사용자(${user})를 자산추가 사용자에 적용했습니다.`);
}
function applySettingInputs() {
  document.getElementById("settingAssetCodeTemplate").value = state.settings.codeTemplate;
  document.getElementById("settingDefaultOwner").value = state.settings.defaultOwner;
  document.getElementById("settingDefaultManager").value = state.settings.defaultManager;

  syncCategorySelects();
  syncFilterCategorySelect();
  renderCategorySettingTable();
  setCategorySettingInputs();
  updateCodePreview();
  applyLdapInputs();
  applySoftwareMailInputs();
  syncSoftwareMetaControls();
}

function updateCodePreview() {
  const sampleCategory = state.settings.categories[0]?.name || "노트북";
  const sample = buildPreviewCodeFromTemplate(state.settings.codeTemplate, sampleCategory, "주장비");
  document.getElementById("codePreviewText").textContent = `미리보기: ${sample}`;
}

function persistSettings() {
  localStorage.setItem(STORAGE_KEYS.codeTemplate, state.settings.codeTemplate);
  localStorage.setItem(STORAGE_KEYS.defaultOwner, state.settings.defaultOwner);
  localStorage.setItem(STORAGE_KEYS.defaultManager, state.settings.defaultManager);
  localStorage.setItem(STORAGE_KEYS.categories, JSON.stringify(state.settings.categories));
  localStorage.setItem(STORAGE_KEYS.ldapConfig, JSON.stringify(state.settings.ldapConfig));
  localStorage.setItem(STORAGE_KEYS.softwareLicenseCategories, JSON.stringify(state.settings.softwareLicenseCategories));
}

function resetAddForm() {
  document.getElementById("addAssetForm").reset();
  setManagerInputValue("addManager", state.settings.defaultManager);
  setOwnerInputValue("addOwner", state.settings.defaultOwner);
  syncDepartmentByOwner("add", { preserveWhenUnknown: false });
  document.getElementById("addStatus").value = "대기";
  document.getElementById("addUsageType").value = "주장비";
  toggleRentalFields("add", "주장비");

  const addCategory = document.getElementById("addCategory");
  if (addCategory.options.length) {
    addCategory.value = addCategory.options[0].value;
  }
}

function formatHistoryValue(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "object") return escapeHtml(JSON.stringify(value));
  return escapeHtml(String(value));
}

function getHistoryChanges(item) {
  const payload = item.changed_fields;
  if (!payload || typeof payload !== "object") return { memo: "", rows: [] };

  const memo = typeof payload.memo === "string" ? payload.memo : "";
  const rows = [];

  if (payload.changes && typeof payload.changes === "object") {
    Object.entries(payload.changes).forEach(([key, values]) => {
      if (values && typeof values === "object" && ("before" in values || "after" in values)) {
        rows.push({ key, before: values.before, after: values.after });
      }
    });
  }

  if (!rows.length && payload.after && typeof payload.after === "object") {
    Object.entries(payload.after).forEach(([key, value]) => rows.push({ key, before: "-", after: value }));
  }

  if (!rows.length && payload.before && typeof payload.before === "object") {
    Object.entries(payload.before).forEach(([key, value]) => rows.push({ key, before: value, after: "-" }));
  }

  return { memo, rows };
}

function renderHistoryRows(item) {
  const action = actionLabelMap[item.action] || item.action;
  const { memo, rows } = getHistoryChanges(item);

  const changeRowsHtml = rows.length
    ? rows
        .map((row) => {
          const label = fieldLabelMap[row.key] || row.key;
          return `
            <div class="history-change-row">
              <div class="history-change-key">${escapeHtml(label)}</div>
              <div class="history-change-values">변경 전: ${formatHistoryValue(row.before)} / 변경 후: ${formatHistoryValue(row.after)}</div>
            </div>
          `;
        })
        .join("")
    : '<div class="history-change-row">변경 항목 없음</div>';

  const memoHtml = memo ? `<div class="history-memo">메모: ${escapeHtml(memo)}</div>` : "";

  return `
    <div class="history-item">
      <div class="history-top">
        <span class="history-action">${escapeHtml(action)}</span>
        <span class="history-date">${new Date(item.created_at).toLocaleString()}</span>
      </div>
      <div class="history-meta">작업자: ${escapeHtml(item.actor_username || "-")}</div>
      ${memoHtml}
      <div class="history-change-list">${changeRowsHtml}</div>
    </div>
  `;
}

async function openHistoryInModal(assetId) {
  const history = await api(`/assets/${assetId}/history`);
  if (!history.length) {
    editHistoryBox.innerHTML = "<div class='history-item'>변경 이력이 없습니다.</div>";
    return;
  }
  editHistoryBox.innerHTML = history.map((item) => renderHistoryRows(item)).join("");
}

async function openEditModal(assetId) {
  const asset = await api(`/assets/${assetId}`);
  state.currentAssetId = asset.id;

  setFieldValue("editId", asset.id);
  setFieldValue("editName", asset.name);
  fillCategorySelect(document.getElementById("editCategory"), asset.category);
  setFieldValue("editUsageType", asset.usage_type || "기타장비");
  setFieldValue("editRentalStartDate", asset.rental_start_date);
  setFieldValue("editRentalEndDate", asset.rental_end_date);
  toggleRentalFields("edit", asset.usage_type || "기타장비");
  setFieldValue("editStatus", asset.status || "대기");
  setManagerInputValue("editManager", asset.manager || state.settings.defaultManager);
  setOwnerInputValue("editOwner", asset.owner || state.settings.defaultOwner);
  setFieldValue("editDepartment", asset.department);
  syncDepartmentByOwner("edit", { preserveWhenUnknown: true });
  setFieldValue("editLocation", asset.location);
  setFieldValue("editManufacturer", asset.manufacturer);
  setFieldValue("editModelName", asset.model_name);
  setFieldValue("editSerialNumber", asset.serial_number);
  setFieldValue("editAssetCode", asset.asset_code);
  setFieldValue("editVendor", asset.vendor);
  setFieldValue("editPurchaseDate", asset.purchase_date);
  setFieldValue("editWarrantyExpiry", asset.warranty_expiry);
  setFieldValue("editPurchaseCost", asset.purchase_cost);
  setFieldValue("editNotes", asset.notes);

  await openHistoryInModal(asset.id);
  editModal.classList.remove("hidden");
}

function closeEditModal() {
  editModal.classList.add("hidden");
  state.currentAssetId = null;
  editHistoryBox.innerHTML = "";
}

async function applyInlineUpdate(assetId) {
  const row = assetTableBody.querySelector(`tr[data-id="${assetId}"]`);
  if (!row) return;

  const currentStatus = row.dataset.status || "대기";
  const currentOwner = row.dataset.owner || "미지정";
  const status = row.querySelector(".inline-status")?.value;
  const usageType = row.querySelector(".inline-usage")?.value;

  if (!status || !usageType) {
    showToast("상태/분류 값을 확인해주세요.");
    return;
  }

  const payload = { status, usage_type: usageType };

  if (status !== currentStatus) {
    const normalizedOwner = await normalizeOwnerByStatus(status, currentOwner, "빠른수정");
    if (normalizedOwner === null) return;
    payload.owner = normalizedOwner;
  }

  await api(`/assets/${assetId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });

  showToast("상태/분류가 수정되었습니다.");
  await refreshDashboardAndAssets();
}

async function refreshDashboardAndAssets() {
  await loadExchangeRateSetting();
  await Promise.all([loadDashboard(), loadAssets(), loadDisposedAssets(), loadSoftwareLicenses()]);
}

document.getElementById("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;
    const tokenResponse = await api("/auth/login", {
      method: "POST",
      headers: {},
      body: JSON.stringify({ username, password }),
    });

    state.token = tokenResponse.access_token;
    localStorage.setItem(STORAGE_KEYS.token, state.token);

    state.user = await api("/me");
    updateAuthView();
    applyRoleTabVisibility();
    activateTab("dashboard");
    await refreshDashboardAndAssets();
    await refreshUserDataSources();
    if (isAdminUser()) {
      await loadLdapSchedule();
    }
    showToast("로그인되었습니다.");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("logoutBtn").addEventListener("click", () => {
  state.token = "";
  state.user = null;
  state.ldapSession.bindPassword = "";
  state.directoryUsers = [];
  state.managedUsers = [];
  state.managedAdmins = [];
  localStorage.removeItem(STORAGE_KEYS.token);
  updateAuthView();
  applyRoleTabVisibility();
  renderDirectoryUserDatalist();
  renderAdminUserDatalist();
  renderUsersTable("user");
  renderUsersTable("admin");
  updateLdapPasswordStatus();
  closeEditModal();
  showToast("로그아웃했습니다.");
});

tabs.addEventListener("click", async (event) => {
  const button = event.target.closest(".tab-btn");
  if (!button) return;

  const tab = button.dataset.tab;
  activateTab(tab);

  try {
    if (!state.token) return;

    if (tab === "dashboard") {
      await loadExchangeRateSetting();
      await loadDashboard();
      return;
    }

    if (tab === "hardware") {
      if (state.hardwareSubtab === "disposed") {
        await loadDisposedAssets();
      } else if (state.hardwareSubtab === "assets") {
        await loadAssets(state.pagination.page);
      }
      return;
    }

    if (tab === "software") {
      await loadSoftwareLicenses();
      return;
    }

    if (tab === "settings") {
      activateSettingsSubtab(state.settingsSubtab || "hardware");
      await loadSettingsSubtabData(state.settingsSubtab || "hardware");
    }
  } catch (error) {
    showToast(error.message);
  }
});

hardwareSubtabs?.addEventListener("click", async (event) => {
  const button = event.target.closest(".subtab-btn[data-hardware-tab]");
  if (!button) return;

  const subtab = button.dataset.hardwareTab || "assets";
  activateTab(subtab);

  try {
    if (!state.token) return;
    if (subtab === "disposed") {
      await loadDisposedAssets();
    } else if (subtab === "assets") {
      await loadAssets(state.pagination.page);
    }
  } catch (error) {
    showToast(error.message);
  }
});

softwareSubtabs?.addEventListener("click", async (event) => {
  const button = event.target.closest(".subtab-btn[data-software-tab]");
  if (!button) return;

  const subtab = button.dataset.softwareTab || "editor";
  activateSoftwareSubtab(subtab);

  try {
    if (!state.token) return;
    await loadSoftwareLicenses();
  } catch (error) {
    showToast(error.message);
  }
});
settingsSubtabs?.addEventListener("click", async (event) => {
  const button = event.target.closest(".subtab-btn[data-settings-tab]");
  if (!button) return;

  const subtab = button.dataset.settingsTab || "hardware";
  if (button.dataset.adminOnly === "1" && !isAdminUser()) {
    showToast("관리자 권한이 필요합니다.");
    activateSettingsSubtab("hardware");
    return;
  }

  activateSettingsSubtab(subtab);

  try {
    await loadSettingsSubtabData(subtab);
  } catch (error) {
    showToast(error.message);
  }
});

settingsAccountsSubtabs?.addEventListener("click", async (event) => {
  const button = event.target.closest(".subtab-btn[data-settings-accounts-tab]");
  if (!button) return;

  if (!isAdminUser()) {
    showToast("관리자 권한이 필요합니다.");
    return;
  }

  const subtab = button.dataset.settingsAccountsTab || "users";
  activateSettingsAccountsSubtab(subtab);

  try {
    await loadSettingsSubtabData("accounts");
  } catch (error) {
    showToast(error.message);
  }
});

settingsMiscSubtabs?.addEventListener("click", async (event) => {
  const button = event.target.closest(".subtab-btn[data-settings-misc-tab]");
  if (!button) return;

  if (!isAdminUser()) {
    showToast("관리자 권한이 필요합니다.");
    activateSettingsSubtab("hardware");
    return;
  }

  const subtab = button.dataset.settingsMiscTab || "ldap";
  activateSettingsMiscSubtab(subtab);

  try {
    await loadSettingsSubtabData("misc");
  } catch (error) {
    showToast(error.message);
  }
});

settingsMailSubtabs?.addEventListener("click", async (event) => {
  const button = event.target.closest(".subtab-btn[data-settings-mail-tab]");
  if (!button) return;

  if (!isAdminUser()) {
    showToast("관리자 권한이 필요합니다.");
    activateSettingsSubtab("hardware");
    return;
  }

  const subtab = button.dataset.settingsMailTab || "smtp";
  activateSettingsMailSubtab(subtab);

  try {
    await loadSettingsSubtabData("misc");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("reloadAssetsBtn").addEventListener("click", async () => {
  try {
    await refreshDashboardAndAssets();
    showToast("새로고침 완료");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("exportAssetsCsvBtn")?.addEventListener("click", async () => {
  await exportAssetsCsv();
});

document.getElementById("downloadHardwareCsvTemplateBtn")?.addEventListener("click", () => {
  downloadHardwareImportTemplate();
  showToast("하드웨어 업로드 양식을 다운로드했습니다.");
});

document.getElementById("importHardwareCsvForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();

  const fileInput = document.getElementById("importHardwareCsvFile");
  const resultBox = document.getElementById("importHardwareCsvResult");
  const file = fileInput?.files?.[0];

  if (!file) {
    showToast("CSV 파일을 선택해주세요.");
    return;
  }

  try {
    if (resultBox) resultBox.textContent = "업로드 중입니다...";
    const result = await uploadCsvToEndpoint(file, "/imports/hardware-csv");
    if (resultBox) resultBox.textContent = formatHwSwImportResult(result);

    await refreshDashboardAndAssets();
    showToast(`HW CSV 업로드 완료: 성공 ${result.processed_rows || 0}건, 실패 ${result.failed_rows || 0}건`);
  } catch (error) {
    if (resultBox) resultBox.textContent = `오류: ${error.message}`;
    showToast(error.message || "CSV 업로드에 실패했습니다.");
  }
});

document.getElementById("downloadSoftwareCsvTemplateBtn")?.addEventListener("click", () => {
  downloadSoftwareImportTemplate();
  showToast("소프트웨어 업로드 양식을 다운로드했습니다.");
});

document.getElementById("importSoftwareCsvForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();

  const fileInput = document.getElementById("importSoftwareCsvFile");
  const resultBox = document.getElementById("importSoftwareCsvResult");
  const file = fileInput?.files?.[0];

  if (!file) {
    showToast("CSV 파일을 선택해주세요.");
    return;
  }

  try {
    if (resultBox) resultBox.textContent = "업로드 중입니다...";
    const result = await uploadCsvToEndpoint(file, "/imports/software-csv");
    if (resultBox) resultBox.textContent = formatHwSwImportResult(result);

    await refreshDashboardAndAssets();
    showToast(`SW CSV 업로드 완료: 성공 ${result.processed_rows || 0}건, 실패 ${result.failed_rows || 0}건`);
  } catch (error) {
    if (resultBox) resultBox.textContent = `오류: ${error.message}`;
    showToast(error.message || "CSV 업로드에 실패했습니다.");
  }
});
document.getElementById("reloadDisposedBtn").addEventListener("click", async () => {
  try {
    await loadDisposedAssets();
    showToast("폐기완료 목록 새로고침 완료");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("reloadSoftwareBtn")?.addEventListener("click", async () => {
  try {
    await loadSoftwareLicenses();
    showToast("소프트웨어 라이선스 목록 새로고침 완료");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("reloadSoftwareAssignedBtn")?.addEventListener("click", async () => {
  try {
    await loadSoftwareLicenses();
    showToast("할당 전체 리스트 새로고침 완료");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("softwareFilterForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await loadSoftwareLicenses();
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("softwareAssignedFilterForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  try {
    renderSoftwareAssignedRows();
  } catch (error) {
    showToast(error.message);
  }
});

document.querySelector("#softwareAssignedTable thead")?.addEventListener("click", (event) => {
  const button = event.target.closest(".table-sort-btn[data-sort-key]");
  if (!button) return;

  toggleSoftwareAssignedSort(button.dataset.sortKey || "");
  renderSoftwareAssignedRows();
});
document.getElementById("cancelSoftwareEditBtn")?.addEventListener("click", () => {
  resetSoftwareForm();
});

document.getElementById("softwareForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();

  try {
    const payload = readSoftwareFormPayload();
    const id = Number(document.getElementById("swId")?.value || 0);

    if (id > 0) {
      await api(`/software-licenses/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      showToast("소프트웨어 라이선스를 수정했습니다.");
    } else {
      await api("/software-licenses", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("소프트웨어 라이선스를 등록했습니다.");
    }

    resetSoftwareForm();
    await Promise.all([loadSoftwareLicenses(), loadDashboard()]);
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("swEditTarget")?.addEventListener("change", (event) => {
  const id = Number(event.target.value || 0);
  if (!id) {
    resetSoftwareForm();
    return;
  }

  const row = findSoftwareLicenseById(id);
  if (!row) {
    showToast("선택한 라이선스를 찾을 수 없습니다.");
    resetSoftwareForm();
    return;
  }

  fillSoftwareForm(row);
});

document.getElementById("swTotalQuantity")?.addEventListener("input", () => {
  updateSoftwareQuantityFields();
});

document.getElementById("softwareCategoryForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.getElementById("softwareCategoryInput");
  const value = String(input?.value || "").trim();
  if (!value) return;

  state.settings.softwareLicenseCategories = normalizeSoftwareMetaList(
    [...(state.settings.softwareLicenseCategories || []), value],
    DEFAULTS.softwareLicenseCategories,
  );
  persistSettings();
  syncSoftwareMetaControls();
  if (input) input.value = "";
  showToast("라이선스 구분을 저장했습니다.");
});


function handleSoftwareMetaRemove(kind, value) {
  const targetValue = String(value || "").trim();
  if (!targetValue) return;

  if (kind !== "category") return;

  state.settings.softwareLicenseCategories = normalizeSoftwareMetaList(
    (state.settings.softwareLicenseCategories || []).filter((item) => String(item || "").trim() !== targetValue),
    DEFAULTS.softwareLicenseCategories,
  );
  persistSettings();
  syncSoftwareMetaControls();
  showToast("라이선스 구분을 삭제했습니다.");
}

softwareCategoryTableBody?.addEventListener("click", (event) => {
  const button = event.target.closest(".software-meta-remove-btn");
  if (!button) return;
  handleSoftwareMetaRemove(button.dataset.kind || "category", button.dataset.value || "");
});


document.getElementById("softwareAssignLicenseInput")?.addEventListener("change", (event) => {
  const id = resolveSoftwareAssignmentLicenseIdFromInput(event.target.value, false);
  setSoftwareAssignmentLicenseById(id, true);
  if (!id && String(event.target.value || "").trim()) {
    showToast("대상 라이선스를 목록에서 선택해주세요.");
  }
  renderSoftwareAssignmentPanel();
});

document.getElementById("softwareAssignLicenseInput")?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  const id = resolveSoftwareAssignmentLicenseIdFromInput(event.target.value, true);
  setSoftwareAssignmentLicenseById(id, true);
  renderSoftwareAssignmentPanel();
});

document.getElementById("softwareAssignSearchField")?.addEventListener("change", () => {
  renderSoftwareAssignmentPanel();
});

document.getElementById("softwareAssignSearch")?.addEventListener("input", () => {
  renderSoftwareAssignmentPanel();
});

softwareAssignUserTableBody?.addEventListener("click", async (event) => {
  const saveButton = event.target.closest(".software-assignment-save-btn");
  if (saveButton) {
    const licenseId = Number(saveButton.dataset.licenseId || 0);
    const username = saveButton.dataset.username || "";
    const row = saveButton.closest("tr");

    try {
      await saveSoftwareAssigneeDetail(licenseId, username, row);
      showToast("사용자별 라이선스 정보를 저장했습니다.");
    } catch (error) {
      showToast(error.message);
    }
    return;
  }

  const button = event.target.closest(".software-assignment-action-btn");
  if (!button) return;

  const licenseId = Number(button.dataset.licenseId || 0);
  const username = button.dataset.username || "";
  const action = button.dataset.action || "assign";

  try {
    await toggleSoftwareAssignment(licenseId, username, action);
    showToast(action === "assign" ? "사용자를 할당했습니다." : "사용자 할당을 해제했습니다.");
  } catch (error) {
    showToast(error.message);
  }
});
softwareTableBody?.addEventListener("click", async (event) => {
  const editBtn = event.target.closest(".software-edit-btn");
  if (editBtn) {
    const id = Number(editBtn.dataset.id || 0);
    const row = findSoftwareLicenseById(id);
    if (!row) return;
    fillSoftwareForm(row);
    activateTab("software");
    activateSoftwareSubtab("editor");
    return;
  }

  const deleteBtn = event.target.closest(".software-delete-btn");
  if (deleteBtn) {
    const id = Number(deleteBtn.dataset.id || 0);
    if (!id) return;

    if (!confirm("이 라이선스를 삭제하시겠습니까?")) return;

    try {
      await api(`/software-licenses/${id}`, { method: "DELETE" });
      showToast("소프트웨어 라이선스를 삭제했습니다.");
      await Promise.all([loadSoftwareLicenses(), loadDashboard()]);
    } catch (error) {
      showToast(error.message);
    }
    return;
  }

  const row = event.target.closest("tr[data-license-id]");
  if (!row) return;

  const id = Number(row.dataset.licenseId || 0);
  if (!id) return;
  openSoftwareAssignmentForLicense(id);
});
softwareAssignedTableBody?.addEventListener("click", (event) => {
  const row = event.target.closest("tr[data-license-id]");
  if (!row) return;

  const id = Number(row.dataset.licenseId || 0);
  if (!id) return;

  openSoftwareAssignmentForLicense(id);
});
document.getElementById("openLdapPasswordModalBtn")?.addEventListener("click", () => {
  openLdapPasswordModal();
});

document.getElementById("ldapPasswordConfirmBtn")?.addEventListener("click", () => {
  applyLdapSessionPassword();
});

document.getElementById("ldapPasswordCancelBtn")?.addEventListener("click", () => {
  closeLdapPasswordModal();
});

ldapPasswordModal?.addEventListener("click", (event) => {
  if (event.target === ldapPasswordModal) closeLdapPasswordModal();
});

document.getElementById("closeUserMailPreviewModalBtn")?.addEventListener("click", () => {
  closeUserMailPreviewModal();
});

userMailPreviewModal?.addEventListener("click", (event) => {
  if (event.target === userMailPreviewModal) closeUserMailPreviewModal();
});

document.getElementById("saveLdapConfigBtn").addEventListener("click", () => {
  try {
    const form = readLdapForm(false);
    state.settings.ldapConfig = {
      ...state.settings.ldapConfig,
      server_url: form.server_url,
      use_ssl: form.use_ssl,
      port: form.port || "",
      bind_dn: form.bind_dn,
      base_dn: form.base_dn,
      user_id_attribute: form.user_id_attribute,
      user_name_attribute: form.user_name_attribute,
      user_email_attribute: form.user_email_attribute,
      user_department_attribute: form.user_department_attribute,
      user_title_attribute: form.user_title_attribute,
      manager_dn_attribute: form.manager_dn_attribute,
      user_dn_attribute: form.user_dn_attribute,
      user_guid_attribute: form.user_guid_attribute,
      size_limit: form.size_limit,
    };
    persistSettings();
    showToast("LDAP 설정을 저장했습니다.");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("testLdapBtn").addEventListener("click", async () => {
  try {
    const form = readLdapForm(true, false);
    await api("/ldap/test", {
      method: "POST",
      body: JSON.stringify({
        server_url: form.server_url,
        use_ssl: form.use_ssl,
        port: form.port,
        bind_dn: form.bind_dn,
        bind_password: form.bind_password,
      }),
    });
    showToast("LDAP 연결 테스트 성공");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("ldapSearchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const form = readLdapForm(true, false);
    const query = document.getElementById("ldapQuery").value.trim();
    const result = await api("/ldap/search", {
      method: "POST",
      body: JSON.stringify({
        server_url: form.server_url,
        use_ssl: form.use_ssl,
        port: form.port,
        bind_dn: form.bind_dn,
        bind_password: form.bind_password,
        base_dn: form.base_dn,
        query,
        user_id_attribute: form.user_id_attribute,
        user_name_attribute: form.user_name_attribute,
        user_email_attribute: form.user_email_attribute,
        user_department_attribute: form.user_department_attribute,
        user_title_attribute: form.user_title_attribute,
        manager_dn_attribute: form.manager_dn_attribute,
        user_dn_attribute: form.user_dn_attribute,
        user_guid_attribute: form.user_guid_attribute,
        size_limit: form.size_limit,
      }),
    });
    renderLdapResults(result.users || []);
    state.settings.ldapConfig = {
      ...state.settings.ldapConfig,
      server_url: form.server_url,
      use_ssl: form.use_ssl,
      port: form.port || "",
      bind_dn: form.bind_dn,
      base_dn: form.base_dn,
      user_id_attribute: form.user_id_attribute,
      user_name_attribute: form.user_name_attribute,
      user_email_attribute: form.user_email_attribute,
      user_department_attribute: form.user_department_attribute,
      user_title_attribute: form.user_title_attribute,
      manager_dn_attribute: form.manager_dn_attribute,
      user_dn_attribute: form.user_dn_attribute,
      user_guid_attribute: form.user_guid_attribute,
      size_limit: form.size_limit,
    };
    persistSettings();
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("ldapSyncNowBtn")?.addEventListener("click", async () => {
  try {
    if (!isAdminUser()) {
      throw new Error("관리자 권한이 필요합니다.");
    }

    const form = readLdapForm(true, false);
    const saveForSchedule = Boolean(document.getElementById("ldapSavePasswordForSchedule")?.checked);

    const result = await api("/ldap/sync-now", {
      method: "POST",
      body: JSON.stringify({
        server_url: form.server_url,
        use_ssl: form.use_ssl,
        port: form.port,
        bind_dn: form.bind_dn,
        bind_password: form.bind_password,
        base_dn: form.base_dn,
        user_id_attribute: form.user_id_attribute,
        user_name_attribute: form.user_name_attribute,
        user_email_attribute: form.user_email_attribute,
        user_department_attribute: form.user_department_attribute,
        user_title_attribute: form.user_title_attribute,
        manager_dn_attribute: form.manager_dn_attribute,
        user_dn_attribute: form.user_dn_attribute,
        user_guid_attribute: form.user_guid_attribute,
        size_limit: form.size_limit,
        save_for_schedule: saveForSchedule,
      }),
    });

    showToast(`동기화 완료: ${result.result?.total_synced ?? 0}명`);
    await refreshUserDataSources();
    await loadLdapSchedule();
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("ldapScheduleForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();

  try {
    if (!isAdminUser()) {
      throw new Error("관리자 권한이 필요합니다.");
    }

    const form = readLdapForm(false);
    const interval = Number(document.getElementById("ldapScheduleInterval")?.value || 60);
    const enabled = Boolean(document.getElementById("ldapScheduleEnabled")?.checked);

    const payload = {
      enabled,
      interval_minutes: interval,
      server_url: form.server_url,
      use_ssl: form.use_ssl,
      port: form.port,
      bind_dn: form.bind_dn,
      base_dn: form.base_dn,
      user_id_attribute: form.user_id_attribute,
      user_name_attribute: form.user_name_attribute,
      user_email_attribute: form.user_email_attribute,
      user_department_attribute: form.user_department_attribute,
      user_title_attribute: form.user_title_attribute,
      manager_dn_attribute: form.manager_dn_attribute,
      user_dn_attribute: form.user_dn_attribute,
      user_guid_attribute: form.user_guid_attribute,
      size_limit: form.size_limit,
      bind_password: state.ldapSession.bindPassword || null,
    };

    const saved = await api("/ldap/sync-schedule", {
      method: "PUT",
      body: JSON.stringify(payload),
    });

    state.ldapSchedule = {
      ...state.ldapSchedule,
      ...(saved || {}),
    };
    renderLdapScheduleInfo();
    showToast("LDAP 동기화 스케줄을 저장했습니다.");
  } catch (error) {
    showToast(error.message);
  }
});
document.getElementById("ldapImportSearchResultBtn")?.addEventListener("click", async () => {
  try {
    if (!isAdminUser()) {
      throw new Error("관리자 권한이 필요합니다.");
    }

    if (!state.lastLdapSearchUsers.length) {
      throw new Error("먼저 LDAP 검색을 실행해주세요.");
    }

    const result = await api("/directory-users/import", {
      method: "POST",
      body: JSON.stringify({ users: state.lastLdapSearchUsers }),
    });

    await loadManagedUsers("user", document.getElementById("userSearchQ")?.value || "");
    await loadDirectoryUsers();
    showToast(`사용자 탭 반영 완료: ${result.result?.total_incoming ?? 0}건`);
  } catch (error) {
    showToast(error.message);
  }
});
ldapResultBody?.addEventListener("click", (event) => {
  const applyBtn = event.target.closest(".ldap-apply-btn");
  if (!applyBtn) return;
  applyLdapUserToForm(applyBtn.dataset.username || "");
});


const reloadUsersBtn = document.getElementById("reloadUsersBtn");
const reloadInactiveUsersBtn = document.getElementById("reloadInactiveUsersBtn");
const reloadAdminsBtn = document.getElementById("reloadAdminsBtn");
const reloadOrgChartBtn = document.getElementById("reloadOrgChartBtn");

reloadUsersBtn?.addEventListener("click", async () => {
  try {
    await loadManagedUsers("user", document.getElementById("userSearchQ")?.value || "");
    await loadDirectoryUsers();
    showToast("사용자 목록을 새로고침했습니다.");
  } catch (error) {
    showToast(error.message);
  }
});

reloadInactiveUsersBtn?.addEventListener("click", async () => {
  try {
    await loadManagedUsers("user", document.getElementById("inactiveUserSearchQ")?.value || "");
    await loadDirectoryUsers();
    showToast("비활성 사용자 목록을 새로고침했습니다.");
  } catch (error) {
    showToast(error.message);
  }
});

reloadAdminsBtn?.addEventListener("click", async () => {
  try {
    await loadManagedUsers("admin", document.getElementById("adminSearchQ")?.value || "");
    showToast("관리자 목록을 새로고침했습니다.");
  } catch (error) {
    showToast(error.message);
  }
});



reloadOrgChartBtn?.addEventListener("click", async () => {
  try {
    await loadManagedUsers("user", document.getElementById("orgChartSearchQ")?.value || "");
    showToast("\uC870\uC9C1\uB3C4\uB97C \uC0C8\uB85C\uACE0\uCE68\uD588\uC2B5\uB2C8\uB2E4.");
  } catch (error) {
    showToast(error.message);
  }
});

orgChartShowInactiveInput?.addEventListener("change", () => {
  state.orgChartShowInactive = Boolean(orgChartShowInactiveInput.checked);
  renderOrgChart(state.managedUsers || []);
});

orgChartToggleDeptExpandBtn?.addEventListener("click", () => {
  state.orgChartDeptExpanded = !state.orgChartDeptExpanded;
  updateOrgChartDeptToggleButton();
  renderOrgChart(state.managedUsers || []);
});

document.getElementById("userFilterForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await loadManagedUsers("user", document.getElementById("userSearchQ")?.value || "");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("inactiveUserFilterForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await loadManagedUsers("user", document.getElementById("inactiveUserSearchQ")?.value || "");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("adminFilterForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await loadManagedUsers("admin", document.getElementById("adminSearchQ")?.value || "");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("orgChartFilterForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await loadManagedUsers("user", document.getElementById("orgChartSearchQ")?.value || "");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("userCreateForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const username = document.getElementById("newUserUsername")?.value.trim();
    const displayName = document.getElementById("newUserDisplayName")?.value.trim() || null;
    const email = document.getElementById("newUserEmail")?.value.trim() || null;

    await api("/directory-users", {
      method: "POST",
      body: JSON.stringify({
        username,
        display_name: displayName,
        email,
      }),
    });

    document.getElementById("newUserUsername").value = "";
    document.getElementById("newUserDisplayName").value = "";
    document.getElementById("newUserEmail").value = "";

    await loadManagedUsers("user", "");
    await loadDirectoryUsers();
    showToast("할당 사용자를 추가했습니다.");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("adminCreateForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const username = document.getElementById("newAdminUsername")?.value.trim();
    const password = document.getElementById("newAdminPassword")?.value;
    await api("/users", {
      method: "POST",
      body: JSON.stringify({ username, password, role: "admin" }),
    });
    document.getElementById("newAdminUsername").value = "";
    document.getElementById("newAdminPassword").value = "";
    await loadManagedUsers("admin", "");
    showToast("관리자 계정을 추가했습니다.");
  } catch (error) {
    showToast(error.message);
  }
});

[usersTableBody, inactiveUsersTableBody, adminsTableBody].forEach((tableBody) => {
  tableBody?.addEventListener("click", async (event) => {
    const toggleBtn = event.target.closest(".user-toggle-btn");
    if (!toggleBtn) return;

    const userId = Number(toggleBtn.dataset.id);
    const role = toggleBtn.dataset.role === "admin" ? "admin" : "user";
    const isActive = toggleBtn.dataset.active === "1";

    try {
      if (role === "admin") {
        await api(`/users/${userId}`, {
          method: "PUT",
          body: JSON.stringify({ is_active: !isActive }),
        });
      } else {
        await api(`/directory-users/${userId}`, {
          method: "PUT",
          body: JSON.stringify({ is_active: !isActive }),
        });
      }

      if (role === "admin") {
        await loadManagedUsers("admin", document.getElementById("adminSearchQ")?.value || "");
      } else {
        const subtab = String(state.settingsAccountsSubtab || "users");
        let query = document.getElementById("userSearchQ")?.value || "";
        if (subtab === "users-inactive") {
          query = document.getElementById("inactiveUserSearchQ")?.value || "";
        } else if (subtab === "orgchart") {
          query = document.getElementById("orgChartSearchQ")?.value || "";
        }
        await loadManagedUsers("user", query);
      }
      if (role === "user") {
        await loadDirectoryUsers();
      }

      showToast(`${role === "admin" ? "관리자" : "사용자"} 상태를 변경했습니다.`);
    } catch (error) {
      showToast(error.message);
    }
  });
});
[summaryCards, statusBoard, usageBoard, categoryBoard].forEach((board) => {
  board.addEventListener("click", async (event) => {
    const metricButton = event.target.closest(".metric-link[data-dashboard-kind]");
    if (!metricButton) return;

    const kind = metricButton.dataset.dashboardKind;
    const value = metricButton.dataset.dashboardValue;

    try {
      await handleDashboardMetricClick(kind, value);
    } catch (error) {
      showToast(error.message);
    }
  });
});

dashboardCostPeriodTabs?.addEventListener("click", (event) => {
  const button = event.target.closest(".period-tab-btn[data-period]");
  if (!button) return;

  const period = String(button.dataset.period || "month");
  if (!["month", "quarter", "year"].includes(period)) return;

  state.dashboardCostPeriod = period;
  renderDashboardCostTrend();
  requestAnimationFrame(syncDashboardCardsHeight);
});


dashboardCostScopeTabs?.addEventListener("click", (event) => {
  const button = event.target.closest(".period-tab-btn[data-scope]");
  if (!button) return;

  const scope = String(button.dataset.scope || "all");
  if (!["all", "required", "general"].includes(scope)) return;

  state.dashboardCostScope = scope;
  renderDashboardCostTrend();
  requestAnimationFrame(syncDashboardCardsHeight);
});

document.getElementById("addUsageType").addEventListener("change", (event) => {
  toggleRentalFields("add", event.target.value);
});

document.getElementById("editUsageType").addEventListener("change", (event) => {
  toggleRentalFields("edit", event.target.value);
});

window.addEventListener("resize", () => {
  requestAnimationFrame(syncDashboardCardsHeight);
});

assetsPrevPageBtn.addEventListener("click", async () => {
  if (state.pagination.page <= 1) return;
  try {
    await loadAssets(state.pagination.page - 1);
  } catch (error) {
    showToast(error.message);
  }
});

assetsNextPageBtn.addEventListener("click", async () => {
  if (!state.pagination.hasNext) return;
  try {
    await loadAssets(state.pagination.page + 1);
  } catch (error) {
    showToast(error.message);
  }
});

disposedTableBody.addEventListener("click", async (event) => {
  const cancelBtn = event.target.closest(".undispose-btn");
  const deleteBtn = event.target.closest(".delete-disposed-btn");
  if (!cancelBtn && !deleteBtn) return;

  const targetButton = cancelBtn || deleteBtn;
  const assetId = Number(targetButton.dataset.id);
  if (!assetId) return;

  if (cancelBtn) {
    const confirmed = confirm("이 자산의 폐기완료를 취소하고 대기 상태로 복원할까요?");
    if (!confirmed) return;

    try {
      await api(`/assets/${assetId}`, {
        method: "PUT",
        body: JSON.stringify({ status: "대기" }),
      });
      showToast("폐기완료가 취소되어 대기 상태로 복원되었습니다.");
      await refreshDashboardAndAssets();
    } catch (error) {
      showToast(error.message);
    }
    return;
  }

  const confirmedDelete = confirm("폐기완료 자산을 영구 삭제할까요? 이 작업은 되돌릴 수 없습니다.");
  if (!confirmedDelete) return;

  try {
    await api(`/assets/${assetId}`, {
      method: "DELETE",
    });
    showToast("폐기완료 자산을 삭제했습니다.");
    await refreshDashboardAndAssets();
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("assetFilterForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  state.dashboardDrilldown = null;
  state.pagination.page = 1;
  try {
    await loadAssets(1);
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("addGenerateAssetCodeBtn").addEventListener("click", async () => {
  try {
    await generateAssetCode("add");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("editGenerateAssetCodeBtn").addEventListener("click", async () => {
  try {
    await generateAssetCode("edit");
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("saveExchangeRateBtn")?.addEventListener("click", async () => {
  try {
    if (!isAdminUser()) {
      throw new Error("환율 변경은 관리자만 가능합니다.");
    }

    const rateInput = document.getElementById("settingUsdKrwRate");
    const dateInput = document.getElementById("settingExchangeRateDate");
    const usdKrw = Number(rateInput?.value || "");
    const effectiveDate = String(dateInput?.value || "").trim() || TODAY_ISO;

    if (!Number.isFinite(usdKrw) || usdKrw <= 0) {
      throw new Error("환율은 0보다 큰 숫자로 입력해주세요.");
    }

    const saved = await api("/settings/exchange-rate", {
      method: "PUT",
      body: JSON.stringify({
        usd_krw: usdKrw,
        effective_date: effectiveDate,
      }),
    });

    state.settings.exchangeRate = normalizeExchangeRateSetting(saved);
    applyExchangeRateInputs();
    await Promise.all([loadDashboard(), loadSoftwareLicenses()]);
    showToast("오늘 환율을 저장했습니다.");
  } catch (error) {
    showToast(error.message || "환율 저장에 실패했습니다.");
  }
});


document.getElementById("saveSmtpConfigBtn")?.addEventListener("click", async () => {
  try {
    if (!isAdminUser()) {
      throw new Error("SMTP 설정 변경은 관리자만 가능합니다.");
    }

    const payload = readMailSmtpForm();
    const saved = await api("/settings/mail/smtp", {
      method: "PUT",
      body: JSON.stringify(payload),
    });

    state.settings.mailSmtp = normalizeMailSmtpSetting(saved);
    applyMailSmtpInputs();
    showToast("SMTP 설정을 저장했습니다.");
  } catch (error) {
    showToast(error.message || "SMTP 설정 저장에 실패했습니다.");
  }
});


document.getElementById("saveAdminMailBtn")?.addEventListener("click", async () => {
  try {
    if (!isAdminUser()) {
      throw new Error("관리자 메일 설정 변경은 관리자만 가능합니다.");
    }

    const payload = readAdminMailForm();
    const saved = await api("/settings/mail/admin", {
      method: "PUT",
      body: JSON.stringify(payload),
    });

    state.settings.mailAdmin = normalizeMailAdminSetting(saved);
    applyMailAdminInputs();
    showToast("관리자 메일 설정을 저장했습니다.");
  } catch (error) {
    showToast(error.message || "관리자 메일 설정 저장에 실패했습니다.");
  }
});


document.getElementById("saveUserMailBtn")?.addEventListener("click", async () => {
  try {
    if (!isAdminUser()) {
      throw new Error("사용자 메일 설정 변경은 관리자만 가능합니다.");
    }

    const payload = readUserMailForm();
    const saved = await api("/settings/mail/user", {
      method: "PUT",
      body: JSON.stringify(payload),
    });

    state.settings.mailUser = normalizeMailUserSetting(saved);
    applyMailUserInputs();
    showToast("사용자 메일 설정을 저장했습니다.");
  } catch (error) {
    showToast(error.message || "사용자 메일 설정 저장에 실패했습니다.");
  }
});


document.getElementById("previewUserMailTargetsBtn")?.addEventListener("click", async () => {
  try {
    if (!isAdminUser()) {
      throw new Error("대상자 미리보기는 관리자만 가능합니다.");
    }

    const payload = readUserMailForm();
    if (userMailPreviewSummary) {
      userMailPreviewSummary.textContent = "대상자 정보를 불러오는 중입니다.";
    }
    if (userMailPreviewTableBody) {
      userMailPreviewTableBody.innerHTML = '<tr><td colspan="5">불러오는 중...</td></tr>';
    }
    userMailPreviewModal?.classList.remove("hidden");

    const preview = await api("/settings/mail/user/preview-targets", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    renderUserMailPreviewModal(preview);
  } catch (error) {
    closeUserMailPreviewModal();
    showToast(error.message || "대상자 미리보기를 불러오지 못했습니다.");
  }
});

document.getElementById("sendAdminMailNowBtn")?.addEventListener("click", async () => {
  try {
    if (!isAdminUser()) {
      throw new Error("즉시 발송은 관리자만 가능합니다.");
    }

    const password = String(document.getElementById("smtpPassword")?.value || "").trim() || null;
    const result = await api("/settings/mail/admin/send-now", {
      method: "POST",
      body: JSON.stringify({ smtp_password: password }),
    });

    await loadMailAdminSetting();
    await loadMailSmtpSetting();
    showToast(result?.message || "관리자 메일을 발송했습니다.");
  } catch (error) {
    showToast(error.message || "관리자 메일 발송에 실패했습니다.");
  }
});


document.getElementById("sendUserMailNowBtn")?.addEventListener("click", async () => {
  try {
    if (!isAdminUser()) {
      throw new Error("즉시 발송은 관리자만 가능합니다.");
    }

    const password = String(document.getElementById("smtpPassword")?.value || "").trim() || null;
    const result = await api("/settings/mail/user/send-now", {
      method: "POST",
      body: JSON.stringify({ smtp_password: password }),
    });

    await loadMailUserSetting();
    await loadMailSmtpSetting();
    showToast(result?.message || "사용자 메일을 발송했습니다.");
  } catch (error) {
    showToast(error.message || "사용자 메일 발송에 실패했습니다.");
  }
});

document.getElementById("saveCodeSettingBtn").addEventListener("click", () => {
  const template = document.getElementById("settingAssetCodeTemplate").value.trim() || DEFAULTS.codeTemplate;
  state.settings.codeTemplate = template;
  persistSettings();
  updateCodePreview();
  applyLdapInputs();
  applySoftwareMailInputs();
  syncSoftwareMetaControls();
  showToast("자산코드 양식을 저장했습니다.");
});

document.getElementById("previewCodeSettingBtn").addEventListener("click", () => {
  const template = document.getElementById("settingAssetCodeTemplate").value.trim() || DEFAULTS.codeTemplate;
  state.settings.codeTemplate = template;
  updateCodePreview();
  applyLdapInputs();
  applySoftwareMailInputs();
  syncSoftwareMetaControls();
});

document.getElementById("saveDefaultSettingBtn").addEventListener("click", () => {
  state.settings.defaultOwner = document.getElementById("settingDefaultOwner").value.trim() || DEFAULTS.defaultOwner;
  state.settings.defaultManager = document.getElementById("settingDefaultManager").value.trim() || DEFAULTS.defaultManager;
  persistSettings();
  resetAddForm();
  showToast("기본값 설정을 저장했습니다.");
});

document.getElementById("addCategorySettingBtn").addEventListener("click", () => {
  const nameInput = document.getElementById("settingCategoryName");
  const tokenInput = document.getElementById("settingCategoryToken");

  const name = nameInput.value.trim();
  if (!name) {
    showToast("카테고리명을 입력해주세요.");
    nameInput.focus();
    return;
  }

  const token = sanitizeTokenValue(tokenInput.value.trim() || name, "CAT");
  const key = name.toLocaleLowerCase();
  const index = state.settings.categories.findIndex((item) => item.name.toLocaleLowerCase() === key);

  if (index >= 0) {
    state.settings.categories[index] = { name, token };
    showToast("카테고리 설정을 수정했습니다.");
  } else {
    state.settings.categories.push({ name, token });
    showToast("카테고리를 추가했습니다.");
  }

  state.settings.categories = normalizeCategorySettings(state.settings.categories);
  persistSettings();

  const editCategoryValue = document.getElementById("editCategory")?.value || "";
  const filterCategoryValue = document.getElementById("filterCategory")?.value || "";
  syncCategorySelects(name, editCategoryValue);
  syncFilterCategorySelect(filterCategoryValue || name);
  renderCategorySettingTable();
  setCategorySettingInputs();
  updateCodePreview();
  applyLdapInputs();
  applySoftwareMailInputs();
  syncSoftwareMetaControls();
});

document.getElementById("clearCategorySettingBtn").addEventListener("click", () => {
  setCategorySettingInputs();
});

document.getElementById("settingCategoryTableBody").addEventListener("click", (event) => {
  const actionButton = event.target.closest("button[data-action]");
  if (!actionButton) return;

  const index = Number(actionButton.dataset.index);
  const item = state.settings.categories[index];
  if (!item) return;

  if (actionButton.dataset.action === "edit") {
    setCategorySettingInputs(item.name, item.token);
    return;
  }

  if (state.settings.categories.length <= 1) {
    showToast("카테고리는 최소 1개 이상 필요합니다.");
    return;
  }

  state.settings.categories.splice(index, 1);
  state.settings.categories = normalizeCategorySettings(state.settings.categories);
  persistSettings();

  const addCategoryValue = document.getElementById("addCategory")?.value || "";
  const editCategoryValue = document.getElementById("editCategory")?.value || "";
  const filterCategoryValue = document.getElementById("filterCategory")?.value || "";
  syncCategorySelects(addCategoryValue, editCategoryValue);
  syncFilterCategorySelect(filterCategoryValue);
  renderCategorySettingTable();
  setCategorySettingInputs();
  updateCodePreview();
  applyLdapInputs();
  applySoftwareMailInputs();
  syncSoftwareMetaControls();
  showToast("카테고리를 삭제했습니다.");
});

document.getElementById("addAssetForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  try {
    const payload = readCommonForm("add");
    const normalizedOwner = await normalizeOwnerByStatus(payload.status, payload.owner, "자산등록");
    if (normalizedOwner === null) return;
    payload.owner = normalizedOwner;

    await api("/assets", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    resetAddForm();
    showToast("자산이 등록되었습니다.");
    await refreshDashboardAndAssets();
    activateTab("assets");
  } catch (error) {
    showToast(error.message);
  }
});

assetTableBody.addEventListener("click", async (event) => {
  const applyInlineBtn = event.target.closest(".apply-inline-btn");
  if (applyInlineBtn) {
    event.stopPropagation();
    try {
      await applyInlineUpdate(Number(applyInlineBtn.dataset.id));
    } catch (error) {
      showToast(error.message);
    }
    return;
  }

  if (event.target.closest(".inline-edit")) {
    event.stopPropagation();
    return;
  }

  const historyBtn = event.target.closest(".history-btn");
  if (historyBtn) {
    event.stopPropagation();
    try {
      await openEditModal(Number(historyBtn.dataset.id));
    } catch (error) {
      showToast(error.message);
    }
    return;
  }

  const row = event.target.closest("tr[data-id]");
  if (!row) return;

  try {
    await openEditModal(Number(row.dataset.id));
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("editAssetForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!state.currentAssetId) {
    showToast("수정할 자산을 다시 선택해주세요.");
    return;
  }

  try {
    const payload = readCommonForm("edit");
    const normalizedOwner = await normalizeOwnerByStatus(payload.status, payload.owner, "자산수정");
    if (normalizedOwner === null) return;
    payload.owner = normalizedOwner;

    await api(`/assets/${state.currentAssetId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });

    showToast("자산 정보가 수정되었습니다.");
    await refreshDashboardAndAssets();
    await openHistoryInModal(state.currentAssetId);
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("closeEditModalBtn").addEventListener("click", closeEditModal);

editModal.addEventListener("click", (event) => {
  if (event.target === editModal) closeEditModal();
});

async function initialize() {
  setupOwnerLookupInputs();
  bindOwnerDepartmentSync("add");
  bindOwnerDepartmentSync("edit");
  applySettingInputs();
  resetAddForm();
  resetSoftwareForm();
  updateAuthView();
  applyRoleTabVisibility();
  updateLdapPasswordStatus();
  renderUsersTable("user");
  renderUsersTable("admin");

  if (!state.token) return;

  try {
    state.user = await api("/me");
    updateAuthView();
    applyRoleTabVisibility();
    activateTab("dashboard");
    await refreshDashboardAndAssets();
    await refreshUserDataSources();
    if (isAdminUser()) {
      await loadLdapSchedule();
    }
  } catch {
    state.token = "";
    state.user = null;
    localStorage.removeItem(STORAGE_KEYS.token);
    updateAuthView();
    applyRoleTabVisibility();
  }
}

initialize();





























































































































































































































































