package com.zihen.phonetrackerhelper

import android.app.AppOpsManager
import android.app.usage.UsageEvents
import android.app.usage.UsageStats
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Environment
import android.os.Process
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter

class UsageStatsExporter(private val context: Context) {
    companion object {
        private val COMPLETE_SOURCE_STATUSES = setOf("ok", "empty_from_system")
        private const val QUERY_END_TOLERANCE_MS = 1_000L
    }

    private val zone: ZoneId = ZoneId.systemDefault()
    private val usageStatsManager =
        context.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
    private val packageManager = context.packageManager
    private val repository = UsageRepository(context)
    private val contextExporter by lazy { DailyContextExporter(context) }

    private data class EventTotals(
        var totalForegroundMillis: Long = 0L,
        var firstSeenMillis: Long? = null,
        var lastSeenMillis: Long? = null,
        var sessions: Int = 0,
    )

    val exportRoot: File
        get() = File(Environment.getExternalStorageDirectory(), "PhoneTracker/export")

    fun hasUsageAccess(): Boolean {
        val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            appOps.unsafeCheckOpNoThrow(
                AppOpsManager.OPSTR_GET_USAGE_STATS,
                Process.myUid(),
                context.packageName,
            )
        } else {
            @Suppress("DEPRECATION")
            appOps.checkOpNoThrow(
                AppOpsManager.OPSTR_GET_USAGE_STATS,
                Process.myUid(),
                context.packageName,
            )
        }
        return mode == AppOpsManager.MODE_ALLOWED
    }

    fun hasExportStorageAccess(): Boolean {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.R || Environment.isExternalStorageManager()
    }

    fun exportRecentDays(days: Long = 30): ExportResult {
        val end = LocalDate.now(zone)
        val start = end.minusDays(days - 1)
        return exportRange(start, end)
    }

    fun collectRecentDays(days: Long = 14, force: Boolean = false): ExportResult {
        val end = LocalDate.now(zone)
        val start = end.minusDays(days - 1)
        return collectDateRange(start, end, force)
    }

    fun exportRange(startDate: LocalDate, endDate: LocalDate, force: Boolean = true): ExportResult {
        require(!endDate.isBefore(startDate)) { "End date must be on or after start date" }
        exportRoot.mkdirs()
        return collectDateRange(startDate, endDate, force)
    }

    private fun collectDateRange(startDate: LocalDate, endDate: LocalDate, force: Boolean): ExportResult {
        val today = LocalDate.now(zone)
        var exportedDays = 0
        var skippedDays = 0
        var appRows = 0
        var emptyDays = 0
        var failedDays = 0
        var cursor = startDate
        while (!cursor.isAfter(endDate)) {
            if (!force && isDayFullyProcessed(cursor, today)) {
                skippedDays += 1
                refreshContextExport(cursor)
            } else {
                val status = collectDay(cursor)
                exportedDays += 1
                appRows += exportDay(cursor, status)
                if (status.exportedAppCount == 0) emptyDays += 1
                if (status.sourceStatus == "query_failed") failedDays += 1
            }
            cursor = cursor.plusDays(1)
        }
        return ExportResult(exportedDays, appRows, emptyDays, failedDays, exportRoot.absolutePath, skippedDays)
    }

    private fun isDayFullyProcessed(date: LocalDate, today: LocalDate): Boolean {
        if (!date.isBefore(today)) return false

        val status = repository.statusFor(date) ?: return false
        if (status.sourceStatus !in COMPLETE_SOURCE_STATUSES) return false
        if (!status.coversFullNaturalDay(today)) return false
        return hasValidUsageExport(date)
    }

    private fun DayStatus.coversFullNaturalDay(today: LocalDate): Boolean {
        if (!date.isBefore(today)) return false
        val queryEndMillis = parseIsoToEpochMillis(queryEnd) ?: return false
        val expectedEndMillis = date.plusDays(1).atStartOfDay(zone).toInstant().toEpochMilli()
        return queryEndMillis >= expectedEndMillis - QUERY_END_TOLERANCE_MS
    }

    private fun hasValidUsageExport(date: LocalDate): Boolean {
        val file = File(exportRoot, "${date}/usage_stats.json")
        if (!file.exists() || file.length() == 0L) return false
        return try {
            val body = JSONObject(file.readText(Charsets.UTF_8))
            body.optString("date") == date.toString()
        } catch (_: RuntimeException) {
            false
        }
    }

    private fun parseIsoToEpochMillis(value: String): Long? {
        return try {
            ZonedDateTime.parse(value).toInstant().toEpochMilli()
        } catch (_: RuntimeException) {
            null
        }
    }

    private fun refreshContextExport(date: LocalDate) {
        try {
            contextExporter.exportDay(date)
        } catch (_: RuntimeException) {
            // Usage export is complete; context refresh is best-effort.
        }
    }

    fun cacheSummary(): CacheSummary = repository.summary()

    fun recentDiagnostics(limit: Int = 30): List<DayStatus> = repository.recentStatuses(limit)

    fun recordsFor(date: LocalDate): List<UsageAppRecord> = repository.recordsFor(date)

    fun pruneCache(retentionDays: Long) {
        repository.pruneBefore(LocalDate.now(zone).minusDays(retentionDays))
    }

    private fun collectDay(date: LocalDate): DayStatus {
        val start = date.atStartOfDay(zone)
        val end = date.plusDays(1).atStartOfDay(zone)
        val now = ZonedDateTime.now(zone)
        val queriedAt = now.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
        val queriedAtMillis = now.toInstant().toEpochMilli()
        val queryEnd = minOf(end.toInstant().toEpochMilli(), queriedAtMillis)
        val queryEndText = formatMillis(queryEnd) as String
        val hasPermission = hasUsageAccess()
        if (!hasPermission) {
            val cached = repository.recordsFor(date)
            val status = DayStatus(
                date = date,
                queriedAt = queriedAt,
                queryStart = start.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME),
                queryEnd = queryEndText,
                rawAppCount = 0,
                exportedAppCount = cached.size,
                hasUsagePermission = false,
                sourceStatus = if (cached.isNotEmpty()) "cached_only" else "permission_missing",
                errorMessage = "Usage access permission is missing.",
            )
            repository.replaceDay(status, cached)
            return status
        }

        return try {
            val eventRecords = collectEventRecords(date, start, queryEnd)
            val stats = usageStatsManager.queryUsageStats(
                UsageStatsManager.INTERVAL_DAILY,
                start.toInstant().toEpochMilli(),
                queryEnd,
            ).orEmpty()
            val validStats = stats
                .filter { it.isWithinDayBucket(start, end) }
            val apps = validStats
                .filter { it.totalTimeInForeground > 0L }
                .sortedByDescending { it.totalTimeInForeground }
                .map { it.toRecord(date, "helper_system_query", recordedByHelper = true) }
            val cachedBefore = repository.recordsFor(date)
            val useCache = eventRecords.isEmpty() && stats.isEmpty() && cachedBefore.isNotEmpty()
            val recordsToStore = when {
                eventRecords.isNotEmpty() -> eventRecords
                apps.isNotEmpty() -> apps
                useCache -> cachedBefore
                else -> emptyList()
            }
            val exportedCount = recordsToStore.size
            val status = DayStatus(
                date = date,
                queriedAt = queriedAt,
                queryStart = start.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME),
                queryEnd = queryEndText,
                rawAppCount = eventRecords.size.takeIf { it > 0 } ?: stats.size,
                exportedAppCount = exportedCount,
                hasUsagePermission = true,
                sourceStatus = when {
                    eventRecords.isNotEmpty() -> "ok"
                    apps.isNotEmpty() -> "ok"
                    useCache -> "cached_only"
                    else -> "empty_from_system"
                },
                errorMessage = null,
            )
            repository.replaceDay(status, recordsToStore)
            status
        } catch (e: RuntimeException) {
            val cached = repository.recordsFor(date)
            val status = DayStatus(
                date = date,
                queriedAt = queriedAt,
                queryStart = start.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME),
                queryEnd = queryEndText,
                rawAppCount = 0,
                exportedAppCount = cached.size,
                hasUsagePermission = true,
                sourceStatus = if (cached.isNotEmpty()) "cached_only" else "query_failed",
                errorMessage = e.message,
            )
            repository.replaceDay(status, cached)
            status
        }
    }

    private fun collectEventRecords(
        date: LocalDate,
        start: ZonedDateTime,
        queryEndMillis: Long,
    ): List<UsageAppRecord> {
        val startMillis = start.toInstant().toEpochMilli()
        val totalsByPackage = mutableMapOf<String, EventTotals>()
        val events = usageStatsManager.queryEvents(startMillis, queryEndMillis)
        val event = UsageEvents.Event()
        var currentPackage: String? = null
        var currentStartMillis: Long? = null

        fun closeCurrent(rawEndMillis: Long) {
            val packageName = currentPackage
            val rawStartMillis = currentStartMillis
            if (packageName != null && rawStartMillis != null) {
                val segmentStart = rawStartMillis.coerceAtLeast(startMillis)
                val segmentEnd = rawEndMillis.coerceAtMost(queryEndMillis)
                val duration = segmentEnd - segmentStart
                if (duration > 0L) {
                    val totals = totalsByPackage.getOrPut(packageName) { EventTotals() }
                    totals.totalForegroundMillis += duration
                    totals.firstSeenMillis = minOfNullable(totals.firstSeenMillis, segmentStart)
                    totals.lastSeenMillis = maxOfNullable(totals.lastSeenMillis, segmentEnd)
                    totals.sessions += 1
                }
            }
            currentPackage = null
            currentStartMillis = null
        }

        while (events.hasNextEvent()) {
            events.getNextEvent(event)
            val packageName = event.packageName ?: continue
            val eventMillis = event.timeStamp.coerceIn(startMillis, queryEndMillis)
            when (event.eventType) {
                UsageEvents.Event.MOVE_TO_FOREGROUND,
                UsageEvents.Event.ACTIVITY_RESUMED,
                -> {
                    if (currentPackage != null && currentPackage != packageName) {
                        closeCurrent(eventMillis)
                    }
                    if (currentPackage != packageName) {
                        currentPackage = packageName
                        currentStartMillis = eventMillis
                    }
                }
                UsageEvents.Event.MOVE_TO_BACKGROUND,
                UsageEvents.Event.ACTIVITY_PAUSED,
                UsageEvents.Event.ACTIVITY_STOPPED,
                -> {
                    if (currentPackage == packageName) {
                        closeCurrent(eventMillis)
                    }
                }
            }
        }
        closeCurrent(queryEndMillis)

        return totalsByPackage.entries
            .filter { it.value.totalForegroundMillis > 0L }
            .sortedByDescending { it.value.totalForegroundMillis }
            .map { (packageName, totals) ->
                UsageAppRecord(
                    date = date,
                    packageName = packageName,
                    appName = appName(packageName),
                    totalForegroundSeconds = totals.totalForegroundMillis / 1000L,
                    totalVisibleSeconds = totals.totalForegroundMillis / 1000L,
                    lastUsed = totals.lastSeenMillis?.let { formatMillis(it) as String },
                    firstTimeStamp = totals.firstSeenMillis?.let { formatMillis(it) as String },
                    lastTimeStamp = totals.lastSeenMillis?.let { formatMillis(it) as String },
                    launchCount = totals.sessions.takeIf { it > 0 },
                    recordedByHelper = true,
                    source = "helper_usage_events",
                )
            }
    }

    private fun exportDay(date: LocalDate, status: DayStatus): Int {
        val records = repository.recordsFor(date)

        val body = JSONObject()
            .put("schema_version", 2)
            .put("date", date.toString())
            .put("timezone", zone.id)
            .put("source", "PhoneTrackerHelper")
            .put("source_status", status.sourceStatus)
            .put("recorded_by_helper", records.isNotEmpty())
            .put("raw_system_has_data", status.rawAppCount > 0)
            .put("cache_has_data", records.isNotEmpty())
            .put("exported_at", ZonedDateTime.now(zone).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME))
            .put(
                "query_range",
                JSONObject()
                    .put("start", status.queryStart)
                    .put("end", status.queryEnd),
            )
            .put("diagnostics", status.toDiagnostics())
            .put("has_data", records.isNotEmpty())
            .put("app_count", records.size)
            .put("apps", JSONArray().also { array ->
                records.forEach { record -> array.put(record.toJson()) }
            })

        val dayDir = File(exportRoot, date.toString())
        dayDir.mkdirs()
        File(dayDir, "usage_stats.json").writeText(body.toString(2), Charsets.UTF_8)
        contextExporter.exportDay(date)
        return records.size
    }

    private fun UsageStats.totalVisibleTime(): Long {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) totalTimeVisible else 0L
    }

    private fun UsageStats.isWithinDayBucket(start: ZonedDateTime, end: ZonedDateTime): Boolean {
        return firstTimeStamp >= start.toInstant().toEpochMilli() &&
            lastTimeStamp <= end.toInstant().toEpochMilli()
    }

    private fun minOfNullable(left: Long?, right: Long): Long {
        return if (left == null) right else minOf(left, right)
    }

    private fun maxOfNullable(left: Long?, right: Long): Long {
        return if (left == null) right else maxOf(left, right)
    }

    private fun UsageStats.launchCountOrNull(): Any {
        val count = try {
            UsageStats::class.java.getMethod("getAppLaunchCount").invoke(this) as? Int
        } catch (_: ReflectiveOperationException) {
            null
        } catch (_: RuntimeException) {
            null
        }
        return if (count != null && count > 0) count else JSONObject.NULL
    }

    private fun formatMillis(millis: Long): Any {
        if (millis <= 0L) return JSONObject.NULL
        return ZonedDateTime.ofInstant(Instant.ofEpochMilli(millis), zone)
            .format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
    }

    private fun appName(packageName: String): String {
        return try {
            val info = packageManager.getApplicationInfo(packageName, 0)
            packageManager.getApplicationLabel(info).toString()
        } catch (_: PackageManager.NameNotFoundException) {
            packageName
        } catch (_: RuntimeException) {
            packageName
        }
    }

    private fun UsageStats.toRecord(date: LocalDate, source: String, recordedByHelper: Boolean): UsageAppRecord {
        return UsageAppRecord(
            date = date,
            packageName = packageName,
            appName = appName(packageName),
            totalForegroundSeconds = totalTimeInForeground / 1000L,
            totalVisibleSeconds = totalVisibleTime() / 1000L,
            lastUsed = formatMillis(lastTimeUsed).takeUnless { it == JSONObject.NULL } as? String,
            firstTimeStamp = formatMillis(firstTimeStamp).takeUnless { it == JSONObject.NULL } as? String,
            lastTimeStamp = formatMillis(lastTimeStamp).takeUnless { it == JSONObject.NULL } as? String,
            launchCount = launchCountOrNull().takeUnless { it == JSONObject.NULL } as? Int,
            recordedByHelper = recordedByHelper,
            source = source,
        )
    }

    private fun UsageAppRecord.toJson(): JSONObject {
        return JSONObject()
            .put("package", packageName)
            .put("name", appName)
            .put("total_foreground_seconds", totalForegroundSeconds)
            .put("total_visible_seconds", totalVisibleSeconds)
            .put("last_used", lastUsed ?: JSONObject.NULL)
            .put("first_time_stamp", firstTimeStamp ?: JSONObject.NULL)
            .put("last_time_stamp", lastTimeStamp ?: JSONObject.NULL)
            .put("launch_count", launchCount ?: JSONObject.NULL)
            .put("recorded_by_helper", recordedByHelper)
            .put("source", source)
    }

    private fun DayStatus.toDiagnostics(): JSONObject {
        val notes = JSONArray()
        when (sourceStatus) {
            "ok" -> notes.put("Android returned daily app records; cache refreshed.")
            "cached_only" -> notes.put("System query was empty or unavailable during export; using helper local cache.")
            "empty_from_system" -> notes.put("Helper checked this day, but Android returned no daily app records.")
            "permission_missing" -> notes.put("Usage access permission was missing during export.")
            "query_failed" -> notes.put("Android UsageStatsManager query failed.")
        }
        if (!errorMessage.isNullOrBlank()) notes.put(errorMessage)
        return JSONObject()
            .put("queried_at", queriedAt)
            .put("query_range", JSONObject().put("start", queryStart).put("end", queryEnd))
            .put("raw_app_count", rawAppCount)
            .put("exported_app_count", exportedAppCount)
            .put("has_usage_permission", hasUsagePermission)
            .put("source_status", sourceStatus)
            .put("export_notes", notes)
    }
}
