package com.zihen.phonetrackerhelper

import android.animation.ObjectAnimator
import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.provider.Settings
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.animation.LinearInterpolator
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import android.Manifest
import android.content.pm.PackageManager
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.SwitchCompat
import androidx.core.content.ContextCompat
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.android.material.button.MaterialButton
import com.google.android.material.card.MaterialCardView
import com.google.android.material.chip.Chip
import com.google.android.material.datepicker.MaterialDatePicker
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException
import java.util.concurrent.TimeUnit

class MainActivity : AppCompatActivity() {
    private lateinit var exporter: UsageStatsExporter
    private lateinit var homePage: View
    private lateinit var diagnosticsPage: View
    private lateinit var settingsPage: View
    private lateinit var contentFrame: FrameLayout
    private var diagnosticsDetailPage: View? = null

    // Home
    private lateinit var progressText: TextView
    private lateinit var heroCard: MaterialCardView
    private lateinit var collectionTitle: TextView
    private lateinit var collectionSubtitle: TextView
    private lateinit var collectionProgress: ProgressBar
    private var collectionTitleText = "准备采集"
    private var collectionSubtitleText = "打开 App 会自动检查最近 14 天，已完整的使用时长会跳过"
    private var collectionProgressValue = 0
    private var collectionRunning = false
    private var collectionAttention = false
    private var collectionAnimator: ObjectAnimator? = null
    private var skipResumeCollectionOnce = false

    // Export
    private var exportStartDate = LocalDate.now().minusDays(29)
    private var exportEndDate = LocalDate.now()
    private lateinit var dateRangeLabel: TextView
    private lateinit var exportProgressText: TextView

    // Settings
    private lateinit var autoCollectSwitch: SwitchCompat
    private lateinit var settingsProgressText: TextView

