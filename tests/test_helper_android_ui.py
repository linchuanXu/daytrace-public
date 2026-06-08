from pathlib import Path


MAIN_ACTIVITY = (
    Path(__file__).resolve().parents[1]
    / "helper-android"
    / "app"
    / "src"
    / "main"
    / "java"
    / "com"
    / "zihen"
    / "phonetrackerhelper"
    / "MainActivity.kt"
)
HELPER_APP = MAIN_ACTIVITY.parents[6]
MANIFEST = HELPER_APP / "src" / "main" / "AndroidManifest.xml"
CONTEXT_EXPORTER = MAIN_ACTIVITY.parent / "DailyContextExporter.kt"
CONTEXT_READER = MAIN_ACTIVITY.parent / "DailyContextReader.kt"
PERMISSION_STATUS = MAIN_ACTIVITY.parent / "PermissionStatus.kt"
USAGE_EXPORTER = MAIN_ACTIVITY.parent / "UsageStatsExporter.kt"
NOTIFICATION_SERVICE = MAIN_ACTIVITY.parent / "NotificationArchiveService.kt"
ACCESSIBILITY_SERVICE = MAIN_ACTIVITY.parent / "AccessibilityArchiveService.kt"
LOCATION_ARCHIVE = MAIN_ACTIVITY.parent / "LocationArchive.kt"
LOCATION_WORKER = MAIN_ACTIVITY.parent / "LocationArchiveWorker.kt"
USAGE_REPOSITORY = MAIN_ACTIVITY.parent / "UsageRepository.kt"
DAILY_WORKER = MAIN_ACTIVITY.parent / "DailyCollectWorker.kt"
KEEP_ALIVE_SERVICE = MAIN_ACTIVITY.parent / "KeepAliveService.kt"
ACCESSIBILITY_CONFIG = HELPER_APP / "src" / "main" / "res" / "xml" / "accessibility_archive_config.xml"
RES_DIR = HELPER_APP / "src" / "main" / "res"


def test_export_controls_live_in_settings_not_bottom_nav():
    source = MAIN_ACTIVITY.read_text(encoding="utf-8")

    bottom_nav = source.split("private fun buildBottomNav()", 1)[1].split(
        "private fun switchToPage", 1
    )[0]
    settings_page = source.split("private fun buildSettingsPage()", 1)[1].split(
        "// ─── View Builders", 1
    )[0]

    assert 'add(0, PAGE_EXPORT, 0, "Export")' not in bottom_nav
    assert "buildExportSection()" in settings_page


def test_helper_apk_uses_chinese_main_interface():
    source = MAIN_ACTIVITY.read_text(encoding="utf-8")
    permission_status = PERMISSION_STATUS.read_text(encoding="utf-8")

    assert 'add(0, PAGE_HOME, 0, "首页")' in source
    assert 'add(0, PAGE_DIAGNOSTICS, 0, "分析")' in source
    assert 'add(0, PAGE_SETTINGS, 0, "设置")' in source
    assert 'pageTitle("分析")' in source
    assert 'pageTitle("设置")' in source
    assert '"权限中心"' in source
    assert '"每日数据状态"' in source
    assert '"媒体明细"' in source
    assert '"位置明细"' in source
    assert '"文件活动"' in source
    assert '"App 变化"' in source
    assert '"通知历史"' in source
    assert '"无障碍事件"' in source
    assert '"模块诊断"' in source
    assert "使用情况访问" in permission_status
    assert "所有文件访问" in permission_status
    assert "后台定位" in permission_status
    assert "通知访问" in permission_status
    assert "无障碍服务" in permission_status


def test_helper_apk_shows_complete_permission_center():
    source = MAIN_ACTIVITY.read_text(encoding="utf-8")
    permission_status = PERMISSION_STATUS.read_text(encoding="utf-8")

    assert "buildPermissionCenterCard()" in source
    assert "PermissionStatusProvider.items(this, exporter)" in source
    assert "使用情况访问" in permission_status
    assert "所有文件访问" in permission_status
    assert "后台定位" in permission_status
    assert "通知访问" in permission_status
    assert "无障碍服务" in permission_status
    assert "电池优化" in permission_status
    assert "READ_SMS" in permission_status
    assert "READ_CALL_LOG" in permission_status
    assert "READ_CALENDAR" in permission_status
    assert "READ_CONTACTS" in permission_status
    assert "ACTION_NOTIFICATION_LISTENER_SETTINGS" in permission_status
    assert "ACTION_ACCESSIBILITY_SETTINGS" in permission_status
    assert "POST_NOTIFICATIONS" in permission_status


