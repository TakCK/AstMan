from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .. import models


@dataclass
class UserAccessScope:
    is_admin: bool
    is_team_lead: bool
    managed_usernames: set[str] = field(default_factory=set)
    subordinate_usernames: set[str] = field(default_factory=set)
    subordinate_org_unit_ids: set[int] = field(default_factory=set)
    asset_owner_values: set[str] = field(default_factory=set)


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip()


def _normalize_key(value: str | None) -> str:
    return _normalize_text(value).lower()


def _normalize_dn_key(value: str | None) -> str:
    return _normalize_key(value)


def _owner_identity_candidates(username: str, display_name: str | None) -> set[str]:
    user = _normalize_text(username)
    display = _normalize_text(display_name)

    values: set[str] = set()
    if user:
        values.add(user)
    if display:
        values.add(display)

    if user and display:
        values.update(
            {
                f"{display} ({user})",
                f"{user} ({display})",
                f"{user} | {display}",
                f"{display} | {user}",
            }
        )

    return values


def _find_directory_user_by_username(db: Session, username: str) -> models.DirectoryUser | None:
    key = _normalize_key(username)
    if not key:
        return None

    rows = db.query(models.DirectoryUser).all()
    for row in rows:
        if _normalize_key(getattr(row, "username", None)) == key:
            return row
    return None


def _finalize_non_admin_scope(scope: UserAccessScope) -> UserAccessScope:
    if scope.is_admin:
        return scope

    if not scope.subordinate_usernames:
        scope.subordinate_usernames = {"__NO_VISIBLE_USERNAME__"}

    if not scope.asset_owner_values:
        scope.asset_owner_values = {"__NO_VISIBLE_OWNER__"}

    return scope


def _collect_subordinates_by_manager_dn(
    rows: list[models.DirectoryUser],
    leader: models.DirectoryUser,
) -> list[models.DirectoryUser]:
    leader_username_key = _normalize_key(getattr(leader, "username", None))
    leader_dn_key = _normalize_dn_key(getattr(leader, "user_dn", None))
    if not leader_dn_key:
        return []

    children_by_manager_dn: dict[str, list[models.DirectoryUser]] = defaultdict(list)
    for row in rows:
        manager_dn_key = _normalize_dn_key(getattr(row, "manager_dn", None))
        if not manager_dn_key:
            continue
        children_by_manager_dn[manager_dn_key].append(row)

    result: list[models.DirectoryUser] = []
    seen_usernames: set[str] = set()
    queue: deque[str] = deque([leader_dn_key])
    visited_dns: set[str] = set()

    while queue:
        manager_dn_key = queue.popleft()
        if not manager_dn_key or manager_dn_key in visited_dns:
            continue
        visited_dns.add(manager_dn_key)

        for child in children_by_manager_dn.get(manager_dn_key, []):
            child_username = _normalize_key(getattr(child, "username", None))
            if not child_username or child_username == leader_username_key:
                continue

            if child_username not in seen_usernames:
                seen_usernames.add(child_username)
                result.append(child)

            child_dn_key = _normalize_dn_key(getattr(child, "user_dn", None))
            if child_dn_key and child_dn_key not in visited_dns:
                queue.append(child_dn_key)

    return result


def _collect_descendant_org_unit_ids(db: Session, root_org_unit_id: int) -> set[int]:
    rows = db.query(models.OrganizationUnit.id, models.OrganizationUnit.parent_id, models.OrganizationUnit.is_active).all()
    children_by_parent: dict[int, list[int]] = defaultdict(list)
    active_by_id: dict[int, bool] = {}

    for org_id, parent_id, is_active in rows:
        if org_id is None:
            continue
        key = int(org_id)
        active_by_id[key] = bool(is_active)
        if parent_id is not None:
            children_by_parent[int(parent_id)].append(key)

    result: set[int] = set()
    queue: deque[int] = deque([int(root_org_unit_id)])
    visited: set[int] = set()

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)

        for child_id in children_by_parent.get(current, []):
            if child_id in visited:
                continue
            if not active_by_id.get(child_id, True):
                continue
            result.add(child_id)
            queue.append(child_id)

    return result


