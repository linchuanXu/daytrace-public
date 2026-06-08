package com.zihen.phonetrackerhelper

import android.content.Context
import androidx.work.Worker
import androidx.work.WorkerParameters

class DailyCollectWorker(
    appContext: Context,
    workerParams: WorkerParameters,
) : Worker(appContext, workerParams) {
    override fun doWork(): Result {
        return try {
            LocationArchive.recordBestEffort(applicationContext, "daily_collect_worker")
            UsageStatsExporter(applicationContext).collectRecentDays(14, force = false)
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }
}
