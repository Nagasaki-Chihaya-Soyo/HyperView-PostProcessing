import os
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import signal
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.orchestrator import Orchestrator, State
from core.db_store import DBStore


def _safe_float(value):
    """Return float(value) or None if conversion fails."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HyperView Post-Processing Tools")
        self.geometry("900x650")
        self.minsize(width=800, height=600)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.orchestrator = Orchestrator(base_dir)
        self.orchestrator.on_log = self._on_log
        self.orchestrator.on_state_change = self._on_state_change
        self.db = self.orchestrator.db
        self._create_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.current_report_path = None
        self._is_closing = False

    def _create_ui(self):
        style = ttk.Style()
        style.configure('Treeview',
                        rowheight=28,
                        font=('TkDefaultFont', 9),
                        fieldbackground='#ffffff')
        style.configure('Treeview.Heading',
                        font=('TkDefaultFont', 9),
                        relief='raised',
                        padding=(0, 5))
        style.map('Treeview.Heading',
                  background=[('active', '#e2e8f0'), ('!active', '#e2e8f0')],
                  foreground=[('active', '#000000'), ('!active', '#000000')])
        self._create_status_bar()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self._create_run_tab()
        self._create_parts_tab()
        self._create_log_tab()

    def _create_status_bar(self):
        frame = ttk.Frame(self)
        frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(frame, text="HyperView Now:").pack(side=tk.LEFT)
        self.status_label = ttk.Label(frame, text="Disconnected", foreground="gray")
        self.status_label.pack(side=tk.LEFT, padx=5)
        self.connect_btn = ttk.Button(frame, text="Starting HyperView", command=self._start_hv)
        self.connect_btn.pack(side=tk.RIGHT)

    def _create_run_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Run Application")
        file_frame = ttk.LabelFrame(tab, text="Select Files", padding=10)
        file_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(file_frame, text="Model Files:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.model_entry = ttk.Entry(file_frame, width=60)
        self.model_entry.grid(row=0, column=1, padx=5, pady=5)
        self.model_view_btn = ttk.Button(file_frame, text="View...", command=self._browse_model, state=tk.DISABLED)
        self.model_view_btn.grid(row=0, column=2, pady=5)

        ttk.Label(file_frame, text="Result Files:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.result_entry = ttk.Entry(file_frame, width=60)
        self.result_entry.grid(row=1, column=1, padx=5, pady=5)
        self.result_view_btn = ttk.Button(file_frame, text="View...", command=self._browse_result, state=tk.DISABLED)
        self.result_view_btn.grid(row=1, column=2, pady=5)

        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        self.load_btn = ttk.Button(btn_frame, text="Load Model", padding=10, command=self._load_model, state=tk.DISABLED)
        self.load_btn.pack(side=tk.LEFT, padx=10)

        self.run_btn = ttk.Button(btn_frame, text="Analysing", padding=10, command=self._run_analysis, state=tk.DISABLED)
        self.run_btn.pack(side=tk.LEFT, padx=20)

        self.progress = ttk.Progressbar(btn_frame, mode='determinate', length=200, maximum=100)
        self.progress.pack(side=tk.LEFT, padx=20)
        self._progress_running = False

        # 自动最小化选项
        self.auto_minimize_var = tk.BooleanVar(value=True)
        self.auto_minimize_cb = ttk.Checkbutton(
            btn_frame,
            text="Auto Minimize",
            variable=self.auto_minimize_var
        )
        self.auto_minimize_cb.pack(side=tk.LEFT, padx=20)

        result_frame = ttk.LabelFrame(tab, text="Analysing Result", padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.result_text = tk.Text(result_frame, height=15, state=tk.DISABLED)
        self.result_text.pack(fill=tk.BOTH, expand=True)

        self.report_btn = ttk.Button(result_frame, text="Open Report Files", state=tk.DISABLED, command=self._open_report)
        self.report_btn.pack(pady=10)

    def _browse_model(self):
        filetypes = [("Model Files", "*.h3d"),
                     ("HyperMesh Files", "*.h3m"),
                     ("FEM Files", "*.fem;*.bdf;*.nas"),
                     ("LS-DYNA Files", "*.k;*.key;*.d3plot"),
                     ("Nastran Results", "*.op2;*.pch"),
                     ("ANSYS Results", "*.rst"),
                     ("All Files", "*.*")
        ]
        path = filedialog.askopenfilename(title="Select Model Files", filetypes=filetypes)
        if path:
            self.model_entry.delete(0, tk.END)
            self.model_entry.insert(0, path)
            # Sequential unlock: enable Result View and Load Model after model path is set
            self.result_view_btn.config(state=tk.NORMAL)
            self.load_btn.config(state=tk.NORMAL)
            # Default result path to match model path
            self.result_entry.delete(0, tk.END)
            self.result_entry.insert(0, path)
            # Reset Analysing button since model changed, needs reload
            self.run_btn.config(state=tk.DISABLED)

    def _browse_result(self):
        filetypes = [
            ("H3D Results", "*.h3d"),
            ("Nastran Results", "*.op2;*.pch"),
            ("LS-DYNA Files", "*.d3plot"),
            ("ANSYS Results", "*.rst"),
            ("All Files", "*.*")
        ]
        path = filedialog.askopenfilename(title="Select ResultFiles", filetypes=filetypes)
        if path:
            self.result_entry.delete(0, tk.END)
            self.result_entry.insert(0, path)

    def _run_analysis(self):
        model_path = self.model_entry.get().strip()
        result_path = self.result_entry.get().strip()
        if not model_path:
            messagebox.showwarning(title="WARNING", message="Select a model file first")
            return
        if self.auto_minimize_var.get():
            self.iconify()
        AnalysisDialog(self, self.orchestrator, model_path, result_path)
        self.deiconify()

    def _start_progress(self):
        """启动进度条动画"""
        self.progress['value'] = 0
        self._progress_running = True
        self._update_progress()

    def _update_progress(self):
        """更新进度条（模拟进度）"""
        if not self._progress_running:
            return
        current = self.progress['value']
        if current < 90:
            increment = max(1, (90 - current) / 20)
            self.progress['value'] = min(90, current + increment)
            self.after(200, self._update_progress)

    def _stop_progress(self, success=True):
        """停止进度条"""
        self._progress_running = False
        self.progress['value'] = 100 if success else 0

    def _load_model(self):
        model_path = self.model_entry.get().strip()
        result_path = self.result_entry.get().strip()
        if not model_path:
            messagebox.showwarning(title="WARNING", message="Select a model file first")
            return
        self.load_btn.config(state=tk.DISABLED)
        self._start_progress()

        def load():
            success = self.orchestrator.load_model(model_path, result_path)
            self.after(0, lambda: self._on_model_loaded(success))

        threading.Thread(target=load, daemon=True).start()

    def _on_model_loaded(self, success: bool):
        self._stop_progress(success)
        self.load_btn.config(state=tk.NORMAL)
        if success:
            self.run_btn.config(state=tk.NORMAL)
        else:
            messagebox.showerror(title="ERROR", message="Failed to load model. Check log for details.")


    def _show_result(self, result):
        self.progress.stop()
        self.run_btn.config(state=tk.NORMAL)

        self.result_text.config(state=tk.NORMAL)
        self.result_text.delete(1.0, tk.END)

        if result is None:
            self.result_text.insert(tk.END, "Analysis Failed.Check The Error Log for Details")
            self.report_btn.config(state=tk.DISABLED)
        else:
            analysis = result['analysis']
            status = "Analysis Passed" if analysis.passed else "failed"
            text = f"""\
Analysing Result:{status}

Peak Information:
    -Peak:{analysis.peak_value:.4f}
    -ComponentID:{analysis.peak_entity_id}

Deviation from Standard:
    -PartID:{analysis.part_no or 'Not Found'}
    -Allowable:{analysis.allowable:.2f if analysis.allowable else '-' } MPa
    -Margin:{analysis.margin:.2f if analysis.margin else '-'} MPa
    -Ratio:{analysis.ratio:.2% if analysis.ratio else '-'}

Conclusion:{analysis.message}