def test_helper_apk_uses_foreground_notification_keep_alive():
    manifest = MANIFEST.read_text(encoding="utf-8")
    source = MAIN_ACTIVITY.read_text(encoding="utf-8")
    keep_alive = KEEP_ALIVE_SERVICE.read_text(encoding="utf-8")
    permission_status = PERMISSION_STATUS.read_text(encoding="utf-8")

    assert "android.permission.FOREGROUND_SERVICE" in manifest
    assert "android.permission.FOREGROUND_SERVICE_DATA_SYNC" in manifest
    assert "android.permission.POST_NOTIFICATIONS" in manifest
    assert "KeepAliveService" in manifest
    assert 'android:foregroundServiceType="dataSync"' in manifest
    assert "startKeepAliveService()" in source
    assert "Intent(this, KeepAliveService::class.java)" in source
    assert "ContextCompat.startForegroundService(this, intent)" in source
    assert "Manifest.permission.POST_NOTIFICATIONS" in source
    assert "startForeground(KEEP_ALIVE_NOTIFICATION_ID" in keep_alive
    assert "START_STICKY" in keep_alive
    assert "IMPORTANCE_LOW" in keep_alive
    assert "setOngoing(true)" in keep_alive
    assert "后台保活" in permission_status


def test_permission_center_classifies_collection_mechanisms():
    permission_status = PERMISSION_STATUS.read_text(encoding="utf-8")
    source = MAIN_ACTIVITY.read_text(encoding="utf-8")

    assert "实时归档" in permission_status
    assert "周期采样" in permission_status
    assert "历史回查" in permission_status
    assert "当前快照" in permission_status
    assert "从开启后开始记录" in permission_status
    assert "可回查" in permission_status
    assert "按采样点记录" in permission_status
    assert "导出时刷新当前状态" in permission_status
    assert "采集机制" in source
    assert "实时归档：通知、无障碍必须在发生时开启" in source
    assert "历史回查：使用时长、媒体、通讯等可打开后补全" in source


def test_permission_center_is_compact_and_only_problem_items_open_settings():
    source = MAIN_ACTIVITY.read_text(encoding="utf-8")

    home_page = source.split("private fun buildHomePage()", 1)[1].split(
        "private fun refreshHeroCard", 1
    )[0]
    permission_center = source.split("private fun buildPermissionCenterCard()", 1)[1].split(
        "private fun openPermissionSetting", 1
    )[0]
    compact_row = source.split("private fun compactPermissionRow", 1)[1].split(
        "private fun permissionSetupButton", 1
    )[0]

    assert 'sectionHeader("权限状态")' not in home_page
    assert 'statusRow("使用情况访问"' not in home_page
    assert 'statusRow("存储权限"' not in home_page
    assert "val grantedCount = items.count { it.granted }" in permission_center
    assert "已授权 $grantedCount/${items.size}" in permission_center
    assert "compactPermissionRow(item)" in permission_center
    assert "permissionSetupButton(item)" in permission_center
    assert "val pendingItems = items.filterNot { it.granted }" in permission_center
    assert "setOnClickListener { openPermissionSetting(item) }" not in compact_row


def test_home_page_explains_daytrace_data_persistence_requirements():
    source = MAIN_ACTIVITY.read_text(encoding="utf-8")
    keep_alive = KEEP_ALIVE_SERVICE.read_text(encoding="utf-8")
    strings = (HELPER_APP / "src" / "main" / "res" / "values" / "strings.xml").read_text(
        encoding="utf-8"
    )

    home_page = source.split("private fun buildHomePage()", 1)[1].split(
        "private fun refreshStatus", 1
    )[0]

    assert "<string name=\"app_name\">日迹</string>" in strings
    assert "日迹 后台保活" in keep_alive
    assert 'text = "日迹"' in home_page
    assert 'text = "DayTrace"' in home_page
    assert "R.drawable.ic_daytrace_mark" in home_page
    assert "记录一天留下的数字痕迹" in home_page
    assert "数据会保存在手机本地" in home_page
    assert "打开 App 会采集并准备电脑同步" in home_page
    assert "自动跳过已完整的使用时长" in home_page
    assert "仍会刷新通知/位置等上下文" in home_page
    assert "开启通知和无障碍后，实时事件才会持续归档" in home_page
    assert "电脑只需要运行 main.py" in home_page


