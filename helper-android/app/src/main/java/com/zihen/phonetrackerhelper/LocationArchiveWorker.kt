package com.zihen.phonetrackerhelper

import android.content.Context
import androidx.work.Worker
import androidx.work.WorkerParameters

class LocationArchiveWorker(
    appContext: Context,
    workerParams: WorkerParameters,
) : Worker(appContext, workerParams) {
    override fun doWork(): Result {
        LocationArchive.recordBestEffort(applicationContext, "periodic_location_worker")
        return Result.success()
    }
}
