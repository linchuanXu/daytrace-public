package com.zihen.phonetrackerhelper

import android.content.Context
import android.os.Environment
import org.json.JSONObject
import java.io.File
import java.time.LocalDate

class DailyContextReader(private val context: Context) {
    fun readFor(date: LocalDate): JSONObject? {
        val path = File(
            File(Environment.getExternalStorageDirectory(), "PhoneTracker/export/${date}"),
            "daily_context.json",
        )
        return try {
            if (!path.exists()) return null
            JSONObject(path.readText(Charsets.UTF_8))
        } catch (_: RuntimeException) {
            null
        } catch (_: java.io.IOException) {
            null
        }
    }
}
