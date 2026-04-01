import threading

from ..database import SessionLocal
from ..services import ldap_service

LDAP_SCHEDULER_LOCK = threading.Lock()
LDAP_SCHEDULER_STOP = threading.Event()
LDAP_SCHEDULER_THREAD: threading.Thread | None = None


def _run_ldap_scheduled_sync_once(db):
    return ldap_service._run_ldap_scheduled_sync_once(db)


def _ldap_scheduler_loop():
    while not LDAP_SCHEDULER_STOP.wait(20):
        db = SessionLocal()
        try:
            _run_ldap_scheduled_sync_once(db)
        except Exception:
            pass
        finally:
            db.close()


def _start_ldap_scheduler():
    global LDAP_SCHEDULER_THREAD

    with LDAP_SCHEDULER_LOCK:
        if LDAP_SCHEDULER_THREAD and LDAP_SCHEDULER_THREAD.is_alive():
            return

        LDAP_SCHEDULER_STOP.clear()
        LDAP_SCHEDULER_THREAD = threading.Thread(
            target=_ldap_scheduler_loop,
            name="ldap-sync-scheduler",
            daemon=True,
        )
        LDAP_SCHEDULER_THREAD.start()


def _stop_ldap_scheduler():
    LDAP_SCHEDULER_STOP.set()
