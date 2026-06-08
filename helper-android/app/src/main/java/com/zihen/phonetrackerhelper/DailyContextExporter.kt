package com.zihen.phonetrackerhelper

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.net.wifi.WifiManager
import android.os.BatteryManager
import android.os.Environment
import android.os.StatFs
import android.provider.CalendarContract
import android.provider.CallLog
import android.provider.ContactsContract
import android.provider.MediaStore
import android.provider.Telephony
import androidx.exifinterface.media.ExifInterface
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter

class DailyContextExporter(private val context: Context) {
    private val zone: ZoneId = ZoneId.systemDefault()

    private val exportRoot: File
        get() = File(Environment.getExternalStorageDirectory(), "PhoneTracker/export")

    fun exportDay(date: LocalDate): Int {
        val diagnostics = JSONObject()
        val media = collectMedia(date, diagnostics)
        val locations = collectLocationSnapshots(diagnostics)
        val archivedLocations = collectArchivedLocationSnapshots(date, diagnostics)
        val deviceState = collectDeviceState(diagnostics)
        val files = collectFileActivity(date, diagnostics)
        val appChanges = collectAppChanges(date, diagnostics)
        val communicationBackup = JSONObject()
            .put("sms_count", collectSmsBackup(date, diagnostics).length())
            .put("call_count", collectCallBackup(date, diagnostics).length())
            .put("calendar_count", collectCalendarBackup(date, diagnostics).length())
            .put("contacts_updated_count", collectContactsBackup(date, diagnostics).length())
        val notificationHistory = collectNotificationHistory(date, diagnostics)
        val accessibilityEvents = collectAccessibilityEvents(date, diagnostics)

        val body = JSONObject()
            .put("schema_version", 1)
            .put("date", date.toString())
            .put("timezone", zone.id)
            .put("source", "PhoneTrackerHelper")
            .put("source_status", sourceStatus(diagnostics))
            .put("exported_at", ZonedDateTime.now(zone).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME))
            .put("media", media)
            .put("location_snapshots", locations)
            .put("archived_location_snapshots", archivedLocations)
            .put("device_state", deviceState)
            .put("files", files)
            .put("app_changes", appChanges)
            .put("communication_backup", communicationBackup)
            .put("notification_history", notificationHistory)
            .put("accessibility_events", accessibilityEvents)
            .put("diagnostics", diagnostics)

