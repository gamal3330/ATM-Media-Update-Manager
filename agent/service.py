from __future__ import annotations

import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path


def write_bootstrap_log(config_path: Path, message: str) -> None:
    log_dir = config_path.parent / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "service-bootstrap.log"
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with log_path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(f"{timestamp} {message}\n")
    except Exception:
        pass


def run_service(config_path: Path) -> None:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil

    class ATMUnifiedAgentWindowsService(win32serviceutil.ServiceFramework):
        _svc_name_ = "ATMUnifiedAgent"
        _svc_display_name_ = "QIB ATM Manager Agent Service"
        _svc_description_ = "Pull-based unified ATM agent"

        def __init__(self, args):
            super().__init__(args)
            self.stop_event_handle = win32event.CreateEvent(None, 0, 0, None)
            self.stop_event = threading.Event()

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self.stop_event.set()
            win32event.SetEvent(self.stop_event_handle)

        def SvcDoRun(self):
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            servicemanager.LogInfoMsg("QIB ATM Manager Agent service entered running state")
            write_bootstrap_log(config_path, "Windows service entered running state")
            try:
                from atm_agent import AtmAgent

                AtmAgent(config_path, stop_event=self.stop_event, startup_mode="service").run_forever()
            except Exception:
                details = traceback.format_exc()
                write_bootstrap_log(config_path, f"Service failed during startup or run:\n{details}")
                servicemanager.LogErrorMsg(f"QIB ATM Manager Agent failed: {details}")
                raise

    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(ATMUnifiedAgentWindowsService)
    servicemanager.StartServiceCtrlDispatcher()
