from __future__ import annotations

from sqlalchemy import text


def run_schema_upgrade(engine) -> None:
    if engine.url.get_backend_name() != "postgresql":
        return

    statements = [
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS asset_code VARCHAR(50)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS usage_type VARCHAR(30)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS manager VARCHAR(120)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS manufacturer VARCHAR(120)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS model_name VARCHAR(120)",
        "ALTER TABLE assets ADD COLUMN IF NOT EXISTS department VARCHAR(120)",
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
    ]

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))

        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_assets_asset_code ON assets (asset_code)"))
        conn.execute(text("ALTER TABLE assets ALTER COLUMN serial_number DROP NOT NULL"))
        conn.execute(text("UPDATE assets SET owner = '???' WHERE owner IS NULL OR owner = ''"))
        conn.execute(text("UPDATE assets SET location = '???' WHERE location IS NULL OR location = ''"))
        conn.execute(text("UPDATE assets SET manager = COALESCE(NULLIF(manager, ''), owner, '???')"))
        conn.execute(text("UPDATE assets SET disposed_at = COALESCE(disposed_at, updated_at, now()) WHERE status = '????'"))
        conn.execute(text("UPDATE assets SET disposed_at = NULL WHERE status <> '????'"))

        conn.execute(
            text(
                "UPDATE assets SET usage_type = CASE "
                "WHEN usage_type IN ('???', 'primary') THEN '???' "
                "WHEN usage_type IN ('????', 'loaner') THEN '????' "
                "WHEN usage_type IN ('??????', 'project') THEN '??????' "
                "WHEN usage_type IN ('????', 'auxiliary') THEN '????' "
                "WHEN usage_type IN ('????', 'server') THEN '????' "
                "WHEN usage_type IN ('??????', 'network') THEN '??????' "
                "WHEN usage_type IN ('????', 'other') THEN '????' "
                "ELSE COALESCE(NULLIF(usage_type, ''), '????') END"
            )
        )

        conn.execute(text("UPDATE assets SET rental_start_date = NULL, rental_end_date = NULL WHERE usage_type <> '????'"))

        conn.execute(
            text(
                "UPDATE assets SET status = CASE "
                "WHEN status IN ('active', 'assigned', 'in_use', '???') THEN '???' "
                "WHEN status IN ('available', 'maintenance', 'standby', '??') THEN '??' "
                "WHEN status IN ('retired', 'disposal_required', '????') THEN '????' "
                "WHEN status IN ('disposed', 'disposal_done', '????') THEN '????' "
                "ELSE '??' END"
            )
        )

        conn.execute(
            text(
                "UPDATE assets "
                "SET asset_code = 'AST-' || LPAD(id::text, 5, '0') "
                "WHERE asset_code IS NULL"
            )
        )

        conn.execute(text("UPDATE software_licenses SET license_category = COALESCE(NULLIF(license_category, ''), '??')"))
        conn.execute(
            text(
                "UPDATE software_licenses SET subscription_type = CASE "
                "WHEN subscription_type IS NOT NULL AND subscription_type <> '' THEN subscription_type "
                "WHEN license_type IN ('??', '?? ??') THEN '?? ??' "
                "WHEN license_type IN ('? ??') THEN '? ??' "
                "WHEN license_type IN ('????? ??') THEN '????? ??' "
                "ELSE '? ??' END"
            )
        )
        conn.execute(text("UPDATE software_licenses SET purchase_currency = COALESCE(NULLIF(purchase_currency, ''), '?')"))
        conn.execute(
            text(
                "UPDATE software_licenses SET license_scope = CASE "
                "WHEN license_scope IN ('??', 'required', 'mandatory', 'critical') THEN '??' "
                "WHEN license_scope IN ('??', 'general') THEN '??' "
                "ELSE '??' END"
            )
        )
        conn.execute(text("UPDATE software_licenses SET license_type = COALESCE(NULLIF(subscription_type, ''), '? ??')"))
        conn.execute(text("UPDATE software_licenses SET allow_multiple_assignments = COALESCE(allow_multiple_assignments, FALSE)"))
