const STORAGE_KEYS = {
  token: "token",
  codeTemplate: "setting.asset_code_template",
  defaultOwner: "setting.default_owner",
  defaultManager: "setting.default_manager",
  categories: "setting.asset_categories",
  seq: "asset_code_seq",
  ldapConfig: "setting.ldap_config",
  softwareLicenseTypes: "setting.software_license_types",
  softwareVendors: "setting.software_vendors",
};

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
    size_limit: 1000,
  },
  softwareLicenseTypes: ["구독", "영구"],
  softwareVendors: [],
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
    last_synced_at: null,
    last_error: null,
    last_result: null,
  },
  activeMainTab: "dashboard",
  hardwareSubtab: "assets",
  softwareSubtab: "editor",
  pagination: {
    page: 1,
    pageSize: 50,
    hasNext: false,
  },
  dashboardDrilldown: null,
  dashboardSummary: null,
  settingsSubtab: "general",
  settings: {
    codeTemplate: localStorage.getItem(STORAGE_KEYS.codeTemplate) || DEFAULTS.codeTemplate,
    defaultOwner: localStorage.getItem(STORAGE_KEYS.defaultOwner) || DEFAULTS.defaultOwner,
    defaultManager: localStorage.getItem(STORAGE_KEYS.defaultManager) || DEFAULTS.defaultManager,
    categories: loadCategorySettings(),
    ldapConfig: loadLdapConfig(),
    softwareLicenseTypes: loadSoftwareMetaList(STORAGE_KEYS.softwareLicenseTypes, DEFAULTS.softwareLicenseTypes),
    softwareVendors: loadSoftwareMetaList(STORAGE_KEYS.softwareVendors, DEFAULTS.softwareVendors),
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
const toast = document.getElementById("toast");
const summaryCards = document.getElementById("summaryCards");
const softwareSummaryCards = document.getElementById("softwareSummaryCards");
const statusBoard = document.getElementById("statusBoard");
const usageBoard = document.getElementById("usageBoard");
const categoryBoard = document.getElementById("categoryBoard");
const assetTableBody = document.getElementById("assetTableBody");
const disposedTableBody = document.getElementById("disposedTableBody");
const softwareTableBody = document.getElementById("softwareTableBody");
const softwareAssignUserTableBody = document.getElementById("softwareAssignUserTableBody");
const softwareTypeTableBody = document.getElementById("softwareTypeTableBody");
const softwareVendorTableBody = document.getElementById("softwareVendorTableBody");
const assetsPrevPageBtn = document.getElementById("assetsPrevPageBtn");
const assetsNextPageBtn = document.getElementById("assetsNextPageBtn");
const assetsPageInfo = document.getElementById("assetsPageInfo");
const editModal = document.getElementById("editModal");
const editHistoryBox = document.getElementById("editHistoryBox");
const ldapResultBody = document.getElementById("ldapResultBody");
const ldapResultInfo = document.getElementById("ldapResultInfo");
const ldapPasswordStatus = document.getElementById("ldapPasswordStatus");
const ldapScheduleInfo = document.getElementById("ldapScheduleInfo");
const directoryUserDatalist = document.getElementById("directoryUserDatalist");
const adminUserDatalist = document.getElementById("adminUserDatalist");
const softwareVendorDatalist = document.getElementById("softwareVendorDatalist");
const usersTableBody = document.getElementById("usersTableBody");
const adminsTableBody = document.getElementById("adminsTableBody");
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
  ldapPasswordStatus.textContent = state.ldapSession.bindPassword ? "비밀번호 설정됨(세션 메모리)" : "비밀번호 미설정";
}