def test_home_page_places_today_insights_above_data_persistence():
    source = MAIN_ACTIVITY.read_text(encoding="utf-8")

    home_page = source.split("private fun buildHomePage()", 1)[1].split(
        "private fun refreshStatus", 1
    )[0]

    assert "layout.addView(buildTodayInsightsCard())" in home_page
    assert home_page.index("layout.addView(buildTodayInsightsCard())") < home_page.index(
        "layout.addView(buildDataPersistenceCard())"
    )
    assert "今日一眼看懂" in home_page
    assert "今天使用总时长" in home_page
    assert "解锁次数" in home_page
    assert "最常用 App" in home_page
    assert "记录完整度" in home_page
    assert "日内节奏" in home_page
    assert "今天最常待在哪些 App" not in home_page
    assert "最近 7 天趋势" in home_page
    assert "compactStatTile(" in home_page
    assert "miniUsageBar(" in home_page
    assert "miniTrendBar(" in home_page
    assert "record.packageName" not in home_page


def test_helper_apk_uses_private_vault_launcher_icon():
    manifest = MANIFEST.read_text(encoding="utf-8")
    adaptive_icon = (RES_DIR / "mipmap-anydpi-v26" / "ic_launcher.xml").read_text(
        encoding="utf-8"
    )
    foreground = (RES_DIR / "drawable" / "ic_launcher_foreground.xml").read_text(
        encoding="utf-8"
    )
    background = (RES_DIR / "drawable" / "ic_launcher_background.xml").read_text(
        encoding="utf-8"
    )

    assert 'android:icon="@mipmap/ic_launcher"' in manifest
    assert 'android:roundIcon="@mipmap/ic_launcher_round"' in manifest
    assert "@drawable/ic_launcher_background" in adaptive_icon
    assert "@drawable/ic_launcher_foreground" in adaptive_icon
    assert "#F7F6F3" in background
    assert "#EDEBE7" in background
    assert "#37352F" in foreground
    assert "#787774" in foreground
    assert "M38,30h32c3.3,0 6,2.7 6,6v36c0,3.3 -2.7,6 -6,6H38c-3.3,0 -6,-2.7 -6,-6V36c0,-3.3 2.7,-6 6,-6z" in foreground
    assert "M45,57 L54,49 L63,55 L70,44" in foreground
    assert "M45,52m-4.5,0" in foreground


def test_helper_auto_collection_skips_fully_processed_days():
    main_activity = MAIN_ACTIVITY.read_text(encoding="utf-8")
    usage_exporter = USAGE_EXPORTER.read_text(encoding="utf-8")

    assert "private fun collectDateRange(" in usage_exporter
    assert "private fun isDayFullyProcessed(" in usage_exporter
    assert "private fun hasValidUsageExport(" in usage_exporter
    assert "COMPLETE_SOURCE_STATUSES" in usage_exporter
    assert "if (!force && isDayFullyProcessed(cursor, today))" in usage_exporter
    assert "refreshContextExport(cursor)" in usage_exporter
    assert "private fun refreshContextExport(" in usage_exporter
    assert "skippedDays" in usage_exporter
    assert "fun collectRecentDays(days: Long = 14, force: Boolean = false)" in usage_exporter
    assert "private fun shouldSkipAutoCollection()" in main_activity
    assert "exporter.collectRecentDays(AUTO_FULL_COLLECTION_DAYS, force = force)" in main_activity
    assert "runCollectionWithProgress(force = true)" in main_activity
    assert "跳过 ${result.skippedDays} 天" in main_activity
    assert "skipResumeCollectionOnce" in main_activity