Report Path:{result['report_path']}
"""
            self.result_text.insert(tk.END, text)
            self.current_report_path = result['report_path']
            self.report_btn.config(state=tk.NORMAL)

        self.result_text.config(state=tk.DISABLED)

    def _open_report(self):
        if self.current_report_path and os.path.exists(self.current_report_path):
            webbrowser.open(f"file://{self.current_report_path}")

    def _create_parts_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Standard Repository")

        # ── Toolbar ──
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=tk.X, padx=10, pady=(8, 2))
        ttk.Button(toolbar, text="Add",    command=self._add_part).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Edit",   command=self._edit_part).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Delete", command=self._delete_part).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(toolbar, text="Import CSV", command=self._import_parts_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Export CSV", command=self._export_parts_csv).pack(side=tk.LEFT, padx=2)

        # ── Search / Filter bar ──
        search_frame = ttk.Frame(tab)
        search_frame.pack(fill=tk.X, padx=10, pady=(2, 4))
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        self._parts_search_var = tk.StringVar()
        self._parts_search_var.trace_add('write', lambda *_: self._refresh_parts())
        ttk.Entry(search_frame, textvariable=self._parts_search_var, width=30).pack(side=tk.LEFT, padx=5)
        ttk.Button(search_frame, text="Clear",
                   command=lambda: self._parts_search_var.set('')).pack(side=tk.LEFT)

        # ── Tree frame (Treeview + vertical scrollbar side by side) ──
        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 0))

        columns = ('part_no', 'name', 'allowable_vm', 'safety_factor', 'effective', 'units', 'notes')
        self.parts_tree = ttk.Treeview(tree_frame, columns=columns, show='headings',
                                       selectmode='browse')

        for col, text, w in [
            ('part_no',       'Parts ID',            80),
            ('name',          'Name',               160),
            ('allowable_vm',  'Allowable Stress',   130),
            ('safety_factor', 'Safety Factor',      100),
            ('effective',     'Effective (÷SF)',    120),
            ('units',         'Unit',                60),
            ('notes',         'Notes',              180),
        ]:
            self.parts_tree.heading(col, text=text, anchor='center')
            self.parts_tree.column(col, width=w, minwidth=50, anchor='center')

        self.parts_tree.tag_configure('odd',  background='#dbeafe', foreground='#1e3a5f')
        self.parts_tree.tag_configure('even', background='#ffffff', foreground='#1f2937')

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.parts_tree.yview)
        self.parts_tree.configure(yscrollcommand=scrollbar.set)
        self.parts_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Status bar ──
        status_frame = ttk.Frame(tab)
        status_frame.pack(fill=tk.X, padx=10, pady=(2, 6))
        self._parts_count_var = tk.StringVar(value="0 parts")
        ttk.Label(status_frame, textvariable=self._parts_count_var,
                  foreground='gray').pack(side=tk.LEFT)
        ttk.Label(status_frame, text="  |  Drag rows to reorder",
                  foreground='gray').pack(side=tk.LEFT)

        self._refresh_parts()

        self._drag_item = None
        self._drag_original_order = []
        self.parts_tree.bind('<ButtonPress-1>',   self._on_parts_drag_start)
        self.parts_tree.bind('<B1-Motion>',        self._on_parts_drag_motion)
        self.parts_tree.bind('<ButtonRelease-1>',  self._on_parts_drag_release)
        self.parts_tree.bind('<Double-1>',         lambda e: self._edit_part())

    def _refresh_parts(self):
        for item in self.parts_tree.get_children():
            self.parts_tree.delete(item)

        keyword = getattr(self, '_parts_search_var', None)
        keyword = keyword.get().strip().lower() if keyword else ''

        parts = self.db.get_all_parts()
        if keyword:
            parts = [p for p in parts if
                     keyword in str(p.get('part_no', '')).lower() or
                     keyword in str(p.get('name', '')).lower() or
                     keyword in str(p.get('notes', '')).lower()]

        for i, p in enumerate(parts):
            tag = 'odd' if i % 2 else 'even'
            try:
                eff = p['allowable_vm'] / p['safety_factor']
                eff_str = f"{eff:.2f}"
            except (TypeError, ZeroDivisionError):
                eff_str = '-'
            self.parts_tree.insert('', tk.END, values=(
                p['part_no'], p['name'], p['allowable_vm'], p['safety_factor'],
                eff_str, p['units'], p['notes']
            ), tags=(tag,))

        count = len(parts)
        total = len(self.db.get_all_parts())
        if keyword and count != total:
            label = f"{count} of {total} parts (filtered)"
        else:
            label = f"{total} part{'s' if total != 1 else ''}"
        if hasattr(self, '_parts_count_var'):
            self._parts_count_var.set(label)

    def _on_parts_drag_start(self, event):
        if self.parts_tree.identify_region(event.x, event.y) != 'cell':
            return
        item = self.parts_tree.identify_row(event.y)
        if item:
            self._drag_item = item
            self._drag_original_order = list(self.parts_tree.get_children())
            self.parts_tree.configure(cursor='hand2')

    def _on_parts_drag_motion(self, event):
        if not self._drag_item:
            return
        target = self.parts_tree.identify_row(event.y)
        if target and target != self._drag_item:
            self.parts_tree.move(self._drag_item, '', self.parts_tree.index(target))

    def _on_parts_drag_release(self, event):
        self.parts_tree.configure(cursor='')
        if not self._drag_item:
            return
        current_order = list(self.parts_tree.get_children())
        if current_order != self._drag_original_order:
            ordered_part_nos = [str(self.parts_tree.item(i)['values'][0]) for i in current_order]
            self.db.renumber_parts(ordered_part_nos)
            self._refresh_parts()
        self._drag_item = None
        self._drag_original_order = []

    def _add_part(self):
        dialog = PartDialog(self, title="Add Material")
        if dialog.result:
            self.db.add_part(part_no=self.db.get_next_part_no(), **dialog.result)
            self._refresh_parts()

    def _edit_part(self):
        selection = self.parts_tree.selection()
        if not selection:
            messagebox.showwarning(title="WARNING", message="SELECT A PART FIRST")
            return
        values = self.parts_tree.item(selection[0])['values']
        part_no = str(values[0])
        data = {
            'allowable_vm': values[1],
            'safety_factor': values[2],
            'units': values[3],
            'name': values[4],
            'notes': values[5]
        }
        dialog = PartDialog(self, title="Edit Material", data=data)
        if dialog.result:
            self.db.update_part(part_no=part_no, **dialog.result)
            self._refresh_parts()

    def _delete_part(self):
        selection = self.parts_tree.selection()
        if not selection:
            messagebox.showwarning(title="WARNING", message="SELECT A PART FIRST")
            return
        if messagebox.askyesno(title="Confirm", message="Are you sure you want to delete the selected parts?This action can not be undone"):
            for sel in selection:
                part_no = self.parts_tree.item(sel)['values'][0]
                self.db.delete_part(part_no)
            remaining = [p['part_no'] for p in self.db.get_all_parts()]
            if remaining:
                self.db.renumber_parts(remaining)
            self._refresh_parts()

    def _import_parts_csv(self):
        path = filedialog.askopenfilename(
            title="Select CSV Files",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if path:
            count = self.db.import_parts_csv(path)
            messagebox.showinfo(title="Complete", message=f"Import Files {count} Successfully")
            self._refresh_parts()

    def _export_parts_csv(self):
        path = filedialog.asksaveasfilename(
            title="Save CSV Files",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if path:
            self.db.export_parts_csv(path)
            messagebox.showinfo(title="Complete", message=f"Export Files {path} Successfully")

    def _create_log_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Logs")

        self.log_text = tk.Text(tab, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.tag_configure('error', foreground='red')
        self.log_text.tag_configure('success', foreground='green')
        self.log_text.tag_configure('info', foreground='blue')
        scrollbar = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=10)

        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_frame, text="Clear Logs", command=self._clear_log).pack(side=tk.RIGHT)

    def _clear_log(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _on_log(self, msg: str):
        self.log_text.config(state=tk.NORMAL)
        if 'ERROR' in msg or '失败' in msg or 'Fail' in msg:
            tag = 'error'
        elif 'Ready' in msg or '完成' in msg or 'Complete' in msg:
            tag = 'success'
        else:
            tag = 'info'
        self.log_text.insert(tk.END, f"{msg}\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _start_hv(self):
        self.connect_btn.config(state=tk.DISABLED)
        def start():
            success = self.orchestrator.start_hyperview()
            self.after(0, lambda: self._on_hv_started(success))
        threading.Thread(target=start, daemon=True).start()

    def _on_hv_started(self, success: bool):
        self.connect_btn.config(state=tk.NORMAL)
        if not success:
            messagebox.showerror(title="ERROR", message="HyperView Failed to Start")

    def _on_state_change(self, state: State):
        state_text = {
            State.IDLE: ("Disconnected", "gray"),
            State.STARTING: ("Starting...", "orange"),
            State.AGENT_READY: ("Ready", "green"),
            State.RUNNING: ("Running...", "blue"),
            State.FAILED: ("Failed", "red"),
            State.EXITED: ("Exit", "gray"),
        }
        text, color = state_text.get(state, ("Unknown", "gray"))
        self.status_label.config(text=text, foreground=color)

        # Sequential unlock: enable Model View button when HyperView is ready
        if state == State.AGENT_READY:
            self.model_view_btn.config(state=tk.NORMAL)
        elif state in (State.IDLE, State.FAILED, State.EXITED):
            # Reset all buttons to disabled when HyperView is not connected
            self.model_view_btn.config(state=tk.DISABLED)
            self.result_view_btn.config(state=tk.DISABLED)
            self.load_btn.config(state=tk.DISABLED)
            self.run_btn.config(state=tk.DISABLED)

    def _on_close(self):
        if self._is_closing:
            return
        self._is_closing = True
        try:
            self.orchestrator.shutdown()
        finally:
            self.destroy()


class PartDialog(tk.Toplevel):
    def __init__(self, parent, title, data=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("420x310")
        self.resizable(width=False, height=False)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self.data = data or {}
        self._create_ui()
        self.wait_window()

    def _create_ui(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Allowable Stress").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.allowable_entry = ttk.Entry(frame, width=30)
        self.allowable_entry.grid(row=0, column=1, pady=5)
        self.allowable_entry.insert(0, self.data.get('allowable_vm', ''))

        ttk.Label(frame, text="Safety Factor").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.safety_factor = ttk.Entry(frame, width=30)
        self.safety_factor.grid(row=1, column=1, pady=5)
        self.safety_factor.insert(0, self.data.get('safety_factor', '1.0'))

        # Live preview: Effective allowable = allowable / safety_factor
        self._effective_var = tk.StringVar(value='—')
        ttk.Label(frame, text="Effective (÷SF)").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Label(frame, textvariable=self._effective_var,
                  foreground='#1d6fa4', font=('TkDefaultFont', 9, 'bold')
                  ).grid(row=2, column=1, sticky=tk.W, pady=5, padx=4)

        ttk.Label(frame, text="Unit").grid(row=3, column=0, sticky=tk.W, pady=5)
        _UNITS = ['Pa', 'kPa', 'MPa', 'GPa', 'psi', 'ksi']
        self.units_cb = ttk.Combobox(frame, width=28, values=_UNITS, state='readonly')
        self.units_cb.grid(row=3, column=1, pady=5)
        current_unit = self.data.get('units', 'MPa')
        self.units_cb.set(current_unit if current_unit in _UNITS else 'MPa')

        ttk.Label(frame, text="Name").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.name_entry = ttk.Entry(frame, width=30)
        self.name_entry.grid(row=4, column=1, pady=5)
        self.name_entry.insert(0, self.data.get('name', ''))

        ttk.Label(frame, text="Notes").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.notes_entry = ttk.Entry(frame, width=30)
        self.notes_entry.grid(row=5, column=1, pady=5)
        self.notes_entry.insert(0, self.data.get('notes', ''))

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="Confirm", command=self._ok).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel",  command=self.destroy).pack(side=tk.LEFT, padx=10)

        # Wire up live preview
        self.allowable_entry.bind('<KeyRelease>', lambda e: self._update_effective())
        self.safety_factor.bind('<KeyRelease>',   lambda e: self._update_effective())
        self.units_cb.bind('<<ComboboxSelected>>', lambda e: self._update_effective())
        self._update_effective()

        self._bind_navigation()
        self.after(50, self.allowable_entry.focus_set)

    def _update_effective(self):
        try:
            a = float(self.allowable_entry.get())
            sf = float(self.safety_factor.get())
            if sf == 0:
                raise ZeroDivisionError
            unit = self.units_cb.get() or 'MPa'
            self._effective_var.set(f"{a / sf:.3f} {unit}")
        except (ValueError, ZeroDivisionError):
            self._effective_var.set('—')

    def _bind_navigation(self):
        fields = [
            self.allowable_entry,
            self.safety_factor,
            self.units_cb,
            self.name_entry,
            self.notes_entry,
        ]
        cb_idx = 2  # index of units_cb in fields

        # Entry widgets: Up/Down navigate fields, Enter confirms
        for idx, widget in [(0, self.allowable_entry), (1, self.safety_factor),
                            (3, self.name_entry), (4, self.notes_entry)]:
            if idx > 0:
                pw = fields[idx - 1]
                widget.bind('<Up>', lambda e, w=pw: (w.focus_set(), 'break')[1])
            if idx < len(fields) - 1:
                nw = fields[idx + 1]
                widget.bind('<Down>', lambda e, w=nw: (w.focus_set(), 'break')[1])
            widget.bind('<Return>', lambda e: self._ok())

        # Combobox: Up/Down navigate fields (only fires when dropdown is closed)
        self.units_cb.bind('<Up>', lambda e, w=fields[cb_idx - 1]: (w.focus_set(), 'break')[1])
        self.units_cb.bind('<Down>', lambda e, w=fields[cb_idx + 1]: (w.focus_set(), 'break')[1])

        # Combobox Enter: 1st press opens dropdown, 2nd selects unit,
        # 3rd press confirms dialog
        self._cb_ready = False

        def _on_cb_selected(e):
            # Defer so the Return event in this same cycle does not trigger confirm
            self.after(0, lambda: setattr(self, '_cb_ready', True))

        def _on_cb_return(e):
            if self._cb_ready:
                self._cb_ready = False
                self._ok()
                return 'break'

        def _on_cb_focus_out(e):
            self._cb_ready = False

        self.units_cb.bind('<<ComboboxSelected>>', _on_cb_selected)
        self.units_cb.bind('<Return>', _on_cb_return)
        self.units_cb.bind('<FocusOut>', _on_cb_focus_out)

    def _ok(self):
        try:
            self.result = {
                'allowable_vm': float(self.allowable_entry.get()),
                'safety_factor': float(self.safety_factor.get() or 1.0),
                'units': self.units_cb.get() or 'MPa',
                'name': self.name_entry.get().strip(),
                'notes': self.notes_entry.get().strip()
            }
            self.destroy()
        except ValueError as e:
            messagebox.showerror(title="Error", message=str(e))


class ContourOptionDialog(tk.Toplevel):
    """云图参数设置对话框（含 Hotspot 分析功能）"""

    CATEGORIES = {
        "Stress & Displacement": [
            "Element Stresses (2D & 3D)",
            "Displacement",
        ],
        "Plastic Strain": [
            "Plastic Strains (2D & 3D)",
            "Plastic Strains (2D & 3D) (Gauss)",
            "Element Strains (2D & 3D)",
            "Element Strains (2D & 3D) (Gauss)",
        ],
    }

    COMPONENTS = {
        "Element Stresses (2D & 3D)": [
            "vonMises", "SignedVonMises", "Tresca", "Triaxiality",
            "Lode Param xi", "Lode Param theta",
            "P1 (major)", "P2 (mid)", "P3 (minor)",
            "Extreme Principal", "Max Abs Principal", "MaxShear",
            "Intensity", "Pressure",
            "XX", "YY", "ZZ", "XY", "YZ", "ZX",
        ],
        "Displacement": ["Mag", "X", "Y", "Z"],
        "Plastic Strains (2D & 3D)": ["Equivalent Plastic Strain"],
        "Plastic Strains (2D & 3D) (Gauss)": ["Equivalent Plastic Strain"],
        "Element Strains (2D & 3D)": [
            "vonMises",
            "P1 (major)", "P2 (mid)", "P3 (minor)",
            "Extreme Principal", "Max Abs Principal", "MaxShear",
            "XX", "YY", "ZZ", "XY", "YZ", "ZX",
        ],
        "Element Strains (2D & 3D) (Gauss)": [
            "vonMises",
            "P1 (major)", "P2 (mid)", "P3 (minor)",
            "Extreme Principal", "Max Abs Principal", "MaxShear",
            "XX", "YY", "ZZ", "XY", "YZ", "ZX",
        ],
    }

    VIEWMODE_OPTIONS = {
        "component": ["componenttransparency", "isolatecomponent"],
        "global":    ["component", "location", "model", "region", "spheres"],
        "local":     ["contour", "entityzoom", "transparency"],
    }

    def __init__(self, parent, orchestrator=None, on_execute=None,
                 applied_model_path=None, current_model_path=None):
        super().__init__(parent)
        self.title("Contour & Hotspot Settings")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.orchestrator = orchestrator
        self.on_execute = on_execute
        self.result = None
        self._hotspot_counter = 0
        self._capture_counter = 0
        self._viewmode_var = tk.StringVar(value="")  # "component" | "global" | "local" | ""
        self._vm_component_var = tk.IntVar(value=0)
        self._vm_global_var = tk.IntVar(value=0)
        self._vm_local_var = tk.IntVar(value=0)
        self._vm_option_var = tk.StringVar(value="")
        # Unlock is allowed only when Apply/Confirm was previously done on the
        # same model file (i.e. the user had results but accidentally hit Cancel)
        self._can_unlock = (
            applied_model_path is not None
            and current_model_path is not None
            and applied_model_path == current_model_path
        )
        self._create_ui()
        self.wait_window()

    def _create_ui(self):
        # ── Contour 设置区域 ──
        contour_frame = ttk.LabelFrame(self, text="Contour Settings", padding=10)
        contour_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Label(contour_frame, text="Category:").grid(row=0, column=0, sticky=tk.W, pady=5)
        cats = list(self.CATEGORIES.keys())
        self.cat_var = tk.StringVar(value=cats[0])
        self.cat_cb = ttk.Combobox(contour_frame, textvariable=self.cat_var, values=cats, width=35, state="readonly")
        self.cat_cb.grid(row=0, column=1, pady=5, padx=5)
        self.cat_cb.bind("<<ComboboxSelected>>", self._on_cat_changed)

        ttk.Label(contour_frame, text="Data Type:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.type_var = tk.StringVar()
        self.type_cb = ttk.Combobox(contour_frame, textvariable=self.type_var, width=35, state="readonly")
        self.type_cb.grid(row=1, column=1, pady=5, padx=5)
        self.type_cb.bind("<<ComboboxSelected>>", self._on_type_changed)

        ttk.Label(contour_frame, text="Component:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.comp_var = tk.StringVar()
        self.comp_cb = ttk.Combobox(contour_frame, textvariable=self.comp_var, width=35, state="readonly")
        self.comp_cb.grid(row=2, column=1, pady=5, padx=5)

        self._update_types()

        contour_btn_frame = ttk.Frame(contour_frame)
        contour_btn_frame.grid(row=3, column=0, columnspan=2, pady=10)
        ttk.Button(contour_btn_frame, text="Confirm", command=self._on_confirm, width=12).pack(side=tk.LEFT, padx=10)
        ttk.Button(contour_btn_frame, text="Apply", command=self._on_apply, width=12).pack(side=tk.LEFT, padx=10)
        ttk.Button(contour_btn_frame, text="Cancel", command=self.destroy, width=12).pack(side=tk.LEFT, padx=10)

        # ── Hotspot 分析区域 ──
        hotspot_frame = ttk.LabelFrame(self, text="Hotspot Analysis", padding=8)
        hotspot_frame.pack(fill=tk.X, padx=10, pady=(2, 8))

        nav = ttk.Frame(hotspot_frame)
        nav.pack(pady=5, fill=tk.X)
        self.prev_btn = ttk.Button(nav, text="< Previous",
                                   command=self._on_prev, width=12, state=tk.DISABLED)
        self.prev_btn.pack(side=tk.LEFT)
        self.find_btn = ttk.Button(nav, text="Find Hotspot",
                                   command=self._on_find_hotspot, width=14, state=tk.DISABLED)
        self.find_btn.pack(side=tk.LEFT, expand=True)
        self.next_btn = ttk.Button(nav, text="Next >",
                                   command=self._on_next, width=12, state=tk.DISABLED)
        self.next_btn.pack(side=tk.RIGHT)

        self.hotspot_status_var = tk.StringVar(value="Apply contour first to unlock")
        ttk.Label(hotspot_frame, textvariable=self.hotspot_status_var,
                  foreground="gray").pack(pady=(5, 0), anchor=tk.W)

        # ── View Mode CheckBoxes (kpi hotspot display viewmode) ──
        viewmode_frame = ttk.Frame(hotspot_frame)
        viewmode_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(viewmode_frame, text="View Mode:").pack(side=tk.LEFT)
        self._vm_comp_cbtn = ttk.Checkbutton(
            viewmode_frame, text="Component",
            variable=self._vm_component_var,
            command=lambda: self._on_viewmode_check("component"),
            state=tk.DISABLED,
        )
        self._vm_comp_cbtn.pack(side=tk.LEFT, padx=(8, 0))
        self._vm_global_cbtn = ttk.Checkbutton(
            viewmode_frame, text="Global",
            variable=self._vm_global_var,
            command=lambda: self._on_viewmode_check("global"),
            state=tk.DISABLED,
        )
        self._vm_global_cbtn.pack(side=tk.LEFT, padx=(8, 0))
        self._vm_local_cbtn = ttk.Checkbutton(
            viewmode_frame, text="Local",
            variable=self._vm_local_var,
            command=lambda: self._on_viewmode_check("local"),
            state=tk.DISABLED,
        )
        self._vm_local_cbtn.pack(side=tk.LEFT, padx=(8, 0))

        # ── View Mode Option 下拉栏 ──
        vm_option_row = ttk.Frame(hotspot_frame)
        vm_option_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(vm_option_row, text="Option:").pack(side=tk.LEFT)
        self._vm_option_cb = ttk.Combobox(
            vm_option_row, textvariable=self._vm_option_var,
            state="disabled", width=24,
        )
        self._vm_option_cb.pack(side=tk.LEFT, padx=(8, 0))

        # ── Change View + Capture 按钮（同一行）──
        vm_btn_row = ttk.Frame(hotspot_frame)
        vm_btn_row.pack(pady=(6, 2))
        self._change_view_btn = ttk.Button(
            vm_btn_row, text="Change View",
            command=self._on_change_view, state=tk.DISABLED, width=14,
        )
        self._change_view_btn.pack(side=tk.LEFT, padx=(0, 6))
        self._capture_btn = ttk.Button(
            vm_btn_row, text="Capture",
            command=self._on_capture, state=tk.DISABLED, width=10,
        )
        self._capture_btn.pack(side=tk.LEFT)
        unlock_state = tk.NORMAL if self._can_unlock else tk.DISABLED
        self._unlock_btn = ttk.Button(
            vm_btn_row, text="Unlock",
            command=self._on_unlock, state=unlock_state, width=8,
        )
        self._unlock_btn.pack(side=tk.LEFT, padx=(6, 0))

    def _on_cat_changed(self, event=None):
        self._update_types()

    def _on_type_changed(self, event=None):
        self._update_components()

    def _update_types(self):
        cat = self.cat_var.get()
        types = self.CATEGORIES.get(cat, [])
        self.type_cb['values'] = types
        if types:
            self.type_var.set(types[0])
        self._update_components()

    def _update_components(self):
        t = self.type_var.get()
        comps = self.COMPONENTS.get(t, [])
        self.comp_cb['values'] = comps
        if comps:
            self.comp_var.set(comps[0])

    def _execute_contour(self, close_after=False):
        """执行 apply_contour + report_run_position"""
        if not self.orchestrator:
            return
        result_type = self.type_var.get()
        component = self.comp_var.get()
        label = f"{result_type} - {component}"
        config = {'type': result_type, 'component': component}

        def run():
            try:
                print(f"[ContourOptionDialog] Executing apply_contour: {label}")
                self.orchestrator.apply_contour(result_type, component, label)
                print("[ContourOptionDialog] apply_contour done, running report_run_position...")
                self.orchestrator.report_run_position(label)
                print("[ContourOptionDialog] report_run_position done")
            except Exception as e:
                print(f"[ContourOptionDialog] ERROR in thread: {e}")
            if self.on_execute:
                self.on_execute(config)
            if close_after:
                self.after(0, self.destroy)
            else:
                self.after(0, self._unlock_hotspot_buttons)

        threading.Thread(target=run, daemon=True).start()

    def _unlock_hotspot_buttons(self):
        """Contour 已应用后解锁 Hotspot 按钮及 View Mode CheckBox"""
        self.find_btn.config(state=tk.NORMAL)
        self.hotspot_status_var.set("Click Find Hotspot to start")
        self._vm_comp_cbtn.config(state=tk.NORMAL)
        self._vm_global_cbtn.config(state=tk.NORMAL)
        self._vm_local_cbtn.config(state=tk.NORMAL)

    def _on_unlock(self):
        """Restore hotspot buttons using a previously confirmed result.
        Only callable when a prior Apply/Confirm existed on the same model file."""
        self._unlock_hotspot_buttons()
        self._unlock_btn.config(state=tk.DISABLED)

    def _on_apply(self):
        """执行指令但不退出对话框"""
        self._execute_contour(close_after=False)

    def _on_confirm(self):
        """执行指令后退出对话框"""
        self.result = {
            'type': self.type_var.get(),
            'component': self.comp_var.get()
        }
        self._execute_contour(close_after=True)

    # ── Hotspot 功能 ──

    def _on_find_hotspot(self):
        if not self.orchestrator:
            return
        self._hotspot_counter += 1
        name = f"hotspot{self._hotspot_counter}"
        result_type = self.type_var.get()
        component = self.comp_var.get()
        label = f"{result_type} - {component} (view hotspot)"
        config = {'type': result_type, 'component': component}
        self.find_btn.config(state=tk.DISABLED)
        self.hotspot_status_var.set(f"Applying contour & finding {name}...")

        def run():
            try:
                self.orchestrator.apply_contour(result_type, component, label)
            except Exception as e:
                print(f"[FindHotspot] apply_contour error: {e}")
            if self.on_execute:
                self.on_execute(config)
            ok = self.orchestrator.hotspot_find(name)
            try:
                self.orchestrator.report_run_position(label)
            except Exception as e:
                print(f"[FindHotspot] report_run_position error: {e}")
            def done():
                self.find_btn.config(state=tk.NORMAL)
                self.prev_btn.config(state=tk.NORMAL)
                self.next_btn.config(state=tk.NORMAL)
                if ok:
                    self.hotspot_status_var.set(f"{name} found. Navigate or find more.")
                else:
                    self.hotspot_status_var.set(f"{name} failed. Try again.")
            self.after(0, done)

        threading.Thread(target=run, daemon=True).start()

    def _on_viewmode_check(self, mode: str):
        """处理 View Mode CheckBox 互斥逻辑（kpi hotspot display viewmode <mode>）。
        勾选某项时取消其余两项并更新 Option 下拉栏；取消勾选时重置下拉栏。"""
        var_map = {
            "component": self._vm_component_var,
            "global": self._vm_global_var,
            "local": self._vm_local_var,
        }
        if var_map[mode].get() == 1:
            # 选中此项，取消其他项
            for m, v in var_map.items():
                if m != mode:
                    v.set(0)
            self._viewmode_var.set(mode)
            opts = self.VIEWMODE_OPTIONS[mode]
            self._vm_option_cb.config(values=opts, state="readonly")
            self._vm_option_var.set(opts[0])
            self._change_view_btn.config(state=tk.NORMAL)
            self._capture_btn.config(state=tk.NORMAL)
        else:
            # 取消选中，清空记录并禁用下拉栏和按钮
            self._viewmode_var.set("")
            self._vm_option_cb.config(values=[], state="disabled")
            self._vm_option_var.set("")
            self._change_view_btn.config(state=tk.DISABLED)
            self._capture_btn.config(state=tk.DISABLED)

    def _on_change_view(self):
        """执行 hwc kpi hotspot display viewmode <mode> <option>"""
        if not self.orchestrator:
            return
        mode = self._viewmode_var.get()
        option = self._vm_option_var.get()
        if not mode or not option:
            return
        self._change_view_btn.config(state=tk.DISABLED)

        def run():
            self.orchestrator.hotspot_display_viewmode(mode, option)
            self.after(0, lambda: self._change_view_btn.config(state=tk.NORMAL))

        threading.Thread(target=run, daemon=True).start()

    def _on_capture(self):
        """Add slide + run position，label 中附加当前 View Mode 名称。不执行 result scalar。"""
        if not self.orchestrator:
            return
        mode = self._viewmode_var.get()
        option = self._vm_option_var.get()
        result_type = self.type_var.get()
        component = self.comp_var.get()
        self._capture_counter += 1
        vm_suffix = f" ({mode} {option})" if mode and option else ""
        label = f"{result_type} - {component}{vm_suffix} [{self._capture_counter}]"
        self._capture_btn.config(state=tk.DISABLED)

        def run():
            self.orchestrator.capture_slide(label)
            self.after(0, lambda: self._capture_btn.config(state=tk.NORMAL))

        threading.Thread(target=run, daemon=True).start()

    def _on_prev(self):
        if not self.orchestrator:
            return
        self.prev_btn.config(state=tk.DISABLED)

        def run():
            self.orchestrator.hotspot_navigate("previous")
            self.after(0, lambda: self.prev_btn.config(state=tk.NORMAL))

        threading.Thread(target=run, daemon=True).start()

    def _on_next(self):
        if not self.orchestrator:
            return
        self.next_btn.config(state=tk.DISABLED)

        def run():
            self.orchestrator.hotspot_navigate("next")
            self.after(0, lambda: self.next_btn.config(state=tk.NORMAL))

        threading.Thread(target=run, daemon=True).start()


class ReadMaxValueDialog(tk.Toplevel):
    """Plot contour, find hotspot, export CSV → read peak stress → compare to material."""

    # Reuse contour option tables from ContourOptionDialog
    CATEGORIES = ContourOptionDialog.CATEGORIES
    COMPONENTS = ContourOptionDialog.COMPONENTS

    def __init__(self, parent, orchestrator, db, model_path, result_path=""):
        super().__init__(parent)
        self.title("Read Max Value")
        self.geometry("560x680")
        self.resizable(True, True)
        self.minsize(480, 580)
        self.transient(parent)
        self.grab_set()

        self.orchestrator = orchestrator
        self.db = db
        self.model_path = model_path
        self.result_path = result_path
        self._hotspot_counter = 0
        self._peak_value = None
        self._entity_id = ""
        self._parts_data = []
        self._res_counter = 0

        self._create_ui()
        self.wait_window()

    # ── UI construction ──

    def _create_ui(self):
        # ── Contour Settings ──
        contour_frame = ttk.LabelFrame(self, text="Contour Settings", padding=10)
        contour_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        ttk.Label(contour_frame, text="Category:").grid(row=0, column=0, sticky=tk.W, pady=5)
        cats = list(self.CATEGORIES.keys())
        self.cat_var = tk.StringVar(value=cats[0])
        self.cat_cb = ttk.Combobox(contour_frame, textvariable=self.cat_var,
                                   values=cats, width=35, state="readonly")
        self.cat_cb.grid(row=0, column=1, pady=5, padx=5)
        self.cat_cb.bind("<<ComboboxSelected>>", self._on_cat_changed)

        ttk.Label(contour_frame, text="Data Type:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.type_var = tk.StringVar()
        self.type_cb = ttk.Combobox(contour_frame, textvariable=self.type_var,
                                    width=35, state="readonly")
        self.type_cb.grid(row=1, column=1, pady=5, padx=5)
        self.type_cb.bind("<<ComboboxSelected>>", self._on_type_changed)

        ttk.Label(contour_frame, text="Component:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.comp_var = tk.StringVar()
        self.comp_cb = ttk.Combobox(contour_frame, textvariable=self.comp_var,
                                    width=35, state="readonly")
        self.comp_cb.grid(row=2, column=1, pady=5, padx=5)
        self._update_types()

        # ── Read button row ──
        action_row = ttk.Frame(self, padding=(10, 4))
        action_row.pack(fill=tk.X)
        self._read_btn = ttk.Button(action_row, text="Read", command=self._do_read, width=10)
        self._read_btn.pack(side=tk.LEFT)
        self._status_var = tk.StringVar(value="Configure contour settings and click Read.")
        ttk.Label(action_row, textvariable=self._status_var,
                  foreground='gray').pack(side=tk.LEFT, padx=8)

        # Progress bar — determinate, hidden until running
        self._progress = ttk.Progressbar(self, mode='determinate', maximum=100, value=0)
        # (packed/unpacked dynamically)

        # ── Result section ──
        res_frame = ttk.LabelFrame(self, text="Peak Value Result", padding=10)
        res_frame.pack(fill=tk.X, padx=10, pady=(4, 2))

        ttk.Label(res_frame, text="Peak Stress:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self._max_val_var = tk.StringVar(value="—")
        ttk.Label(res_frame, textvariable=self._max_val_var,
                  foreground='#1e3a5f',
                  font=('Arial', 10, 'bold')).grid(row=0, column=1, sticky=tk.W, padx=6)

        ttk.Label(res_frame, text="Entity ID:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self._entity_var = tk.StringVar(value="—")
        ttk.Label(res_frame, textvariable=self._entity_var,
                  foreground='gray').grid(row=1, column=1, sticky=tk.W, padx=6)

        # ── Add to Mapping section ──
        map_frame = ttk.LabelFrame(self, text="Add to Mapping", padding=10)
        map_frame.pack(fill=tk.X, padx=10, pady=2)

        ttk.Label(map_frame, text="材料:").grid(row=0, column=0, sticky=tk.W, pady=4)
        self._part_var = tk.StringVar()
        self._part_cb = ttk.Combobox(map_frame, textvariable=self._part_var,
                                     state="readonly", width=36)
        self._part_cb.grid(row=0, column=1, columnspan=2, sticky=tk.W, padx=6, pady=4)
        self._refresh_parts()

        ttk.Label(map_frame, text="Max Value:").grid(row=1, column=0, sticky=tk.W, pady=4)
        self._map_val_var = tk.StringVar()
        ttk.Entry(map_frame, textvariable=self._map_val_var,
                  state="readonly", width=24).grid(row=1, column=1, sticky=tk.W, padx=6, pady=4)
        ttk.Label(map_frame, text="(contour max value)",
                  foreground='gray').grid(row=1, column=2, sticky=tk.W, padx=4)

        # ── Results table ──
        res_outer = ttk.LabelFrame(self, text="Results", padding=8)
        res_outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 2))

        res_cols = ('no', 'material', 'value', 'unit')
        self._res_tree = ttk.Treeview(res_outer, columns=res_cols, show='headings',
                                      selectmode='browse', height=5)
        for col, text, w in [
            ('no',       '结果编号', 70),
            ('material', '材料',    200),
            ('value',    '结果值',  120),
            ('unit',     '单位',     70),
        ]:
            self._res_tree.heading(col, text=text, anchor='center')
            self._res_tree.column(col, width=w, minwidth=40, anchor='center')
        self._res_tree.tag_configure('odd',  background='#dbeafe', foreground='#1e3a5f')
        self._res_tree.tag_configure('even', background='#ffffff', foreground='#1f2937')

        res_sb = ttk.Scrollbar(res_outer, orient=tk.VERTICAL, command=self._res_tree.yview)
        self._res_tree.configure(yscrollcommand=res_sb.set)
        self._res_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        res_sb.pack(side=tk.RIGHT, fill=tk.Y)

        # ── Bottom buttons ──
        btn_frame = ttk.Frame(self, padding=(10, 6))
        btn_frame.pack(fill=tk.X)
        self._add_run_btn = ttk.Button(btn_frame, text="Add Result",
                                       command=self._add_and_run, width=30,
                                       state=tk.DISABLED)
        self._add_run_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Close",
                   command=self.destroy, width=10).pack(side=tk.LEFT)

    # ── Contour dropdowns ──

    def _on_cat_changed(self, event=None):
        self._update_types()

    def _on_type_changed(self, event=None):
        self._update_components()

    def _update_types(self):
        cat = self.cat_var.get()
        types = self.CATEGORIES.get(cat, [])
        self.type_cb['values'] = types
        if types:
            self.type_var.set(types[0])
        self._update_components()

    def _update_components(self):
        t = self.type_var.get()
        comps = self.COMPONENTS.get(t, [])
        self.comp_cb['values'] = comps
        if comps:
            self.comp_var.set(comps[0])

    def _refresh_parts(self):
        parts = self.db.get_all_parts()
        self._parts_data = parts
        opts = [
            f"{i + 1}. {p['name'] or 'Unnamed'}  "
            f"({p['allowable_vm']}/{p['safety_factor']} {p['units']})"
            for i, p in enumerate(parts)
        ]
        self._part_cb['values'] = opts
        if opts:
            self._part_cb.current(0)

    # ── Read workflow (3 steps with determinate progress) ──

    def _set_progress(self, value: int, status: str = ""):
        """Update progress bar value (0-100) and optional status label (call from main thread)."""
        self._progress['value'] = value
        if status:
            self._status_var.set(status)

    def _do_read(self):
        if not self.orchestrator:
            messagebox.showerror(title="Error", message="Orchestrator not available.", parent=self)
            return
        self._read_btn.config(state=tk.DISABLED)
        self._add_run_btn.config(state=tk.DISABLED)
        self._progress['value'] = 0
        self._progress.pack(fill=tk.X, padx=10, pady=(2, 0))
        self._status_var.set("Step 1/3 — Plotting contour…")

        self._hotspot_counter += 1
        hotspot_name = f"maxhotspot{self._hotspot_counter}"
        result_type = self.type_var.get()
        component = self.comp_var.get()

        import datetime
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_dir = os.path.join(self.orchestrator.runs_dir, f"maxval_{ts}")
        os.makedirs(csv_dir, exist_ok=True)
        csv_path = os.path.join(csv_dir, "result.csv").replace('\\', '/')

        def run():
            import time as _time
            _t0 = _time.time()

            # ── Step 1: result scalar edit + plot (0 → 30%) ──
            # Matches ContourOptionDialog._on_find_hotspot → apply_contour,
            # but WITHOUT the 'hwc report Report add slide' PPT command.
            ok = self.orchestrator.plot_contour_only(result_type, component)
            _t1 = _time.time()
            print(f"[timing] Step 1 plot_contour_only: {_t1 - _t0:.1f}s")
            if not ok:
                self.after(0, lambda: self._on_read_failed("Step 1 failed — contour plot error."))
                return
            self.after(0, lambda: self._set_progress(30, "Step 2/3 — Finding hotspot…"))

            # ── Step 2: kpi hotspot create + findhotspots + review (30 → 75%) ──
            # Identical to ContourOptionDialog._on_find_hotspot → hotspot_find.
            ok = self.orchestrator.hotspot_find(hotspot_name)
            _t2 = _time.time()
            print(f"[timing] Step 2 hotspot_find: {_t2 - _t1:.1f}s")
            if not ok:
                self.after(0, lambda: self._on_read_failed("Step 2 failed — hotspot find error."))
                return
            self.after(0, lambda: self._set_progress(75, "Step 3/3 — Exporting CSV…"))

            # ── Step 3: show/hide components + kpi hotspot export (75 → 100%) ──
            result = self.orchestrator.export_hotspot_csv(hotspot_name, csv_path)
            _t3 = _time.time()
            print(f"[timing] Step 3 export_hotspot_csv: {_t3 - _t2:.1f}s  total: {_t3 - _t0:.1f}s")
            if not result:
                # Bridge may have timed out while HyperView was still writing the file.
                # Check whether the CSV landed on disk before giving up.
                if not os.path.exists(csv_path):
                    self.after(0, lambda: self._on_read_failed(
                        "Step 3 failed — CSV export error. Check Logs."))
                    return
                # CSV exists despite the timeout — proceed to parse it.
            self.after(0, lambda: self._set_progress(100, "Parsing results…"))
            self.after(0, lambda: self._on_read_done(csv_path))

        threading.Thread(target=run, daemon=True).start()

    def _on_read_failed(self, msg: str):
        self._progress.pack_forget()
        self._progress['value'] = 0
        self._read_btn.config(state=tk.NORMAL)
        self._status_var.set(msg)

    def _on_read_done(self, csv_path):
        self._progress.pack_forget()
        self._progress['value'] = 0
        self._read_btn.config(state=tk.NORMAL)

        # result is always truthy here (failures handled in _on_read_failed)

        peak_value, entity_id, rows, headers = self._parse_csv(csv_path)
        if peak_value is None:
            self._status_var.set("CSV exported but could not parse max value.")
            return

        self._peak_value = peak_value
        self._entity_id = entity_id

        dtype = self.type_var.get()
        unit = 'mm' if 'Displacement' in dtype else ('—' if 'Strain' in dtype else 'MPa')
        self._max_val_var.set(f"{peak_value:.4f} {unit}")
        self._entity_var.set(str(entity_id))
        self._map_val_var.set(f"{peak_value:.4f}")

        img_path = self._save_table_image(csv_path, rows, headers, peak_value)
        if img_path:
            print(f"[table image] {img_path}")

        self._status_var.set("Done. Select material and click Add Result.")
        self._add_run_btn.config(state=tk.NORMAL)

    @staticmethod
    def _parse_csv(csv_path: str):
        """Find the column whose header contains 'Contour' (case-insensitive),
        return (max_value, entity_id_of_that_row, all_rows, headers)."""
        import csv as csv_mod
        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv_mod.DictReader(f)
                rows = list(reader)
            if not rows:
                return None, "", [], []

            headers = list(rows[0].keys())
            contour_col = next((h for h in headers if 'contour' in h.lower()), None)
            if contour_col is None:
                print(f"[_parse_csv] No 'Contour' column found. Headers: {headers}")
                return None, "", rows, headers

            best_value = None
            best_row = None
            for row in rows:
                v = _safe_float(row.get(contour_col, ""))
                if v is not None and (best_value is None or v > best_value):
                    best_value = v
                    best_row = row

            if best_row is None:
                return None, "", rows, headers

            entity_id = ""
            for col in ('ID', 'id', 'Entity ID', 'EntityID',
                        'Element', 'Element ID', 'ElementID',
                        'Rank', 'rank', 'Index', 'index'):
                if col in best_row and best_row[col].strip():
                    entity_id = best_row[col].strip()
                    break
            if not entity_id:
                entity_id = str(next(iter(best_row.values()), ""))

            return best_value, entity_id, rows, headers
        except Exception as e:
            print(f"[_parse_csv] {e}")
            return None, "", [], []

    @staticmethod
    def _save_table_image(csv_path: str, rows: list, headers: list, peak_value: float) -> str:
        """Generate a PNG table image via PowerShell + System.Drawing (no pip required)."""
        import subprocess
        try:
            if not rows or not headers:
                return ""

            display_rows = rows[:50]  # cap to keep image size reasonable

            contour_col = next((h for h in headers if 'contour' in h.lower()), None)
            peak_row_idx = -1
            if contour_col is not None:
                best_v = None
                for i, row in enumerate(display_rows):
                    v = _safe_float(row.get(contour_col, ""))
                    if v is not None and (best_v is None or v > best_v):
                        best_v = v
                        peak_row_idx = i

            def ps_str(s):
                """Escape value for a PowerShell single-quoted string literal."""
                return "'" + str(s).replace("'", "''").replace('\r', '').replace('\n', ' ') + "'"

            header_ps = '@(' + ', '.join(ps_str(h) for h in headers) + ')'
            row_lines = []
            for row in display_rows:
                cells = ', '.join(ps_str(row.get(h, '')) for h in headers)
                row_lines.append(f'    @({cells})')
            rows_ps = '@(\n' + ',\n'.join(row_lines) + '\n)'

            img_path = os.path.splitext(csv_path)[0] + '_table.png'
            # ps_str wraps in quotes; strip them — the content is safe for single-quote embedding
            out_ps = ps_str(img_path)[1:-1]

            ps_script = f"""
