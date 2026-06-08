# Privacy

DayTrace handles sensitive phone data. Treat every generated report and export as private.

## Local-First Design

The project does not provide a server, cloud sync, hosted storage or telemetry endpoint. The default workflow is:

1. Android Helper collects data on your phone when permissions allow it.
2. `python main.py` pulls data through ADB.
3. Reports are generated under local `data/`.

## Sensitive Data Types

Depending on enabled permissions and Android behavior, DayTrace may process:

- App usage and screen activity.
- SMS and MMS metadata or content.
- Call log metadata.
- Calendar events.
- Notification text.
- File and media metadata.
- Location snapshots.
- Device information and storage/battery/network status.

## What Not To Publish

Never publish generated `data/`, `db/`, raw ADB dumps, helper exports or Markdown reports unless you have intentionally sanitized them.

The public source repository excludes those folders through `.gitignore`.
