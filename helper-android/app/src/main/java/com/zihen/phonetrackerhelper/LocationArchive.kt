package com.zihen.phonetrackerhelper

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import org.json.JSONObject
import java.io.File

object LocationArchive {
    fun recordBestEffort(context: Context, reason: String): Boolean {
        if (
            context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED &&
            context.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED
        ) {
            return false
        }
        return try {
            val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
            val best = manager.getProviders(true)
                .mapNotNull { provider -> runCatching { manager.getLastKnownLocation(provider) }.getOrNull() }
                .maxByOrNull { it.time }
                ?: return false
            File(context.filesDir, "location_events.jsonl").appendText(best.toJson(reason).toString() + "\n", Charsets.UTF_8)
            true
        } catch (_: RuntimeException) {
            false
        }
    }

    private fun Location.toJson(reason: String): JSONObject {
        val body = JSONObject()
            .put("time_millis", time)
            .put("recorded_at_millis", System.currentTimeMillis())
            .put("reason", reason)
            .put("provider", provider)
            .put("latitude", latitude)
            .put("longitude", longitude)
            .put("accuracy_m", if (hasAccuracy()) accuracy.toDouble() else JSONObject.NULL)
        if (hasAltitude()) body.put("altitude_m", altitude)
        if (hasSpeed()) body.put("speed_mps", speed.toDouble())
        return body
    }
}