Add-Type -AssemblyName System.Drawing

$headers  = {header_ps}
$rows     = {rows_ps}
$peakIdx  = {peak_row_idx}
$outPath  = '{out_ps}'

$font      = New-Object System.Drawing.Font('Arial', 9)
$boldFont  = New-Object System.Drawing.Font('Arial', 9,  [System.Drawing.FontStyle]::Bold)
$titleFont = New-Object System.Drawing.Font('Arial', 11, [System.Drawing.FontStyle]::Bold)

# Measure column widths from content
$tmp = New-Object System.Drawing.Bitmap(1, 1)
$tg  = [System.Drawing.Graphics]::FromImage($tmp)
$colW = @()
foreach ($h in $headers) {{
    $colW += [int]($tg.MeasureString($h, $boldFont).Width) + 20
}}
for ($r = 0; $r -lt $rows.Count; $r++) {{
    for ($c = 0; $c -lt $headers.Count; $c++) {{
        $w = [int]($tg.MeasureString($rows[$r][$c], $font).Width) + 20
        if ($w -gt $colW[$c]) {{ $colW[$c] = $w }}
    }}
}}
$tg.Dispose(); $tmp.Dispose()

$cellH  = 24
$totalW = ($colW | Measure-Object -Sum).Sum
$totalH = ($rows.Count + 1) * $cellH + 40

