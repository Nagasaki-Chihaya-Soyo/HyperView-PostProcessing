"""
Internationalization (i18n) module for HyperView Post-Processing Tools.

Supports hot-switching between Chinese (zh) and English (en) at runtime.
All UI strings are registered via ``t(key)`` which returns the current
translation.  Widgets that need live updates register themselves with
``register(widget, key, attr)`` and are refreshed automatically when the
language changes.
"""

import tkinter as tk
from typing import Dict, List, Tuple, Any, Optional

# ---------------------------------------------------------------------------
# Translation dictionaries
# ---------------------------------------------------------------------------

_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # ── Main window ──
    "app.title":                    {"zh": "HyperView \u540e\u5904\u7406\u5de5\u5177", "en": "HyperView Post-Processing Tools"},
    "status.hv_now":                {"zh": "HyperView \u72b6\u6001:", "en": "HyperView Now:"},
    "status.disconnected":          {"zh": "\u672a\u8fde\u63a5", "en": "Disconnected"},
    "status.starting":              {"zh": "\u542f\u52a8\u4e2d...", "en": "Starting..."},
    "status.ready":                 {"zh": "\u5c31\u7eea", "en": "Ready"},
    "status.running":               {"zh": "\u8fd0\u884c\u4e2d...", "en": "Running..."},
    "status.failed":                {"zh": "\u5931\u8d25", "en": "Failed"},
    "status.exited":                {"zh": "\u5df2\u9000\u51fa", "en": "Exit"},
    "status.unknown":               {"zh": "\u672a\u77e5", "en": "Unknown"},
    "btn.start_hv":                 {"zh": "\u542f\u52a8 HyperView", "en": "Starting HyperView"},
    "label.agent":                  {"zh": "Agent:", "en": "Agent:"},

    # ── Tabs ──
    "tab.run":                      {"zh": "\u8fd0\u884c\u5e94\u7528", "en": "Run Application"},
    "tab.parts":                    {"zh": "\u6807\u51c6\u5e93", "en": "Standard Repository"},
    "tab.logs":                     {"zh": "\u65e5\u5fd7", "en": "Logs"},

    # ── Run tab ──
    "frame.select_files":           {"zh": "\u9009\u62e9\u6587\u4ef6", "en": "Select Files"},
    "label.model_files":            {"zh": "\u6a21\u578b\u6587\u4ef6:", "en": "Model Files:"},
    "label.result_files":           {"zh": "\u7ed3\u679c\u6587\u4ef6:", "en": "Result Files:"},
    "btn.view":                     {"zh": "\u6d4f\u89c8...", "en": "View..."},
    "btn.load_model":               {"zh": "\u52a0\u8f7d\u6a21\u578b", "en": "Load Model"},
    "btn.analysing":                {"zh": "\u5206\u6790", "en": "Analysing"},
    "chk.auto_minimize":            {"zh": "\u81ea\u52a8\u6700\u5c0f\u5316", "en": "Auto Minimize"},
    "frame.analysis_result":        {"zh": "\u5206\u6790\u7ed3\u679c", "en": "Analysing Result"},
    "btn.open_result_folder":       {"zh": "\u6253\u5f00\u7ed3\u679c\u6587\u4ef6\u5939", "en": "Open Result File Folder"},

    # ── Parts tab ──
    "btn.add":                      {"zh": "\u6dfb\u52a0", "en": "Add"},
    "btn.edit":                     {"zh": "\u7f16\u8f91", "en": "Edit"},
    "btn.delete":                   {"zh": "\u5220\u9664", "en": "Delete"},
    "btn.import_csv":               {"zh": "\u5bfc\u5165 CSV", "en": "Import CSV"},
    "btn.export_csv":               {"zh": "\u5bfc\u51fa CSV", "en": "Export CSV"},
    "label.search":                 {"zh": "\u641c\u7d22:", "en": "Search:"},
    "btn.clear":                    {"zh": "\u6e05\u9664", "en": "Clear"},
    "col.part_no":                  {"zh": "\u96f6\u4ef6\u53f7", "en": "Parts ID"},
    "col.name":                     {"zh": "\u540d\u79f0", "en": "Name"},
    "col.allowable_vm":             {"zh": "\u8bb8\u7528\u5e94\u529b", "en": "Allowable Stress"},
    "col.safety_factor":            {"zh": "\u5b89\u5168\u7cfb\u6570", "en": "Safety Factor"},
    "col.effective":                {"zh": "\u6709\u6548\u503c (\u00f7SF)", "en": "Effective (\u00f7SF)"},
    "col.units":                    {"zh": "\u5355\u4f4d", "en": "Unit"},
    "col.notes":                    {"zh": "\u5907\u6ce8", "en": "Notes"},
    "label.drag_hint":              {"zh": "  |  \u62d6\u62fd\u884c\u6765\u91cd\u65b0\u6392\u5e8f", "en": "  |  Drag rows to reorder"},

    # ── Log tab ──
    "btn.clear_logs":               {"zh": "\u6e05\u9664\u65e5\u5fd7", "en": "Clear Logs"},

    # ── PartDialog ──
    "dialog.add_material":          {"zh": "\u6dfb\u52a0\u6750\u6599", "en": "Add Material"},
    "dialog.edit_material":         {"zh": "\u7f16\u8f91\u6750\u6599", "en": "Edit Material"},
    "label.allowable_stress":       {"zh": "\u8bb8\u7528\u5e94\u529b", "en": "Allowable Stress"},
    "label.safety_factor":          {"zh": "\u5b89\u5168\u7cfb\u6570", "en": "Safety Factor"},
    "label.effective_sf":           {"zh": "\u6709\u6548\u503c (\u00f7SF)", "en": "Effective (\u00f7SF)"},
    "label.unit":                   {"zh": "\u5355\u4f4d", "en": "Unit"},
    "label.name":                   {"zh": "\u540d\u79f0", "en": "Name"},
    "label.notes":                  {"zh": "\u5907\u6ce8", "en": "Notes"},
    "btn.confirm":                  {"zh": "\u786e\u8ba4", "en": "Confirm"},
    "btn.cancel":                   {"zh": "\u53d6\u6d88", "en": "Cancel"},

    # ── ContourOptionDialog ──
    "dialog.contour_settings":      {"zh": "\u4e91\u56fe\u53c2\u6570\u8bbe\u7f6e", "en": "Contour & Hotspot Settings"},
    "frame.contour_settings":       {"zh": "\u4e91\u56fe\u8bbe\u7f6e", "en": "Contour Settings"},
    "label.category":               {"zh": "\u7c7b\u522b:", "en": "Category:"},
    "label.data_type":              {"zh": "\u6570\u636e\u7c7b\u578b:", "en": "Data Type:"},
    "label.component":              {"zh": "\u5206\u91cf:", "en": "Component:"},
    "btn.apply":                    {"zh": "\u5e94\u7528", "en": "Apply"},
    "frame.hotspot":                {"zh": "Hotspot \u5206\u6790", "en": "Hotspot Analysis"},
    "btn.prev":                     {"zh": "< \u4e0a\u4e00\u4e2a", "en": "< Previous"},
    "btn.find_hotspot":             {"zh": "\u67e5\u627e Hotspot", "en": "Find Hotspot"},
    "btn.next":                     {"zh": "\u4e0b\u4e00\u4e2a >", "en": "Next >"},
    "hint.apply_first":             {"zh": "\u5148\u5e94\u7528\u4e91\u56fe\u4ee5\u89e3\u9501", "en": "Apply contour first to unlock"},
    "hint.click_find":              {"zh": "\u70b9\u51fb\u67e5\u627e Hotspot \u5f00\u59cb", "en": "Click Find Hotspot to start"},
    "label.view_mode":              {"zh": "\u89c6\u56fe\u6a21\u5f0f:", "en": "View Mode:"},
    "btn.change_view":              {"zh": "\u5207\u6362\u89c6\u56fe", "en": "Change View"},
    "btn.capture":                  {"zh": "\u6355\u83b7", "en": "Capture"},
    "btn.unlock":                   {"zh": "\u89e3\u9501", "en": "Unlock"},

    # ── ReadMaxValueDialog ──
    "dialog.read_max":              {"zh": "\u8bfb\u53d6\u6700\u5927\u503c", "en": "Read Max Value"},
    "btn.read":                     {"zh": "\u8bfb\u53d6", "en": "Read"},
    "hint.configure_read":          {"zh": "\u914d\u7f6e\u4e91\u56fe\u8bbe\u7f6e\u5e76\u70b9\u51fb\u8bfb\u53d6\u3002", "en": "Configure contour settings and click Read."},
    "frame.peak_result":            {"zh": "\u5cf0\u503c\u7ed3\u679c", "en": "Peak Value Result"},
    "label.peak_stress":            {"zh": "\u5cf0\u503c\u5e94\u529b:", "en": "Peak Stress:"},
    "label.entity_id":              {"zh": "\u5b9e\u4f53 ID:", "en": "Entity ID:"},
    "frame.add_mapping":            {"zh": "\u6dfb\u52a0\u5230\u6620\u5c04", "en": "Add to Mapping"},
    "label.material":               {"zh": "\u6750\u6599:", "en": "Material:"},
    "label.max_value":              {"zh": "\u6700\u5927\u503c:", "en": "Max Value:"},
    "hint.contour_max":             {"zh": "(\u4e91\u56fe\u6700\u5927\u503c)", "en": "(contour max value)"},
    "btn.add_result":               {"zh": "\u6dfb\u52a0\u7ed3\u679c", "en": "Add Result"},
    "btn.close":                    {"zh": "\u5173\u95ed", "en": "Close"},
    "hint.done_select":             {"zh": "\u5b8c\u6210\u3002\u9009\u62e9\u6750\u6599\u5e76\u70b9\u51fb\u6dfb\u52a0\u7ed3\u679c\u3002", "en": "Done. Select material and click Add Result."},
    "hint.result_added":            {"zh": "\u7ed3\u679c\u5df2\u6dfb\u52a0\u3002\u70b9\u51fb\u8bfb\u53d6\u83b7\u53d6\u4e0b\u4e00\u4e2a\u503c\u3002", "en": "Result added. Click Read for the next value."},

    # ── CompareOptionDialog ──
    "dialog.compare":               {"zh": "\u4e0e\u6750\u6599\u6807\u51c6\u6bd4\u8f83", "en": "Compare with Material Standards"},
    "frame.standards":              {"zh": "\u6807\u51c6\u6982\u89c8", "en": "Standards Overview"},
    "col.id":                       {"zh": "ID", "en": "ID"},
    "col.allowable":                {"zh": "\u8bb8\u7528\u503c", "en": "Allowable"},
    "col.sf":                       {"zh": "SF", "en": "SF"},
    "frame.results":                {"zh": "\u7ed3\u679c", "en": "Results"},
    "col.res_no":                   {"zh": "\u7ed3\u679c\u7f16\u53f7", "en": "Result No."},
    "col.res_material":             {"zh": "\u6750\u6599", "en": "Material"},
    "col.res_value":                {"zh": "\u7ed3\u679c\u503c", "en": "Result Value"},
    "col.res_unit":                 {"zh": "\u5355\u4f4d", "en": "Unit"},
    "frame.analysis_result_box":    {"zh": "\u5206\u6790\u7ed3\u679c", "en": "Analysis Result"},
    "btn.run_analysis":             {"zh": "\u8fd0\u884c\u5206\u6790", "en": "Run Analysis"},
    "btn.read_max_value":           {"zh": "\u8bfb\u53d6\u6700\u5927\u503c", "en": "Read Max Value"},
    "hint.add_standards":           {"zh": "  \u5148\u6dfb\u52a0\u6750\u6599\u6807\u51c6\uff0c\u518d\u70b9\u51fb\u8fd0\u884c\u5206\u6790\u3002", "en": "  Add material standards above, then click Run Analysis."},
    "hint.no_results":              {"zh": "\u6ca1\u6709\u7ed3\u679c\u53ef\u5206\u6790\u3002\n\u8bf7\u5148\u4f7f\u7528\u201c\u8bfb\u53d6\u6700\u5927\u503c\u201d\u3002", "en": "No results to analyze.\nUse 'Read Max Value' first."},
    "pct.exceed":                   {"zh": "\u8d85\u51fa", "en": "Exceed"},
    "pct.under":                    {"zh": "\u4e0d\u8db3", "en": "Under"},

    # ── AnalysisDialog ──
    "dialog.analysis_options":      {"zh": "\u5206\u6790\u9009\u9879", "en": "Analysis Options"},
    "frame.model_info":             {"zh": "\u6a21\u578b\u4fe1\u606f", "en": "Model Information"},
    "frame.select_items":           {"zh": "\u9009\u62e9\u5206\u6790\u9879", "en": "Select Analysis Items"},
    "chk.plot_contour":             {"zh": "\u7ed8\u5236\u4e91\u56fe", "en": "Plot Contour"},
    "hint.plot_contour":            {"zh": "    \u5728\u6a21\u578b\u4e0a\u7ed8\u5236\u4e91\u56fe\u5e76\u67e5\u627e\u5e94\u529b\u70ed\u70b9", "en": "    Plot contour on the model and find stress hotspots"},
    "chk.compare":                  {"zh": "\u4e0e\u6750\u6599\u6807\u51c6\u6bd4\u8f83", "en": "Compare with Material Standards"},
    "hint.compare":                 {"zh": "    \u5c06\u5cf0\u503c\u5e94\u529b\u4e0e\u6570\u636e\u5e93\u4e2d\u7684\u8bb8\u7528\u503c\u6bd4\u8f83", "en": "    Compare peak stress with allowable values from database"},
    "label.option":                 {"zh": "\u9009\u9879", "en": "Option"},
    "btn.export":                   {"zh": "\u5bfc\u51fa", "en": "Export"},
    "btn.create_report":            {"zh": "\u521b\u5efa\u62a5\u544a", "en": "Create Report"},
    "status.step1":                 {"zh": "\u6b65\u9aa41: \u70b9\u51fb\u521b\u5efa\u62a5\u544a", "en": "Step 1: Click Create Report"},
    "status.step1_creating":        {"zh": "\u6b65\u9aa41: \u6b63\u5728\u521b\u5efa\u62a5\u544a...", "en": "Step 1: Creating report..."},
    "status.waiting_hv":            {"zh": "\u62a5\u544a\u5df2\u521b\u5efa\u3002\u7b49\u5f85 HyperView...", "en": "Report created. Waiting for HyperView..."},
    "status.step2":                 {"zh": "\u6b65\u9aa42: \u52fe\u9009\u9879\u76ee\u5e76\u70b9\u51fb\u9009\u9879\u914d\u7f6e\uff0c\u7136\u540e\u6b65\u9aa43: \u5bfc\u51fa PPT", "en": "Step 2: Tick items and click Option to configure, then Step 3: Export PPT"},
    "status.exporting":             {"zh": "\u6b63\u5728\u5bfc\u51fa\u62a5\u544a...", "en": "Exporting report..."},
    "status.all_done":              {"zh": "\u5168\u90e8\u5b8c\u6210\uff01\u62a5\u544a\u5df2\u5bfc\u51fa\u3002", "en": "All done! Report exported."},

    # ── Messages ──
    "msg.select_model":             {"zh": "\u8bf7\u5148\u9009\u62e9\u6a21\u578b\u6587\u4ef6", "en": "Select a model file first"},
    "msg.hv_start_fail":            {"zh": "HyperView \u542f\u52a8\u5931\u8d25", "en": "HyperView Failed to Start"},
    "msg.load_fail":                {"zh": "\u52a0\u8f7d\u6a21\u578b\u5931\u8d25\u3002\u8bf7\u67e5\u770b\u65e5\u5fd7\u3002", "en": "Failed to load model. Check log for details."},
    "msg.select_part":              {"zh": "\u8bf7\u5148\u9009\u62e9\u4e00\u4e2a\u96f6\u4ef6", "en": "SELECT A PART FIRST"},
    "msg.confirm_delete":           {"zh": "\u786e\u5b9a\u8981\u5220\u9664\u9009\u4e2d\u7684\u96f6\u4ef6\u5417\uff1f\u6b64\u64cd\u4f5c\u4e0d\u53ef\u64a4\u9500", "en": "Are you sure you want to delete the selected parts?This action can not be undone"},
    "msg.import_ok":                {"zh": "\u5bfc\u5165\u6587\u4ef6 {count} \u6761\u6210\u529f", "en": "Import Files {count} Successfully"},
    "msg.export_ok":                {"zh": "\u5bfc\u51fa\u6587\u4ef6 {path} \u6210\u529f", "en": "Export Files {path} Successfully"},
    "msg.select_standard":          {"zh": "\u8bf7\u5148\u9009\u62e9\u4e00\u4e2a\u6807\u51c6", "en": "Select a standard first"},
    "msg.confirm_delete_std":       {"zh": "\u5220\u9664\u6240\u9009\u6807\u51c6\uff1f\u6b64\u64cd\u4f5c\u4e0d\u53ef\u64a4\u9500\u3002", "en": "Delete selected standard? This cannot be undone."},
    "msg.imported_parts":           {"zh": "\u6210\u529f\u5bfc\u5165 {count} \u6761\u8bb0\u5f55", "en": "Imported {count} parts successfully"},
    "msg.exported_to":              {"zh": "\u5df2\u5bfc\u51fa\u5230 {path}", "en": "Exported to {path} successfully"},
    "msg.no_peak":                  {"zh": "\u6ca1\u6709\u5cf0\u503c\u3002\u8bf7\u5148\u70b9\u51fb\u8bfb\u53d6\u3002", "en": "No peak value available. Click Read first."},
    "msg.select_material":          {"zh": "\u8bf7\u5148\u9009\u62e9\u6750\u6599\u6807\u51c6\u3002", "en": "Select a material standard first."},
    "msg.max_empty":                {"zh": "\u6700\u5927\u503c\u4e3a\u7a7a\u3002\u8bf7\u5148\u70b9\u51fb\u8bfb\u53d6\u3002", "en": "Max Value is empty. Click Read first."},

    # ── File dialog titles ──
    "dlg.select_model":             {"zh": "\u9009\u62e9\u6a21\u578b\u6587\u4ef6", "en": "Select Model Files"},
    "dlg.select_result":            {"zh": "\u9009\u62e9\u7ed3\u679c\u6587\u4ef6", "en": "Select ResultFiles"},
    "dlg.select_csv":               {"zh": "\u9009\u62e9 CSV \u6587\u4ef6", "en": "Select CSV Files"},
    "dlg.save_csv":                 {"zh": "\u4fdd\u5b58 CSV \u6587\u4ef6", "en": "Save CSV Files"},

    # ── Report data (for PNG images) ──
    "rpt.title":                    {"zh": "\u5206\u6790\u7ed3\u679c", "en": "Analysis Result"},
    "rpt.no":                       {"zh": "\u7f16\u53f7", "en": "No."},
    "rpt.material_name":            {"zh": "\u6750\u6599\u540d\u79f0", "en": "Material Name"},
    "rpt.allowable":                {"zh": "\u8bb8\u7528\u503c", "en": "Allowable"},
    "rpt.safety_factor":            {"zh": "\u5b89\u5168\u56e0\u5b50", "en": "Safety Factor"},
    "rpt.effective_allowable":      {"zh": "\u6709\u6548\u8bb8\u7528\u503c", "en": "Effective Allowable"},
    "rpt.actual":                   {"zh": "\u5b9e\u9645\u503c", "en": "Actual Value"},
    "rpt.diff":                     {"zh": "\u5dee\u503c", "en": "Difference"},
    "rpt.pct":                      {"zh": "\u8d85\u51fa/\u4e0d\u8db3\u5360\u6bd4", "en": "Exceed/Under %"},
    "rpt.status":                   {"zh": "\u72b6\u6001", "en": "Status"},
    "rpt.peak_compare":             {"zh": "\u5cf0\u503c\u4e0e\u6750\u6599\u8bb8\u7528\u503c\u6bd4\u8f83", "en": "Peak vs Material Allowable"},
    "rpt.peak":                     {"zh": "\u5cf0\u503c", "en": "Peak"},
    "rpt.compare_result":           {"zh": "\u6bd4\u8f83\u7ed3\u679c", "en": "Compare Result"},
    "rpt.exceeded":                 {"zh": "\u8d85\u51fa", "en": "Exceeded"},
    "rpt.not_exceeded":             {"zh": "\u672a\u8d85\u51fa", "en": "Not Exceeded"},

    # ── Language toggle ──
    "lang.toggle":                  {"zh": "EN", "en": "\u4e2d\u6587"},
}

