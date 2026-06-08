package com.zihen.phonetrackerhelper

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder

class KeepAliveService : Service() {
    override fun onCreate() {
        super.onCreate()
        ensureNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = buildNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                KEEP_ALIVE_NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
            )
        } else {
            startForeground(KEEP_ALIVE_NOTIFICATION_ID, notification)
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel(
            KEEP_ALIVE_CHANNEL_ID,
            "日迹 后台保活",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "保持 Helper 后台采集、位置采样和监听服务更稳定"
            setShowBadge(false)
        }
        manager.createNotificationChannel(channel)
    }

    private fun buildNotification(): Notification {
        return Notification.Builder(this, KEEP_ALIVE_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_shield)
            .setContentTitle("日迹正在后台保活")
            .setContentText("用于提高自动采集、位置采样和监听服务稳定性")
            .setOngoing(true)
            .setShowWhen(false)
            .build()
    }

    companion object {
        private const val KEEP_ALIVE_CHANNEL_ID = "phone_tracker_keep_alive"
        private const val KEEP_ALIVE_NOTIFICATION_ID = 4201
    }
}