$bmp = New-Object System.Drawing.Bitmap($totalW, $totalH)
$g   = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::White)
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit

$sf = New-Object System.Drawing.StringFormat
$sf.Alignment     = [System.Drawing.StringAlignment]::Center
$sf.LineAlignment = [System.Drawing.StringAlignment]::Center

# Title
$titleBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(31, 56, 100))
$g.DrawString('Hotspot KPI Table', $titleFont, $titleBrush, 5, 8)

# Header row
$y = 34; $x = 0
$hdrBg = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(31, 56, 100))
$hdrFg = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
for ($c = 0; $c -lt $headers.Count; $c++) {{
    $g.FillRectangle($hdrBg, $x, $y, $colW[$c], $cellH)
    $g.DrawRectangle([System.Drawing.Pens]::DarkGray, $x, $y, $colW[$c], $cellH)
    $rect = New-Object System.Drawing.RectangleF($x, $y, $colW[$c], $cellH)
    $g.DrawString($headers[$c], $boldFont, $hdrFg, $rect, $sf)
    $x += $colW[$c]
}}
$y += $cellH

# Data rows
$peakBg = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 217, 102))
$altBg  = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(242, 242, 242))
$whtBg  = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
$blkFg  = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::Black)

for ($r = 0; $r -lt $rows.Count; $r++) {{
    if      ($r -eq $peakIdx)   {{ $bg = $peakBg; $f = $boldFont }}
    elseif  ($r % 2 -eq 0)     {{ $bg = $altBg;  $f = $font }}
    else                        {{ $bg = $whtBg;  $f = $font }}
    $x = 0
    for ($c = 0; $c -lt $headers.Count; $c++) {{
        $g.FillRectangle($bg, $x, $y, $colW[$c], $cellH)
        $g.DrawRectangle([System.Drawing.Pens]::LightGray, $x, $y, $colW[$c], $cellH)
        $rect = New-Object System.Drawing.RectangleF($x, $y, $colW[$c], $cellH)
        $g.DrawString($rows[$r][$c], $f, $blkFg, $rect, $sf)
        $x += $colW[$c]
    }}
    $y += $cellH
}}

$bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Host "Saved: $outPath"
"""
            ps_file = img_path + '.ps1'
            try:
                with open(ps_file, 'w', encoding='utf-8') as f:
                    f.write(ps_script)
                proc = subprocess.run(
                    ['powershell', '-ExecutionPolicy', 'Bypass', '-File', ps_file],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30
                )
                if proc.returncode != 0:
                    print(f"[_save_table_image] PS error: {proc.stderr.decode(errors='replace').strip()}")
                return img_path if os.path.exists(img_path) else ""
            finally:
                try:
                    os.remove(ps_file)
                except OSError:
                    pass
        except Exception as e:
            print(f"[_save_table_image] {e}")
            return ""

    @staticmethod
    def _save_comparison_image(peak_value: float, unit: str,
                               parts: list, selected_part_no: str = "") -> str:
        """Generate a PNG that compares peak_value against every part in the database.

        Row colours:
          yellow  (#FFD966) – the material the user selected (bold)
          red     (#FFC7CE) – peak exceeds this material's effective allowable
          green   (#C6EFCE) – peak is within this material's effective allowable
        """
        import subprocess, os, datetime

        if not parts:
            return ""

        def ps_str(s):
            return "'" + str(s).replace("'", "''").replace('\r', '').replace('\n', ' ') + "'"

        # Build comparison rows
        col_keys = ('part_no', 'name', 'allowable_vm', 'safety_factor',
                    'effective', 'peak', 'result', 'margin')
        headers = ['编号', '材料名称',
                   f'许用值({unit})', '安全系数',
                   f'有效许用值({unit})', f'峰值({unit})',
                   '比较结果', f'差值({unit})']

        row_lines = []
        for idx, p in enumerate(parts):
            sf = p.get('safety_factor') or 1.0
            eff = p['allowable_vm'] / sf
            exceeded = peak_value > eff
            margin = eff - peak_value
            is_selected = (str(p['part_no']) == str(selected_part_no))
            # color code: 2=yellow(selected), 1=red(exceeded), 0=green(ok)
            color = 2 if is_selected else (1 if exceeded else 0)
            cells_ps = ', '.join([
                ps_str(str(idx + 1)),
                ps_str(p.get('name') or '—'),
                ps_str(f"{p['allowable_vm']:.2f}"),
                ps_str(f"{sf:.2f}"),
                ps_str(f"{eff:.2f}"),
                ps_str(f"{peak_value:.4f}"),
                ps_str('超出' if exceeded else '未超出'),
                ps_str(f"{margin:.2f}"),
            ])
            row_lines.append(f"    @({cells_ps}, {color})")

        header_ps = '@(' + ', '.join(ps_str(h) for h in headers) + ')'
        rows_ps = '@(\n' + ',\n'.join(row_lines) + '\n)'

        # Save location: project root (parent of gui/)
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        img_path = os.path.join(app_dir, f'comparison_{ts}.png')

        out_ps = ps_str(img_path)[1:-1]
        peak_label_ps = ps_str(f"峰值: {peak_value:.4f} {unit}")[1:-1]
        ncols = len(headers)

        ps_script = f"""
Add-Type -AssemblyName System.Drawing

$headers   = {header_ps}
$rows      = {rows_ps}
$peakLabel = '{peak_label_ps}'
$outPath   = '{out_ps}'
$nCols     = {ncols}

$font      = New-Object System.Drawing.Font('Arial', 9)
$boldFont  = New-Object System.Drawing.Font('Arial', 9,  [System.Drawing.FontStyle]::Bold)
$titleFont = New-Object System.Drawing.Font('Arial', 11, [System.Drawing.FontStyle]::Bold)

# Measure column widths from content
$tmp = New-Object System.Drawing.Bitmap(1, 1)
$tg  = [System.Drawing.Graphics]::FromImage($tmp)
$colW = @()
foreach ($h in $headers) {{
    $colW += [int]($tg.MeasureString($h, $boldFont).Width) + 20
}}
for ($r = 0; $r -lt $rows.Count; $r++) {{
    for ($c = 0; $c -lt $nCols; $c++) {{
        $w = [int]($tg.MeasureString($rows[$r][$c], $font).Width) + 20
        if ($w -gt $colW[$c]) {{ $colW[$c] = $w }}
    }}
}}
$tg.Dispose(); $tmp.Dispose()

$cellH  = 24
$totalW = ($colW | Measure-Object -Sum).Sum
$totalH = ($rows.Count + 1) * $cellH + 50

$bmp = New-Object System.Drawing.Bitmap($totalW, $totalH)
$g   = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::White)
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit

$sf = New-Object System.Drawing.StringFormat
$sf.Alignment     = [System.Drawing.StringAlignment]::Center
$sf.LineAlignment = [System.Drawing.StringAlignment]::Center

# Title + peak label
$titleBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(31, 56, 100))
$g.DrawString('峰值与材料许用值比较', $titleFont, $titleBrush, 5, 5)
$g.DrawString($peakLabel, $font, $titleBrush, 5, 28)

# Header row
$y = 50; $x = 0
$hdrBg = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(31, 56, 100))
$hdrFg = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
for ($c = 0; $c -lt $nCols; $c++) {{
    $g.FillRectangle($hdrBg, $x, $y, $colW[$c], $cellH)
    $g.DrawRectangle([System.Drawing.Pens]::DarkGray, $x, $y, $colW[$c], $cellH)
    $rect = New-Object System.Drawing.RectangleF($x, $y, $colW[$c], $cellH)
    $g.DrawString($headers[$c], $boldFont, $hdrFg, $rect, $sf)
    $x += $colW[$c]
}}
$y += $cellH