# ---------------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------------

_current_lang: str = "en"

# Registry: list of (widget_ref, key, attr) where widget_ref is a weakref-like id
_registry: List[Tuple[Any, str, str]] = []


def current_language() -> str:
    """Return the current language code ('zh' or 'en')."""
    return _current_lang


def t(key: str, **kwargs) -> str:
    """Return the translated string for *key* in the current language.

    Extra ``kwargs`` are passed to ``str.format()`` for parameterised messages.
    """
    entry = _TRANSLATIONS.get(key)
    if entry is None:
        return key
    text = entry.get(_current_lang, entry.get("en", key))
    if kwargs:
        text = text.format(**kwargs)
    return text


def register(widget, key: str, attr: str = "text", **kwargs):
    """Register *widget* so its *attr* is updated when the language changes.

    ``attr`` can be ``"text"`` (default), ``"title"``, or any config key.
    Extra ``kwargs`` are stored and forwarded to ``t()`` on each refresh.
    """
    _registry.append((widget, key, attr, kwargs))


def _refresh_all():
    """Re-apply translations to every registered widget."""
    alive: List[Tuple[Any, str, str]] = []
    for entry in _registry:
        widget, key, attr, kwargs = entry
        try:
            text = t(key, **kwargs)
            if attr == "title":
                widget.title(text)
            elif attr == "tab":
                # For notebook tabs: widget is (notebook, tab_id)
                notebook, tab_id = widget
                notebook.tab(tab_id, text=text)
            elif attr == "heading":
                # For treeview headings: widget is (treeview, col_name)
                tree, col = widget
                tree.heading(col, text=text)
            else:
                widget.config(**{attr: text})
            alive.append(entry)
        except (tk.TclError, Exception):
            # Widget was destroyed — skip
            pass
    _registry.clear()
    _registry.extend(alive)


def set_language(lang: str):
    """Switch the UI language and refresh all registered widgets.

    ``lang`` should be ``'zh'`` or ``'en'``.
    """
    global _current_lang
    if lang not in ("zh", "en"):
        return
    _current_lang = lang
    _refresh_all()


def toggle_language():
    """Toggle between Chinese and English."""
    new_lang = "en" if _current_lang == "zh" else "zh"
    set_language(new_lang)
