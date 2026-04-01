import threading

from ..database import SessionLocal
from ..services import mail_service

SOFTWARE_MAIL_SCHEDULER_LOCK = threading.Lock()
SOFTWARE_MAIL_SCHEDULER_STOP = threading.Event()
SOFTWARE_MAIL_SCHEDULER_THREAD: threading.Thread | None = None


def _run_software_mail_scheduled_once(db):
    return mail_service._run_software_mail_scheduled_once(db)


def _software_mail_scheduler_loop():
    while not SOFTWARE_MAIL_SCHEDULER_STOP.wait(30):
        db = SessionLocal()
        try:
            _run_software_mail_scheduled_once(db)
        except Exception:
            pass
        finally:
            db.close()


def _start_software_mail_scheduler():
    global SOFTWARE_MAIL_SCHEDULER_THREAD

    with SOFTWARE_MAIL_SCHEDULER_LOCK:
        if SOFTWARE_MAIL_SCHEDULER_THREAD and SOFTWARE_MAIL_SCHEDULER_THREAD.is_alive():
            return

        SOFTWARE_MAIL_SCHEDULER_STOP.clear()
        SOFTWARE_MAIL_SCHEDULER_THREAD = threading.Thread(
            target=_software_mail_scheduler_loop,
            name="software-mail-scheduler",
            daemon=True,
        )
        SOFTWARE_MAIL_SCHEDULER_THREAD.start()


def _stop_software_mail_scheduler():
    SOFTWARE_MAIL_SCHEDULER_STOP.set()