def test_collect_recent_days_exports_desktop_ready_json():
    usage_exporter = USAGE_EXPORTER.read_text(encoding="utf-8")
    daily_worker = DAILY_WORKER.read_text(encoding="utf-8")

    collect_date_range = usage_exporter.split("private fun collectDateRange", 1)[1].split(
        "private fun isDayFullyProcessed", 1
    )[0]
    assert "val status = collectDay(cursor)" in collect_date_range
    assert "appRows += exportDay(cursor, status)" in collect_date_range
    assert "if (!force && isDayFullyProcessed(cursor, today))" in collect_date_range
    assert "refreshContextExport(cursor)" in collect_date_range
    assert 'collectRecentDays(14, force = false)' in daily_worker


def test_helper_usage_exporter_rejects_cross_day_usage_stats_buckets():
    usage_exporter = USAGE_EXPORTER.read_text(encoding="utf-8")

    assert "val validStats = stats" in usage_exporter
    assert "private fun UsageStats.isWithinDayBucket(" in usage_exporter
    assert "firstTimeStamp >= start.toInstant().toEpochMilli()" in usage_exporter
    assert "lastTimeStamp <= end.toInstant().toEpochMilli()" in usage_exporter
    assert "val useCache = eventRecords.isEmpty() && stats.isEmpty() && cachedBefore.isNotEmpty()" in usage_exporter
    assert "apps.isNotEmpty() -> apps" in usage_exporter
    assert "repository.replaceDay(status, recordsToStore)" in usage_exporter


def test_helper_usage_exporter_builds_natural_day_totals_from_events_first():
    usage_exporter = USAGE_EXPORTER.read_text(encoding="utf-8")

    assert "import android.app.usage.UsageEvents" in usage_exporter
    assert "private fun collectEventRecords(" in usage_exporter
    assert "usageStatsManager.queryEvents(startMillis, queryEndMillis)" in usage_exporter
    assert "UsageEvents.Event.MOVE_TO_FOREGROUND" in usage_exporter
    assert "UsageEvents.Event.ACTIVITY_RESUMED" in usage_exporter
    assert "UsageEvents.Event.MOVE_TO_BACKGROUND" in usage_exporter
    assert "UsageEvents.Event.ACTIVITY_PAUSED" in usage_exporter
    assert 'source = "helper_usage_events"' in usage_exporter
    assert "val eventRecords = collectEventRecords(date, start, queryEnd)" in usage_exporter
    assert "val recordsToStore = when {" in usage_exporter
    assert "eventRecords.isNotEmpty() -> eventRecords" in usage_exporter


def test_helper_usage_exporter_caps_today_event_query_at_query_time():
    usage_exporter = USAGE_EXPORTER.read_text(encoding="utf-8")

    assert "val queryEnd = minOf(end.toInstant().toEpochMilli(), queriedAtMillis)" in usage_exporter
    assert "val queryEndText = formatMillis(queryEnd) as String" in usage_exporter
    assert "val eventRecords = collectEventRecords(date, start, queryEnd)" in usage_exporter
    assert "queryEnd = queryEndText" in usage_exporter
    assert "usageStatsManager.queryEvents(startMillis, queryEndMillis)" in usage_exporter
    assert "closeCurrent(queryEndMillis)" in usage_exporter


def test_helper_usage_exporter_preserves_cache_when_collection_unavailable():
    usage_exporter = USAGE_EXPORTER.read_text(encoding="utf-8")

    permission_missing = usage_exporter.split("if (!hasPermission)", 1)[1].split(
        "return try", 1
    )[0]
    failure_handler = usage_exporter.split("} catch (e: RuntimeException)", 1)[1].split(
        "private fun collectEventRecords", 1
    )[0]

    assert "repository.replaceDay(status, cached)" in permission_missing
    assert "repository.replaceDay(status, cached)" in failure_handler


def test_usage_repository_clears_stale_records_when_replacing_day():
    repository = USAGE_REPOSITORY.read_text(encoding="utf-8")
    replace_day = repository.split("fun replaceDay", 1)[1].split(
        "fun recordsFor", 1
    )[0]

    delete_call = 'writableDatabase.delete("usage_records", "date=?", arrayOf(status.date.toString()))'
    insert_call = "records.forEach { writableDatabase.insertWithOnConflict"
    conditional_insert = "if (records.isNotEmpty())"
    assert delete_call in replace_day
    assert insert_call in replace_day
    assert conditional_insert not in replace_day
    assert replace_day.index(delete_call) < replace_day.index(insert_call)


