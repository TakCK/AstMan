import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base
from app.services import report_service


class ReportServiceOrgFirstTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.SessionLocal()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_report_org_first_with_department_fallback(self):
        org = models.OrganizationUnit(name="영업팀", is_active=True, sort_order=0)
        self.db.add(org)
        self.db.commit()
        self.db.refresh(org)

        self.db.add(
            models.DirectoryUser(
                username="user_a",
                display_name="사용자A",
                source="manual",
                is_active=True,
                org_unit_id=org.id,
                department="영업팀",
            )
        )
        self.db.add(
            models.DirectoryUser(
                username="user_b",
                display_name="사용자B",
                source="manual",
                is_active=True,
                org_unit_id=None,
                department="영업팀",
            )
        )
        self.db.add(
            models.SoftwareLicense(
                product_name="SaaS-1",
                license_scope="일반",
                subscription_type="월 구독",
                total_quantity=2,
                purchase_cost=100,
                purchase_currency="원",
                assignees=["user_a", "user_b"],
                assignee_details=[],
            )
        )
        self.db.commit()

        summary = report_service.build_dashboard_software_cost_summary(self.db, scope_filter="all")
        team_rows = summary.get("team_summary") or []
        same_name_rows = [row for row in team_rows if row.get("team_name") == "영업팀"]

        # org bucket과 department fallback bucket을 분리 집계해야 한다.
        self.assertEqual(len(same_name_rows), 2)

        general_report = report_service.build_general_license_report_data(self.db)
        user_rows = general_report.get("user_detail") or []
        user_map = {row.get("user"): row for row in user_rows}

        self.assertEqual(user_map["사용자A"]["team"], "영업팀")
        self.assertEqual(user_map["사용자B"]["team"], "영업팀")


if __name__ == "__main__":
    unittest.main()
