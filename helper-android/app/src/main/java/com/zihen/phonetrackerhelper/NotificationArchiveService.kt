package com.zihen.phonetrackerhelper

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONObject
import java.io.File

class NotificationArchiveService : NotificationListenerService() {
    override fun onListenerConnected() {
        super.onListenerConnected()
        activeNotifications.orEmpty().forEach { sbn ->
            archive("active", sbn)
        }
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        archive("posted", sbn)
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        archive("removed", sbn)
    }

    private fun archive(event: String, sbn: StatusBarNotification) {
        val extras = sbn.notification.extras
        val body = JSONObject()
            .put("time_millis", System.currentTimeMillis())
            .put("event", event)
            .put("package", sbn.packageName)
            .put("title", extras.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: "")
            .put("text", extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: "")
            .put("post_time_millis", sbn.postTime)
            .put("key", sbn.key ?: "")
        File(filesDir, "notification_events.jsonl").appendText(body.toString() + "\n", Charsets.UTF_8)
    }
}
