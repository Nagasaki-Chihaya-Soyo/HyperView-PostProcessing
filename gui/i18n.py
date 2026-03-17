"""
轻量级国际化模块 —— 中英文双语切换。
用法:
    from gui.i18n import t, set_lang, get_lang, on_lang_change

    label.config(text=t("app.title"))

    # 注册语言变更回调
    on_lang_change(my_refresh_func)

    # 切换语言
    set_lang("en")   # 所有已注册回调自动触发
"""

_current_lang = "en"
_callbacks = []

# ── 翻译表 ──

_STRINGS = {

    # ======== Application 主窗口 ========
    "app.title":                    {"zh": "HyperView 后处理工具", "en": "HyperView Post-Processing Tools"},
    "app.hv_now":                   {"zh": "HyperView 状态:", "en": "HyperView Now:"},
    "app.disconnected":             {"zh": "未连接", "en": "Disconnected"},
    "app.start_hv":                 {"zh": "启动 HyperView", "en": "Starting HyperView"},
    "app.agent":                    {"zh": "模式:", "en": "Agent:"},
    "app.lang_btn":                 {"zh": "EN", "en": "中文"},

    # 状态
    "state.idle":                   {"zh": "未连接", "en": "Disconnected"},
    "state.starting":               {"zh": "启动中...", "en": "Starting..."},
    "state.ready":                  {"zh": "就绪", "en": "Ready"},
    "state.running":                {"zh": "运行中...", "en": "Running..."},
    "state.failed":                 {"zh": "失败", "en": "Failed"},
    "state.exited":                 {"zh": "已退出", "en": "Exit"},

    # Tab 标签
    "tab.run":                      {"zh": "运行应用", "en": "Run Application"},
    "tab.parts":                    {"zh": "标准库", "en": "Standard Repository"},
    "tab.logs":                     {"zh": "日志", "en": "Logs"},

    # Run Tab
    "run.select_files":             {"zh": "选择文件", "en": "Select Files"},
    "run.model_files":              {"zh": "模型文件:", "en": "Model Files:"},
    "run.result_files":             {"zh": "结果文件:", "en": "Result Files:"},
    "run.view":                     {"zh": "浏览...", "en": "View..."},
    "run.load_model":               {"zh": "加载模型", "en": "Load Model"},
    "run.analysing":                {"zh": "分析", "en": "Analysing"},
    "run.auto_minimize":            {"zh": "自动最小化", "en": "Auto Minimize"},
    "run.result_title":             {"zh": "分析结果", "en": "Analysing Result"},
    "run.open_folder":              {"zh": "打开结果文件夹", "en": "Open Result File Folder"},

    # Run Tab - 消息
    "run.select_model_first":       {"zh": "请先选择模型文件", "en": "Select a model file first"},
    "run.load_failed":              {"zh": "模型加载失败，请查看日志。", "en": "Failed to load model. Check log for details."},
    "run.analysis_failed":          {"zh": "分析失败，请检查错误日志。", "en": "Analysis Failed. Check The Error Log for Details"},
    "run.hv_start_failed":          {"zh": "HyperView 启动失败", "en": "HyperView Failed to Start"},

    # File Dialogs
    "dlg.select_model":             {"zh": "选择模型文件", "en": "Select Model Files"},
    "dlg.select_result":            {"zh": "选择结果文件", "en": "Select Result Files"},
    "dlg.select_csv_import":        {"zh": "选择 CSV 文件", "en": "Select CSV Files"},
    "dlg.save_csv":                 {"zh": "保存 CSV 文件", "en": "Save CSV Files"},

    # Parts Tab
    "parts.add":                    {"zh": "添加", "en": "Add"},
    "parts.edit":                   {"zh": "编辑", "en": "Edit"},
    "parts.delete":                 {"zh": "删除", "en": "Delete"},
    "parts.import_csv":             {"zh": "导入 CSV", "en": "Import CSV"},
    "parts.export_csv":             {"zh": "导出 CSV", "en": "Export CSV"},
    "parts.search":                 {"zh": "搜索:", "en": "Search:"},
    "parts.clear":                  {"zh": "清空", "en": "Clear"},
    "parts.drag_hint":              {"zh": "  |  拖拽行以重新排序", "en": "  |  Drag rows to reorder"},
    "parts.select_first":           {"zh": "请先选择一条记录", "en": "SELECT A PART FIRST"},
    "parts.confirm_delete":         {"zh": "确定要删除所选记录吗？此操作不可撤消。",
                                     "en": "Are you sure you want to delete the selected parts? This action can not be undone"},

    # Parts - 列标题
    "col.part_no":                  {"zh": "零件号", "en": "Parts ID"},
    "col.name":                     {"zh": "名称", "en": "Name"},
    "col.allowable":                {"zh": "许用应力", "en": "Allowable Stress"},
    "col.safety_factor":            {"zh": "安全系数", "en": "Safety Factor"},
    "col.effective":                {"zh": "有效值 (÷SF)", "en": "Effective (÷SF)"},
    "col.units":                    {"zh": "单位", "en": "Unit"},
    "col.notes":                    {"zh": "备注", "en": "Notes"},

    # Logs Tab
    "logs.clear":                   {"zh": "清除日志", "en": "Clear Logs"},

    # 通用按钮 / 标题
    "btn.confirm":                  {"zh": "确认", "en": "Confirm"},
    "btn.cancel":                   {"zh": "取消", "en": "Cancel"},
    "btn.apply":                    {"zh": "应用", "en": "Apply"},
    "btn.close":                    {"zh": "关闭", "en": "Close"},
    "title.warning":                {"zh": "警告", "en": "WARNING"},
    "title.error":                  {"zh": "错误", "en": "ERROR"},
    "title.complete":               {"zh": "完成", "en": "Complete"},
    "msg.import_ok":                {"zh": "成功导入 {count} 条记录", "en": "Import Files {count} Successfully"},
    "msg.export_ok":                {"zh": "成功导出到 {path}", "en": "Export Files {path} Successfully"},

    # ======== PartDialog ========
    "part.add_title":               {"zh": "添加材料", "en": "Add Material"},
    "part.edit_title":              {"zh": "编辑材料", "en": "Edit Material"},
    "part.allowable":               {"zh": "许用应力", "en": "Allowable Stress"},
    "part.safety_factor":           {"zh": "安全系数", "en": "Safety Factor"},
    "part.effective":               {"zh": "有效值 (÷SF)", "en": "Effective (÷SF)"},
    "part.unit":                    {"zh": "单位", "en": "Unit"},
    "part.name":                    {"zh": "名称", "en": "Name"},
    "part.notes":                   {"zh": "备注", "en": "Notes"},

    # ======== ContourOptionDialog ========
    "contour.title":                {"zh": "云图与热点设置", "en": "Contour & Hotspot Settings"},
    "contour.settings":             {"zh": "云图设置", "en": "Contour Settings"},
    "contour.category":             {"zh": "分类:", "en": "Category:"},
    "contour.data_type":            {"zh": "数据类型:", "en": "Data Type:"},
    "contour.component":            {"zh": "分量:", "en": "Component:"},
    "contour.hotspot":              {"zh": "热点分析", "en": "Hotspot Analysis"},
    "contour.prev":                 {"zh": "< 上一个", "en": "< Previous"},
    "contour.find":                 {"zh": "查找热点", "en": "Find Hotspot"},
    "contour.next":                 {"zh": "下一个 >", "en": "Next >"},
    "contour.apply_first":          {"zh": "请先应用云图以解锁", "en": "Apply contour first to unlock"},
    "contour.click_find":           {"zh": "点击 查找热点 开始", "en": "Click Find Hotspot to start"},
    "contour.viewmode":             {"zh": "视图模式:", "en": "View Mode:"},
    "contour.option":               {"zh": "选项:", "en": "Option:"},
    "contour.change_view":          {"zh": "切换视图", "en": "Change View"},
    "contour.capture":              {"zh": "截图", "en": "Capture"},
    "contour.unlock":               {"zh": "解锁", "en": "Unlock"},
    "contour.finding":              {"zh": "正在应用云图并查找 {name}...", "en": "Applying contour & finding {name}..."},
    "contour.found":                {"zh": "{name} 已找到。可导航或继续查找。", "en": "{name} found. Navigate or find more."},
    "contour.failed":               {"zh": "{name} 查找失败，请重试。", "en": "{name} failed. Try again."},

    # ======== ReadMaxValueDialog ========
    "rmv.title":                    {"zh": "读取最大值", "en": "Read Max Value"},
    "rmv.peak_result":              {"zh": "峰值结果", "en": "Peak Value Result"},
    "rmv.peak_stress":              {"zh": "峰值应力:", "en": "Peak Stress:"},
    "rmv.entity_id":                {"zh": "单元号:", "en": "Entity ID:"},
    "rmv.add_mapping":              {"zh": "添加到映射", "en": "Add to Mapping"},
    "rmv.material":                 {"zh": "材料:", "en": "Material:"},
    "rmv.max_value":                {"zh": "最大值:", "en": "Max Value:"},
    "rmv.max_hint":                 {"zh": "(云图最大值)", "en": "(contour max value)"},
    "rmv.read":                     {"zh": "读取", "en": "Read"},
    "rmv.add_result":               {"zh": "添加结果", "en": "Add Result"},
    "rmv.status_init":              {"zh": "配置云图设置后点击 读取。", "en": "Configure contour settings and click Read."},
    "rmv.step1":                    {"zh": "步骤 1/3 — 绘制云图…", "en": "Step 1/3 — Plotting contour…"},
    "rmv.step2":                    {"zh": "步骤 2/3 — 查找热点…", "en": "Step 2/3 — Finding hotspot…"},
    "rmv.step3":                    {"zh": "步骤 3/3 — 导出 CSV…", "en": "Step 3/3 — Exporting CSV…"},
    "rmv.parsing":                  {"zh": "正在解析结果…", "en": "Parsing results…"},
    "rmv.no_parse":                 {"zh": "CSV 已导出但无法解析最大值。", "en": "CSV exported but could not parse max value."},
    "rmv.done":                     {"zh": "完成。选择材料并点击 添加结果。", "en": "Done. Select material and click Add Result."},
    "rmv.no_orch":                  {"zh": "Orchestrator 不可用。", "en": "Orchestrator not available."},
    "rmv.step1_fail":               {"zh": "步骤 1 失败 — 云图绘制错误。", "en": "Step 1 failed — contour plot error."},
    "rmv.step2_fail":               {"zh": "步骤 2 失败 — 热点查找错误。", "en": "Step 2 failed — hotspot find error."},
    "rmv.step3_fail":               {"zh": "步骤 3 失败 — CSV 导出错误，请查看日志。", "en": "Step 3 failed — CSV export error. Check Logs."},
    "rmv.no_peak":                  {"zh": "没有可用的峰值，请先点击 读取。", "en": "No peak value available. Click Read first."},
    "rmv.select_mat":               {"zh": "请先选择材料标准。", "en": "Select a material standard first."},
    "rmv.empty_max":                {"zh": "最大值为空，请先点击 读取。", "en": "Max Value is empty. Click Read first."},

    # ======== CompareOptionDialog ========
    "cmp.title":                    {"zh": "与材料标准对比", "en": "Compare with Material Standards"},
    "cmp.standards":                {"zh": "标准概览", "en": "Standards Overview"},
    "cmp.results":                  {"zh": "结果", "en": "Results"},
    "cmp.analysis_result":          {"zh": "分析结果", "en": "Analysis Result"},
    "cmp.run_analysis":             {"zh": "运行分析", "en": "Run Analysis"},
    "cmp.read_max":                 {"zh": "读取最大值", "en": "Read Max Value"},
    "cmp.select_std":               {"zh": "请先选择一条标准", "en": "Select a standard first"},
    "cmp.confirm_del":              {"zh": "删除所选标准？此操作不可撤消。", "en": "Delete selected standard? This cannot be undone."},
    "cmp.imported":                 {"zh": "成功导入 {count} 条记录", "en": "Imported {count} parts successfully"},
    "cmp.exported":                 {"zh": "成功导出到 {path}", "en": "Exported to {path} successfully"},
    "cmp.add_hint":                 {"zh": "  请先在上方添加材料标准，然后点击 运行分析。",
                                     "en": "  Add material standards above, then click Run Analysis."},
    "cmp.no_results":               {"zh": "没有结果可分析。\n请先使用 '读取最大值'。",
                                     "en": "No results to analyze.\nUse 'Read Max Value' first."},

    # CompareOptionDialog - 列标题
    "cmp.col_id":                   {"zh": "编号", "en": "ID"},
    "cmp.col_name":                 {"zh": "名称", "en": "Name"},
    "cmp.col_allow":                {"zh": "许用值", "en": "Allowable"},
    "cmp.col_sf":                   {"zh": "安全系数", "en": "SF"},
    "cmp.col_eff":                  {"zh": "有效值 (÷SF)", "en": "Effective (÷SF)"},
    "cmp.col_unit":                 {"zh": "单位", "en": "Unit"},
    "cmp.col_result_no":            {"zh": "结果编号", "en": "Result No."},
    "cmp.col_material":             {"zh": "材料", "en": "Material"},
    "cmp.col_value":                {"zh": "结果值", "en": "Value"},

    # ======== AnalysisDialog ========
    "ana.title":                    {"zh": "分析选项", "en": "Analysis Options"},
    "ana.model_info":               {"zh": "模型信息", "en": "Model Information"},
    "ana.select_items":             {"zh": "选择分析项", "en": "Select Analysis Items"},
    "ana.plot_contour":             {"zh": "绘制云图", "en": "Plot Contour"},
    "ana.option":                   {"zh": "选项", "en": "Option"},
    "ana.contour_desc":             {"zh": "    在模型上绘制云图并查找应力热点",
                                     "en": "    Plot contour on the model and find stress hotspots"},
    "ana.compare":                  {"zh": "与材料标准对比", "en": "Compare with Material Standards"},
    "ana.compare_desc":             {"zh": "    将峰值应力与数据库中的许用值进行比较",
                                     "en": "    Compare peak stress with allowable values from database"},
    "ana.create_report":            {"zh": "创建报告", "en": "Create Report"},
    "ana.export":                   {"zh": "导出", "en": "Export"},
    "ana.insert":                   {"zh": "插入", "en": "Insert"},

    # AnalysisDialog - 状态
    "ana.step1_click":              {"zh": "步骤 1: 点击 创建报告", "en": "Step 1: Click Create Report"},
    "ana.step1_creating":           {"zh": "步骤 1: 正在创建报告...", "en": "Step 1: Creating report..."},
    "ana.report_created":           {"zh": "报告已创建，等待 HyperView...", "en": "Report created. Waiting for HyperView..."},
    "ana.step2":                    {"zh": "步骤 2: 勾选项目并点击 选项 进行配置，然后步骤 3: 导出 PPT",
                                     "en": "Step 2: Tick items and click Option to configure, then Step 3: Export PPT"},
    "ana.compare_done":             {"zh": "对比完成。可继续操作或导出。", "en": "Compare done. Continue or Export to finish."},
    "ana.exporting":                {"zh": "正在导出报告...", "en": "Exporting report..."},
    "ana.all_done":                 {"zh": "全部完成！报告已导出。", "en": "All done! Report exported."},

    # AnalysisDialog - Insert
    "ana.select_files":             {"zh": "选择要插入的文件", "en": "Select files to insert"},
    "ana.select_pptx":              {"zh": "选择 PowerPoint 文件", "en": "Select PowerPoint file"},
    "ana.inserting":                {"zh": "正在插入文件到 PPT...", "en": "Inserting files into PPT..."},
    "ana.inserted":                 {"zh": "已插入 {n} 页到 {file}", "en": "Inserted {n} slide(s) into {file}"},
    "ana.insert_failed":            {"zh": "插入失败", "en": "Insert Failed"},

    # AnalysisDialog - Report Summary
    "ana.summary":                  {"zh": "=== 分析摘要 ===", "en": "=== Analysis Summary ==="},
    "ana.ppt_exported":             {"zh": "PPT 报告已通过 HyperView 导出", "en": "PPT Report exported via HyperView"},

    # PNG Export
    "png.export_failed":            {"zh": "PNG 导出失败", "en": "PNG Export Failed"},
}


def t(key: str, **kwargs) -> str:
    """获取当前语言对应的翻译文本。支持 format 参数。"""
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(_current_lang, entry.get("en", key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


def get_lang() -> str:
    return _current_lang


def set_lang(lang: str):
    """切换语言并触发所有已注册的刷新回调。"""
    global _current_lang
    if lang == _current_lang:
        return
    _current_lang = lang
    # 清理已销毁的回调，然后触发存活的
    alive = []
    for cb in _callbacks:
        try:
            cb()
            alive.append(cb)
        except Exception:
            pass
    _callbacks.clear()
    _callbacks.extend(alive)


def on_lang_change(callback):
    """注册语言变更回调。回调在 set_lang() 时自动触发。"""
    if callback not in _callbacks:
        _callbacks.append(callback)


def remove_lang_callback(callback):
    """移除回调（窗口关闭时调用）。"""
    if callback in _callbacks:
        _callbacks.remove(callback)
