package com.zihen.phonetrackerhelper

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent
import org.json.JSONObject
import java.io.File

class AccessibilityArchiveService : AccessibilityService() {
    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        val text = event.text.joinToString(" ").take(500)
        val body = JSONObject()
            .put("time_millis", System.currentTimeMillis())
            .put("event_uptime_millis", event.eventTime)
            .put("event_type", eventTypeName(event.eventType))
            .put("package", event.packageName?.toString() ?: "")
            .put("class_name", event.className?.toString() ?: "")
            .put("text", text)
            .put("content_description", event.contentDescription?.toString() ?: "")
            .put("view_id", event.source?.viewIdResourceName ?: "")
        File(filesDir, "accessibility_events.jsonl").appendText(body.toString() + "\n", Charsets.UTF_8)
    }

    override fun onInterrupt() = Unit

    private fun eventTypeName(type: Int): String {
        return when (type) {
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED -> "TYPE_WINDOW_STATE_CHANGED"
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED -> "TYPE_WINDOW_CONTENT_CHANGED"
            AccessibilityEvent.TYPE_VIEW_CLICKED -> "TYPE_VIEW_CLICKED"
            AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED -> "TYPE_VIEW_TEXT_CHANGED"
            AccessibilityEvent.TYPE_VIEW_FOCUSED -> "TYPE_VIEW_FOCUSED"
            else -> type.toString()
        }
    }
}
