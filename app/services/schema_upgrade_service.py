from __future__ import annotations

from sqlalchemy import text


def run_schema_upgrade(engine) -> None:
    if engine.url.get_backend_name() != "postgresql":
        return

    statements = [
        "CREATE TABLE IF NOT EXISTS organization_units ("
        "id SERIAL PRIMARY KEY, "
        "name VARCHAR(200) NOT NULL UNIQUE, "
        "code VARCHAR(50) UNIQUE, "
        "parent_id INTEGER NULL, "
        "is_active BOOLEAN NOT NULL DEFAULT TRUE, "
        "sort_order INTEGER NOT NULL DEFAULT 0, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
        ")",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS asset_code VARCHAR(50)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS usage_type VARCHAR(30)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS manager VARCHAR(120)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS manufacturer VARCHAR(120)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS model_name VARCHAR(120)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS department VARCHAR(120)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS org_unit_id INTEGER",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS vendor VARCHAR(120)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS purchase_date DATE",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS purchase_cost NUMERIC(12, 2)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS warranty_expiry DATE",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS rental_start_date DATE",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS rental_end_date DATE",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS disposed_at TIMESTAMPTZ",
        "ALTER TABLE software_licenses ADD COLUMN IF NOT EXISTS license_category VARCHAR(40)",
        "ALTER TABLE software_licenses ADD COLUMN IF NOT EXISTS subscription_type VARCHAR(30)",
        "ALTER TABLE software_licenses ADD COLUMN IF NOT EXISTS license_scope VARCHAR(20)",
        "ALTER TABLE software_licenses ADD COLUMN IF NOT EXISTS purchase_cost NUMERIC(14, 2)",
        "ALTER TABLE software_licenses ADD COLUMN IF NOT EXISTS purchase_currency VARCHAR(10)",
        "ALTER TABLE software_licenses ADD COLUMN IF NOT EXISTS assignee_details JSONB",
        "ALTER TABLE software_licenses ADD COLUMN IF NOT EXISTS allow_multiple_assignments BOOLEAN DEFAULT FALSE",
        "ALTER TABLE directory_users ADD COLUMN IF NOT EXISTS manager_dn VARCHAR(500)",
        "ALTER TABLE directory_users ADD COLUMN IF NOT EXISTS user_dn VARCHAR(500)",
        "ALTER TABLE directory_users ADD COLUMN IF NOT EXISTS object_guid VARCHAR(80)",
        "ALTER TABLE directory_users ADD COLUMN IF NOT EXISTS org_unit_id INTEGER",
    ]

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))

        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_assets_asset_code ON assets (asset_code)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_organization_units_name ON organization_units (name)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_organization_units_code ON organization_units (code)"))
        conn.execute(text("ALTER TABLE assets ALTER COLUMN serial_number DROP NOT NULL"))

        conn.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_organization_units_parent_id') THEN "
                "ALTER TABLE organization_units ADD CONSTRAINT fk_organization_units_parent_id "
                "FOREIGN KEY (parent_id) REFERENCES organization_units(id) ON DELETE SET NULL; "
                "END IF; END $$;"
            )
        )
        conn.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_assets_org_unit_id') THEN "
                "ALTER TABLE assets ADD CONSTRAINT fk_assets_org_unit_id "
                "FOREIGN KEY (org_unit_id) REFERENCES organization_units(id) ON DELETE SET NULL; "
                "END IF; END $$;"
            )
        )
        conn.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_directory_users_org_unit_id') THEN "
                "ALTER TABLE directory_users ADD CONSTRAINT fk_directory_users_org_unit_id "
                "FOREIGN KEY (org_unit_id) REFERENCES organization_units(id) ON DELETE SET NULL; "
                "END IF; END $$;"
            )
        )

        conn.execute(text("UPDATE assets SET owner = '미지정' WHERE owner IS NULL OR owner = ''"))
        conn.execute(text("UPDATE assets SET location = '미지정' WHERE location IS NULL OR location = ''"))
        conn.execute(text("UPDATE assets SET manager = COALESCE(NULLIF(manager, ''), owner, '미지정')"))
        conn.execute(text("UPDATE assets SET disposed_at = COALESCE(disposed_at, updated_at, now()) WHERE status = '폐기완료'"))
        conn.execute(text("UPDATE assets SET disposed_at = NULL WHERE status <> '폐기완료'"))

        conn.execute(
            text(
                "UPDATE assets SET usage_type = CASE "
                "WHEN usage_type IN ('주장비', 'primary') THEN '주장비' "
                "WHEN usage_type IN ('대여장비', 'loaner') THEN '대여장비' "
                "WHEN usage_type IN ('프로젝트장비', 'project') THEN '프로젝트장비' "
                "WHEN usage_type IN ('보조장비', 'auxiliary') THEN '보조장비' "
                "WHEN usage_type IN ('서버장비', 'server') THEN '서버장비' "
                "WHEN usage_type IN ('네트워크장비', 'network') THEN '네트워크장비' "
                "WHEN usage_type IN ('기타장비', 'other') THEN '기타장비' "
                "ELSE COALESCE(NULLIF(usage_type, ''), '기타장비') END"
            )
        )

        conn.execute(text("UPDATE assets SET rental_start_date = NULL, rental_end_date = NULL WHERE usage_type <> '대여장비'"))

        conn.execute(
            text(
                "UPDATE assets SET status = CASE "
                "WHEN status IN ('active', 'assigned', 'in_use', '사용중') THEN '사용중' "
                "WHEN status IN ('available', 'maintenance', 'standby', '대기') THEN '대기' "
                "WHEN status IN ('retired', 'disposal_required', '폐기필요') THEN '폐기필요' "
                "WHEN status IN ('disposed', 'disposal_done', '폐기완료') THEN '폐기완료' "
                "ELSE '대기' END"
            )
        )

        conn.execute(
            text(
                "UPDATE assets "
                "SET asset_code = 'AST-' || LPAD(id::text, 5, '0') "
                "WHERE asset_code IS NULL"
            )
        )

        conn.execute(text("UPDATE software_licenses SET license_category = COALESCE(NULLIF(license_category, ''), '기타')"))
        conn.execute(text("UPDATE software_licenses SET subscription_type = COALESCE(NULLIF(subscription_type, ''), '연 구독')"))
        conn.execute(text("UPDATE software_licenses SET purchase_currency = COALESCE(NULLIF(purchase_currency, ''), '원')"))
        conn.execute(
            text(
                "UPDATE software_licenses SET license_scope = CASE "
                "WHEN license_scope IN ('필수', 'required', 'mandatory', 'critical') THEN '필수' "
                "WHEN license_scope IN ('일반', 'general') THEN '일반' "
                "ELSE '일반' END"
            )
        )
        conn.execute(text("UPDATE software_licenses SET license_type = COALESCE(NULLIF(subscription_type, ''), '연 구독')"))
        conn.execute(text("UPDATE software_licenses SET allow_multiple_assignments = COALESCE(allow_multiple_assignments, FALSE)"))
