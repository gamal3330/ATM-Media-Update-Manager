from __future__ import annotations

import threading
from pathlib import Path

from atm_agent import AtmAgent


def run_service(config_path: Path) -> None:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil

    class ATMUnifiedAgentWindowsService(win32serviceutil.ServiceFramework):
        _svc_name_ = "ATMUnifiedAgent"
        _svc_display_name_ = "ATM Unified Agent Service"
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
            servicemanager.LogInfoMsg("ATM Unified Agent started")
            AtmAgent(config_path, stop_event=self.stop_event).run_forever()

    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(ATMUnifiedAgentWindowsService)
    servicemanager.StartServiceCtrlDispatcher()
