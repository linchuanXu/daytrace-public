# Android Permissions

The Helper app uses permissions only to enrich local exports. You can leave permissions disabled; the corresponding report sections will be incomplete.

## Common Permissions

- Usage Access: daily app usage and foreground activity.
- Files and Media: photos, videos, audio and file activity metadata.
- Location: current and periodic location snapshots.
- SMS, Calls and Calendar: backup context for communication and schedule sections.
- Notification Access: notification history while the listener is enabled.
- Accessibility: window and interaction events while the service is enabled.

## Notes

- Notification and accessibility history cannot be reconstructed before the services were enabled.
- Location samples are periodic best-effort snapshots, not a full route trace.
- Android vendors may restrict background work, storage access or usage stats retention.
