# DayTrace

DayTrace is a local-first Android life log toolkit. It combines a small Android helper app with a Python ADB sync script to turn phone activity into private daily Markdown reports on your own computer.

No cloud account. No hosted database. No telemetry. Your phone data stays on your device and in the local folder you choose.

## What It Captures

- App usage and screen timeline from Android usage stats.
- SMS, calls, calendar entries, Wi-Fi hints, battery and network snapshots through ADB.
- Helper app exports for media, files, app changes, notifications, accessibility events and location samples when you grant those permissions.
- Daily Markdown reports plus structured JSON summaries for your own analysis.

Android data access is best-effort. Some modules depend on device vendor behavior, Android version, permissions and how recently the helper app was opened.

## Repository Contents

- `main.py` and `src/`: desktop sync and report generation.
- `helper-android/`: Android Helper app source.
- `config.example.yaml`: starter config. Copy it to `config.yaml` before running.
- `tests/`: Python and Android-source behavior tests.
- `releases/`: optional place for locally built APK files.

This public repository intentionally does not include personal reports, raw ADB dumps, local databases or helper export caches.

## Quick Start

1. Install Python 3.10+ and Android platform tools.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Copy the example config:

```powershell
Copy-Item -LiteralPath .\config.example.yaml -Destination .\config.yaml
```

4. Install the Helper APK from the latest GitHub Release, or build it from `helper-android/`.
5. Enable USB debugging on your Android phone and connect it to your computer.
6. Run:

```powershell
python main.py
```

Reports are written to `data/YYYY-MM-DD/` by default. The `data/` folder is ignored by git.

## Build the Helper APK

From `helper-android/`:

```powershell
gradle :app:assembleDebug
```

The debug APK is usually produced under:

```text
helper-android/app/build/outputs/apk/debug/app-debug.apk
```

If you use Android Studio, open `helper-android/` and run the `app` configuration.

## Privacy Model

DayTrace is designed for local personal archiving:

- The Python script talks to your phone through ADB.
- The Helper app writes exports to your phone storage.
- Generated reports and raw snapshots stay on your computer.
- Nothing is uploaded by this project.

Read `PRIVACY.md` and `PERMISSIONS.md` before enabling sensitive Android permissions.

## Data Completeness

DayTrace deliberately separates data sources by how they can be collected:

- 实时归档: notifications and accessibility events must be captured while the Android services are enabled. 通知监听连接时会补抓当前仍存在的通知, but 已经消失且监听当时未开启的通知无法回补.
- 周期采样: location is recorded by app launch, daily work and periodic work on a best-effort basis. It is a set of samples, not a complete route trace.
- 历史回查: app usage, media, SMS, calls, calendar, contacts, files and app changes are queried from Android providers when the system still retains them and permissions allow access.
- 当前快照: battery, storage, Wi-Fi and current notification state describe the sync moment, not the full day.

打开 Helper 后会刷新最近 3 天 daily_context.json, which helps reports catch up after notification, accessibility or location archives changed on the phone.

## Why This Exists

Most phone analytics tools either summarize too little or require sending personal data somewhere else. DayTrace is for people who want a detailed personal record while keeping the data under their own control.

## License

See `LICENSE`.
