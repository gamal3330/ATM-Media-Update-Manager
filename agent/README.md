# ATM Unified Agent

Permanent pull-based Windows Agent for ATM Media Update Manager. It is one executable and one Windows Service with modular internals.

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
```

## Install Service

Run Command Prompt as Administrator:

```bat
atm-agent.exe install --server-url https://atm-update-server.local --atm-id ATM001 --api-key CHANGE_ME
```

If a previous agent is already installed, `install` validates the server/API key first, stops and deletes
the existing Windows Service registration, removes the old executable when the installer is running from
another folder, copies the new executable, recreates the service, and starts it again.

The installer writes files to:

```text
C:\Program Files\ATM Media Agent
```

It creates and starts this Windows Service:

```text
ATM Unified Agent Service
```

The service name is:

```text
ATMUnifiedAgent
```

## Commands

```bat
atm-agent.exe install --server-url https://server --atm-id ATM001 --api-key XXXXX
atm-agent.exe uninstall
atm-agent.exe status
atm-agent.exe version
atm-agent.exe xfs-cdm-diagnose
atm-agent.exe run --config "C:\Program Files\ATM Media Agent\config.json"
atm-agent.exe run --config config.json --once
```

`status` shows the configured ATM ID, service status, server connectivity, last heartbeat, last config sync, and last local error state.

Switch reachability checks are handled by the service automatically after the dashboard requests one. The agent performs
a direct TCP connect to the configured `switch_probe_host:switch_probe_port` only. It does not run `cmd`, `telnet.exe`,
PowerShell, or any shell command.

`xfs-cdm-diagnose` is read-only. It scans NCR APTRA/XFS files and registry hints to find CDM provider files and possible
logical service names before the real `xfs_cdm` provider is enabled. It does not call dispense, exchange, reset, or any
state-changing XFS command.

For NCR APTRA installs, run:

```bat
atm-agent.exe xfs-cdm-diagnose --aptra-root "C:\Program Files (x86)\NCR APTRA"
```

If you need machine-readable output:

```bat
atm-agent.exe xfs-cdm-diagnose --json
```

## Security

- The agent never accepts shell commands from the server.
- The agent never executes files downloaded from the server.
- Update packages must be ZIP files containing allowed image extensions only.
- ZIP entries with absolute paths or path traversal are rejected.
- Cash monitoring is DISPENSE_ONLY and reads CDM cash dispenser data only.
- Supported dispense providers are `mock`, `xfs_cdm`, and `vendor_cdm`.
- The module reads dispense cassettes, reject count, and retract count when available.
- There is no CIM, Cash-In, Deposit, Recycler, dispense command, cash unit exchange, reset counters, shell, PowerShell, or script execution path.
- The API key is only stored locally on the ATM and is stored as a hash on the server.