# Data rows
$greenBg  = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(198, 239, 206))
$redBg    = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 199, 206))
$yellowBg = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 217, 102))
$blkFg    = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::Black)

for ($r = 0; $r -lt $rows.Count; $r++) {{
    $code = [int]$rows[$r][$nCols]
    if      ($code -eq 2) {{ $bg = $yellowBg; $f = $boldFont }}
    elseif  ($code -eq 1) {{ $bg = $redBg;    $f = $font }}
    else                  {{ $bg = $greenBg;  $f = $font }}
    $x = 0
    for ($c = 0; $c -lt $nCols; $c++) {{
        $g.FillRectangle($bg, $x, $y, $colW[$c], $cellH)
        $g.DrawRectangle([System.Drawing.Pens]::LightGray, $x, $y, $colW[$c], $cellH)
        $rect = New-Object System.Drawing.RectangleF($x, $y, $colW[$c], $cellH)
        $g.DrawString($rows[$r][$c], $f, $blkFg, $rect, $sf)
        $x += $colW[$c]
    }}
    $y += $cellH
}}

$bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
Write-Host "Saved: $outPath"
"""
        ps_file = img_path + '.ps1'
        try:
            with open(ps_file, 'w', encoding='utf-8') as f:
                f.write(ps_script)
            proc = subprocess.run(
                ['powershell', '-ExecutionPolicy', 'Bypass', '-File', ps_file],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30
            )
            if proc.returncode != 0:
                print(f"[_save_comparison_image] PS error: "
                      f"{proc.stderr.decode(errors='replace').strip()}")
            return img_path if os.path.exists(img_path) else ""
        except Exception as e:
            print(f"[_save_comparison_image] {e}")
            return ""
        finally:
            try:
                os.remove(ps_file)
            except OSError:
                pass

    # ── Add mapping & direct analysis ──

    def _add_and_run(self):
        if self._peak_value is None:
            messagebox.showwarning(title="Warning",
                                   message="No peak value available. Click Read first.",
                                   parent=self)
            return

        sel_idx = self._part_cb.current()
        if sel_idx < 0 or not self._parts_data:
            messagebox.showwarning(title="Warning",
                                   message="Select a material standard first.", parent=self)
            return
        part = self._parts_data[sel_idx]

        map_value = self._map_val_var.get().strip()
        if not map_value:
            messagebox.showwarning(title="Warning",
                                   message="Max Value is empty. Click Read first.", parent=self)
            return

        # Compare peak_value against ALL parts in database → PNG table
        dtype = self.type_var.get()
        unit = 'mm' if 'Displacement' in dtype else ('—' if 'Strain' in dtype else 'MPa')
        all_parts = self.db.get_all_parts()
        img_path = self._save_comparison_image(
            self._peak_value, unit, all_parts, part['part_no']
        )
        if img_path:
            print(f"[comparison image] {img_path}")

        # Append to results table
        self._res_counter += 1
        material_label = part.get('name') or part.get('part_no', '—')
        tag = 'odd' if self._res_counter % 2 else 'even'
        self._res_tree.insert('', tk.END, values=(
            self._res_counter,
            material_label,
            f"{self._peak_value:.4f}",
            unit,
        ), tags=(tag,))

class CompareOptionDialog(tk.Toplevel):
    """Compare with Material Standards 选项对话框"""

    def __init__(self, parent, orchestrator, db, model_path, result_path="", on_complete=None):
        super().__init__(parent)
        self.title("Compare with Material Standards")
        self.geometry("660x780")
        self.resizable(True, True)
        self.minsize(520, 600)
        self.transient(parent)
        self.grab_set()

        self.orchestrator = orchestrator
        self.db = db
        self.model_path = model_path
        self.result_path = result_path
        self.on_complete = on_complete

        self._create_ui()
        self.wait_window()

    def _create_ui(self):
        # ── Standards Overview with CRUD toolbar ──
        std_outer = ttk.LabelFrame(self, text="Standards Overview", padding=8)
        std_outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 4))

        std_toolbar = ttk.Frame(std_outer)
        std_toolbar.pack(fill=tk.X, pady=(0, 4))
        ttk.Button(std_toolbar, text="Add",    width=6,
                   command=self._std_add).pack(side=tk.LEFT, padx=2)
        ttk.Button(std_toolbar, text="Edit",   width=6,
                   command=self._std_edit).pack(side=tk.LEFT, padx=2)
        ttk.Button(std_toolbar, text="Delete", width=6,
                   command=self._std_delete).pack(side=tk.LEFT, padx=2)
        ttk.Separator(std_toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Button(std_toolbar, text="Import CSV", width=10,
                   command=self._std_import_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(std_toolbar, text="Export CSV", width=10,
                   command=self._std_export_csv).pack(side=tk.LEFT, padx=2)

        std_tree_frame = ttk.Frame(std_outer)
        std_tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ('part_no', 'name', 'allowable_vm', 'safety_factor', 'effective', 'units')
        self._std_tree = ttk.Treeview(std_tree_frame, columns=columns, show='headings',
                                      selectmode='browse', height=5)
        for col, text, w in [
            ('part_no',       'ID',              50),
            ('name',          'Name',           130),
            ('allowable_vm',  'Allowable',       90),
            ('safety_factor', 'SF',              55),
            ('effective',     'Effective (÷SF)', 110),
            ('units',         'Unit',             55),
        ]:
            self._std_tree.heading(col, text=text, anchor='center')
            self._std_tree.column(col, width=w, minwidth=40, anchor='center')
        self._std_tree.tag_configure('odd',  background='#dbeafe', foreground='#1e3a5f')
        self._std_tree.tag_configure('even', background='#ffffff', foreground='#1f2937')
        self._std_tree.bind('<Double-1>', lambda e: self._std_edit())

        std_sb = ttk.Scrollbar(std_tree_frame, orient=tk.VERTICAL,
                               command=self._std_tree.yview)
        self._std_tree.configure(yscrollcommand=std_sb.set)
        self._std_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        std_sb.pack(side=tk.RIGHT, fill=tk.Y)

        self._refresh_std()

        # ── Analysis Result ──
        result_frame = ttk.LabelFrame(self, text="Analysis Result", padding=8)
        result_frame.pack(fill=tk.X, padx=10, pady=4)

        self._result_text = tk.Text(result_frame, height=5, state=tk.DISABLED,
                                    wrap=tk.WORD, font=('Courier', 9))
        self._result_text.tag_configure('pass', foreground='#166534',
                                        font=('Courier', 9, 'bold'))
        self._result_text.tag_configure('fail', foreground='#991b1b',
                                        font=('Courier', 9, 'bold'))
        self._result_text.tag_configure('info', foreground='#1e40af')
        self._result_text.tag_configure('dim',  foreground='gray')
        self._result_text.pack(fill=tk.X)

        # ── Progress bar (hidden until analysis is running) ──
        self._progress = ttk.Progressbar(self, mode='indeterminate')
        # do not pack now; shown only while running

        # ── Buttons ──
        btn_frame = ttk.Frame(self, padding=(10, 6))
        btn_frame.pack(fill=tk.X)
        can_run = bool(self.db.get_all_parts())
        self._run_btn = ttk.Button(btn_frame, text="Run Analysis",
                                   command=self._run, width=14,
                                   state=tk.NORMAL if can_run else tk.DISABLED)
        self._run_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Read Max Value",
                   command=self._read_max_value, width=16).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Close",
                   command=self.destroy, width=10).pack(side=tk.LEFT)

        if not can_run:
            self._set_result("  Add material standards above, then click Run Analysis.", 'dim')

    # ── Standards helpers ──

    def _refresh_std(self):
        for item in self._std_tree.get_children():
            self._std_tree.delete(item)
        parts = self.db.get_all_parts()
        for i, p in enumerate(parts):
            tag = 'odd' if i % 2 else 'even'
            try:
                eff = f"{p['allowable_vm'] / p['safety_factor']:.2f}"
            except (TypeError, ZeroDivisionError):
                eff = '-'
            self._std_tree.insert('', tk.END, values=(
                p['part_no'], p['name'] or '-', p['allowable_vm'],
                p['safety_factor'], eff, p['units']
            ), tags=(tag,))

    def _std_add(self):
        dialog = PartDialog(self, title="Add Material")
        if dialog.result:
            self.db.add_part(part_no=self.db.get_next_part_no(), **dialog.result)
            self._refresh_std()
            self._update_run_btn()

    def _std_edit(self):
        sel = self._std_tree.selection()
        if not sel:
            messagebox.showwarning(title="WARNING", message="Select a standard first", parent=self)
            return
        values = self._std_tree.item(sel[0])['values']
        part_no = str(values[0])
        data = {
            'allowable_vm': values[2],
            'safety_factor': values[3],
            'units': values[5],
            'name': values[1] if values[1] != '-' else '',
            'notes': '',
        }
        part = self.db.get_part(part_no)
        if part:
            data['notes'] = part.get('notes', '')
        dialog = PartDialog(self, title="Edit Material", data=data)
        if dialog.result:
            self.db.update_part(part_no=part_no, **dialog.result)
            self._refresh_std()

    def _std_delete(self):
        sel = self._std_tree.selection()
        if not sel:
            messagebox.showwarning(title="WARNING", message="Select a standard first", parent=self)
            return
        if messagebox.askyesno(title="Confirm",
                               message="Delete selected standard? This cannot be undone.",
                               parent=self):
            part_no = str(self._std_tree.item(sel[0])['values'][0])
            self.db.delete_part(part_no)
            remaining = [p['part_no'] for p in self.db.get_all_parts()]
            if remaining:
                self.db.renumber_parts(remaining)
            self._refresh_std()
            self._update_run_btn()

    def _std_import_csv(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select CSV File",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            parent=self)
        if path:
            count = self.db.import_parts_csv(path)
            messagebox.showinfo(title="Complete",
                                message=f"Imported {count} parts successfully", parent=self)
            self._refresh_std()
            self._update_run_btn()

    def _std_export_csv(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            title="Save CSV File",
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            parent=self)
        if path:
            self.db.export_parts_csv(path)
            messagebox.showinfo(title="Complete",
                                message=f"Exported to {path} successfully", parent=self)

    def _read_max_value(self):
        """Open ReadMaxValueDialog — plot contour, export hotspot CSV, compare to material."""
        ReadMaxValueDialog(
            self,
            orchestrator=self.orchestrator,
            db=self.db,
            model_path=self.model_path,
            result_path=self.result_path,
        )

    def _update_run_btn(self):
        can_run = bool(self.db.get_all_parts())
        self._run_btn.config(state=tk.NORMAL if can_run else tk.DISABLED)
        if not can_run:
            self._set_result("  Add material standards above, then click Run Analysis.", 'dim')

    # ── Helpers ──

    def _set_result(self, text, tag='info'):
        self._result_text.config(state=tk.NORMAL)
        self._result_text.delete(1.0, tk.END)
        self._result_text.insert(tk.END, text, tag)
        self._result_text.config(state=tk.DISABLED)

    # ── Analysis execution ──

    def _run(self):
        self._run_btn.config(state=tk.DISABLED)
        self._progress.pack(fill=tk.X, padx=10, pady=(2, 0))
        self._progress.start(10)
        self._set_result("Running analysis, please wait...", 'info')

        def do_run():
            result = self.orchestrator.run_analysis(self.model_path, self.result_path)
            self.after(0, lambda: self._on_done(result))

        threading.Thread(target=do_run, daemon=True).start()

    def _on_done(self, result):
        self._progress.stop()
        self._progress.pack_forget()
        self._run_btn.config(state=tk.NORMAL)

        if not result or not result.get('success'):
            self._set_result("Analysis failed. Check the Logs tab for details.", 'fail')
            return

        a = result['analysis']
        status_tag = 'pass' if a.passed else 'fail'
        status_str = "PASSED" if a.passed else "FAILED"
        unit = getattr(a, 'units', None) or 'MPa'

        lines = [f"  Status       :  {status_str}\n\n"]
        lines.append(f"  Peak Stress  :  {a.peak_value:.4f} {unit}\n")
        lines.append(f"  Component ID :  {a.peak_entity_id}\n")

        if a.part_no:
            lines.append(f"  Part No.     :  {a.part_no}  ({a.part_name or '-'})\n")
            lines.append(f"  Allowable    :  {a.allowable_vm:.2f}  "
                         f"SF={a.safety_factor:.2f}  →  Effective={a.allowable:.2f} {unit}\n")
            lines.append(f"  Margin       :  {a.margin:.2f} {unit}   "
                         f"Ratio={a.ratio:.2%}\n")
        else:
            lines.append("  Part No.     :  Not matched\n")

        lines.append(f"\n  {a.message}\n")

        self._result_text.config(state=tk.NORMAL)
        self._result_text.delete(1.0, tk.END)
        self._result_text.insert(tk.END, f"  {'─' * 50}\n", 'dim')
        self._result_text.insert(tk.END, "".join(lines), status_tag)
        self._result_text.insert(tk.END, f"  {'─' * 50}\n", 'dim')
        self._result_text.config(state=tk.DISABLED)

        if self.on_complete:
            self.on_complete(result)


class AnalysisDialog(tk.Toplevel):
    """分析功能对话框"""

    def __init__(self, parent, orchestrator, model_path, result_path=""):
        super().__init__(parent)
        self.title("Analysis Options")
        self.geometry("550x500")
        self.resizable(width=False, height=False)
        # 不使用 transient 和 grab_set，让窗口独立运行

        self.parent = parent
        self.orchestrator = orchestrator
        self.model_path = model_path
        self.result_path = result_path
        self.result = None
        # model path recorded when Apply/Confirm last succeeded; None if never done
        self._contour_applied_model: str | None = None

        # 启动 setup_view 线程
        self._setup_thread = threading.Thread(target=self.orchestrator.setup_view, daemon=True)
        self._setup_thread.start()

        self._create_ui()
        # 等待窗口关闭
        self.wait_window()

    def _create_ui(self):
        # 主容器
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_frame = ttk.Frame(main_frame, padding=10)
        title_frame.pack(fill=tk.X)
        ttk.Label(title_frame, text="Analysis Options", font=('Arial', 12, 'bold')).pack()

        # 模型信息
        info_frame = ttk.LabelFrame(main_frame, text="Model Information", padding=10)
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(info_frame, text=f"Model: {os.path.basename(self.model_path)}", wraplength=450).pack(anchor=tk.W)
        if self.result_path:
            ttk.Label(info_frame, text=f"Result: {os.path.basename(self.result_path)}", wraplength=450).pack(anchor=tk.W)

        # Checkbox 选项区域
        opt_frame = ttk.LabelFrame(main_frame, text="Select Analysis Items", padding=10)
        opt_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.chk_contour = tk.BooleanVar(value=False)
        self.chk_compare = tk.BooleanVar(value=False)
        # Track whether Create Report has completed (checkboxes locked before that)
        self._report_created = False

        row1 = ttk.Frame(opt_frame)
        row1.pack(fill=tk.X, pady=4)
        self.chk_btn_contour = ttk.Checkbutton(
            row1, text="Plot Contour",
            variable=self.chk_contour, state=tk.DISABLED,
            command=self._on_checkbox_toggled)
        self.chk_btn_contour.pack(side=tk.LEFT)
        self.opt_btn_contour = ttk.Button(row1, text="Option", width=8, state=tk.DISABLED,
                                          command=self._open_contour_option)
        self.opt_btn_contour.pack(side=tk.RIGHT)
        ttk.Label(opt_frame, text="    Plot contour on the model and find stress hotspots",
                  foreground='gray').pack(anchor=tk.W)

        row3 = ttk.Frame(opt_frame)
        row3.pack(fill=tk.X, pady=4)
        self.chk_btn_compare = ttk.Checkbutton(
            row3, text="Compare with Material Standards",
            variable=self.chk_compare, state=tk.DISABLED,
            command=self._on_checkbox_toggled)
        self.chk_btn_compare.pack(side=tk.LEFT)
        self.opt_btn_compare = ttk.Button(row3, text="Option", width=8, state=tk.DISABLED,
                                           command=self._run_compare)
        self.opt_btn_compare.pack(side=tk.RIGHT)
        ttk.Label(opt_frame, text="    Compare peak stress with allowable values from database",
                  foreground='gray').pack(anchor=tk.W)

        # 结果追踪
        self._completed_results = []

        # 底部区域 (从下往上: 状态栏 -> 进度条 -> 按钮)
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # 状态栏
        self.status_var = tk.StringVar(value="Step 1: Click Create Report")
        status_bar = ttk.Label(bottom_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=5)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # 进度条
        self.progress = ttk.Progressbar(bottom_frame, mode='determinate', length=480, maximum=100)
        self.progress.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=5)

        # 按钮区域
        btn_frame = ttk.Frame(bottom_frame, padding=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.close_btn = ttk.Button(btn_frame, text="Close", command=self.destroy, width=15, state=tk.DISABLED)
        self.close_btn.pack(side=tk.RIGHT, padx=5)
        self.run_btn = ttk.Button(btn_frame, text="Export", command=self._export_report, width=15, state=tk.DISABLED)
        self.run_btn.pack(side=tk.RIGHT, padx=5)
        self.create_report_btn = ttk.Button(btn_frame, text="Create Report", command=self._create_report, width=15)
        self.create_report_btn.pack(side=tk.RIGHT, padx=5)

    # ── Step 1: Create Report ──

    def _create_report(self):
        """Step 1: 创建报告模板，完成后解锁 Option 和 Run"""
        self.create_report_btn.config(state=tk.DISABLED)
        self.run_btn.config(state=tk.DISABLED)
        self.close_btn.config(state=tk.DISABLED)
        self._set_status("Step 1: Creating report...")

        def do_create():
            self._setup_thread.join()
            self.orchestrator.create_report()
            self.after(0, lambda: self._set_status("Report created. Waiting for HyperView..."))
            self.after(0, lambda: self.after(20000, self._unlock_after_create))

        threading.Thread(target=do_create, daemon=True).start()

    def _unlock_after_create(self):
        """Create Report 完成后解锁 Checkbox 和 Run/Close"""
        self._report_created = True
        self.run_btn.config(state=tk.NORMAL)
        self.close_btn.config(state=tk.NORMAL)
        # Enable checkboxes so user can tick them
        self.chk_btn_contour.config(state=tk.NORMAL)
        self.chk_btn_compare.config(state=tk.NORMAL)
        # Option buttons stay disabled until their checkbox is ticked
        self._set_status("Step 2: Tick items and click Option to configure, then Step 3: Export PPT")

    def _on_checkbox_toggled(self):
        """Checkbox 状态变化时，同步更新对应 Option 按钮的启用/禁用"""
        if not self._report_created:
            return
        self.opt_btn_contour.config(
            state=tk.NORMAL if self.chk_contour.get() else tk.DISABLED)
        self.opt_btn_compare.config(
            state=tk.NORMAL if self.chk_compare.get() else tk.DISABLED)

    # ── Step 2: 自由配置分析项 ──

    def _open_contour_option(self):
        """打开云图参数设置对话框，Apply/Confirm 都会执行 hwc 指令"""
        ContourOptionDialog(self, orchestrator=self.orchestrator,
                            on_execute=self._on_contour_executed,
                            applied_model_path=self._contour_applied_model,
                            current_model_path=self.model_path)

    def _on_contour_executed(self, config):
        """每次 Apply/Confirm 执行后的回调"""
        self._completed_results.append({
            'type': 'contour', 'success': True, 'config': config
        })
        # Record that a successful apply/confirm was done for this model file
        self._contour_applied_model = self.model_path

    def _run_compare(self):
        """打开 Compare Options 对话框"""
        CompareOptionDialog(
            self,
            orchestrator=self.orchestrator,
            db=self.orchestrator.db,
            model_path=self.model_path,
            result_path=self.result_path,
            on_complete=self._on_compare_done,
        )

    def _on_compare_done(self, result):
        """CompareOptionDialog 分析完成后的回调"""
        if result and result.get('success'):
            self._completed_results.append({
                'type': 'compare', 'success': True, 'result': result
            })
            self._set_status("Compare done. Continue or Export to finish.")

            def do_report():
                self.orchestrator.report_run()

            threading.Thread(target=do_report, daemon=True).start()

    # ── Step 3: 导出 PPT ──

    def _export_report(self):
        """导出 PPT"""
        self.run_btn.config(state=tk.DISABLED)
        self.close_btn.config(state=tk.DISABLED)
        self._set_status("Exporting report...")

        def export():
            self.orchestrator.report_export()
            self.after(0, lambda: self._set_status("All done! Report exported."))
            self.after(0, lambda: self.run_btn.config(state=tk.NORMAL))
            self.after(0, lambda: self.close_btn.config(state=tk.NORMAL))
            self.after(0, self._update_parent_results)

        threading.Thread(target=export, daemon=True).start()

    # ── 工具方法 ──

    def _set_status(self, msg):
        self.status_var.set(msg)
        self.update()

    def _update_parent_results(self):
        """将分析摘要写入主窗口的 Analysing Result 区域"""
        if not hasattr(self.parent, 'result_text'):
            return

        lines = ["=== Analysis Summary ===\n"]
        report_path = None

        for r in self._completed_results:
            if not r['success']:
                lines.append(f"  [{r['type']}]  FAILED\n")
                continue

            if r['type'] == 'contour':
                cfg = r.get('config')
                if cfg:
                    lines.append(f"  [Plot Contour]  {cfg['type']} - {cfg['component']}\n")

            elif r['type'] == 'compare':
                a = r['result']['analysis']
                status = "PASSED" if a.passed else "FAILED"
                allowable = f"{a.allowable:.2f}" if a.allowable else "N/A"
                lines.append(f"  [Material Compare]  {status}  "
                             f"Peak={a.peak_value:.4f}  Allowable={allowable} MPa\n")
                if not report_path:
                    report_path = r['result'].get('report_path')

        lines.append(f"\nModel: {os.path.basename(self.model_path)}")
        lines.append("\nPPT Report exported via HyperView")

        self.parent.result_text.config(state=tk.NORMAL)
        self.parent.result_text.delete(1.0, tk.END)
        self.parent.result_text.insert(tk.END, "".join(lines))
        self.parent.result_text.config(state=tk.DISABLED)

        if report_path:
            self.parent.current_report_path = report_path
            self.parent.report_btn.config(state=tk.NORMAL)


def main():
    app = Application()

    def _signal_close(signum, frame):
        try:
            app.after(0, app._on_close)
        except Exception:
            app._on_close()

    signal.signal(signal.SIGTERM, _signal_close)
    signal.signal(signal.SIGINT, _signal_close)

    app.mainloop()


if __name__ == '__main__':
    main()