def test_helper_apk_daily_detail_reads_and_renders_context_export():
    source = MAIN_ACTIVITY.read_text(encoding="utf-8")
    reader = CONTEXT_READER.read_text(encoding="utf-8")

    assert "DailyContextReader(this).readFor(status.date)" in source
    assert "addDailyContextCards(layout, dailyContext)" in source
    assert "addDailyStatusChecklist(layout, countedRecords, dailyContext)" in source
    assert "sectionHeader(\"每日数据状态\")" in source
    assert "导出时间" in source
    assert "需要刷新导出" in source
    assert "freshnessWarning(dailyContext)" in source
    assert "Triple(\"位置\", locationCount" in source
    assert "Triple(\"无障碍\", accessibility?.optInt" in source
    assert "sectionHeader(\"Helper 上下文\")" in source
    assert "媒体明细" in source
    assert "位置明细" in source
    assert "文件活动" in source
    assert "App 变化" in source
    assert "通知历史" in source
    assert "无障碍事件" in source
    assert "模块诊断" in source
    assert "daily_context.json" in reader
    assert "JSONObject" in reader


def test_helper_apk_daily_detail_uses_compact_expandable_sections():
    source = MAIN_ACTIVITY.read_text(encoding="utf-8")

    assert "private fun expandableCard(" in source
    assert 'expandableCard("顶部 App"' in source
    assert 'expandableCard(title,' in source
    assert '"展开"' in source
    assert '"收起"' in source
    assert "visibleRecords.take(DEFAULT_COLLAPSED_APP_COUNT)" in source
    assert "private const val DEFAULT_COLLAPSED_APP_COUNT = 5" in source
    assert "private const val DEFAULT_COLLAPSED_DETAIL_COUNT = 3" in source


def test_helper_apk_uses_time_only_display_in_daily_detail():
    source = MAIN_ACTIVITY.read_text(encoding="utf-8")

    assert 'pageTitle("当天详情")' in source
    assert 'val exportedAt = formatUiTime(dailyContext.optString("exported_at"))' in source
    assert 'addView(settingsRow("导出时间", exportedAt))' in source
    assert 'formatUiTime(it.optString("time"))' in source
    assert 'formatDetailTime(it, listOf("last_update_time", "first_install_time"))' in source
    assert "private fun formatUiTime(value: String?): String {" in source
    assert "private fun formatDetailTime(item: JSONObject, timeKeys: List<String>): String {" in source
    assert 'DateTimeFormatter.ofPattern("HH:mm")' in source


def test_helper_apk_sorts_timed_detail_sections_newest_first():
    source = MAIN_ACTIVITY.read_text(encoding="utf-8")

    assert "private fun sortJsonArrayByTimeDesc(" in source
    assert "val sortedArray = sortJsonArrayByTimeDesc(array, timeKeys)" in source
    assert "sortedArray.optJSONObject(i)" in source
    assert 'timeKeys: List<String> = listOf("time")' in source
    assert 'timeKeys = listOf("last_update_time", "first_install_time")' in source


def test_helper_apk_exports_daily_context_alongside_usage_stats():
    manifest = MANIFEST.read_text(encoding="utf-8")
    usage_exporter = USAGE_EXPORTER.read_text(encoding="utf-8")
    context_exporter = CONTEXT_EXPORTER.read_text(encoding="utf-8")

    assert 'android.permission.ACCESS_FINE_LOCATION' in manifest
    assert 'android.permission.READ_MEDIA_IMAGES' in manifest
    assert 'android.permission.READ_MEDIA_VIDEO' in manifest
    assert 'android.permission.READ_CONTACTS' in manifest
    assert 'android.permission.READ_SMS' in manifest
    assert 'android.permission.READ_CALL_LOG' in manifest
    assert 'android.permission.READ_CALENDAR' in manifest
    assert "contextExporter.exportDay(date)" in usage_exporter
    assert '"daily_context.json"' in context_exporter
    assert "MediaStore.Images.Media.EXTERNAL_CONTENT_URI" in context_exporter
    assert "MediaStore.Audio.Media.EXTERNAL_CONTENT_URI" in context_exporter
    assert "LocationManager" in context_exporter
    assert "BatteryManager" in context_exporter
    assert "collectFileActivity(date, diagnostics)" in context_exporter
    assert "collectAppChanges(date, diagnostics)" in context_exporter
    assert "collectSmsBackup(date, diagnostics)" in context_exporter
    assert "collectCallBackup(date, diagnostics)" in context_exporter
    assert "collectCalendarBackup(date, diagnostics)" in context_exporter
    assert "collectContactsBackup(date, diagnostics)" in context_exporter


