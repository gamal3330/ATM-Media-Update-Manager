# QIB ATM Manager Agent

Permanent pull-based Windows Agent for QIB ATM Manager. It is one executable and one Windows Service with modular internals.

## Local Config

The local config contains only connection data:

```json
{
  "server_url": "https://atm-update-server.local",
  "atm_id": "ATM001",
  "api_key": "CHANGE_ME",
  "local_log_path": "C:\\ATM\\Agent\\logs",
  "fallback_heartbeat_interval_seconds": 60,
  "fallback_config_sync_interval_seconds": 120
}
```

`media_path`, `backup_path`, `temp_path`, module flags, heartbeat interval, and monitoring intervals are pulled from the server with:

```text
GET /api/agent/config
```

## Build EXE

On a Windows build machine:

```bat
cd agent
build_agent.bat
```

The output is:

```text
agent\dist\atm-agent.exe
agent\dist\agent-updater.exe
```

For NCR/GRG XFS providers installed under `Program Files (x86)`, build the 32-bit executable:

```bat
build_agent_x86.bat
```

Production ATM builds should use `build_agent_x86.bat`. It builds both:

```text
dist\atm-agent.exe
dist\agent-updater.exe
```

with a 32-bit Python runtime. The central Agent package upload rejects 64-bit PE files.

## Install Agent

Run Command Prompt as Administrator:

```bat
atm-agent.exe install --server-url="https://atm-update-server.local" --atm-id="ATM001" --api-key="CHANGE_ME"
```

`install` validates the server/API key first, copies the executable, and starts the agent. In `--run-mode auto`
it keeps NCR/APTRA ATMs as a Windows Service and installs GRG ATMs as a hidden interactive Scheduled Task,
because some GRG XFS CDM providers do not allow `WFSOpen(CDM)` from Windows Service Session 0.

You can force a mode when needed:

```bat
atm-agent.exe install --server-url="https://atm-update-server.local" --atm-id="ATM001" --api-key="CHANGE_ME" --run-mode service
atm-agent.exe install --server-url="https://atm-update-server.local" --atm-id="ATM001" --api-key="CHANGE_ME" --run-mode scheduled-task --task-user="ATM-PC\Administrator"
```

If a previous agent is already installed, `install` validates credentials first, removes existing service/task
startup registrations, removes the old executable when the installer is running from another folder, copies the
new executable, and starts the selected startup mode.

The installer writes files to:

```text
C:\Program Files\QIB ATM Manager Agent
```

For service mode it creates and starts this Windows Service:

```text
QIB ATM Manager Agent Service
```

The service name is:

```text
ATMUnifiedAgent
```

For scheduled-task mode it creates and starts this hidden task:

```text
QIB ATM Manager Agent
```

## Commands

```bat
atm-agent.exe install --server-url="https://server" --atm-id="ATM001" --api-key="XXXXX"
atm-agent.exe uninstall
atm-agent.exe status
atm-agent.exe version
atm-agent.exe xfs-cdm-diagnose
atm-agent.exe run --config "C:\Program Files\QIB ATM Manager Agent\config.json"
atm-agent.exe run --config config.json --once
```

`status` shows the configured ATM ID, service status, server connectivity, last heartbeat, last config sync, and last local error state.

Switch reachability checks are handled by the service automatically after the dashboard requests one. The agent performs
a direct TCP connect to the configured `switch_probe_host:switch_probe_port` only. It does not run `cmd`, `telnet.exe`,
PowerShell, or any shell command.

`xfs-cdm-diagnose` is read-only. It scans XFS files and registry hints to find CDM provider files and possible
logical service names before the real `xfs_cdm` provider is enabled. It does not call dispense, exchange, reset, or any
state-changing XFS command.

For NCR APTRA installs, run:

```bat
atm-agent.exe xfs-cdm-diagnose --aptra-root "C:\Program Files (x86)\NCR APTRA"
```

For GRG installs, start with the generic registry-based diagnostic:

```bat
atm-agent.exe xfs-cdm-diagnose --json
```