    private val prefs by lazy { getSharedPreferences("helper_settings", MODE_PRIVATE) }
    private val dateFmt = DateTimeFormatter.ofPattern("yyyy-MM-dd")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        exporter = UsageStatsExporter(this)
        applySystemBarStyle()

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            fitsSystemWindows = true
            setBackgroundColor(getColorInt(COLOR_BACKGROUND))
        }

        contentFrame = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f
            )
        }

        homePage = buildHomePage()
        diagnosticsPage = buildDiagnosticsPage()
        settingsPage = buildSettingsPage()

        contentFrame.addView(homePage)
        contentFrame.addView(diagnosticsPage)
        contentFrame.addView(settingsPage)

        val bottomNav = buildBottomNav()
        root.addView(contentFrame)
        root.addView(bottomNav)
        setContentView(root)

        switchToPage(PAGE_HOME)
        requestContextRuntimePermissions()
        startKeepAliveService()
        LocationArchive.recordBestEffort(this, "app_launch")
        scheduleLocationArchiveWork()
        skipResumeCollectionOnce = true
        runAutoCollection()
        handleIntentCommand(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntentCommand(intent)
    }

    override fun onResume() {
        super.onResume()
        if (skipResumeCollectionOnce) {
            skipResumeCollectionOnce = false
            refreshStatus()
            return
        }
        runAutoCollection()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (diagnosticsDetailPage != null) {
            closeDiagnosticsDetail()
        } else {
            super.onBackPressed()
        }
    }

    // ─── Navigation ───────────────────────────────────────────────

    private fun buildBottomNav(): BottomNavigationView {
        return BottomNavigationView(this).apply {
            backgroundTintList = ColorStateList.valueOf(getColorInt(COLOR_CARD_BG))
            itemIconTintList = navIconTint()
            itemTextColor = navIconTint()
            elevation = 0f
            menu.apply {
                add(0, PAGE_HOME, 0, "首页").setIcon(R.drawable.ic_home)
                add(0, PAGE_DIAGNOSTICS, 0, "分析").setIcon(R.drawable.ic_diagnostics)
                add(0, PAGE_SETTINGS, 0, "设置").setIcon(R.drawable.ic_settings)
            }
            setOnItemSelectedListener { item ->
                switchToPage(item.itemId)
                true
            }
        }
    }

    private fun switchToPage(pageId: Int) {
        closeDiagnosticsDetail()
        homePage.visibility = if (pageId == PAGE_HOME) View.VISIBLE else View.GONE
        diagnosticsPage.visibility = if (pageId == PAGE_DIAGNOSTICS) View.VISIBLE else View.GONE
        settingsPage.visibility = if (pageId == PAGE_SETTINGS) View.VISIBLE else View.GONE
    }

    // ─── Home Page ────────────────────────────────────────────────

    private fun buildHomePage(): View {
        val scroll = pageScroll()
        val layout = pageLayout()

        heroCard = card {}
        refreshHeroCard()
        layout.addView(heroCard)

        layout.addView(buildTodayInsightsCard())
        layout.addView(buildDataPersistenceCard())
        layout.addView(buildPermissionCenterCard())

        layout.addView(card {
            addView(sectionHeader("快捷操作"))
            addView(iconButton("采集最近 14 天", R.drawable.ic_cloud_download) {
                runCollectionWithProgress(force = true)
            })
            addView(secondaryIconButton("导出全部缓存（395 天）", R.drawable.ic_share) {
                runExport { exporter.exportRecentDays(395) }
            })
        })

        progressText = body("就绪")
        progressText.setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
        progressText.textSize = 13f
        progressText.setPadding(dp(8), dp(8), dp(8), dp(16))
        layout.addView(progressText)

        scroll.addView(layout)
        return scroll
    }

    private fun buildTodayInsightsCard(): MaterialCardView {
        val today = LocalDate.now()
        val todayRecords = exporter.recordsFor(today)
            .filter { it.totalForegroundSeconds >= MIN_COUNTED_APP_SECONDS }
        val visibleRecords = todayRecords
            .filter { it.totalForegroundSeconds >= MIN_VISIBLE_APP_SECONDS }
        val totalForegroundSeconds = todayRecords.sumOf { it.totalForegroundSeconds }
        val topApp = visibleRecords.firstOrNull()
        val permissionItems = PermissionStatusProvider.items(this, exporter)
        val grantedCount = permissionItems.count { it.granted }
        val recentStatuses = exporter.recentDiagnostics(7).sortedBy { it.date }
        val recentTotals = recentStatuses.associate { status ->
            status.date to exporter.recordsFor(status.date)
                .filter { it.totalForegroundSeconds >= MIN_COUNTED_APP_SECONDS }
                .sumOf { it.totalForegroundSeconds }
        }
        val maxTrendSeconds = maxOf(recentTotals.values.maxOrNull() ?: 0L, 1L)

        return compactCard {
            addView(compactSectionTitle("今日一眼看懂"))
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                addView(compactStatTile("今天使用总时长", formatDuration(totalForegroundSeconds), true))
                addView(compactStatTile("解锁次数", "电脑同步后", false))
            })
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                setPadding(0, dp(8), 0, 0)
                addView(compactStatTile("最常用 App", topApp?.appName ?: "暂无", true))
                addView(compactStatTile("记录完整度", "$grantedCount/${permissionItems.size}", false))
            })

            addView(compactDivider())
            addView(compactSectionTitle("日内节奏"))
            addView(TextView(this@MainActivity).apply {
                text = dayRhythmSummary(visibleRecords)
                textSize = 12f
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
                setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                setPadding(0, 0, 0, dp(4))
            })
            if (visibleRecords.isEmpty()) {
                addView(compactEmptyText("今天还没有达到 5 分钟的记录"))
            } else {
                visibleRecords.take(3).forEach { record ->
                    addView(miniUsageBar(record, totalForegroundSeconds))
                }
            }

            addView(compactDivider())
            addView(compactSectionTitle("最近 7 天趋势"))
            if (recentStatuses.isEmpty()) {
                addView(compactEmptyText("采集后显示每日总时长"))
            } else {
                addView(LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                    gravity = Gravity.BOTTOM
                    setPadding(0, dp(2), 0, 0)
                    recentStatuses.forEach { status ->
                        addView(miniTrendBar(
                            status.date.format(DateTimeFormatter.ofPattern("MM-dd")),
                            recentTotals[status.date] ?: 0L,
                            maxTrendSeconds,
                        ))
                    }
                })
            }
        }
    }

    private fun dayRhythmSummary(records: List<UsageAppRecord>): String {
        val firstSeen = records.asSequence()
            .mapNotNull { parseUiDateTimeMillis(it.firstTimeStamp) }
            .minOrNull()
        val lastSeen = records.asSequence()
            .mapNotNull { parseUiDateTimeMillis(it.lastTimeStamp ?: it.lastUsed) }
            .maxOrNull()
        val timeRange = if (firstSeen != null && lastSeen != null) {
            val formatter = DateTimeFormatter.ofPattern("HH:mm")
            val start = Instant.ofEpochMilli(firstSeen).atZone(ZoneId.systemDefault()).format(formatter)
            val end = Instant.ofEpochMilli(lastSeen).atZone(ZoneId.systemDefault()).format(formatter)
            "$start - $end"
        } else {
            "时间范围待补全"
        }
        val appNames = records.take(3).joinToString("、") { it.appName }
        return if (appNames.isBlank()) {
            "今天的日内节奏会在采集到 App 使用后显示。"
        } else {
            "$timeRange · 主要停留在 $appNames"
        }
    }

    private fun miniUsageBar(record: UsageAppRecord, maxSeconds: Long): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(4), 0, dp(4))
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                addView(TextView(this@MainActivity).apply {
                    text = record.appName
                    textSize = 12f
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
                    maxLines = 1
                    ellipsize = TextUtils.TruncateAt.END
                    layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                })
                addView(TextView(this@MainActivity).apply {
                    text = formatDuration(record.totalForegroundSeconds)
                    textSize = 11f
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                    setPadding(dp(8), 0, 0, 0)
                })
            })
            addView(ProgressBar(this@MainActivity, null, android.R.attr.progressBarStyleHorizontal).apply {
                max = 100
                progress = percentOf(record.totalForegroundSeconds, maxSeconds)
                progressTintList = ColorStateList.valueOf(getColorInt(COLOR_ACCENT))
                progressBackgroundTintList = ColorStateList.valueOf(getColorInt(COLOR_SEPARATOR))
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    dp(3),
                ).apply {
                    topMargin = dp(3)
                }
            })
        }
    }

    private fun miniTrendBar(label: String, seconds: Long, maxSeconds: Long): LinearLayout {
        val barHeight = dp((percentOf(seconds, maxSeconds) * 34 / 100).coerceAtLeast(4))
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                marginEnd = dp(4)
            }
            addView(FrameLayout(this@MainActivity).apply {
                background = roundedBackground(COLOR_SOFT_BG, dpToPxF(6), COLOR_SEPARATOR)
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    dp(40),
                )
                addView(View(this@MainActivity).apply {
                    background = roundedBackground(COLOR_ACCENT, dpToPxF(5))
                    layoutParams = FrameLayout.LayoutParams(
                        ViewGroup.LayoutParams.MATCH_PARENT,
                        barHeight,
                        Gravity.BOTTOM,
                    )
                })
            })
            addView(TextView(this@MainActivity).apply {
                text = label.removePrefix("0")
                textSize = 9f
                gravity = Gravity.CENTER
                maxLines = 1
                setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                setPadding(0, dp(3), 0, 0)
            })
        }
    }

    private fun compactStatTile(label: String, value: String, addEndMargin: Boolean): MaterialCardView {
        val inner = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(10), dp(8), dp(10), dp(8))
            addView(TextView(this@MainActivity).apply {
                text = value
                textSize = 16f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
            })
            addView(TextView(this@MainActivity).apply {
                text = label
                textSize = 10f
                setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
                setPadding(0, dp(2), 0, 0)
            })
        }
        return MaterialCardView(this).apply {
            radius = dpToPxF(10)
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = getColorInt(COLOR_SEPARATOR)
            setCardBackgroundColor(ColorStateList.valueOf(getColorInt(COLOR_SOFT_BG)))
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                if (addEndMargin) marginEnd = dp(8)
            }
            addView(inner)
        }
    }

    private fun compactCard(block: LinearLayout.() -> Unit): MaterialCardView {
        val inner = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = dp(14)
            setPadding(pad, pad, pad, pad)
            block()
        }
        return MaterialCardView(this).apply {
            radius = dpToPxF(14)
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = getColorInt(COLOR_SEPARATOR)
            setCardBackgroundColor(ColorStateList.valueOf(getColorInt(COLOR_CARD_BG)))
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply {
                bottomMargin = dp(12)
            }
            addView(inner)
        }
    }

    private fun compactSectionTitle(text: String): TextView = TextView(this).apply {
        this.text = text
        textSize = 13f
        typeface = Typeface.DEFAULT_BOLD
        setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
        setPadding(0, dp(2), 0, dp(8))
    }

    private fun compactEmptyText(text: String): TextView = TextView(this).apply {
        this.text = text
        textSize = 12f
        setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
        setPadding(0, dp(2), 0, dp(2))
    }

    private fun compactDivider(): View = View(this).apply {
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            dp(1),
        ).apply {
            topMargin = dp(10)
            bottomMargin = dp(8)
        }
        setBackgroundColor(getColorInt(COLOR_SEPARATOR))
    }

    private fun percentOf(value: Long, max: Long): Int {
        if (value <= 0L || max <= 0L) return 0
        return ((value * 100L) / max).coerceIn(4L, 100L).toInt()
    }

    private fun buildDataPersistenceCard(): MaterialCardView {
        return card {
            addView(sectionHeader("数据怎么保存"))
            addView(body("数据会保存在手机本地，用来生成每天的使用记录和电脑端日报。").apply {
                setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
                typeface = Typeface.DEFAULT_BOLD
            })
            addView(statusRow(
                "打开 App 会采集并准备电脑同步",
                "自动跳过已完整的使用时长，仍会刷新通知/位置等上下文；只重查今天和缺失/过期的天。",
                pill("自动采集"),
            ))
            addView(statusRow(
                "开启通知和无障碍后，实时事件才会持续归档",
                "这些事件不能完整回补，越早开启权限，后续日报越完整。",
                pill("实时记录"),
            ))
            addView(statusRow(
                "电脑只需要运行 main.py",
                "电脑端会读取 /sdcard/PhoneTracker/export，把手机本地记录合并进 summary.json 和日报。",
                pill("同步就绪"),
            ))
        }
    }

    private fun refreshHeroCard() {
        val summary = exporter.cacheSummary()
        heroCard.removeAllViews()

        val inner = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = dp(22)
            setPadding(pad, pad, pad, pad)
        }

        val titleRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        titleRow.addView(android.widget.ImageView(this).apply {
            setImageResource(R.drawable.ic_daytrace_mark)
            layoutParams = LinearLayout.LayoutParams(dp(44), dp(44)).apply {
                marginEnd = dp(12)
            }
        })
        titleRow.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(TextView(this@MainActivity).apply {
                text = "日迹"
                textSize = 28f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
            })
            addView(TextView(this@MainActivity).apply {
                text = "DayTrace"
                textSize = 16f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(getColorInt(COLOR_ACCENT))
                setPadding(0, dp(2), 0, 0)
            })
        })
        inner.addView(titleRow)
        inner.addView(TextView(this).apply {
            text = "记录一天留下的数字痕迹"
            textSize = 14f
            setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
            setPadding(0, dp(5), 0, dp(14))
        })

        inner.addView(collectionStatusPanel())
        inner.addView(pill("最近采集  ${formatLastCollected(summary.lastQueriedAt)}").apply {
            setPadding(dp(12), dp(7), dp(12), dp(7))
        })

        val statsRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(16), 0, 0)
        }
        statsRow.addView(statTile("缓存天数", summary.cachedDays.toString(), true))
        statsRow.addView(statTile("App 记录", formatNumber(summary.cachedAppRows), false))
        inner.addView(statsRow)
        heroCard.addView(inner)
    }

    private fun refreshStatus() {
        if (collectionRunning) {
            renderCollectionStatus()
        } else {
            refreshHeroCard()
        }

    }

    // ─── Export Section ───────────────────────────────────────────

    private fun buildExportSection(): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL

            // Date range card with picker
            addView(card {
                addView(sectionHeader("日期范围"))
                dateRangeLabel = body("${exportStartDate.format(dateFmt)}  –  ${exportEndDate.format(dateFmt)}")
                dateRangeLabel.setTextColor(getColorInt(COLOR_ACCENT))
                dateRangeLabel.typeface = Typeface.DEFAULT_BOLD
                addView(dateRangeLabel)
                addView(body("点按修改").apply {
                    textSize = 12f
                    setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                })
            }.apply {
                setOnClickListener { showDatePicker() }
            })

            // Quick select chips
            addView(card {
                addView(sectionHeader("快速选择"))
                val chipRow = LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.HORIZONTAL
                }
                chipRow.addView(chip("最近 7 天") { setDateRange(7) })
                chipRow.addView(chip("最近 30 天") { setDateRange(30) })
                chipRow.addView(chip("最近 90 天") { setDateRange(90) })
                addView(chipRow)
            })

            addView(iconButton("导出所选日期", R.drawable.ic_share) {
                if (!exporter.hasUsageAccess()) {
                    exportProgressText.text = "请先授予使用情况访问权限"
                    return@iconButton
                }
                if (!exporter.hasExportStorageAccess()) {
                    exportProgressText.text = "请先授予存储权限"
                    return@iconButton
                }
                runExport { exporter.exportRange(exportStartDate, exportEndDate) }
            })

            addView(card {
                addView(body("电脑同步命令："))
                addView(body("adb pull /sdcard/PhoneTracker/export data/_helper_exports").apply {
                    background = roundedBackground(COLOR_SOFT_BG, dpToPxF(10))
                    setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
                    typeface = Typeface.MONOSPACE
                    textSize = 12f
                    setPadding(dp(12), dp(10), dp(12), dp(10))
                })
            })

            exportProgressText = body("准备导出")
            exportProgressText.setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
            addView(card {
                addView(exportProgressText)
            })
        }
    }

    private fun showDatePicker() {
        val picker = MaterialDatePicker.Builder.dateRangePicker()
            .setTitleText("选择日期范围")
            .setSelection(
                androidx.core.util.Pair(
                    exportStartDate.atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli(),
                    exportEndDate.atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli(),
                )
            )
            .build()

        picker.addOnPositiveButtonClickListener { selection ->
            exportStartDate = Instant.ofEpochMilli(selection.first)
                .atZone(ZoneId.systemDefault()).toLocalDate()
            exportEndDate = Instant.ofEpochMilli(selection.second)
                .atZone(ZoneId.systemDefault()).toLocalDate()
            dateRangeLabel.text = "${exportStartDate.format(dateFmt)}  –  ${exportEndDate.format(dateFmt)}"
        }

        picker.show(supportFragmentManager, "date_range_picker")
    }

    private fun setDateRange(days: Int) {
        exportEndDate = LocalDate.now()
        exportStartDate = exportEndDate.minusDays(days.toLong() - 1)
        dateRangeLabel.text = "${exportStartDate.format(dateFmt)}  –  ${exportEndDate.format(dateFmt)}"
    }

    // ─── Diagnostics Page ─────────────────────────────────────────

    private fun buildDiagnosticsPage(): View {
        val scroll = pageScroll()
        val layout = pageLayout()

        layout.addView(pageTitle("分析"))

        val statuses = exporter.recentDiagnostics(60)
        val okCount = statuses.count { it.errorMessage == null && it.exportedAppCount > 0 }
        val errCount = statuses.count { it.errorMessage != null }
        val emptyCount = statuses.size - okCount - errCount

        layout.addView(card {
            addView(sectionHeader("最近 ${statuses.size} 天"))
            val statsRow = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.HORIZONTAL
            }
            statsRow.addView(miniStat("正常", okCount, COLOR_GREEN))
            statsRow.addView(miniStat("错误", errCount, COLOR_RED))
            statsRow.addView(miniStat("空", emptyCount, COLOR_TEXT_SECONDARY))
            addView(statsRow)
        })

        // Timeline list
        statuses.forEach { status ->
            val dotColor = when {
                status.errorMessage != null -> COLOR_RED
                status.exportedAppCount > 0 -> COLOR_GREEN
                else -> COLOR_TEXT_SECONDARY
            }
            layout.addView(card {
                addView(timelineRow(
                    date = status.date.toString(),
                    dotColor = dotColor,
                    source = status.sourceStatus,
                    raw = status.rawAppCount,
                    exported = status.exportedAppCount,
                    error = status.errorMessage,
                ))
            }.apply {
                isClickable = true
                isFocusable = true
                setOnClickListener { showDiagnosticsDetail(status) }
            })
        }

        scroll.addView(layout)
        return scroll
    }

    private fun miniStat(label: String, value: Int, color: String): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            addView(TextView(this@MainActivity).apply {
                text = value.toString()
                textSize = 22f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(getColorInt(color))
                gravity = Gravity.CENTER
            })
            addView(TextView(this@MainActivity).apply {
                text = label
                textSize = 11f
                setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                gravity = Gravity.CENTER
            })
        }
    }

    private fun timelineRow(date: String, dotColor: String, source: String, raw: Int, exported: Int, error: String?): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL

            // Color dot
            addView(View(this@MainActivity).apply {
                val size = dp(12)
                layoutParams = LinearLayout.LayoutParams(size, size).apply {
                    marginEnd = dp(12)
                }
                background = GradientDrawable().apply {
                    shape = GradientDrawable.OVAL
                    setColor(getColorInt(dotColor))
                }
            })

            // Content
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)

                addView(TextView(this@MainActivity).apply {
                    text = date
                    textSize = 15f
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
                })
                addView(TextView(this@MainActivity).apply {
                    text = "$source  •  原始: $raw  •  导出: $exported"
                    textSize = 13f
                    setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                })
                if (error != null) {
                    addView(TextView(this@MainActivity).apply {
                        text = error
                        textSize = 12f
                        setTextColor(getColorInt(COLOR_RED))
                    })
                }
            })
        }
    }

    private fun showDiagnosticsDetail(status: DayStatus) {
        closeDiagnosticsDetail()
        homePage.visibility = View.GONE
        diagnosticsPage.visibility = View.GONE
        settingsPage.visibility = View.GONE

        diagnosticsDetailPage = buildDiagnosticsDetailPage(status).also {
            contentFrame.addView(it)
        }
    }

    private fun closeDiagnosticsDetail() {
        diagnosticsDetailPage?.let { contentFrame.removeView(it) }
        diagnosticsDetailPage = null
        diagnosticsPage.visibility = View.VISIBLE
    }

    private fun buildDiagnosticsDetailPage(status: DayStatus): View {
        val countedRecords = exporter.recordsFor(status.date)
            .filter { it.totalForegroundSeconds >= MIN_COUNTED_APP_SECONDS }
        val visibleRecords = countedRecords
            .filter { it.totalForegroundSeconds >= MIN_VISIBLE_APP_SECONDS }
        val totalForegroundSeconds = countedRecords.sumOf { it.totalForegroundSeconds }
        val dailyContext = DailyContextReader(this).readFor(status.date)
        val scroll = pageScroll()
        val layout = pageLayout()

        val detailSummary = if (countedRecords.isEmpty()) {
            "没有计入的 App 记录"
        } else {
            "前台 ${formatDuration(totalForegroundSeconds)} · 已计入 ${countedRecords.size} 个 App"
        }

        layout.addView(backRow("分析") { closeDiagnosticsDetail() })
        layout.addView(pageTitle("当天详情").apply {
            setPadding(dp(2), dp(8), dp(2), dp(4))
        })
        layout.addView(body(detailSummary).apply {
            textSize = 13f
            setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
            setPadding(dp(2), 0, dp(2), dp(14))
        })
        addDailyStatusChecklist(layout, countedRecords, dailyContext)

        layout.addView(card {
            addView(sectionHeader("概览"))
            addView(settingsRow("前台总时长", formatDuration(totalForegroundSeconds)))
            addView(separator())
            addView(settingsRow("App 数量", countedRecords.size.toString()))
            addView(separator())
            addView(settingsRow("来源状态", status.sourceStatus))
            addView(body("少于 1 分钟的 App 不计入；顶部 App 列表隐藏少于 5 分钟的记录。").apply {
                textSize = 12f
                setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                setPadding(0, dp(12), 0, 0)
            })
        })

        val topAppCanExpand = visibleRecords.size > DEFAULT_COLLAPSED_APP_COUNT
        val topAppSummary = when {
            visibleRecords.isEmpty() -> "这一天没有达到 5 分钟的 App。"
            topAppCanExpand -> "共 ${visibleRecords.size} 个 App，默认显示前 $DEFAULT_COLLAPSED_APP_COUNT 个"
            else -> "共 ${visibleRecords.size} 个 App"
        }
        layout.addView(expandableCard("顶部 App", topAppSummary, canExpand = topAppCanExpand) { expanded ->
            if (visibleRecords.isEmpty()) {
                addView(body("这一天没有达到 5 分钟的 App。").apply {
                    setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                })
            } else {
                val records = if (expanded) visibleRecords else visibleRecords.take(DEFAULT_COLLAPSED_APP_COUNT)
                records.forEachIndexed { index, record ->
                    if (index > 0) addView(separator())
                    addView(appUsageRow(record))
                }
                if (!expanded && visibleRecords.size > records.size) {
                    addView(body("还有 ${visibleRecords.size - records.size} 个 App，点“展开”查看。").apply {
                        textSize = 12f
                        setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                        setPadding(0, dp(8), 0, 0)
                    })
                }
            }
        })
        addDailyContextCards(layout, dailyContext)

        scroll.addView(layout)
        return scroll
    }

    private fun backRow(label: String, onClick: () -> Unit): TextView {
        return TextView(this).apply {
            text = "← $label"
            textSize = 15f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
            setPadding(dp(2), 0, dp(2), dp(12))
            setOnClickListener { onClick() }
        }
    }

    private fun appUsageRow(record: UsageAppRecord): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(6), 0, dp(6))

            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                addView(TextView(this@MainActivity).apply {
                    text = record.appName
                    textSize = 14f
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
                    maxLines = 1
                    ellipsize = TextUtils.TruncateAt.END
                })
                addView(TextView(this@MainActivity).apply {
                    text = record.packageName
                    textSize = 12f
                    setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                    maxLines = 1
                    ellipsize = TextUtils.TruncateAt.END
                    setPadding(0, dp(3), dp(12), 0)
                })
            })

            addView(TextView(this@MainActivity).apply {
                text = formatDuration(record.totalForegroundSeconds)
                textSize = 14f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
            })
        }
    }

    private fun addDailyStatusChecklist(
        layout: LinearLayout,
        countedRecords: List<UsageAppRecord>,
        dailyContext: JSONObject?,
    ) {
        layout.addView(card {
            addView(sectionHeader("每日数据状态"))
            if (dailyContext == null) {
                addView(statusChecklistRow("App 使用", countedRecords.size, countedRecords.isNotEmpty(), "没有计入的 App 使用记录"))
                addView(separator())
                addView(statusChecklistRow("Helper 导出", 0, false, "没有 daily_context.json"))
                return@card
            }

            val exportedAt = formatUiTime(dailyContext.optString("exported_at"))
            addView(settingsRow("导出时间", exportedAt))
            freshnessWarning(dailyContext)?.let { warning ->
                addView(body(warning).apply {
                    textSize = 12f
                    setTextColor(getColorInt(COLOR_RED))
                    setPadding(0, dp(2), 0, dp(8))
                })
            }
            addView(separator())
            val diagnostics = dailyContext.optJSONObject("diagnostics")
            val media = dailyContext.optJSONObject("media")
            val files = dailyContext.optJSONObject("files")
            val apps = dailyContext.optJSONObject("app_changes")
            val comm = dailyContext.optJSONObject("communication_backup")
            val notifications = dailyContext.optJSONObject("notification_history")
            val accessibility = dailyContext.optJSONObject("accessibility_events")
            val locationCount = (dailyContext.optJSONArray("location_snapshots")?.length() ?: 0) +
                (dailyContext.optJSONArray("archived_location_snapshots")?.length() ?: 0)
            val mediaCount = (media?.optInt("photos_count", 0) ?: 0) +
                (media?.optInt("videos_count", 0) ?: 0) +
                (media?.optInt("audio_count", 0) ?: 0)
            val appChangeCount = (apps?.optInt("installed_count", 0) ?: 0) +
                (apps?.optInt("updated_count", 0) ?: 0)
            val commCount = (comm?.optInt("sms_count", 0) ?: 0) +
                (comm?.optInt("call_count", 0) ?: 0) +
                (comm?.optInt("calendar_count", 0) ?: 0) +
                (comm?.optInt("contacts_updated_count", 0) ?: 0)

            val rows = listOf(
                Triple("App 使用", countedRecords.size, countedRecords.isNotEmpty()),
                Triple("位置", locationCount, diagnosticsOk(diagnostics, "location", "archived_location")),
                Triple("媒体", mediaCount, diagnosticsOk(diagnostics, "image_media", "video_media", "audio_media")),
                Triple("文件", files?.optInt("created_or_modified_count", 0) ?: 0, diagnosticsOk(diagnostics, "files")),
                Triple("App 变化", appChangeCount, diagnosticsOk(diagnostics, "apps")),
                Triple("通讯", commCount, diagnosticsOk(diagnostics, "sms_backup", "calls_backup", "calendar_backup", "contacts_backup")),
                Triple("通知", notifications?.optInt("count", 0) ?: 0, diagnosticsOk(diagnostics, "notification_history")),
                Triple("无障碍", accessibility?.optInt("count", 0) ?: 0, diagnosticsOk(diagnostics, "accessibility_events")),
            )
            rows.forEachIndexed { index, (name, count, ok) ->
                if (index > 0) addView(separator())
                addView(statusChecklistRow(name, count, ok, diagnosticsIssue(diagnostics, name)))
            }
        })
    }

    private fun freshnessWarning(dailyContext: JSONObject): String? {
        val notificationCount = dailyContext.optJSONObject("notification_history")?.optInt("count", 0) ?: 0
        val notificationStatus = dailyContext
            .optJSONObject("diagnostics")
            ?.optJSONObject("notification_history")
            ?.optString("status")
            .orEmpty()
        return if (notificationCount == 0 && notificationStatus == "empty") {
            "通知为 0：如果刚开启通知监听或刚收到通知，需要刷新导出。"
        } else {
            null
        }
    }

    private fun diagnosticsOk(diagnostics: JSONObject?, vararg keys: String): Boolean {
        if (diagnostics == null) return false
        return keys.all { key ->
            val status = diagnostics.optJSONObject(key)?.optString("status").orEmpty()
            status.isBlank() || status == "ok" || status == "empty"
        }
    }

    private fun diagnosticsIssue(diagnostics: JSONObject?, label: String): String {
        if (diagnostics == null) return "$label 缺少诊断信息"
        return "$label 需要检查权限或采集状态"
    }

    private fun statusChecklistRow(label: String, count: Int, ok: Boolean, issue: String): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(4), 0, dp(4))
            addView(TextView(this@MainActivity).apply {
                text = "${if (ok) "✓" else "!"} $label  $count 条"
                textSize = 14f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(getColorInt(if (ok) COLOR_GREEN else COLOR_RED))
            })
            if (!ok) {
                addView(body(issue).apply {
                    textSize = 12f
                    setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                    setPadding(0, dp(2), 0, 0)
                })
            }
        }
    }

    private fun buildPermissionCenterCard(): MaterialCardView {
        val items = PermissionStatusProvider.items(this, exporter)
        val grantedCount = items.count { it.granted }
        val pendingItems = items.filterNot { it.granted }
        return card {
            addView(sectionHeader("权限中心"))
            addView(label("采集机制"))
            addView(body("实时归档：通知、无障碍必须在发生时开启").apply {
                textSize = 12f
                setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
            })
            addView(body("周期采样：位置按采样点记录，不代表完整轨迹").apply {
                textSize = 12f
                setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
            })
            addView(body("历史回查：使用时长、媒体、通讯等可打开后补全").apply {
                textSize = 12f
                setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                setPadding(0, dp(4), 0, dp(8))
            })
            addView(TextView(this@MainActivity).apply {
                text = "已授权 $grantedCount/${items.size}，${pendingItems.size} 项待设置"
                textSize = 13f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(getColorInt(if (pendingItems.isEmpty()) COLOR_GREEN else COLOR_RED))
                setPadding(0, 0, 0, dp(8))
            })
            items.groupBy { it.group }.forEach { (group, groupItems) ->
                addView(label(group))
                val row = LinearLayout(this@MainActivity).apply {
                    orientation = LinearLayout.VERTICAL
                }
                groupItems.forEach { item ->
                    row.addView(compactPermissionRow(item))
                }
                addView(row)
            }
            if (pendingItems.isNotEmpty()) {
                addView(separator())
                addView(label("需要处理"))
                pendingItems.forEach { item ->
                    addView(permissionSetupButton(item))
                }
            }
        }
    }

    private fun compactPermissionRow(item: PermissionStatusItem): TextView {
        return TextView(this).apply {
            text = "${if (item.granted) "✓" else "!"} ${item.title}"
            textSize = 13f
            setTextColor(getColorInt(if (item.granted) COLOR_GREEN else COLOR_RED))
            setPadding(0, dp(2), dp(8), dp(2))
            maxLines = 1
            ellipsize = TextUtils.TruncateAt.END
        }
    }

    private fun permissionSetupButton(item: PermissionStatusItem): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(5), 0, dp(5))
            isClickable = true
            isFocusable = true
            setOnClickListener { openPermissionSetting(item) }

            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                addView(TextView(this@MainActivity).apply {
                    text = item.title
                    textSize = 14f
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
                })
                addView(TextView(this@MainActivity).apply {
                    text = item.detail
                    textSize = 12f
                    setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                    setPadding(0, dp(3), dp(12), 0)
                })
            })

            addView(TextView(this@MainActivity).apply {
                text = "去设置"
                textSize = 12f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(getColorInt(COLOR_RED))
                setPadding(dp(10), dp(5), dp(10), dp(5))
                background = roundedBackground(COLOR_SOFT_BG, dpToPxF(999), COLOR_SEPARATOR)
            })
        }
    }

    private fun openPermissionSetting(item: PermissionStatusItem) {
        if (!item.granted && item.settingsAction == Settings.ACTION_APPLICATION_DETAILS_SETTINGS) {
            requestContextRuntimePermissions()
        }
        startActivity(Intent(item.settingsAction).apply {
            item.dataUri?.let { data = it }
        })
    }

    private fun addDailyContextCards(layout: LinearLayout, dailyContext: JSONObject?) {
        layout.addView(card {
            addView(sectionHeader("Helper 上下文"))
            if (dailyContext == null) {
                addView(body("这一天没有 daily_context.json 导出。"))
            } else {
                val media = dailyContext.optJSONObject("media")
                val files = dailyContext.optJSONObject("files")
                val apps = dailyContext.optJSONObject("app_changes")
                val comm = dailyContext.optJSONObject("communication_backup")
                val notifications = dailyContext.optJSONObject("notification_history")
                val accessibility = dailyContext.optJSONObject("accessibility_events")
                addView(settingsRow("媒体", "${media?.optInt("photos_count", 0) ?: 0} 张照片 / ${media?.optInt("videos_count", 0) ?: 0} 个视频 / ${media?.optInt("audio_count", 0) ?: 0} 条音频"))
                addView(separator())
                addView(settingsRow("文件", "${files?.optInt("created_or_modified_count", 0) ?: 0} 条变化"))
                addView(separator())
                addView(settingsRow("App 变化", "${apps?.optInt("installed_count", 0) ?: 0} 个安装 / ${apps?.optInt("updated_count", 0) ?: 0} 个更新"))
                addView(separator())
                addView(settingsRow("通讯", "${comm?.optInt("sms_count", 0) ?: 0} 条短信 / ${comm?.optInt("call_count", 0) ?: 0} 条通话 / ${comm?.optInt("calendar_count", 0) ?: 0} 条日历 / ${comm?.optInt("contacts_updated_count", 0) ?: 0} 个联系人"))
                addView(separator())
                addView(settingsRow("通知", "${notifications?.optInt("count", 0) ?: 0} 条事件"))
                addView(separator())
                addView(settingsRow("无障碍", "${accessibility?.optInt("count", 0) ?: 0} 条事件"))
            }
        })
        if (dailyContext == null) return

        addJsonArrayCard(layout, "媒体明细", dailyContext.optJSONObject("media")?.optJSONArray("items"), 12) {
            "${formatUiTime(it.optString("time"))}  ${it.optString("type")}  ${it.optString("display_name")}  ${it.optString("relative_path")}"
        }
        val liveLocations = dailyContext.optJSONArray("location_snapshots")
        val archivedLocations = dailyContext.optJSONArray("archived_location_snapshots")
        addJsonArrayCard(layout, "位置明细", concatArrays(liveLocations, archivedLocations), 20) {
            val reason = it.optString("reason").ifBlank { it.optString("provider") }
            "${formatUiTime(it.optString("time"))}  $reason  ${it.optDouble("latitude")}, ${it.optDouble("longitude")}  ±${it.opt("accuracy_m")}m"
        }
        addJsonArrayCard(layout, "文件活动", dailyContext.optJSONObject("files")?.optJSONArray("items"), 15) {
            "${formatUiTime(it.optString("time"))}  ${it.optString("name")}  ${it.optString("relative_path")}"
        }
        addJsonArrayCard(
            layout,
            "App 变化",
            dailyContext.optJSONObject("app_changes")?.optJSONArray("items"),
            15,
            timeKeys = listOf("last_update_time", "first_install_time"),
        ) {
            "${formatDetailTime(it, listOf("last_update_time", "first_install_time"))}  ${it.optString("event")}  ${it.optString("name")}  ${it.optString("version_name")}  ${it.optString("package")}"
        }
        addJsonArrayCard(layout, "通知历史", dailyContext.optJSONObject("notification_history")?.optJSONArray("items"), 15) {
            "${formatUiTime(it.optString("time"))}  ${it.optString("event")}  ${it.optString("package")}  ${it.optString("title")} ${it.optString("text")}"
        }
        addJsonArrayCard(layout, "无障碍事件", dailyContext.optJSONObject("accessibility_events")?.optJSONArray("items"), 20) {
            "${formatUiTime(it.optString("time"))}  ${it.optString("package")}  ${it.optString("event_type")}  ${it.optString("text")} ${it.optString("view_id")}"
        }
        addDiagnosticsCard(layout, dailyContext.optJSONObject("diagnostics"))
    }

    private fun addJsonArrayCard(
        layout: LinearLayout,
        title: String,
        array: JSONArray?,
        limit: Int,
        timeKeys: List<String> = listOf("time"),
        render: (JSONObject) -> String,
    ) {
        val total = array?.length() ?: 0
        val collapsedCount = minOf(total, DEFAULT_COLLAPSED_DETAIL_COUNT)
        val visibleLimit = minOf(total, limit)
        val canExpand = visibleLimit > DEFAULT_COLLAPSED_DETAIL_COUNT
        val sortedArray = sortJsonArrayByTimeDesc(array, timeKeys)
        val summary = when {
            total == 0 -> "没有记录。"
            canExpand -> "共 $total 条，默认显示前 $collapsedCount 条"
            else -> "共 $total 条"
        }
        layout.addView(expandableCard(title, summary, canExpand = canExpand) { expanded ->
            if (sortedArray == null || total == 0) {
                addView(body("没有记录。"))
                return@expandableCard
            }

            val count = if (expanded) visibleLimit else collapsedCount
            for (i in 0 until count) {
                if (i > 0) addView(separator())
                addView(body(render(sortedArray.optJSONObject(i) ?: JSONObject())).apply {
                    textSize = 13f
                    setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                    maxLines = if (expanded) 3 else 2
                    ellipsize = TextUtils.TruncateAt.END
                })
            }
            when {
                !expanded && visibleLimit > count -> {
                    addView(body("还有 ${visibleLimit - count} 条记录，点“展开”查看。").apply {
                        textSize = 12f
                        setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                        setPadding(0, dp(8), 0, 0)
                    })
                }
                total > visibleLimit -> {
                    addView(body("其余 ${total - visibleLimit} 条未显示，避免列表过长。").apply {
                        textSize = 12f
                        setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                        setPadding(0, dp(8), 0, 0)
                    })
                }
            }
        })
    }

    private fun sortJsonArrayByTimeDesc(array: JSONArray?, timeKeys: List<String>): JSONArray? {
        if (array == null) return null
        val sorted = (0 until array.length())
            .mapNotNull { index -> array.optJSONObject(index) }
            .sortedWith(
                compareByDescending<JSONObject> { item ->
                    timeKeys.asSequence()
                        .mapNotNull { key -> parseUiDateTimeMillis(item.optString(key)) }
                        .firstOrNull() ?: Long.MIN_VALUE
                },
            )
        return JSONArray().apply {
            sorted.forEach { put(it) }
        }
    }

    private fun addDiagnosticsCard(layout: LinearLayout, diagnostics: JSONObject?) {
        val keys = diagnostics?.keys()?.asSequence()?.sorted()?.toList().orEmpty()
        val canExpand = keys.size > DEFAULT_COLLAPSED_DETAIL_COUNT
        val summary = when {
            keys.isEmpty() -> "没有诊断信息。"
            canExpand -> "共 ${keys.size} 项，默认显示前 ${DEFAULT_COLLAPSED_DETAIL_COUNT} 项"
            else -> "共 ${keys.size} 项"
        }
        layout.addView(expandableCard("模块诊断", summary, canExpand = canExpand) { expanded ->
            if (keys.isEmpty()) {
                addView(body("没有诊断信息。"))
                return@expandableCard
            }
            val visibleKeys = if (expanded) keys else keys.take(DEFAULT_COLLAPSED_DETAIL_COUNT)
            visibleKeys.forEachIndexed { index, key ->
                if (index > 0) addView(separator())
                val item = diagnostics?.optJSONObject(key)
                addView(settingsRow(key, item?.optString("status", "unknown") ?: diagnostics?.optString(key).orEmpty()))
            }
            if (!expanded && keys.size > visibleKeys.size) {
                addView(body("还有 ${keys.size - visibleKeys.size} 项，点“展开”查看。").apply {
                    textSize = 12f
                    setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                    setPadding(0, dp(8), 0, 0)
                })
            }
        })
    }

    private fun concatArrays(first: JSONArray?, second: JSONArray?): JSONArray {
        val out = JSONArray()
        listOf(first, second).forEach { array ->
            if (array != null) {
                for (i in 0 until array.length()) out.put(array.opt(i))
            }
        }
        return out
    }

    // ─── Settings Page ────────────────────────────────────────────

    private fun buildSettingsPage(): View {
        val scroll = pageScroll()
        val layout = pageLayout()

        layout.addView(pageTitle("设置"))
        layout.addView(buildPermissionCenterCard())

        layout.addView(sectionHeader("导出").apply {
            setPadding(dp(2), 0, dp(2), dp(12))
        })
        layout.addView(buildExportSection())

        // Storage info
        layout.addView(card {
            addView(sectionHeader("存储"))
            addView(settingsRow("导出目录", "/sdcard/PhoneTracker/export"))
            addView(separator())
            addView(settingsRow("缓存保留", "400 天"))
        })

        // Maintenance
        layout.addView(card {
            addView(sectionHeader("维护"))
            addView(secondaryIconButton("清理缓存（超过 400 天）", R.drawable.ic_close) {
                exporter.pruneCache(400)
                settingsProgressText.text = "旧缓存已清理"
            })
        })

        // Auto-collect with Switch
        val autoEnabled = prefs.getBoolean("auto_daily_capture", false)
        layout.addView(card {
            addView(sectionHeader("后台采集"))
            addView(settingsSwitch(
                title = "每日自动采集",
                subtitle = "通过 WorkManager 每 24 小时采集一次。如果不稳定，请关闭本 App 的电池优化。",
                checked = autoEnabled,
            ) { enabled ->
                prefs.edit().putBoolean("auto_daily_capture", enabled).apply()
                if (enabled) scheduleDailyWork() else cancelDailyWork()
            })
        })

        settingsProgressText = body("")
        settingsProgressText.setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
        layout.addView(settingsProgressText)

        scroll.addView(layout)
        return scroll
    }

    // ─── View Builders ────────────────────────────────────────────

    private fun pageScroll(): ScrollView = ScrollView(this).apply {
        setPadding(0, dp(48), 0, 0)
        clipToPadding = true
        setBackgroundColor(getColorInt(COLOR_BACKGROUND))
    }

    private fun pageLayout(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(18), 0, dp(18), dp(22))
        layoutParams = ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
        )
    }

    private fun pageTitle(text: String): TextView = TextView(this).apply {
        this.text = text
        textSize = 26f
        typeface = Typeface.DEFAULT_BOLD
        setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
        setPadding(dp(2), 0, dp(2), dp(18))
    }

    private fun sectionHeader(text: String): TextView = TextView(this).apply {
        this.text = text
        textSize = 15f
        typeface = Typeface.DEFAULT_BOLD
        setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
        setPadding(0, 0, 0, dp(12))
    }

    private fun card(block: (LinearLayout.() -> Unit)? = null): MaterialCardView {
        val inner = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = dp(20)
            setPadding(pad, pad, pad, pad)
        }
        block?.invoke(inner)

        return MaterialCardView(this).apply {
            radius = dpToPxF(14)
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = getColorInt(COLOR_SEPARATOR)
            setCardBackgroundColor(ColorStateList.valueOf(getColorInt(COLOR_CARD_BG)))
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply {
                bottomMargin = dp(16)
            }
            addView(inner)
        }
    }

    private fun expandableCard(
        title: String,
        summary: String? = null,
        defaultExpanded: Boolean = false,
        canExpand: Boolean = true,
        renderContent: LinearLayout.(Boolean) -> Unit,
    ): MaterialCardView {
        val titleView = TextView(this).apply {
            text = title
            textSize = 15f
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
        }
        val summaryView = TextView(this).apply {
            text = summary.orEmpty()
            textSize = 12f
            setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
            setPadding(0, dp(4), 0, 0)
            visibility = if (summary.isNullOrBlank()) View.GONE else View.VISIBLE
        }
        val toggleView = TextView(this).apply {
            textSize = 12f
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
            setPadding(dp(12), dp(6), dp(12), dp(6))
            background = roundedBackground(COLOR_SOFT_BG, dpToPxF(999), COLOR_SEPARATOR)
        }
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(0, dp(12), 0, 0)
        }
        var expanded = defaultExpanded || !canExpand

        fun render() {
            toggleView.text = if (expanded) "收起" else "展开"
            toggleView.visibility = if (canExpand) View.VISIBLE else View.GONE
            toggleView.setTextColor(getColorInt(if (expanded) COLOR_TEXT_PRIMARY else COLOR_TEXT_SECONDARY))
            content.removeAllViews()
            content.renderContent(expanded)
        }

        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                addView(titleView)
                addView(summaryView)
            })
            addView(toggleView)
            if (canExpand) {
                isClickable = true
                isFocusable = true
                setOnClickListener {
                    expanded = !expanded
                    render()
                }
            }
        }
        if (canExpand) {
            toggleView.setOnClickListener {
                expanded = !expanded
                render()
            }
        }

        val inner = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = dp(16)
            setPadding(pad, pad, pad, pad)
            addView(header)
            addView(content)
        }

        render()

        return MaterialCardView(this).apply {
            radius = dpToPxF(14)
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = getColorInt(COLOR_SEPARATOR)
            setCardBackgroundColor(ColorStateList.valueOf(getColorInt(COLOR_CARD_BG)))
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply {
                bottomMargin = dp(12)
            }
            addView(inner)
        }
    }

    private fun iconButton(text: String, iconRes: Int, onClick: () -> Unit): MaterialButton {
        return MaterialButton(this).apply {
            this.text = text
            textSize = 15f
            typeface = Typeface.DEFAULT_BOLD
            isAllCaps = false
            cornerRadius = dp(10)
            strokeWidth = 0
            icon = getDrawable(iconRes)
            iconGravity = MaterialButton.ICON_GRAVITY_TEXT_START
            iconSize = dp(18)
            iconTint = ColorStateList.valueOf(Color.WHITE)
            backgroundTintList = ColorStateList.valueOf(getColorInt(COLOR_ACCENT))
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply {
                bottomMargin = dp(12)
            }
            setOnClickListener { onClick() }
        }
    }

    private fun secondaryIconButton(text: String, iconRes: Int, onClick: () -> Unit): MaterialButton {
        return MaterialButton(this).apply {
            this.text = text
            textSize = 15f
            typeface = Typeface.DEFAULT_BOLD
            isAllCaps = false
            cornerRadius = dp(10)
            strokeWidth = dp(1)
            strokeColor = ColorStateList.valueOf(getColorInt(COLOR_SEPARATOR))
            icon = getDrawable(iconRes)
            iconGravity = MaterialButton.ICON_GRAVITY_TEXT_START
            iconSize = dp(18)
            iconTint = ColorStateList.valueOf(getColorInt(COLOR_TEXT_PRIMARY))
            backgroundTintList = ColorStateList.valueOf(getColorInt(COLOR_CARD_BG))
            setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply {
                bottomMargin = dp(10)
            }
            setOnClickListener { onClick() }
        }
    }

    private fun statTile(label: String, value: String, addEndMargin: Boolean): MaterialCardView {
        val inner = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
            addView(TextView(this@MainActivity).apply {
                text = label
                textSize = 12f
                setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
            })
            addView(TextView(this@MainActivity).apply {
                text = value
                textSize = 25f
                typeface = Typeface.DEFAULT_BOLD
                setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
                setPadding(0, dp(4), 0, 0)
                maxLines = 1
                ellipsize = TextUtils.TruncateAt.END
            })
        }

        return MaterialCardView(this).apply {
            radius = dpToPxF(12)
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = getColorInt(COLOR_SEPARATOR)
            setCardBackgroundColor(ColorStateList.valueOf(getColorInt(COLOR_SOFT_BG)))
            layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
                if (addEndMargin) marginEnd = dp(10)
            }
            addView(inner)
        }
    }

    private fun collectionStatusPanel(): MaterialCardView {
        val inner = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(13), dp(14), dp(13))

            collectionTitle = TextView(this@MainActivity).apply {
                textSize = 15f
                typeface = Typeface.DEFAULT_BOLD
            }
            collectionSubtitle = TextView(this@MainActivity).apply {
                textSize = 12f
                setPadding(0, dp(4), 0, dp(10))
                maxLines = 2
                ellipsize = TextUtils.TruncateAt.END
            }
            collectionProgress = ProgressBar(
                this@MainActivity,
                null,
                android.R.attr.progressBarStyleHorizontal,
            ).apply {
                max = 100
                progress = 0
                progressTintList = ColorStateList.valueOf(getColorInt(COLOR_ACCENT))
                progressBackgroundTintList = ColorStateList.valueOf(getColorInt(COLOR_SEPARATOR))
                layoutParams = LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    dp(6),
                )
            }

            addView(collectionTitle)
            addView(collectionSubtitle)
            addView(collectionProgress)
        }

        return MaterialCardView(this).apply {
            radius = dpToPxF(12)
            cardElevation = 0f
            strokeWidth = dp(1)
            strokeColor = getColorInt(COLOR_SEPARATOR)
            setCardBackgroundColor(ColorStateList.valueOf(getColorInt(COLOR_SOFT_BG)))
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply {
                bottomMargin = dp(12)
            }
            addView(inner)
            renderCollectionStatus()
        }
    }

    private fun renderCollectionStatus() {
        if (!::collectionTitle.isInitialized) return
        collectionTitle.text = collectionTitleText
        collectionSubtitle.text = collectionSubtitleText
        collectionTitle.setTextColor(getColorInt(if (collectionAttention) COLOR_RED else COLOR_TEXT_PRIMARY))
        collectionSubtitle.setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
        collectionProgress.progress = collectionProgressValue
        collectionProgress.progressTintList = ColorStateList.valueOf(
            getColorInt(
                when {
                    collectionAttention -> COLOR_RED
                    collectionRunning -> COLOR_ACCENT
                    else -> COLOR_GREEN
                }
            )
        )
    }

    private fun pill(text: String): TextView = TextView(this).apply {
        this.text = text
        textSize = 12f
        setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
        maxLines = 1
        ellipsize = TextUtils.TruncateAt.END
        background = roundedBackground(COLOR_SOFT_BG, dpToPxF(999), COLOR_SEPARATOR)
        setPadding(dp(12), dp(7), dp(12), dp(7))
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.WRAP_CONTENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
        )
    }

    private fun statusRow(title: String, subtitle: String, badge: TextView): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(8), 0, dp(8))

            addView(LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
                addView(TextView(this@MainActivity).apply {
                    text = title
                    textSize = 15f
                    typeface = Typeface.DEFAULT_BOLD
                    setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
                })
                addView(TextView(this@MainActivity).apply {
                    text = subtitle
                    textSize = 12f
                    setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                    setPadding(0, dp(3), dp(10), 0)
                })
            })
            addView(badge)
        }
    }

    private fun statusBadge(ok: Boolean): TextView = TextView(this).apply {
        textSize = 12f
        typeface = Typeface.DEFAULT_BOLD
        setPadding(dp(10), dp(5), dp(10), dp(5))
        updateStatusBadge(this, ok)
    }

    private fun updateStatusBadge(view: TextView, ok: Boolean) {
        view.text = if (ok) "已授权" else "待设置"
        view.setTextColor(getColorInt(if (ok) COLOR_GREEN else COLOR_TEXT_SECONDARY))
        view.background = roundedBackground(
            if (ok) COLOR_GREEN_SOFT else COLOR_SOFT_BG,
            dpToPxF(999),
            if (ok) COLOR_GREEN_BORDER else COLOR_SEPARATOR,
        )
    }

    private fun chip(text: String, onClick: () -> Unit): Chip {
        return Chip(this).apply {
            this.text = text
            textSize = 13f
            isCheckable = false
            isClickable = true
            chipBackgroundColor = ColorStateList.valueOf(getColorInt(COLOR_SOFT_BG))
            setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
            chipStrokeWidth = 1f
            chipStrokeColor = ColorStateList.valueOf(getColorInt(COLOR_SEPARATOR))
            setOnClickListener { onClick() }
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
            ).apply {
                marginEnd = dp(8)
            }
        }
    }

    private fun settingsSwitch(title: String, subtitle: String, checked: Boolean, onToggle: (Boolean) -> Unit): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL

            val textCol = LinearLayout(this@MainActivity).apply {
                orientation = LinearLayout.VERTICAL
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            }
            textCol.addView(TextView(this@MainActivity).apply {
                text = title
                textSize = 15f
                setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
            })
            textCol.addView(TextView(this@MainActivity).apply {
                text = subtitle
                textSize = 12f
                setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                setPadding(0, dp(4), 0, 0)
            })
            addView(textCol)

            autoCollectSwitch = SwitchCompat(this@MainActivity).apply {
                this.isChecked = checked
                thumbTintList = ColorStateList(
                    arrayOf(
                        intArrayOf(android.R.attr.state_checked),
                        intArrayOf(-android.R.attr.state_checked),
                    ),
                    intArrayOf(
                        getColorInt(COLOR_ACCENT),
                        getColorInt(COLOR_SEPARATOR),
                    ),
                )
                trackTintList = ColorStateList(
                    arrayOf(
                        intArrayOf(android.R.attr.state_checked),
                        intArrayOf(-android.R.attr.state_checked),
                    ),
                    intArrayOf(
                        getColorInt(COLOR_SOFT_ACCENT),
                        getColorInt(COLOR_SEPARATOR),
                    ),
                )
                setOnCheckedChangeListener { _, isChecked -> onToggle(isChecked) }
            }
            addView(autoCollectSwitch)
        }
    }

    private fun label(text: String): TextView = TextView(this).apply {
        this.text = text
        textSize = 13f
        setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
        setPadding(0, dp(12), 0, dp(4))
    }

    private fun body(text: String): TextView = TextView(this).apply {
        this.text = text
        textSize = 15f
        setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
        setPadding(0, dp(4), 0, dp(4))
    }

    private fun settingsRow(key: String, value: String): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, dp(8), 0, dp(8))

            addView(TextView(this@MainActivity).apply {
                text = key
                textSize = 15f
                setTextColor(getColorInt(COLOR_TEXT_PRIMARY))
                layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)
            })

            addView(TextView(this@MainActivity).apply {
                text = value
                textSize = 15f
                setTextColor(getColorInt(COLOR_TEXT_SECONDARY))
                gravity = Gravity.END
                setPadding(dp(12), 0, 0, 0)
            })
        }
    }

    private fun separator(): View {
        return View(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(1)
            ).apply {
                topMargin = dp(4)
                bottomMargin = dp(4)
            }
            setBackgroundColor(getColorInt(COLOR_SEPARATOR))
        }
    }

    private fun roundedBackground(colorHex: String, radius: Float, strokeHex: String? = null): GradientDrawable {
        return GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = radius
            setColor(getColorInt(colorHex))
            if (strokeHex != null) setStroke(dp(1), getColorInt(strokeHex))
        }
    }

    private fun applySystemBarStyle() {
        window.statusBarColor = getColorInt(COLOR_BACKGROUND)
        window.navigationBarColor = getColorInt(COLOR_CARD_BG)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            var flags = View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                flags = flags or View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR
            }
            window.decorView.systemUiVisibility = flags
        }
    }

    // ─── Logic ────────────────────────────────────────────────────

    private fun requestContextRuntimePermissions() {
        val permissions = buildList {
            add(Manifest.permission.ACCESS_FINE_LOCATION)
            add(Manifest.permission.ACCESS_COARSE_LOCATION)
            add(Manifest.permission.READ_CONTACTS)
            add(Manifest.permission.READ_SMS)
            add(Manifest.permission.READ_CALL_LOG)
            add(Manifest.permission.READ_CALENDAR)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.READ_MEDIA_IMAGES)
                add(Manifest.permission.READ_MEDIA_VIDEO)
                add(Manifest.permission.READ_MEDIA_AUDIO)
                add(Manifest.permission.POST_NOTIFICATIONS)
            } else {
                add(Manifest.permission.READ_EXTERNAL_STORAGE)
            }
        }.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (permissions.isNotEmpty()) {
            requestPermissions(permissions.toTypedArray(), 42)
        }
    }

    private fun startKeepAliveService() {
        val intent = Intent(this, KeepAliveService::class.java)
        try {
            ContextCompat.startForegroundService(this, intent)
        } catch (_: RuntimeException) {
            // Some OEMs may block foreground service start while settings are incomplete.
        }
    }

    private fun handleIntentCommand(intent: Intent?) {
        if (intent?.getStringExtra("command") != "export_recent") return
        val days = intent.getIntExtra("days", 395).toLong()
        runExport { exporter.exportRecentDays(days) }
    }

    private fun runAutoCollection() {
        if (shouldSkipAutoCollection()) {
            refreshStatus()
            return
        }
        runCollectionWithProgress(force = false)
    }

    private fun shouldSkipAutoCollection(): Boolean {
        if (collectionRunning) return true
        val lastCollectionAt = prefs.getLong(KEY_LAST_COLLECTION_AT, 0L)
        if (lastCollectionAt <= 0L) return false
        return System.currentTimeMillis() - lastCollectionAt < AUTO_REFRESH_INTERVAL_MS
    }

    private fun runCollectionWithProgress(force: Boolean) {
        if (collectionRunning) return
        showCollectionRunning(force)
        val startedAt = SystemClock.elapsedRealtime()
        Thread {
            try {
                val result = exporter.collectRecentDays(AUTO_FULL_COLLECTION_DAYS, force = force)
                recordCollectionFinished(result)
                sleepUntilMinimumProgressTime(startedAt)
                runOnUiThread {
                    showCollectionResult(result)
                    refreshStatus()
                }
            } catch (e: Exception) {
                sleepUntilMinimumProgressTime(startedAt)
                runOnUiThread {
                    showCollectionFailure(e)
                    refreshStatus()
                }
            }
        }.start()
    }

    private fun recordCollectionFinished(result: ExportResult) {
        if (result.failedDays > 0) return
        prefs.edit()
            .putLong(KEY_LAST_COLLECTION_AT, System.currentTimeMillis())
            .apply()
    }

    private fun showCollectionRunning(force: Boolean) {
        collectionAnimator?.cancel()
        collectionRunning = true
        collectionAttention = false
        collectionProgressValue = 0
        collectionTitleText = "正在采集并准备电脑同步..."
        collectionSubtitleText = if (force) {
            "强制重查最近 ${AUTO_FULL_COLLECTION_DAYS} 天并写出同步文件"
        } else {
            "检查最近 ${AUTO_FULL_COLLECTION_DAYS} 天，已完整的使用时长会跳过并刷新上下文"
        }
        progressText.text = collectionSubtitleText
        renderCollectionStatus()

        if (::collectionProgress.isInitialized) {
            collectionProgress.progress = 0
            collectionAnimator = ObjectAnimator.ofInt(collectionProgress, "progress", 0, 92).apply {
                duration = MIN_COLLECTION_PROGRESS_MS
                interpolator = LinearInterpolator()
                start()
            }
        }
    }

    private fun showCollectionResult(result: ExportResult) {
        collectionAnimator?.cancel()
        collectionRunning = false
        collectionAttention = result.failedDays > 0
        collectionProgressValue = 100
        collectionTitleText = if (collectionAttention) "采集需要检查" else "最新数据已准备同步"
        collectionSubtitleText = buildCollectionResultText(result)
        progressText.text = collectionSubtitleText
        renderCollectionStatus()
    }

    private fun showCollectionFailure(error: Exception) {
        collectionAnimator?.cancel()
        collectionRunning = false
        collectionAttention = true
        collectionProgressValue = 100
        collectionTitleText = "采集需要检查"
        collectionSubtitleText = "失败：${error.message ?: "未知错误"}"
        progressText.text = collectionSubtitleText
        renderCollectionStatus()
    }

    private fun buildCollectionResultText(result: ExportResult): String {
        val details = mutableListOf<String>()
        if (result.exportedDays > 0) {
            details.add("已更新 ${result.exportedDays} 天")
        }
        if (result.skippedDays > 0) {
            details.add("跳过 ${result.skippedDays} 天")
        }
        if (details.isEmpty()) {
            details.add("没有需要更新的日期")
        }
        if (result.emptyDays > 0) details.add("${result.emptyDays} 天为空")
        if (result.failedDays > 0) details.add("${result.failedDays} 天失败")
        return details.joinToString(" · ")
    }

    private fun sleepUntilMinimumProgressTime(startedAt: Long) {
        val remainingMs = MIN_COLLECTION_PROGRESS_MS - (SystemClock.elapsedRealtime() - startedAt)
        if (remainingMs > 0) Thread.sleep(remainingMs)
    }

    private fun runExport(block: () -> ExportResult) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R &&
            checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.WRITE_EXTERNAL_STORAGE), 1001)
            exportProgressText.text = "请授予存储权限后重试"
            return
        }
        runTask("正在导出...", { exportProgressText }) { block() }
    }

    private fun runTask(message: String, targetView: () -> TextView, block: () -> ExportResult) {
        val tv = targetView()
        tv.text = message
        Thread {
            try {
                val result = block()
                runOnUiThread {
                    tv.text = "完成：${result.exportedDays} 天，${result.appRows} 条记录，${result.emptyDays} 天为空，${result.failedDays} 天失败\n${result.outputDir}"
                    refreshStatus()
                }
            } catch (e: Exception) {
                runOnUiThread { tv.text = "失败：${e.message}" }
            }
        }.start()
    }

    private fun scheduleDailyWork() {
        val request = PeriodicWorkRequestBuilder<DailyCollectWorker>(24, TimeUnit.HOURS)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.NOT_REQUIRED).build())
            .build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork(
            "daily_usage_collect", ExistingPeriodicWorkPolicy.UPDATE, request
        )
    }

    private fun scheduleLocationArchiveWork() {
        val request = PeriodicWorkRequestBuilder<LocationArchiveWorker>(15, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.NOT_REQUIRED).build())
            .build()
        WorkManager.getInstance(this).enqueueUniquePeriodicWork(
            "periodic_location_archive", ExistingPeriodicWorkPolicy.UPDATE, request
        )
    }

    private fun cancelDailyWork() {
        WorkManager.getInstance(this).cancelUniqueWork("daily_usage_collect")
    }

    private fun openStoragePermissionSettings() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            startActivity(Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION).apply {
                data = Uri.parse("package:$packageName")
            })
        } else {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                data = Uri.parse("package:$packageName")
            })
        }
    }

    private fun parseDate(value: String): LocalDate? {
        return try { LocalDate.parse(value.trim()) } catch (_: DateTimeParseException) { null }
    }

    private fun formatLastCollected(value: String?): String {
        if (value.isNullOrBlank()) return "从未"
        return formatUiDateTime(value)
    }

    private fun formatUiDateTime(value: String?): String {
        val trimmed = value?.trim().orEmpty()
        if (trimmed.isBlank()) return "未知"

        val formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")
        return runCatching {
            OffsetDateTime.parse(trimmed).format(formatter)
        }.recoverCatching {
            Instant.parse(trimmed).atZone(ZoneId.systemDefault()).format(formatter)
        }.recoverCatching {
            Instant.parse(trimmed.replace(' ', 'T')).atZone(ZoneId.systemDefault()).format(formatter)
        }.getOrElse {
            trimmed
                .replace('T', ' ')
                .replace(Regex("(\\.\\d+)?([+-]\\d{2}:?\\d{2}|Z)$"), "")
                .let { normalized ->
                    if (normalized.length >= 16) normalized.take(16) else normalized
                }
        }
    }

    private fun formatUiTime(value: String?): String {
        val trimmed = value?.trim().orEmpty()
        if (trimmed.isBlank()) return "未知"

        val formatter = DateTimeFormatter.ofPattern("HH:mm")
        return runCatching {
            OffsetDateTime.parse(trimmed).format(formatter)
        }.recoverCatching {
            Instant.parse(trimmed).atZone(ZoneId.systemDefault()).format(formatter)
        }.recoverCatching {
            Instant.parse(trimmed.replace(' ', 'T')).atZone(ZoneId.systemDefault()).format(formatter)
        }.getOrElse {
            Regex("""\b\d{2}:\d{2}\b""").find(trimmed.replace('T', ' '))?.value ?: trimmed
        }
    }

    private fun formatDetailTime(item: JSONObject, timeKeys: List<String>): String {
        return timeKeys.asSequence()
            .map { key -> item.optString(key) }
            .firstOrNull { it.isNotBlank() }
            ?.let(::formatUiTime)
            ?: "未知"
    }

    private fun parseUiDateTimeMillis(value: String?): Long? {
        val trimmed = value?.trim().orEmpty()
        if (trimmed.isBlank()) return null

        return runCatching {
            OffsetDateTime.parse(trimmed).toInstant().toEpochMilli()
        }.recoverCatching {
            Instant.parse(trimmed).toEpochMilli()
        }.recoverCatching {
            Instant.parse(trimmed.replace(' ', 'T')).toEpochMilli()
        }.getOrNull()
    }

    private fun formatDuration(totalSeconds: Long): String {
        val hours = totalSeconds / 3600
        val minutes = (totalSeconds % 3600) / 60
        val seconds = totalSeconds % 60
        return when {
            hours > 0 -> "${hours}小时 ${minutes}分钟"
            minutes > 0 -> "${minutes}分钟 ${seconds}秒"
            else -> "${seconds}秒"
        }
    }

    // ─── Utility ──────────────────────────────────────────────────

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()
    private fun dpToPxF(value: Int): Float = value * resources.displayMetrics.density
    private fun getColorInt(colorHex: String): Int = Color.parseColor(colorHex)
    private fun formatNumber(n: Int): String = if (n >= 1000) "%,d".format(n) else n.toString()

    private fun navIconTint(): ColorStateList {
        return ColorStateList(
            arrayOf(
                intArrayOf(android.R.attr.state_checked),
                intArrayOf(-android.R.attr.state_checked),
            ),
            intArrayOf(getColorInt(COLOR_ACCENT), getColorInt(COLOR_TEXT_SECONDARY)),
        )
    }

    companion object {
        private const val PAGE_HOME = 0
        private const val PAGE_DIAGNOSTICS = 1
        private const val PAGE_SETTINGS = 2
        private const val MIN_COLLECTION_PROGRESS_MS = 1_000L
        private const val AUTO_FULL_COLLECTION_DAYS = 14L
        private const val AUTO_REFRESH_INTERVAL_MS = 20 * 60 * 1000L
        private const val KEY_LAST_COLLECTION_AT = "last_collection_at"
        private const val MIN_COUNTED_APP_SECONDS = 60L
        private const val MIN_VISIBLE_APP_SECONDS = 5 * 60L
        private const val DEFAULT_COLLAPSED_APP_COUNT = 5
        private const val DEFAULT_COLLAPSED_DETAIL_COUNT = 3

        private const val COLOR_BACKGROUND = "#F7F6F3"
        private const val COLOR_CARD_BG = "#FFFFFF"
        private const val COLOR_SOFT_BG = "#FBFAF8"
        private const val COLOR_ACCENT = "#37352F"
        private const val COLOR_SOFT_ACCENT = "#EDEBE7"
        private const val COLOR_TEXT_PRIMARY = "#37352F"
        private const val COLOR_TEXT_SECONDARY = "#787774"
        private const val COLOR_SEPARATOR = "#E9E6DF"
        private const val COLOR_GREEN = "#2F7D32"
        private const val COLOR_GREEN_SOFT = "#EEF6EE"
        private const val COLOR_GREEN_BORDER = "#D7E9D6"
        private const val COLOR_RED = "#B23B3B"
    }
}