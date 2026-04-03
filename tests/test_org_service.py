import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, schemas
from app.database import Base
from app.services import org_service


class OrgServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _create_org(self, name: str, parent_id=None, is_active: bool = True):
        row = models.OrganizationUnit(name=name, parent_id=parent_id, is_active=is_active, sort_order=0)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def test_org_parent_cycle_blocked(self):
        org_a = self._create_org("본부")
        org_b = self._create_org("팀", parent_id=org_a.id)

        with self.assertRaises(ValueError) as ctx:
            org_service.update_org_unit(
                self.db,
                org_a.id,
                schemas.OrganizationUnitUpdate(parent_id=org_b.id),
            )

        self.assertEqual(str(ctx.exception), "org_unit_parent_cycle")

    def test_org_deactivate_blocked_preview(self):
        source = self._create_org("운영조직")
        self._create_org("하위조직", parent_id=source.id)

        self.db.add(
            models.DirectoryUser(
                username="u1",
                display_name="사용자1",
                source="manual",
                is_active=True,
                org_unit_id=source.id,
                department="운영조직",
            )
        )
        self.db.add(
            models.Asset(
                name="노트북",
                category="노트북",
                usage_type="주장비",
                owner="u1",
                manager="admin",
                location="본사",
                status="사용중",
                org_unit_id=source.id,
                department="운영조직",
            )
        )
        self.db.commit()

        preview = org_service.build_org_unit_deactivation_preview(self.db, source.id)
        self.assertIsNotNone(preview)
        self.assertTrue(preview.has_active_children)
        self.assertGreaterEqual(preview.active_user_count, 1)
        self.assertGreaterEqual(preview.active_asset_count, 1)
        self.assertTrue(len(preview.blocking_reasons) >= 1)

        with self.assertRaises(org_service.OrgUnitDeactivationBlockedError):
            org_service.deactivate_org_unit(self.db, source.id)

    def test_org_transfer_success_and_invalid_target(self):
        source = self._create_org("원본조직")
        target = self._create_org("대상조직")
        inactive_target = self._create_org("비활성조직", is_active=False)

        self.db.add_all(
            [
                models.DirectoryUser(
                    username="u1",
                    display_name="사용자1",
                    source="manual",
                    is_active=True,
                    org_unit_id=source.id,
                    department="원본조직",
                ),
                models.DirectoryUser(
                    username="u2",
                    display_name="사용자2",
                    source="manual",
                    is_active=True,
                    org_unit_id=source.id,
                    department="원본조직",
                ),
                models.Asset(
                    name="모니터",
                    category="모니터",
                    usage_type="주장비",
                    owner="u1",
                    manager="admin",
                    location="본사",
                    status="사용중",
                    org_unit_id=source.id,
                    department="원본조직",
                ),
            ]
        )
        self.db.commit()

        preview = org_service.build_org_unit_transfer_preview(self.db, source.id, target.id)
        self.assertEqual(preview.transferable_user_count, 2)
        self.assertEqual(preview.transferable_asset_count, 1)

        result = org_service.transfer_org_unit(self.db, source.id, target.id)
        self.assertTrue(result.ok)
        self.assertEqual(result.moved_user_count, 2)
        self.assertEqual(result.moved_asset_count, 1)

        users = self.db.query(models.DirectoryUser).filter(models.DirectoryUser.username.in_(["u1", "u2"])).all()
        self.assertTrue(all(int(row.org_unit_id) == int(target.id) for row in users))
        self.assertTrue(all((row.department or "") == "대상조직" for row in users))

        assets = self.db.query(models.Asset).filter(models.Asset.name == "모니터").all()
        self.assertTrue(all(int(row.org_unit_id) == int(target.id) for row in assets))
        self.assertTrue(all((row.department or "") == "대상조직" for row in assets))

        with self.assertRaises(ValueError) as same_target_error:
            org_service.build_org_unit_transfer_preview(self.db, source.id, source.id)
        self.assertEqual(str(same_target_error.exception), "org_unit_transfer_same_target")

        with self.assertRaises(ValueError) as inactive_target_error:
            org_service.build_org_unit_transfer_preview(self.db, source.id, inactive_target.id)
        self.assertEqual(str(inactive_target_error.exception), "org_unit_transfer_target_inactive")


if __name__ == "__main__":
    unittest.main()
