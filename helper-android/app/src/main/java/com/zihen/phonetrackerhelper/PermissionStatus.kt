package com.zihen.phonetrackerhelper

import android.Manifest
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.os.PowerManager
import android.provider.Settings
import android.text.TextUtils

data class PermissionStatusItem(
    val group: String,
    val title: String,
    val detail: String,
    val granted: Boolean,
    val settingsAction: String,
    val dataUri: Uri? = null,
)

object PermissionStatusProvider {
    fun items(context: Context, exporter: UsageStatsExporter): List<PermissionStatusItem> {
        return listOf(
            PermissionStatusItem(
                "历史回查",
                "使用情况访问",
                "可回查 Android App 使用聚合",
                exporter.hasUsageAccess(),
                Settings.ACTION_USAGE_ACCESS_SETTINGS,
            ),
            PermissionStatusItem(
                "历史回查",
                "所有文件访问",
                "可回查公共目录文件变化并写入导出文件",
                exporter.hasExportStorageAccess(),
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                    Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION
                } else {
                    Settings.ACTION_APPLICATION_DETAILS_SETTINGS
                },
                Uri.parse("package:${context.packageName}"),
            ),
            runtimeItem(context, "历史回查", "图片", "可回查照片媒体库", Manifest.permission.READ_MEDIA_IMAGES),
            runtimeItem(context, "历史回查", "视频", "可回查视频媒体库", Manifest.permission.READ_MEDIA_VIDEO),
            runtimeItem(context, "历史回查", "音频/录音", "可回查音频媒体库", Manifest.permission.READ_MEDIA_AUDIO),
            runtimeItem(context, "周期采样", "精确定位", "按采样点记录位置，不能还原完整轨迹", Manifest.permission.ACCESS_FINE_LOCATION),
            runtimeItem(context, "周期采样", "粗略定位", "按采样点记录位置，不能还原完整轨迹", Manifest.permission.ACCESS_COARSE_LOCATION),
            runtimeItem(context, "周期采样", "后台定位", "按采样点记录位置，提升后台采样稳定性", Manifest.permission.ACCESS_BACKGROUND_LOCATION),
            runtimeItem(context, "历史回查", "短信", "可回查系统保留的短信记录", Manifest.permission.READ_SMS),
            runtimeItem(context, "历史回查", "通话记录", "可回查系统保留的通话记录", Manifest.permission.READ_CALL_LOG),
            runtimeItem(context, "历史回查", "日历", "可回查系统保留的日历记录", Manifest.permission.READ_CALENDAR),
            runtimeItem(context, "历史回查", "联系人", "可回查联系人更新时间", Manifest.permission.READ_CONTACTS),
            runtimeItem(context, "后台稳定性", "常驻通知", "POST_NOTIFICATIONS；通知栏常驻，用于后台保活", Manifest.permission.POST_NOTIFICATIONS),
            PermissionStatusItem(
                "实时归档",
                "通知访问",
                "从开启后开始记录通知出现/移除事件",
                enabledServices(context, "enabled_notification_listeners")
                    .contains(context.packageName),
                Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS,
            ),
            PermissionStatusItem(
                "实时归档",
                "无障碍服务",
                "从开启后开始记录窗口切换和交互事件",
                enabledServices(context, "enabled_accessibility_services")
                    .contains("${context.packageName}/${context.packageName}.AccessibilityArchiveService"),
                Settings.ACTION_ACCESSIBILITY_SETTINGS,
            ),
            PermissionStatusItem(
                "当前快照",
                "电池优化",
                "导出时刷新当前状态；忽略优化可提高后台可靠性",
                isIgnoringBatteryOptimizations(context),
                Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS,
            ),
        )
    }

    private fun runtimeItem(
        context: Context,
        group: String,
        title: String,
        detail: String,
        permission: String,
    ): PermissionStatusItem {
        val supported = when (permission) {
            Manifest.permission.READ_MEDIA_IMAGES,
            Manifest.permission.READ_MEDIA_VIDEO,
            Manifest.permission.READ_MEDIA_AUDIO,
            -> Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
            Manifest.permission.POST_NOTIFICATIONS -> Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
            Manifest.permission.ACCESS_BACKGROUND_LOCATION -> Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q
            else -> true
        }
        val granted = !supported || context.checkSelfPermission(permission) == android.content.pm.PackageManager.PERMISSION_GRANTED
        return PermissionStatusItem(
            group,
            title,
            detail,
            granted,
            Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
            Uri.parse("package:${context.packageName}"),
        )
    }

    private fun enabledServices(context: Context, key: String): String {
        return Settings.Secure.getString(context.contentResolver, key).orEmpty()
    }

    private fun isIgnoringBatteryOptimizations(context: Context): Boolean {
        val powerManager = context.getSystemService(Context.POWER_SERVICE) as PowerManager
        return powerManager.isIgnoringBatteryOptimizations(context.packageName)
    }
}
