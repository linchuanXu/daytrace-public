package com.zihen.phonetrackerhelper

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.time.LocalDate

class UsageRepository(context: Context) : SQLiteOpenHelper(context, DB_NAME, null, DB_VERSION) {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE day_status (
                date TEXT PRIMARY KEY,
                queried_at TEXT NOT NULL,
                query_start TEXT NOT NULL,
                query_end TEXT NOT NULL,
                raw_app_count INTEGER NOT NULL,
                exported_app_count INTEGER NOT NULL,
                has_usage_permission INTEGER NOT NULL,
                source_status TEXT NOT NULL,
                error_message TEXT
            )
            """.trimIndent(),
        )
        db.execSQL(
            """
            CREATE TABLE usage_records (
                date TEXT NOT NULL,
                package_name TEXT NOT NULL,
                app_name TEXT NOT NULL,
                total_foreground_seconds INTEGER NOT NULL,
                total_visible_seconds INTEGER NOT NULL,
                last_used TEXT,
                first_time_stamp TEXT,
                last_time_stamp TEXT,
                launch_count INTEGER,
                recorded_by_helper INTEGER NOT NULL,
                source TEXT NOT NULL,
                PRIMARY KEY(date, package_name)
            )
            """.trimIndent(),
        )
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        db.execSQL("DROP TABLE IF EXISTS usage_records")
        db.execSQL("DROP TABLE IF EXISTS day_status")
        onCreate(db)
    }

    fun replaceDay(status: DayStatus, records: List<UsageAppRecord>) {
        writableDatabase.beginTransaction()
        try {
            writableDatabase.delete("usage_records", "date=?", arrayOf(status.date.toString()))
            records.forEach { writableDatabase.insertWithOnConflict("usage_records", null, it.values(), SQLiteDatabase.CONFLICT_REPLACE) }
            writableDatabase.insertWithOnConflict("day_status", null, status.values(), SQLiteDatabase.CONFLICT_REPLACE)
            writableDatabase.setTransactionSuccessful()
        } finally {
            writableDatabase.endTransaction()
        }
    }

    fun recordsFor(date: LocalDate): List<UsageAppRecord> {
        val cursor = readableDatabase.query(
            "usage_records",
            null,
            "date=?",
            arrayOf(date.toString()),
            null,
            null,
            "total_foreground_seconds DESC",
        )
        return cursor.use {
            buildList {
                while (it.moveToNext()) add(it.usageRecord())
            }
        }
    }

    fun statusFor(date: LocalDate): DayStatus? {
        val cursor = readableDatabase.query(
            "day_status",
            null,
            "date=?",
            arrayOf(date.toString()),
            null,
            null,
            null,
        )
        return cursor.use {
            if (it.moveToFirst()) it.dayStatus() else null
        }
    }

    fun recentStatuses(limit: Int = 90): List<DayStatus> {
        val cursor = readableDatabase.query("day_status", null, null, null, null, null, "date DESC", limit.toString())
        return cursor.use {
            buildList {
                while (it.moveToNext()) add(it.dayStatus())
            }
        }
    }

    fun summary(): CacheSummary {
        val days = readableDatabase.rawQuery("SELECT COUNT(*) FROM day_status", null).use {
            if (it.moveToFirst()) it.getInt(0) else 0
        }
        val rows = readableDatabase.rawQuery("SELECT COUNT(*) FROM usage_records", null).use {
            if (it.moveToFirst()) it.getInt(0) else 0
        }
        val last = readableDatabase.rawQuery("SELECT MAX(queried_at) FROM day_status", null).use {
            if (it.moveToFirst()) it.getString(0) else null
        }
        return CacheSummary(days, rows, last)
    }

    fun pruneBefore(cutoff: LocalDate) {
        writableDatabase.delete("usage_records", "date<?", arrayOf(cutoff.toString()))
        writableDatabase.delete("day_status", "date<?", arrayOf(cutoff.toString()))
    }

    private fun UsageAppRecord.values(): ContentValues = ContentValues().apply {
        put("date", date.toString())
        put("package_name", packageName)
        put("app_name", appName)
        put("total_foreground_seconds", totalForegroundSeconds)
        put("total_visible_seconds", totalVisibleSeconds)
        put("last_used", lastUsed)
        put("first_time_stamp", firstTimeStamp)
        put("last_time_stamp", lastTimeStamp)
        put("launch_count", launchCount)
        put("recorded_by_helper", if (recordedByHelper) 1 else 0)
        put("source", source)
    }

    private fun DayStatus.values(): ContentValues = ContentValues().apply {
        put("date", date.toString())
        put("queried_at", queriedAt)
        put("query_start", queryStart)
        put("query_end", queryEnd)
        put("raw_app_count", rawAppCount)
        put("exported_app_count", exportedAppCount)
        put("has_usage_permission", if (hasUsagePermission) 1 else 0)
        put("source_status", sourceStatus)
        put("error_message", errorMessage)
    }

    private fun android.database.Cursor.usageRecord(): UsageAppRecord = UsageAppRecord(
        date = LocalDate.parse(getString(getColumnIndexOrThrow("date"))),
        packageName = getString(getColumnIndexOrThrow("package_name")),
        appName = getString(getColumnIndexOrThrow("app_name")),
        totalForegroundSeconds = getLong(getColumnIndexOrThrow("total_foreground_seconds")),
        totalVisibleSeconds = getLong(getColumnIndexOrThrow("total_visible_seconds")),
        lastUsed = getStringOrNull("last_used"),
        firstTimeStamp = getStringOrNull("first_time_stamp"),
        lastTimeStamp = getStringOrNull("last_time_stamp"),
        launchCount = getIntOrNull("launch_count"),
        recordedByHelper = getInt(getColumnIndexOrThrow("recorded_by_helper")) == 1,
        source = getString(getColumnIndexOrThrow("source")),
    )

    private fun android.database.Cursor.dayStatus(): DayStatus = DayStatus(
        date = LocalDate.parse(getString(getColumnIndexOrThrow("date"))),
        queriedAt = getString(getColumnIndexOrThrow("queried_at")),
        queryStart = getString(getColumnIndexOrThrow("query_start")),
        queryEnd = getString(getColumnIndexOrThrow("query_end")),
        rawAppCount = getInt(getColumnIndexOrThrow("raw_app_count")),
        exportedAppCount = getInt(getColumnIndexOrThrow("exported_app_count")),
        hasUsagePermission = getInt(getColumnIndexOrThrow("has_usage_permission")) == 1,
        sourceStatus = getString(getColumnIndexOrThrow("source_status")),
        errorMessage = getStringOrNull("error_message"),
    )

    private fun android.database.Cursor.getStringOrNull(name: String): String? {
        val index = getColumnIndexOrThrow(name)
        return if (isNull(index)) null else getString(index)
    }

    private fun android.database.Cursor.getIntOrNull(name: String): Int? {
        val index = getColumnIndexOrThrow(name)
        return if (isNull(index)) null else getInt(index)
    }

    companion object {
        private const val DB_NAME = "phone_tracker_helper.db"
        private const val DB_VERSION = 1
    }
}