function renderUsersTable(role) {
  const tableBody = role === "admin" ? adminsTableBody : usersTableBody;
  if (!tableBody) return;

  const rows = role === "admin" ? state.managedAdmins : state.managedUsers;
  if (!rows.length) {
    const emptyColspan = role === "admin" ? 5 : 7;
    tableBody.innerHTML = `<tr><td colspan="${emptyColspan}">등록된 ${role === "admin" ? "관리자" : "사용자"}가 없습니다.</td></tr>`;
    return;
  }

  if (role === "admin") {
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
  params.set("limit", "1000");
  params.set("include_inactive", "true");
  if (q.trim()) params.set("q", q.trim());

  const rows = await api(`/directory-users?${params.toString()}`);
  state.managedUsers = rows;
  renderUsersTable("user");
}

async function loadDirectoryUsers(q = "") {
  const params = new URLSearchParams();
  params.set("limit", "1000");
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
  const runtimePassword = schedule.has_runtime_password ? "설정됨" : "미설정";
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

  document.getElementById("ldapScheduleEnabled").checked = Boolean(state.ldapSchedule.enabled);
  document.getElementById("ldapScheduleInterval").value = state.ldapSchedule.interval_minutes || 60;
  renderLdapScheduleInfo();
}

async function refreshUserDataSources() {
  await loadDirectoryUsers();
  if (state.user?.role === "admin") {
    await Promise.all([loadManagedUsers("user"), loadManagedUsers("admin")]);
  }
}

function activateSettingsSubtab(subtabName = "general") {
  const isAdmin = state.user?.role === "admin";
  const requested = String(subtabName || "general");
  const target = !isAdmin && requested !== "general" ? "general" : requested;

  state.settingsSubtab = target;

  document.querySelectorAll(".subtab-btn[data-settings-tab]").forEach((button) => {
    const isActive = button.dataset.settingsTab === target;
    button.classList.toggle("active", isActive);
  });

  document.querySelectorAll(".settings-subtab-section").forEach((section) => {
    section.classList.toggle("active", section.id === `settings-subtab-${target}`);
  });
}

async function loadSettingsSubtabData(subtabName = "general") {
  if (!state.token) return;
  const target = String(subtabName || "general");

  if (target === "users" && state.user?.role === "admin") {
    await loadManagedUsers("user", document.getElementById("userSearchQ")?.value || "");
    return;
  }

  if (target === "admins" && state.user?.role === "admin") {
    await loadManagedUsers("admin", document.getElementById("adminSearchQ")?.value || "");
    return;
  }

  if (target === "ldap" && state.user?.role === "admin") {
    await loadLdapSchedule();
  }
}

function applyRoleTabVisibility() {
  const isAdmin = state.user?.role === "admin";

  document.querySelectorAll("[data-admin-only]").forEach((el) => {
    el.classList.toggle("hidden", !isAdmin);
  });

  if (!isAdmin && state.settingsSubtab !== "general") {
    state.settingsSubtab = "general";
  }

  activateSettingsSubtab(state.settingsSubtab || "general");
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
  const headers = {
    "Content-Type": "application/json",
    ...authHeaders(),
    ...(options.headers || {}),
  };

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

const hardwareTabKeys = new Set(["assets", "add", "disposed"]);
const softwareTabKeys = new Set(["editor", "list", "info", "assignment"]);
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

function activateSoftwareSubtab(subtabName = "editor") {
  const target = softwareTabKeys.has(subtabName) ? subtabName : "editor";

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
    activateSoftwareSubtab(state.softwareSubtab || "editor");
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
  requestAnimationFrame(syncDashboardCardsHeight);
}

function renderSoftwareSummary(summary = state.dashboardSummary || {}) {
  if (!softwareSummaryCards) return;
  const softwareCount = Array.isArray(state.softwareLicensesAll) ? state.softwareLicensesAll.length : (Array.isArray(state.softwareLicenses) ? state.softwareLicenses.length : 0);

  const cards = [
    { title: "전체 라이선스", value: summary.total_software ?? softwareCount },
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
  const filterExpiring = document.getElementById("softwareFilterExpiring");
  const filterType = document.getElementById("softwareFilterType");
  const filterVendor = document.getElementById("softwareFilterVendor");

  if (filterExpiring) {
    if (mode === "software_30d") {
      filterExpiring.value = "30";
    } else if (mode === "software_expired") {
      filterExpiring.value = "expired";
    } else {
      filterExpiring.value = "";
    }
  }

  if (filterType) filterType.value = "";
  if (filterVendor) filterVendor.value = "";

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

function getSoftwareTypeOptions() {
  const base = normalizeSoftwareMetaList(state.settings.softwareLicenseTypes, DEFAULTS.softwareLicenseTypes);
  const seen = new Set(base.map((value) => value.toLocaleLowerCase()));

  getSoftwareRowsForSelection().forEach((row) => {
    const value = String(row.license_type || "").trim();
    if (!value) return;
    const key = value.toLocaleLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    base.push(value);
  });

  return base;
}

function getSoftwareVendorOptions() {
  const base = normalizeSoftwareMetaList(state.settings.softwareVendors, DEFAULTS.softwareVendors);
  const seen = new Set(base.map((value) => value.toLocaleLowerCase()));

  getSoftwareRowsForSelection().forEach((row) => {
    const value = String(row.vendor || "").trim();
    if (!value) return;
    const key = value.toLocaleLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    base.push(value);
  });

  return base;
}

function renderSoftwareMetaTables() {
  if (softwareTypeTableBody) {
    const rows = getSoftwareTypeOptions();
    softwareTypeTableBody.innerHTML = rows
      .map(
        (value) => `
          <tr>
            <td>${escapeHtml(value)}</td>
            <td>
              <button type="button" class="mini-btn danger software-meta-remove-btn" data-kind="type" data-value="${escapeHtml(value)}">삭제</button>
            </td>
          </tr>
        `,
      )
      .join("");
  }

  if (softwareVendorTableBody) {
    const rows = getSoftwareVendorOptions();
    softwareVendorTableBody.innerHTML = rows
      .map(
        (value) => `
          <tr>
            <td>${escapeHtml(value)}</td>
            <td>
              <button type="button" class="mini-btn danger software-meta-remove-btn" data-kind="vendor" data-value="${escapeHtml(value)}">삭제</button>
            </td>
          </tr>
        `,
      )
      .join("");
  }
}

function syncSoftwareMetaControls() {
  state.settings.softwareLicenseTypes = normalizeSoftwareMetaList(state.settings.softwareLicenseTypes, DEFAULTS.softwareLicenseTypes);
  state.settings.softwareVendors = normalizeSoftwareMetaList(state.settings.softwareVendors, DEFAULTS.softwareVendors);

  const typeOptions = getSoftwareTypeOptions();
  const vendorOptions = getSoftwareVendorOptions();

  const swLicenseType = document.getElementById("swLicenseType");
  if (swLicenseType) {
    const current = swLicenseType.value || "구독";
    swLicenseType.innerHTML = makeOptions(typeOptions, current);
    if (![...swLicenseType.options].some((option) => option.value === current)) {
      swLicenseType.value = typeOptions[0] || "구독";
    }
  }

  const filterType = document.getElementById("softwareFilterType");
  if (filterType) {
    const current = filterType.value || "";
    filterType.innerHTML = `<option value="">전체 유형</option>${makeOptions(typeOptions, current)}`;
    filterType.value = current;
  }

  if (softwareVendorDatalist) {
    softwareVendorDatalist.innerHTML = vendorOptions
      .map((value) => `<option value="${escapeHtml(value)}"></option>`)
      .join("");
  }

  const filterVendor = document.getElementById("softwareFilterVendor");
  if (filterVendor) {
    const current = filterVendor.value || "";
    filterVendor.innerHTML = `<option value="">전체 공급사</option>${makeOptions(vendorOptions, current)}`;
    filterVendor.value = current;
  }

  renderSoftwareMetaTables();
}

function renderSoftwareEditTargetOptions(selectedId = "") {
  const select = document.getElementById("swEditTarget");
  if (!select) return;

  const current = String(selectedId || select.value || "");
  const options = getSoftwareRowsForSelection()
    .map((row) => {
      const vendor = row.vendor ? ` / ${row.vendor}` : "";
      return `<option value="${row.id}">${escapeHtml(row.product_name || `라이선스#${row.id}`)}${escapeHtml(vendor)}</option>`;
    })
    .join("");

  select.innerHTML = `<option value="">신규 라이선스 등록</option>${options}`;
  select.value = current;
}

function renderSoftwareAssignmentLicenseOptions(selectedId = "") {
  const select = document.getElementById("softwareAssignLicenseSelect");
  if (!select) return;

  const current = String(selectedId || select.value || "");
  const options = getSoftwareRowsForSelection()
    .map((row) => `<option value="${row.id}">${escapeHtml(row.product_name || `라이선스#${row.id}`)}</option>`)
    .join("");

  select.innerHTML = `<option value="">라이선스를 선택하세요</option>${options}`;
  select.value = current;
}

function getSoftwareAssigneesFromForm() {
  return [];
}

function readSoftwareFormPayload() {
  const productName = document.getElementById("swProductName")?.value.trim() || "";
  if (!productName) {
    throw new Error("라이선스명을 입력해주세요.");
  }

  const totalQuantity = Number(document.getElementById("swTotalQuantity")?.value || 1);
  if (!Number.isFinite(totalQuantity) || totalQuantity < 1) {
    throw new Error("총 라이선스 수량은 1 이상이어야 합니다.");
  }

  const startDate = document.getElementById("swStartDate")?.value || null;
  const endDate = document.getElementById("swEndDate")?.value || null;
  if (startDate && endDate && endDate < startDate) {
    throw new Error("만료일은 시작일보다 빠를 수 없습니다.");
  }

  return {
    product_name: productName,
    vendor: document.getElementById("swVendor")?.value.trim() || null,
    license_type: document.getElementById("swLicenseType")?.value || "구독",
    total_quantity: Math.floor(totalQuantity),
    start_date: startDate,
    end_date: endDate,
    drafter: document.getElementById("swDrafter")?.value.trim() || null,
    notes: document.getElementById("swNotes")?.value.trim() || null,
  };
}

function resetSoftwareForm() {
  const form = document.getElementById("softwareForm");
  if (!form) return;

  form.reset();
  document.getElementById("swId").value = "";
  const swEditTarget = document.getElementById("swEditTarget");
  if (swEditTarget) swEditTarget.value = "";

  const typeOptions = getSoftwareTypeOptions();
  document.getElementById("swLicenseType").innerHTML = makeOptions(typeOptions, "구독");
  document.getElementById("swLicenseType").value = typeOptions.includes("구독") ? "구독" : typeOptions[0] || "구독";
  document.getElementById("swTotalQuantity").value = "1";

  const saveBtn = document.getElementById("saveSoftwareBtn");
  if (saveBtn) saveBtn.textContent = "라이선스 저장";
}

function fillSoftwareForm(row) {
  document.getElementById("swId").value = String(row.id || "");
  const swEditTarget = document.getElementById("swEditTarget");
  if (swEditTarget) swEditTarget.value = String(row.id || "");

  document.getElementById("swProductName").value = row.product_name || "";
  document.getElementById("swVendor").value = row.vendor || "";

  const typeOptions = getSoftwareTypeOptions();
  const typeValue = row.license_type || typeOptions[0] || "구독";
  document.getElementById("swLicenseType").innerHTML = makeOptions(typeOptions, typeValue);
  document.getElementById("swLicenseType").value = typeValue;

  document.getElementById("swTotalQuantity").value = String(row.total_quantity || 1);
  document.getElementById("swStartDate").value = row.start_date || "";
  document.getElementById("swEndDate").value = row.end_date || "";
  document.getElementById("swDrafter").value = row.drafter || "";
  document.getElementById("swNotes").value = row.notes || "";

  const saveBtn = document.getElementById("saveSoftwareBtn");
  if (saveBtn) saveBtn.textContent = "라이선스 수정 저장";
}

function renderSoftwareRows() {
  if (!softwareTableBody) return;

  if (!state.softwareLicenses.length) {
    softwareTableBody.innerHTML = '<tr><td colspan="9">등록된 라이선스가 없습니다.</td></tr>';
    return;
  }

  const today = new Date();
  const todayKey = new Date(today.getFullYear(), today.getMonth(), today.getDate()).toISOString().slice(0, 10);

  softwareTableBody.innerHTML = state.softwareLicenses
    .map((row) => {
      const assignees = Array.isArray(row.assignees) ? row.assignees : [];
      const assigneeText = assignees.length ? assignees.map((u) => getOwnerDisplayName(u)).join(", ") : "-";
      const totalQty = Number(row.total_quantity || 0);
      const endDate = row.end_date || "";
      const expired = Boolean(endDate && endDate < todayKey);
      const statusText = expired ? "만료" : "사용중";

      return `
        <tr>
          <td>${escapeHtml(row.product_name || "-")}</td>
          <td>${escapeHtml(row.vendor || "-")}</td>
          <td>${escapeHtml(row.license_type || "-")}</td>
          <td>${assignees.length}/${Number.isFinite(totalQty) ? totalQty : 0}</td>
          <td>${escapeHtml(row.start_date || "-")}</td>
          <td>${escapeHtml(endDate || "-")} <span class="muted">(${statusText})</span></td>
          <td>${escapeHtml(row.drafter || "-")}</td>
          <td>${escapeHtml(assigneeText)}</td>
          <td>
            <button type="button" class="mini-btn software-edit-btn" data-id="${row.id}">수정</button>
            <button type="button" class="mini-btn danger software-delete-btn" data-id="${row.id}">삭제</button>
          </td>
        </tr>
      `;
    })
    .join("");
}

function buildSoftwareQueryParams() {
  const params = new URLSearchParams();

  const q = document.getElementById("softwareFilterQ")?.value.trim() || "";
  if (q) params.set("q", q);

  const expiring = document.getElementById("softwareFilterExpiring")?.value || "";
  if (expiring === "30") {
    params.set("expiring_days", "30");
  } else if (expiring === "expired") {
    params.set("expired_only", "true");
  }

  params.set("skip", "0");
  params.set("limit", "500");
  return params;
}

function renderSoftwareAssignmentPanel() {
  if (!softwareAssignUserTableBody) return;

  const select = document.getElementById("softwareAssignLicenseSelect");
  const summary = document.getElementById("softwareAssignSummary");
  const query = String(document.getElementById("softwareAssignSearch")?.value || "").trim().toLocaleLowerCase();

  const selectedId = Number(select?.value || 0);
  const license = findSoftwareLicenseById(selectedId);

  if (!license) {
    softwareAssignUserTableBody.innerHTML = '<tr><td colspan="5">라이선스를 선택해주세요.</td></tr>';
    if (summary) summary.textContent = "라이선스를 선택하면 사용자 할당 상태를 관리할 수 있습니다.";
    return;
  }

  const assignees = Array.isArray(license.assignees) ? license.assignees.map((v) => String(v || "").trim()).filter(Boolean) : [];
  const assignedSet = new Set(assignees);
  const totalQuantity = Math.max(1, Number(license.total_quantity || 1));

  if (summary) {
    summary.textContent = `${license.product_name || `라이선스 #${license.id}`} - 할당 ${assignees.length}/${totalQuantity}`;
  }

  let users = Array.isArray(state.directoryUsers) ? state.directoryUsers : [];
  if (query) {
    users = users.filter((user) => {
      const username = String(user.username || "").toLocaleLowerCase();
      const displayName = String(user.display_name || "").toLocaleLowerCase();
      return username.includes(query) || displayName.includes(query);
    });
  }

  if (!users.length) {
    softwareAssignUserTableBody.innerHTML = '<tr><td colspan="5">검색 조건에 맞는 사용자가 없습니다.</td></tr>';
    return;
  }

  softwareAssignUserTableBody.innerHTML = users
    .map((user) => {
      const username = String(user.username || "").trim();
      const isAssigned = assignedSet.has(username);
      const atCapacity = assignees.length >= totalQuantity;
      const canAssign = !isAssigned && !atCapacity;
      const action = isAssigned ? "remove" : "assign";
      const disabled = !isAssigned && !canAssign ? "disabled" : "";

      return `
        <tr>
          <td>${escapeHtml(username || "-")}</td>
          <td>${escapeHtml(user.display_name || "-")}</td>
          <td>${escapeHtml(user.department || "-")}</td>
          <td><span class="software-assign-status ${isAssigned ? "" : "off"}">${isAssigned ? "할당됨" : "미할당"}</span></td>
          <td>
            <button
              type="button"
              class="mini-btn software-assignment-action-btn ${isAssigned ? "danger" : ""}"
              data-license-id="${license.id}"
              data-username="${escapeHtml(username)}"
              data-action="${action}"
              ${disabled}
            >
              ${isAssigned ? "할당 해제" : (canAssign ? "할당" : "수량초과")}
            </button>
          </td>
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

  const assignees = Array.isArray(license.assignees) ? license.assignees.map((v) => String(v || "").trim()).filter(Boolean) : [];
  const totalQuantity = Math.max(1, Number(license.total_quantity || 1));
  let next = [...assignees];

  if (action === "assign") {
    if (next.includes(userKey)) return;
    if (next.length >= totalQuantity) {
      throw new Error("총 라이선스 수량을 초과하여 할당할 수 없습니다.");
    }
    next.push(userKey);
  } else {
    next = next.filter((value) => value !== userKey);
  }

  await api(`/software-licenses/${license.id}`, {
    method: "PUT",
    body: JSON.stringify({ assignees: next }),
  });

  await Promise.all([loadSoftwareLicenses(), loadDashboard()]);
}

async function loadSoftwareLicenses() {
  if (!state.token) return;

  const prevEditId = document.getElementById("swEditTarget")?.value || "";
  const prevAssignId = document.getElementById("softwareAssignLicenseSelect")?.value || "";

  const params = buildSoftwareQueryParams();
  const rows = await api(`/software-licenses?${params.toString()}`);
  let filtered = Array.isArray(rows) ? rows : [];

  const typeFilter = String(document.getElementById("softwareFilterType")?.value || "").trim();
  if (typeFilter) {
    filtered = filtered.filter((row) => String(row.license_type || "").trim() === typeFilter);
  }

  const vendorFilter = String(document.getElementById("softwareFilterVendor")?.value || "").trim();
  if (vendorFilter) {
    filtered = filtered.filter((row) => String(row.vendor || "").trim() === vendorFilter);
  }

  state.softwareLicenses = filtered;

  const allRows = await api("/software-licenses?skip=0&limit=1000");
  state.softwareLicensesAll = Array.isArray(allRows) ? allRows : [];

  renderSoftwareRows();
  renderSoftwareSummary();
  syncSoftwareMetaControls();
  renderSoftwareEditTargetOptions(prevEditId);
  renderSoftwareAssignmentLicenseOptions(prevAssignId);
  renderSoftwareAssignmentPanel();
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

function applyLdapInputs() {
  const config = state.settings.ldapConfig || { ...DEFAULTS.ldapConfig };

  const serverUrl = document.getElementById("ldapServerUrl");
  const useSsl = document.getElementById("ldapUseSsl");
  const port = document.getElementById("ldapPort");
  const bindDn = document.getElementById("ldapBindDn");
  const baseDn = document.getElementById("ldapBaseDn");
  const userIdAttr = document.getElementById("ldapUserIdAttr");
  const userNameAttr = document.getElementById("ldapUserNameAttr");
  const userEmailAttr = document.getElementById("ldapUserEmailAttr");
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
  sizeLimit.value = config.size_limit || 1000;

  if (ldapResultInfo) ldapResultInfo.textContent = "검색 결과가 없습니다.";
  if (ldapResultBody) ldapResultBody.innerHTML = "";
  state.lastLdapSearchUsers = [];
  const importBtn = document.getElementById("ldapImportSearchResultBtn");
  if (importBtn) importBtn.disabled = true;

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
    }))
    .filter((row) => row.username);

  const importBtn = document.getElementById("ldapImportSearchResultBtn");
  if (importBtn) importBtn.disabled = state.lastLdapSearchUsers.length === 0;

  ldapResultInfo.textContent = `검색 결과: ${rows.length}건`;

  if (!rows.length) {
    ldapResultBody.innerHTML = '<tr><td colspan="6">검색 결과가 없습니다.</td></tr>';
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
  localStorage.setItem(STORAGE_KEYS.softwareLicenseTypes, JSON.stringify(state.settings.softwareLicenseTypes));
  localStorage.setItem(STORAGE_KEYS.softwareVendors, JSON.stringify(state.settings.softwareVendors));
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
    if (state.user.role === "admin") {
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
      activateSettingsSubtab(state.settingsSubtab || "general");
      await loadSettingsSubtabData(state.settingsSubtab || "general");
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

  const subtab = button.dataset.settingsTab || "general";
  if (button.dataset.adminOnly === "1" && state.user?.role !== "admin") {
    showToast("관리자 권한이 필요합니다.");
    activateSettingsSubtab("general");
    return;
  }

  activateSettingsSubtab(subtab);

  try {
    await loadSettingsSubtabData(subtab);
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

document.getElementById("softwareFilterForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await loadSoftwareLicenses();
  } catch (error) {
    showToast(error.message);
  }
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

document.getElementById("softwareTypeForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.getElementById("softwareTypeInput");
  const value = String(input?.value || "").trim();
  if (!value) return;

  state.settings.softwareLicenseTypes = normalizeSoftwareMetaList(
    [...(state.settings.softwareLicenseTypes || []), value],
    DEFAULTS.softwareLicenseTypes,
  );
  persistSettings();
  syncSoftwareMetaControls();
  if (input) input.value = "";
  showToast("라이선스 유형을 저장했습니다.");
});

document.getElementById("softwareVendorForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.getElementById("softwareVendorInput");
  const value = String(input?.value || "").trim();
  if (!value) return;

  state.settings.softwareVendors = normalizeSoftwareMetaList(
    [...(state.settings.softwareVendors || []), value],
    DEFAULTS.softwareVendors,
  );
  persistSettings();
  syncSoftwareMetaControls();
  if (input) input.value = "";
  showToast("공급사 템플릿을 저장했습니다.");
});

function handleSoftwareMetaRemove(kind, value) {
  const targetValue = String(value || "").trim();
  if (!targetValue) return;

  if (kind === "type") {
    state.settings.softwareLicenseTypes = normalizeSoftwareMetaList(
      (state.settings.softwareLicenseTypes || []).filter((item) => String(item || "").trim() !== targetValue),
      DEFAULTS.softwareLicenseTypes,
    );
    persistSettings();
    syncSoftwareMetaControls();
    showToast("라이선스 유형을 삭제했습니다.");
    return;
  }

  state.settings.softwareVendors = normalizeSoftwareMetaList(
    (state.settings.softwareVendors || []).filter((item) => String(item || "").trim() !== targetValue),
    DEFAULTS.softwareVendors,
  );
  persistSettings();
  syncSoftwareMetaControls();
  showToast("공급사 템플릿을 삭제했습니다.");
}

softwareTypeTableBody?.addEventListener("click", (event) => {
  const button = event.target.closest(".software-meta-remove-btn");
  if (!button) return;
  handleSoftwareMetaRemove(button.dataset.kind || "type", button.dataset.value || "");
});

softwareVendorTableBody?.addEventListener("click", (event) => {
  const button = event.target.closest(".software-meta-remove-btn");
  if (!button) return;
  handleSoftwareMetaRemove(button.dataset.kind || "vendor", button.dataset.value || "");
});

document.getElementById("softwareAssignLicenseSelect")?.addEventListener("change", () => {
  renderSoftwareAssignmentPanel();
});

document.getElementById("softwareAssignSearch")?.addEventListener("input", () => {
  renderSoftwareAssignmentPanel();
});

softwareAssignUserTableBody?.addEventListener("click", async (event) => {
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
  if (!deleteBtn) return;

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
      size_limit: form.size_limit,
    };
    persistSettings();
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("ldapSyncNowBtn")?.addEventListener("click", async () => {
  try {
    if (state.user?.role !== "admin") {
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
    if (state.user?.role !== "admin") {
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
    if (state.user?.role !== "admin") {
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
const reloadAdminsBtn = document.getElementById("reloadAdminsBtn");

reloadUsersBtn?.addEventListener("click", async () => {
  try {
    await loadManagedUsers("user", document.getElementById("userSearchQ")?.value || "");
    await loadDirectoryUsers();
    showToast("사용자 목록을 새로고침했습니다.");
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

document.getElementById("userFilterForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await loadManagedUsers("user", document.getElementById("userSearchQ")?.value || "");
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

[usersTableBody, adminsTableBody].forEach((tableBody) => {
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

      await loadManagedUsers(role, "");
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

document.getElementById("saveCodeSettingBtn").addEventListener("click", () => {
  const template = document.getElementById("settingAssetCodeTemplate").value.trim() || DEFAULTS.codeTemplate;
  state.settings.codeTemplate = template;
  persistSettings();
  updateCodePreview();
  applyLdapInputs();
  syncSoftwareMetaControls();
  showToast("자산코드 양식을 저장했습니다.");
});

document.getElementById("previewCodeSettingBtn").addEventListener("click", () => {
  const template = document.getElementById("settingAssetCodeTemplate").value.trim() || DEFAULTS.codeTemplate;
  state.settings.codeTemplate = template;
  updateCodePreview();
  applyLdapInputs();
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
    if (state.user.role === "admin") {
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





































































































































