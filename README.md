# DayTrace

**Private Android context for the AI era.**

[中文说明](docs/README.zh-CN.md) · [Release APK](https://github.com/linchuanXu/daytrace-public/releases/tag/v0.1.0) · [Privacy](PRIVACY.md) · [Permissions](PERMISSIONS.md)

![DayTrace hero](docs/assets/daytrace-hero.png)

DayTrace records what your Android phone can already tell about your day, then turns it into local Markdown and JSON context you can read, search, archive, or connect to your own AI workflows.

Your phone knows which apps shaped your attention, when you moved, what notifications arrived, what files changed, and which calls or messages interrupted the day. That context should belong to you.

No cloud account. No hosted database. No telemetry. No vendor dashboard.

> Long-term vision: every phone should be able to produce a private, structured life context layer for its owner. Not for surveillance. Not for ads. For the person carrying the device.

## Why Star Or Fork This

- **AI-ready personal context**: generate local daily records that can become memory for local LLMs or personal agents.
- **Local-first by default**: reports, raw snapshots and databases stay on your machine.
- **Android-native capture**: a Helper APK records what ADB cannot reliably recover after the fact.
- **Readable output**: Markdown for humans, JSON for scripts and AI pipelines.
- **Hackable source**: Python collectors, Android source and tests are included.
- **Privacy boundary in code**: generated `data/`, local databases and raw dumps are ignored and intentionally absent from this repository.

DayTrace is early, imperfect and Android-vendor-dependent. That is exactly why it is worth forking: phone context should become an open, inspectable layer, not a black-box cloud feature.

## Is This Another Tracker?

Yes, but the goal is different.

Most trackers answer: “How much time did I spend?” DayTrace asks: “What context did my day leave behind, and can I keep it privately for future AI tools?”

Common problems with existing approaches:

- Data is uploaded to a vendor service.
- The user does not own the raw records.
- Output is a dashboard, not an archive.
- Phone context is reduced to screen time.
- Sensitive modules are hidden behind closed-source apps.
- AI memory is built from chat history, not real-life context.

DayTrace tries to be a small open foundation for the opposite: local files, inspectable code, explicit permissions and user-owned context.

## What It Captures

- App usage and screen timeline from Android usage stats.
- SMS, calls, calendar entries, Wi-Fi hints, battery and network snapshots through ADB.
- Helper app exports for media, files, app changes, notifications, accessibility events and location samples when you grant those permissions.
- Daily Markdown reports plus structured JSON summaries for your own analysis.

Android data access is best-effort. Some modules depend on device vendor behavior, Android version, permissions and how recently the Helper app was opened.

## Screenshots

The images below use simulated data. No personal records are included.

| Android Helper | Daily Report |
|---|---|
| ![DayTrace Helper screenshot](docs/assets/daytrace-helper-screenshot.png) | ![DayTrace report screenshot](docs/assets/daytrace-report-screenshot.png) |

## What You Can Build With It

- A personal “what happened today?” timeline.
- A private memory source for local LLMs.
- Searchable second-brain archives based on real device context.
- Attention and app-usage reviews without vendor dashboards.
- Experiments around personal agents that remember your day from local files.
- Redaction, summarization, RAG, or calendar/journal workflows on top of phone context.

## Repository Contents

- `main.py` and `src/`: desktop sync and report generation.
- `helper-android/`: Android Helper app source.
- `config.example.yaml`: starter config. Copy it to `config.yaml` before running.
- `tests/`: Python and Android-source behavior tests.
- `releases/`: optional place for locally built APK files.

This public repository intentionally does not include personal reports, raw ADB dumps, local databases or Helper export caches.

## Quick Start

Download the APK from the latest Release:

- [DayTrace Helper 0.1.0](https://github.com/linchuanXu/daytrace-public/releases/tag/v0.1.0)

Then run the desktop sync:

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

## Output

DayTrace writes local files like:

```text
data/
  2026-01-01/
    2026-01-01.md
    summary.json
  _helper_exports/
  _syncs/
```

Only you should decide where those files go next. Keep them private unless you intentionally sanitize them.

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

## Data Completeness

DayTrace deliberately separates data sources by how they can be collected:

- 实时归档: notifications and accessibility events must be captured while the Android services are enabled. 通知监听连接时会补抓当前仍存在的通知, but 已经消失且监听当时未开启的通知无法回补.
- 周期采样: location is recorded by app launch, daily work and periodic work on a best-effort basis. It is a set of samples, not a complete route trace.
- 历史回查: app usage, media, SMS, calls, calendar, contacts, files and app changes are queried from Android providers when the system still retains them and permissions allow access.
- 当前快照: battery, storage, Wi-Fi and current notification state describe the sync moment, not the full day.

打开 Helper 后会刷新最近 3 天 daily_context.json, which helps reports catch up after notification, accessibility or location archives changed on the phone.

## Project Direction

- Easier setup for non-developers.
- Better Helper APK export and diagnostics UX.
- Safer redaction and demo-data tooling.
- Richer local AI workflows over generated reports.
- More Android vendor compatibility.
- Keep the core data path local, inspectable and user-owned.

Forks are welcome, especially around Android vendor compatibility, better report design, privacy review, redaction tooling, and local AI integrations.

## License

See `LICENSE`.