def test_helper_apk_archives_notification_history_when_listener_enabled():
    manifest = MANIFEST.read_text(encoding="utf-8")
    context_exporter = CONTEXT_EXPORTER.read_text(encoding="utf-8")
    notification_service = NOTIFICATION_SERVICE.read_text(encoding="utf-8")

    assert "NotificationArchiveService" in manifest
    assert "android.permission.BIND_NOTIFICATION_LISTENER_SERVICE" in manifest
    assert "android.service.notification.NotificationListenerService" in manifest
    assert "collectNotificationHistory(date, diagnostics)" in context_exporter
    assert "notification_events.jsonl" in notification_service
    assert "onNotificationPosted" in notification_service
    assert "onNotificationRemoved" in notification_service
    assert "onListenerConnected" in notification_service
    assert "activeNotifications.orEmpty()" in notification_service
    assert 'archive("active", sbn)' in notification_service


def test_readme_documents_collection_completeness_boundaries():
    readme = (Path(__file__).resolve().parents[1] / "Readme.md").read_text(encoding="utf-8")

    assert "实时归档" in readme
    assert "周期采样" in readme
    assert "历史回查" in readme
    assert "当前快照" in readme
    assert "通知监听连接时会补抓当前仍存在的通知" in readme
    assert "已经消失且监听当时未开启的通知无法回补" in readme
    assert "打开 Helper 后会刷新最近 3 天 daily_context.json" in readme


def test_helper_apk_archives_periodic_location_snapshots():
    manifest = MANIFEST.read_text(encoding="utf-8")
    main_activity = MAIN_ACTIVITY.read_text(encoding="utf-8")
    daily_worker = DAILY_WORKER.read_text(encoding="utf-8")
    location_archive = LOCATION_ARCHIVE.read_text(encoding="utf-8")
    location_worker = LOCATION_WORKER.read_text(encoding="utf-8")
    context_exporter = CONTEXT_EXPORTER.read_text(encoding="utf-8")

    assert "android.permission.ACCESS_BACKGROUND_LOCATION" in manifest
    assert "scheduleLocationArchiveWork()" in main_activity
    assert "PeriodicWorkRequestBuilder<LocationArchiveWorker>(15, TimeUnit.MINUTES)" in main_activity
    assert "LocationArchive.recordBestEffort(this, \"app_launch\")" in main_activity
    assert "LocationArchive.recordBestEffort(applicationContext, \"daily_collect_worker\")" in daily_worker
    assert "LocationArchive.recordBestEffort(applicationContext, \"periodic_location_worker\")" in location_worker
    assert "location_events.jsonl" in location_archive
    assert "archived_location_snapshots" in context_exporter


def test_helper_apk_archives_accessibility_events_when_enabled():
    manifest = MANIFEST.read_text(encoding="utf-8")
    context_exporter = CONTEXT_EXPORTER.read_text(encoding="utf-8")
    accessibility_service = ACCESSIBILITY_SERVICE.read_text(encoding="utf-8")
    accessibility_config = ACCESSIBILITY_CONFIG.read_text(encoding="utf-8")

    assert "AccessibilityArchiveService" in manifest
    assert "android.permission.BIND_ACCESSIBILITY_SERVICE" in manifest
    assert "android.accessibilityservice.AccessibilityService" in manifest
    assert "@xml/accessibility_archive_config" in manifest
    assert "accessibility_events.jsonl" in accessibility_service
    assert "onAccessibilityEvent" in accessibility_service
    assert '.put("time_millis", System.currentTimeMillis())' in accessibility_service
    assert "typeWindowStateChanged" in accessibility_config
    assert "collectAccessibilityEvents(date, diagnostics)" in context_exporter
    assert "accessibility_events" in context_exporter