If you know the GRG XFS installation root, pass it explicitly:

```bat
atm-agent.exe xfs-cdm-diagnose --xfs-root "C:\Program Files (x86)\GRG"
```

The same `atm-agent.exe` supports NCR APTRA and GRG. After diagnostics confirm the logical service name, the first
cassette read test is also read-only. Typical values are `MediaDispenser1` for NCR APTRA and `CDM` for the tested GRG
installation:

```bat
atm-agent.exe xfs-cdm-read --logical-service MediaDispenser1 --json
atm-agent.exe xfs-cdm-read --logical-service CDM --msxfs-path "C:\Windows\SysWOW64\msxfs.dll" --json
```

For 32-bit XFS providers installed under `Program Files (x86)`, build and run this command with a 32-bit `atm-agent.exe`.
The command calls `WFSGetInfo` for CDM cash unit information only. It does not dispense, reset, exchange, or change any
ATM state.
When the real provider is enabled, set `XFS Profile` and `XFS Logical Service` in the ATM dashboard settings:

- NCR APTRA: `XFS Profile = NCR APTRA`, `XFS Logical Service = MediaDispenser1`
- GRG: `XFS Profile = GRG`, `XFS Logical Service = CDM`

If you need machine-readable output:

```bat
atm-agent.exe xfs-cdm-diagnose --json
```

## Central Agent Self-Update

`agent-updater.exe` is a small standalone helper used to replace `atm-agent.exe` safely. It is not the full agent.
The dashboard uploads a 32-bit `atm-agent.exe` and a 32-bit `agent-updater.exe` as one Agent package, then assigns
that package to selected ATMs. The running agent periodically calls:

```text
GET /api/agent/check-agent-update
```

If a package is assigned, the agent downloads both files, verifies both SHA256 values, launches `agent-updater.exe`,
and exits. The updater stops the current startup mode, keeps a backup of the old executable, replaces it, starts the
same mode again, and writes `update-result.json` beside the agent.

On the next startup, the new agent reads `update-result.json` and reports the final result to:

```text
POST /api/agent/agent-update-result
```

`run --once` never starts self-update; it is kept for diagnostics and manual cash reads only.

Manual updater examples are still useful for emergency recovery and lab testing.

Scheduled Task mode:

```bat
agent-updater.exe ^
  --current "C:\ATM_AGENT\atm-agent.exe" ^
  --new "C:\ATM_AGENT\downloads\atm-agent-new.exe" ^
  --mode scheduled-task ^
  --task-name "QIB ATM Manager Agent"
```

Windows Service mode:

```bat
agent-updater.exe ^
  --current "C:\Program Files\QIB ATM Manager Agent\atm-agent.exe" ^
  --new "C:\ATM_AGENT\downloads\atm-agent-new.exe" ^
  --mode service ^
  --service-name ATMUnifiedAgent
```

Optional checksum verification:

```bat
agent-updater.exe --current "C:\ATM_AGENT\atm-agent.exe" --new "C:\ATM_AGENT\downloads\atm-agent-new.exe" --mode scheduled-task --expected-sha256 SHA256_VALUE
```

The backup is stored under:

```text
agent_backups\
```

The result file contains `ok`, `status`, `backup_path`, `started`, and `error`.

## Security

- The agent never accepts shell commands from the server.
- The agent only executes `agent-updater.exe` from an assigned Agent package after SHA256 verification.
- Update packages must be ZIP files containing allowed image extensions only.
- ZIP entries with absolute paths or path traversal are rejected.
- Cash monitoring is DISPENSE_ONLY and reads CDM cash dispenser data only.
- Supported dispense provider for production cash monitoring is `xfs_cdm`; `vendor_cdm` is reserved for a future vendor integration.
- The module reads dispense cassettes, reject count, and retract count when available.
- There is no CIM, Cash-In, Deposit, Recycler, dispense command, cash unit exchange, reset counters, shell, PowerShell, or script execution path.
- The API key is only stored locally on the ATM and is stored as a hash on the server.