def _collect_subordinates_by_org(
    db: Session,
    leader: models.DirectoryUser,
) -> list[models.DirectoryUser]:
    if not leader.org_unit_id:
        return []

    descendant_org_ids = _collect_descendant_org_unit_ids(db, int(leader.org_unit_id))
    if not descendant_org_ids:
        return []

    rows = (
        db.query(models.DirectoryUser)
        .filter(models.DirectoryUser.org_unit_id.in_(sorted(descendant_org_ids)))
        .filter(models.DirectoryUser.is_active.is_(True))
        .all()
    )
    return rows


def _collect_members_in_same_org(
    db: Session,
    leader: models.DirectoryUser,
) -> list[models.DirectoryUser]:
    if not leader.org_unit_id:
        return []

    leader_username = _normalize_key(getattr(leader, "username", None))
    rows = (
        db.query(models.DirectoryUser)
        .filter(models.DirectoryUser.org_unit_id == int(leader.org_unit_id))
        .filter(models.DirectoryUser.is_active.is_(True))
        .all()
    )

    result: list[models.DirectoryUser] = []
    for row in rows:
        username = _normalize_key(getattr(row, "username", None))
        if not username or username == leader_username:
            continue
        result.append(row)
    return result


def build_user_access_scope(db: Session, user: models.AppAccount) -> UserAccessScope:
    is_admin = _normalize_key(getattr(user, "role", None)) == "admin"
    if is_admin:
        return UserAccessScope(is_admin=True, is_team_lead=True)

    login_username = _normalize_text(getattr(user, "username", None))
    visible_usernames: set[str] = set()
    if login_username:
        visible_usernames.add(login_username)

    asset_owner_values: set[str] = set()
    leader = _find_directory_user_by_username(db, str(getattr(user, "username", "") or ""))
    if leader:
        asset_owner_values.update(
            _owner_identity_candidates(
                username=login_username or _normalize_text(getattr(leader, "username", None)),
                display_name=getattr(leader, "display_name", None),
            )
        )
    elif login_username:
        asset_owner_values.update(_owner_identity_candidates(username=login_username, display_name=None))

    if not leader:
        return _finalize_non_admin_scope(
            UserAccessScope(
                is_admin=False,
                is_team_lead=False,
                managed_usernames=set(),
                subordinate_usernames=visible_usernames,
                subordinate_org_unit_ids=set(),
                asset_owner_values=asset_owner_values,
            )
        )

    manual_leader = bool(getattr(leader, "is_leader", False))

    all_directory_rows = db.query(models.DirectoryUser).all()
    manager_subordinates = _collect_subordinates_by_manager_dn(all_directory_rows, leader)

    if manager_subordinates:
        subordinates = manager_subordinates
    else:
        subordinates = _collect_subordinates_by_org(db, leader)

    if manual_leader and not subordinates:
        subordinates = _collect_members_in_same_org(db, leader)

    managed_usernames: set[str] = set()
    subordinate_org_unit_ids: set[int] = set()

    for row in subordinates:
        if not bool(getattr(row, "is_active", True)):
            continue

        username = _normalize_text(getattr(row, "username", None))
        if not username:
            continue

        managed_usernames.add(username)
        visible_usernames.add(username)

        org_unit_id = getattr(row, "org_unit_id", None)
        if org_unit_id is not None:
            try:
                subordinate_org_unit_ids.add(int(org_unit_id))
            except (TypeError, ValueError):
                pass

        asset_owner_values.update(
            _owner_identity_candidates(
                username=username,
                display_name=getattr(row, "display_name", None),
            )
        )

    return _finalize_non_admin_scope(
        UserAccessScope(
            is_admin=False,
            is_team_lead=bool(managed_usernames) or manual_leader,
            managed_usernames=managed_usernames,
            subordinate_usernames=visible_usernames,
            subordinate_org_unit_ids=subordinate_org_unit_ids,
            asset_owner_values=asset_owner_values,
        )
    )

def can_login_non_admin(db: Session, user: models.AppAccount) -> bool:
    directory_user = _find_directory_user_by_username(db, str(getattr(user, "username", "") or ""))
    return bool(directory_user and getattr(directory_user, "is_active", False))