        val dayDir = File(exportRoot, date.toString())
        dayDir.mkdirs()
        File(dayDir, "daily_context.json").writeText(body.toString(2), Charsets.UTF_8)
        return media.optJSONArray("items")?.length() ?: 0
    }

    private fun collectMedia(date: LocalDate, diagnostics: JSONObject): JSONObject {
        val items = JSONArray()
        var photos = 0
        var videos = 0
        var audio = 0
        photos += queryMediaItems(
            date = date,
            uri = MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            type = "photo",
            diagnostics = diagnostics,
            target = items,
        )
        videos += queryMediaItems(
            date = date,
            uri = MediaStore.Video.Media.EXTERNAL_CONTENT_URI,
            type = "video",
            diagnostics = diagnostics,
            target = items,
        )
        audio += queryAudioItems(date, diagnostics, items)
        return JSONObject()
            .put("photos_count", photos)
            .put("videos_count", videos)
            .put("audio_count", audio)
            .put("items", items)
    }

    private fun queryMediaItems(
        date: LocalDate,
        uri: android.net.Uri,
        type: String,
        diagnostics: JSONObject,
        target: JSONArray,
    ): Int {
        val startMs = date.atStartOfDay(zone).toInstant().toEpochMilli()
        val endMs = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        val projection = arrayOf(
            MediaStore.MediaColumns.DISPLAY_NAME,
            MediaStore.MediaColumns.RELATIVE_PATH,
            MediaStore.MediaColumns.DATA,
            MediaStore.MediaColumns.SIZE,
            MediaStore.MediaColumns.WIDTH,
            MediaStore.MediaColumns.HEIGHT,
            MediaStore.MediaColumns.MIME_TYPE,
            if (type == "video") MediaStore.Video.Media.DATE_TAKEN else MediaStore.Images.Media.DATE_TAKEN,
            if (type == "video") MediaStore.Video.Media.DURATION else MediaStore.Images.Media.ORIENTATION,
        )
        val dateTakenColumn = if (type == "video") MediaStore.Video.Media.DATE_TAKEN else MediaStore.Images.Media.DATE_TAKEN
        return try {
            var count = 0
            context.contentResolver.query(
                uri,
                projection,
                "$dateTakenColumn >= ? AND $dateTakenColumn < ?",
                arrayOf(startMs.toString(), endMs.toString()),
                "$dateTakenColumn ASC",
            )?.use { cursor ->
                val displayNameIdx = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.DISPLAY_NAME)
                val relativePathIdx = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.RELATIVE_PATH)
                val dataIdx = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.DATA)
                val sizeIdx = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.SIZE)
                val widthIdx = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.WIDTH)
                val heightIdx = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.HEIGHT)
                val mimeIdx = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.MIME_TYPE)
                val dateTakenIdx = cursor.getColumnIndexOrThrow(dateTakenColumn)
                val extraIdx = cursor.getColumnIndexOrThrow(projection.last())
                while (cursor.moveToNext()) {
                    val takenMs = cursor.getLong(dateTakenIdx)
                    val item = JSONObject()
                        .put("type", type)
                        .put("time", formatMillis(takenMs))
                        .put("display_name", cursor.getString(displayNameIdx) ?: "")
                        .put("relative_path", cursor.getString(relativePathIdx) ?: "")
                        .put("size_bytes", cursor.getLong(sizeIdx))
                        .put("width", cursor.getInt(widthIdx))
                        .put("height", cursor.getInt(heightIdx))
                        .put("mime_type", cursor.getString(mimeIdx) ?: "")
                    if (type == "video") {
                        item.put("duration_seconds", cursor.getLong(extraIdx) / 1000L)
                    }
                    addExifLocation(item, cursor.getString(dataIdx))
                    target.put(item)
                    count += 1
                }
            }
            diagnostics.put("${type}_media", JSONObject().put("status", "ok").put("count", count))
            count
        } catch (e: SecurityException) {
            diagnostics.put("${type}_media", JSONObject().put("status", "permission_missing").put("error", e.message ?: "SecurityException"))
            0
        } catch (e: RuntimeException) {
            diagnostics.put("${type}_media", JSONObject().put("status", "failed").put("error", e.message ?: e.javaClass.simpleName))
            0
        }
    }

    private fun addExifLocation(item: JSONObject, path: String?) {
        if (path.isNullOrBlank()) return
        try {
            val latLong = ExifInterface(path).latLong
            if (latLong != null) {
                item.put("latitude", latLong[0])
                item.put("longitude", latLong[1])
            }
        } catch (_: RuntimeException) {
        } catch (_: java.io.IOException) {
        }
    }

    private fun queryAudioItems(date: LocalDate, diagnostics: JSONObject, target: JSONArray): Int {
        val startSeconds = date.atStartOfDay(zone).toEpochSecond()
        val endSeconds = date.plusDays(1).atStartOfDay(zone).toEpochSecond()
        val projection = arrayOf(
            MediaStore.MediaColumns.DISPLAY_NAME,
            MediaStore.MediaColumns.RELATIVE_PATH,
            MediaStore.MediaColumns.SIZE,
            MediaStore.MediaColumns.MIME_TYPE,
            MediaStore.MediaColumns.DATE_MODIFIED,
            MediaStore.Audio.Media.DURATION,
        )
        return try {
            var count = 0
            context.contentResolver.query(
                MediaStore.Audio.Media.EXTERNAL_CONTENT_URI,
                projection,
                "${MediaStore.MediaColumns.DATE_MODIFIED} >= ? AND ${MediaStore.MediaColumns.DATE_MODIFIED} < ?",
                arrayOf(startSeconds.toString(), endSeconds.toString()),
                "${MediaStore.MediaColumns.DATE_MODIFIED} ASC",
            )?.use { cursor ->
                val displayNameIdx = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.DISPLAY_NAME)
                val relativePathIdx = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.RELATIVE_PATH)
                val sizeIdx = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.SIZE)
                val mimeIdx = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.MIME_TYPE)
                val dateModifiedIdx = cursor.getColumnIndexOrThrow(MediaStore.MediaColumns.DATE_MODIFIED)
                val durationIdx = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DURATION)
                while (cursor.moveToNext()) {
                    target.put(
                        JSONObject()
                            .put("type", "audio")
                            .put("time", formatMillis(cursor.getLong(dateModifiedIdx) * 1000L))
                            .put("display_name", cursor.getString(displayNameIdx) ?: "")
                            .put("relative_path", cursor.getString(relativePathIdx) ?: "")
                            .put("size_bytes", cursor.getLong(sizeIdx))
                            .put("mime_type", cursor.getString(mimeIdx) ?: "")
                            .put("duration_seconds", cursor.getLong(durationIdx) / 1000L),
                    )
                    count += 1
                }
            }
            diagnostics.put("audio_media", JSONObject().put("status", "ok").put("count", count))
            count
        } catch (e: SecurityException) {
            diagnostics.put("audio_media", JSONObject().put("status", "permission_missing").put("error", e.message ?: "SecurityException"))
            0
        } catch (e: RuntimeException) {
            diagnostics.put("audio_media", JSONObject().put("status", "failed").put("error", e.message ?: e.javaClass.simpleName))
            0
        }
    }

    private fun collectLocationSnapshots(diagnostics: JSONObject): JSONArray {
        val array = JSONArray()
        if (!hasPermission(Manifest.permission.ACCESS_FINE_LOCATION) && !hasPermission(Manifest.permission.ACCESS_COARSE_LOCATION)) {
            diagnostics.put("location", JSONObject().put("status", "permission_missing"))
            return array
        }
        return try {
            val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
            val locations = manager.getProviders(true)
                .mapNotNull { provider -> runCatching { manager.getLastKnownLocation(provider) }.getOrNull() }
                .sortedByDescending { it.time }
            locations.take(3).forEach { array.put(it.toJson()) }
            diagnostics.put("location", JSONObject().put("status", "ok").put("count", array.length()))
            array
        } catch (e: RuntimeException) {
            diagnostics.put("location", JSONObject().put("status", "failed").put("error", e.message ?: e.javaClass.simpleName))
            array
        }
    }

    private fun collectArchivedLocationSnapshots(date: LocalDate, diagnostics: JSONObject): JSONArray {
        val items = JSONArray()
        val startMs = date.atStartOfDay(zone).toInstant().toEpochMilli()
        val endMs = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        val file = File(context.filesDir, "location_events.jsonl")
        if (!file.exists()) {
            diagnostics.put("archived_location", JSONObject().put("status", "empty"))
            return items
        }
        return try {
            file.forEachLine(Charsets.UTF_8) { line ->
                if (items.length() >= 300 || line.isBlank()) return@forEachLine
                val raw = runCatching { JSONObject(line) }.getOrNull() ?: return@forEachLine
                val timeMs = raw.optLong("time_millis", 0L)
                if (timeMs < startMs || timeMs >= endMs) return@forEachLine
                items.put(
                    JSONObject()
                        .put("time", formatMillis(timeMs))
                        .put("recorded_at", formatMillis(raw.optLong("recorded_at_millis", timeMs)))
                        .put("reason", raw.optString("reason"))
                        .put("provider", raw.optString("provider"))
                        .put("latitude", raw.optDouble("latitude"))
                        .put("longitude", raw.optDouble("longitude"))
                        .put("accuracy_m", raw.opt("accuracy_m")),
                )
            }
            diagnostics.put("archived_location", JSONObject().put("status", "ok").put("count", items.length()))
            items
        } catch (e: RuntimeException) {
            diagnostics.put("archived_location", JSONObject().put("status", "failed").put("error", e.message ?: e.javaClass.simpleName))
            items
        }
    }

    private fun collectDeviceState(diagnostics: JSONObject): JSONObject {
        val body = JSONObject()
        try {
            val battery = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            val level = battery?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
            val scale = battery?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
            if (level >= 0 && scale > 0) body.put("battery_level", (level * 100) / scale)
            val status = battery?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
            body.put(
                "charging",
                status == BatteryManager.BATTERY_STATUS_CHARGING ||
                    status == BatteryManager.BATTERY_STATUS_FULL,
            )
            val temp = battery?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0) ?: 0
            if (temp > 0) body.put("temperature_c", temp / 10.0)

            val stat = StatFs(Environment.getExternalStorageDirectory().absolutePath)
            body.put("available_storage_mb", stat.availableBytes / 1024L / 1024L)
            body.put("total_storage_mb", stat.totalBytes / 1024L / 1024L)

            val wifi = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            val ssid = wifi.connectionInfo?.ssid?.trim('"')
            if (!ssid.isNullOrBlank() && ssid != "<unknown ssid>") body.put("wifi_ssid", ssid)
            body.put("wifi_bssid", wifi.connectionInfo?.bssid ?: "")
            diagnostics.put("device_state", JSONObject().put("status", "ok"))
        } catch (e: RuntimeException) {
            diagnostics.put("device_state", JSONObject().put("status", "failed").put("error", e.message ?: e.javaClass.simpleName))
        }
        return body
    }

    private fun collectFileActivity(date: LocalDate, diagnostics: JSONObject): JSONObject {
        val items = JSONArray()
        val startMs = date.atStartOfDay(zone).toInstant().toEpochMilli()
        val endMs = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        val roots = listOf(
            Environment.DIRECTORY_DOWNLOADS,
            Environment.DIRECTORY_DCIM,
            Environment.DIRECTORY_PICTURES,
            Environment.DIRECTORY_MOVIES,
            Environment.DIRECTORY_MUSIC,
            Environment.DIRECTORY_DOCUMENTS,
        ).map { Environment.getExternalStoragePublicDirectory(it) }
        return try {
            roots.filter { it.exists() }.forEach { root ->
                root.walkTopDown()
                    .maxDepth(5)
                    .filter { it.isFile && it.lastModified() >= startMs && it.lastModified() < endMs }
                    .take(80)
                    .forEach { file ->
                        items.put(
                            JSONObject()
                                .put("time", formatMillis(file.lastModified()))
                                .put("name", file.name)
                                .put("relative_path", root.name + "/" + file.relativeToOrSelf(root).parent.orEmpty())
                                .put("size_bytes", file.length())
                                .put("extension", file.extension.lowercase()),
                        )
                    }
            }
            diagnostics.put("files", JSONObject().put("status", "ok").put("count", items.length()))
            JSONObject()
                .put("created_or_modified_count", items.length())
                .put("items", items)
        } catch (e: RuntimeException) {
            diagnostics.put("files", JSONObject().put("status", "failed").put("error", e.message ?: e.javaClass.simpleName))
            JSONObject().put("created_or_modified_count", 0).put("items", items)
        }
    }

    private fun collectAppChanges(date: LocalDate, diagnostics: JSONObject): JSONObject {
        val items = JSONArray()
        val startMs = date.atStartOfDay(zone).toInstant().toEpochMilli()
        val endMs = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        var installed = 0
        var updated = 0
        return try {
            context.packageManager.getInstalledPackages(0).forEach { pkg ->
                val firstInstall = pkg.firstInstallTime
                val lastUpdate = pkg.lastUpdateTime
                val event = when {
                    firstInstall >= startMs && firstInstall < endMs -> {
                        installed += 1
                        "installed"
                    }
                    lastUpdate >= startMs && lastUpdate < endMs -> {
                        updated += 1
                        "updated"
                    }
                    else -> null
                } ?: return@forEach
                val appInfo = pkg.applicationInfo
                val appName = appInfo?.loadLabel(context.packageManager)?.toString() ?: pkg.packageName
                val isSystem = appInfo?.let { (it.flags and ApplicationInfo.FLAG_SYSTEM) != 0 } ?: false
                items.put(
                    JSONObject()
                        .put("package", pkg.packageName)
                        .put("name", appName)
                        .put("event", event)
                        .put("first_install_time", formatMillis(firstInstall))
                        .put("last_update_time", formatMillis(lastUpdate))
                        .put("version_name", pkg.versionName ?: "")
                        .put("is_system", isSystem),
                )
            }
            diagnostics.put("apps", JSONObject().put("status", "ok").put("count", items.length()))
            JSONObject()
                .put("installed_count", installed)
                .put("updated_count", updated)
                .put("items", items)
        } catch (e: RuntimeException) {
            diagnostics.put("apps", JSONObject().put("status", "failed").put("error", e.message ?: e.javaClass.simpleName))
            JSONObject().put("installed_count", installed).put("updated_count", updated).put("items", items)
        }
    }

    private fun collectSmsBackup(date: LocalDate, diagnostics: JSONObject): JSONArray {
        val items = JSONArray()
        if (!hasPermission(Manifest.permission.READ_SMS)) {
            diagnostics.put("sms_backup", JSONObject().put("status", "permission_missing"))
            return items
        }
        val startMs = date.atStartOfDay(zone).toInstant().toEpochMilli()
        val endMs = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        return try {
            context.contentResolver.query(
                Telephony.Sms.CONTENT_URI,
                arrayOf(Telephony.Sms.DATE, Telephony.Sms.ADDRESS, Telephony.Sms.BODY, Telephony.Sms.TYPE),
                "${Telephony.Sms.DATE} >= ? AND ${Telephony.Sms.DATE} < ?",
                arrayOf(startMs.toString(), endMs.toString()),
                "${Telephony.Sms.DATE} ASC",
            )?.use { cursor ->
                val dateIdx = cursor.getColumnIndexOrThrow(Telephony.Sms.DATE)
                val addressIdx = cursor.getColumnIndexOrThrow(Telephony.Sms.ADDRESS)
                val bodyIdx = cursor.getColumnIndexOrThrow(Telephony.Sms.BODY)
                val typeIdx = cursor.getColumnIndexOrThrow(Telephony.Sms.TYPE)
                while (cursor.moveToNext() && items.length() < 200) {
                    items.put(
                        JSONObject()
                            .put("time", formatMillis(cursor.getLong(dateIdx)))
                            .put("address", cursor.getString(addressIdx) ?: "")
                            .put("body", cursor.getString(bodyIdx) ?: "")
                            .put("type", cursor.getInt(typeIdx)),
                    )
                }
            }
            diagnostics.put("sms_backup", JSONObject().put("status", "ok").put("count", items.length()))
            items
        } catch (e: RuntimeException) {
            diagnostics.put("sms_backup", JSONObject().put("status", "failed").put("error", e.message ?: e.javaClass.simpleName))
            items
        }
    }

    private fun collectCallBackup(date: LocalDate, diagnostics: JSONObject): JSONArray {
        val items = JSONArray()
        if (!hasPermission(Manifest.permission.READ_CALL_LOG)) {
            diagnostics.put("calls_backup", JSONObject().put("status", "permission_missing"))
            return items
        }
        val startMs = date.atStartOfDay(zone).toInstant().toEpochMilli()
        val endMs = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        return try {
            context.contentResolver.query(
                CallLog.Calls.CONTENT_URI,
                arrayOf(CallLog.Calls.DATE, CallLog.Calls.NUMBER, CallLog.Calls.CACHED_NAME, CallLog.Calls.TYPE, CallLog.Calls.DURATION),
                "${CallLog.Calls.DATE} >= ? AND ${CallLog.Calls.DATE} < ?",
                arrayOf(startMs.toString(), endMs.toString()),
                "${CallLog.Calls.DATE} ASC",
            )?.use { cursor ->
                val dateIdx = cursor.getColumnIndexOrThrow(CallLog.Calls.DATE)
                val numberIdx = cursor.getColumnIndexOrThrow(CallLog.Calls.NUMBER)
                val nameIdx = cursor.getColumnIndexOrThrow(CallLog.Calls.CACHED_NAME)
                val typeIdx = cursor.getColumnIndexOrThrow(CallLog.Calls.TYPE)
                val durationIdx = cursor.getColumnIndexOrThrow(CallLog.Calls.DURATION)
                while (cursor.moveToNext() && items.length() < 200) {
                    items.put(
                        JSONObject()
                            .put("time", formatMillis(cursor.getLong(dateIdx)))
                            .put("number", cursor.getString(numberIdx) ?: "")
                            .put("name", cursor.getString(nameIdx) ?: "")
                            .put("type", cursor.getInt(typeIdx))
                            .put("duration_seconds", cursor.getLong(durationIdx)),
                    )
                }
            }
            diagnostics.put("calls_backup", JSONObject().put("status", "ok").put("count", items.length()))
            items
        } catch (e: RuntimeException) {
            diagnostics.put("calls_backup", JSONObject().put("status", "failed").put("error", e.message ?: e.javaClass.simpleName))
            items
        }
    }

    private fun collectCalendarBackup(date: LocalDate, diagnostics: JSONObject): JSONArray {
        val items = JSONArray()
        if (!hasPermission(Manifest.permission.READ_CALENDAR)) {
            diagnostics.put("calendar_backup", JSONObject().put("status", "permission_missing"))
            return items
        }
        val startMs = date.atStartOfDay(zone).toInstant().toEpochMilli()
        val endMs = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        return try {
            context.contentResolver.query(
                CalendarContract.Events.CONTENT_URI,
                arrayOf(CalendarContract.Events.DTSTART, CalendarContract.Events.DTEND, CalendarContract.Events.TITLE, CalendarContract.Events.EVENT_LOCATION),
                "${CalendarContract.Events.DTSTART} < ? AND (${CalendarContract.Events.DTEND} IS NULL OR ${CalendarContract.Events.DTEND} >= ?)",
                arrayOf(endMs.toString(), startMs.toString()),
                "${CalendarContract.Events.DTSTART} ASC",
            )?.use { cursor ->
                val startIdx = cursor.getColumnIndexOrThrow(CalendarContract.Events.DTSTART)
                val endIdx = cursor.getColumnIndexOrThrow(CalendarContract.Events.DTEND)
                val titleIdx = cursor.getColumnIndexOrThrow(CalendarContract.Events.TITLE)
                val locationIdx = cursor.getColumnIndexOrThrow(CalendarContract.Events.EVENT_LOCATION)
                while (cursor.moveToNext() && items.length() < 100) {
                    items.put(
                        JSONObject()
                            .put("start", formatMillis(cursor.getLong(startIdx)))
                            .put("end", if (cursor.isNull(endIdx)) JSONObject.NULL else formatMillis(cursor.getLong(endIdx)))
                            .put("title", cursor.getString(titleIdx) ?: "")
                            .put("location", cursor.getString(locationIdx) ?: ""),
                    )
                }
            }
            diagnostics.put("calendar_backup", JSONObject().put("status", "ok").put("count", items.length()))
            items
        } catch (e: RuntimeException) {
            diagnostics.put("calendar_backup", JSONObject().put("status", "failed").put("error", e.message ?: e.javaClass.simpleName))
            items
        }
    }

    private fun collectContactsBackup(date: LocalDate, diagnostics: JSONObject): JSONArray {
        val items = JSONArray()
        if (!hasPermission(Manifest.permission.READ_CONTACTS)) {
            diagnostics.put("contacts_backup", JSONObject().put("status", "permission_missing"))
            return items
        }
        val startMs = date.atStartOfDay(zone).toInstant().toEpochMilli()
        val endMs = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        return try {
            context.contentResolver.query(
                ContactsContract.Contacts.CONTENT_URI,
                arrayOf(
                    ContactsContract.Contacts.DISPLAY_NAME_PRIMARY,
                    ContactsContract.Contacts.CONTACT_LAST_UPDATED_TIMESTAMP,
                ),
                "${ContactsContract.Contacts.CONTACT_LAST_UPDATED_TIMESTAMP} >= ? AND ${ContactsContract.Contacts.CONTACT_LAST_UPDATED_TIMESTAMP} < ?",
                arrayOf(startMs.toString(), endMs.toString()),
                "${ContactsContract.Contacts.CONTACT_LAST_UPDATED_TIMESTAMP} ASC",
            )?.use { cursor ->
                val nameIdx = cursor.getColumnIndexOrThrow(ContactsContract.Contacts.DISPLAY_NAME_PRIMARY)
                val updatedIdx = cursor.getColumnIndexOrThrow(ContactsContract.Contacts.CONTACT_LAST_UPDATED_TIMESTAMP)
                while (cursor.moveToNext() && items.length() < 100) {
                    items.put(
                        JSONObject()
                            .put("updated_at", formatMillis(cursor.getLong(updatedIdx)))
                            .put("name", cursor.getString(nameIdx) ?: ""),
                    )
                }
            }
            diagnostics.put("contacts_backup", JSONObject().put("status", "ok").put("count", items.length()))
            items
        } catch (e: RuntimeException) {
            diagnostics.put("contacts_backup", JSONObject().put("status", "failed").put("error", e.message ?: e.javaClass.simpleName))
            items
        }
    }

    private fun collectNotificationHistory(date: LocalDate, diagnostics: JSONObject): JSONObject {
        val items = JSONArray()
        val startMs = date.atStartOfDay(zone).toInstant().toEpochMilli()
        val endMs = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        val file = File(context.filesDir, "notification_events.jsonl")
        if (!file.exists()) {
            diagnostics.put("notification_history", JSONObject().put("status", "empty"))
            return JSONObject().put("count", 0).put("items", items)
        }
        return try {
            file.forEachLine(Charsets.UTF_8) { line ->
                if (items.length() >= 300 || line.isBlank()) return@forEachLine
                val raw = runCatching { JSONObject(line) }.getOrNull() ?: return@forEachLine
                val timeMs = raw.optLong("time_millis", 0L)
                if (timeMs < startMs || timeMs >= endMs) return@forEachLine
                items.put(
                    JSONObject()
                        .put("time", formatMillis(timeMs))
                        .put("event", raw.optString("event"))
                        .put("package", raw.optString("package"))
                        .put("title", raw.optString("title"))
                        .put("text", raw.optString("text")),
                )
            }
            diagnostics.put("notification_history", JSONObject().put("status", "ok").put("count", items.length()))
            JSONObject().put("count", items.length()).put("items", items)
        } catch (e: RuntimeException) {
            diagnostics.put("notification_history", JSONObject().put("status", "failed").put("error", e.message ?: e.javaClass.simpleName))
            JSONObject().put("count", items.length()).put("items", items)
        }
    }

    private fun collectAccessibilityEvents(date: LocalDate, diagnostics: JSONObject): JSONObject {
        val items = JSONArray()
        val startMs = date.atStartOfDay(zone).toInstant().toEpochMilli()
        val endMs = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        val file = File(context.filesDir, "accessibility_events.jsonl")
        if (!file.exists()) {
            diagnostics.put("accessibility_events", JSONObject().put("status", "empty"))
            return JSONObject().put("count", 0).put("items", items)
        }
        return try {
            file.forEachLine(Charsets.UTF_8) { line ->
                if (items.length() >= 500 || line.isBlank()) return@forEachLine
                val raw = runCatching { JSONObject(line) }.getOrNull() ?: return@forEachLine
                val timeMs = raw.optLong("time_millis", 0L)
                if (timeMs < startMs || timeMs >= endMs) return@forEachLine
                items.put(
                    JSONObject()
                        .put("time", formatMillis(timeMs))
                        .put("package", raw.optString("package"))
                        .put("event_type", raw.optString("event_type"))
                        .put("class_name", raw.optString("class_name"))
                        .put("text", raw.optString("text"))
                        .put("content_description", raw.optString("content_description"))
                        .put("view_id", raw.optString("view_id")),
                )
            }
            diagnostics.put("accessibility_events", JSONObject().put("status", "ok").put("count", items.length()))
            JSONObject().put("count", items.length()).put("items", items)
        } catch (e: RuntimeException) {
            diagnostics.put("accessibility_events", JSONObject().put("status", "failed").put("error", e.message ?: e.javaClass.simpleName))
            JSONObject().put("count", items.length()).put("items", items)
        }
    }

    private fun Location.toJson(): JSONObject {
        val body = JSONObject()
            .put("time", formatMillis(time))
            .put("provider", provider)
            .put("latitude", latitude)
            .put("longitude", longitude)
            .put("accuracy_m", if (hasAccuracy()) accuracy.toDouble() else JSONObject.NULL)
        if (hasAltitude()) body.put("altitude_m", altitude)
        if (hasSpeed()) body.put("speed_mps", speed.toDouble())
        return body
    }

    private fun hasPermission(permission: String): Boolean {
        return context.checkSelfPermission(permission) == PackageManager.PERMISSION_GRANTED
    }

    private fun formatMillis(millis: Long): String {
        return ZonedDateTime.ofInstant(Instant.ofEpochMilli(millis), zone)
            .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
    }

    private fun sourceStatus(diagnostics: JSONObject): String {
        val keys = diagnostics.keys().asSequence().toList()
        if (keys.isEmpty()) return "empty"
        return if (keys.any { diagnostics.optJSONObject(it)?.optString("status") == "ok" }) "partial" else "failed"
    }
}
