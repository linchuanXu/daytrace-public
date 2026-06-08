package com.zihen.phonetrackerhelper

import java.time.LocalDate

data class UsageAppRecord(
    val date: LocalDate,
    val packageName: String,
    val appName: String,
    val totalForegroundSeconds: Long,
    val totalVisibleSeconds: Long,
    val lastUsed: String?,
    val firstTimeStamp: String?,
    val lastTimeStamp: String?,
    val launchCount: Int?,
    val recordedByHelper: Boolean,
    val source: String,
)

data class DayStatus(
    val date: LocalDate,
    val queriedAt: String,
    val queryStart: String,
    val queryEnd: String,
    val rawAppCount: Int,
    val exportedAppCount: Int,
    val hasUsagePermission: Boolean,
    val sourceStatus: String,
    val errorMessage: String?,
)

data class CacheSummary(
    val cachedDays: Int,
    val cachedAppRows: Int,
    val lastQueriedAt: String?,
)

data class ExportResult(
    val exportedDays: Int,
    val appRows: Int,
    val emptyDays: Int,
    val failedDays: Int,
    val outputDir: String,
    val skippedDays: Int = 0,
)
