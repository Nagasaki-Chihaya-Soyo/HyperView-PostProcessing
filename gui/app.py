import os
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.orchestrator import Orchestrator, State
from core.db_store import DBStore


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

    def _create_ui(self):
        self._create_status_bar()
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self._create_run_tab()
        self._create_parts_tab()
        self._create_mapping_tab()
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
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(toolbar, text="Add", command=self._add_part).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Edit", command=self._edit_part).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Delete", command=self._delete_part).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)
        ttk.Button(toolbar, text="Import CSV", command=self._import_parts_csv).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Export CSV", command=self._export_parts_csv).pack(side=tk.RIGHT, padx=2)

        columns = ('part_no', 'allowable_vm', 'safety_factor', 'units', 'name', 'notes')
        self.parts_tree = ttk.Treeview(tab, columns=columns, show='headings')

        self.parts_tree.heading('part_no', text='Parts ID')
        self.parts_tree.heading('allowable_vm', text='Permissible Stress')
        self.parts_tree.heading('safety_factor', text='Safety Factor')
        self.parts_tree.heading('units', text='Unit')
        self.parts_tree.heading('name', text='Name')
        self.parts_tree.heading('notes', text='Notes')

        self.parts_tree.column('part_no', width=100)
        self.parts_tree.column('allowable_vm', width=100)
        self.parts_tree.column('safety_factor', width=80)
        self.parts_tree.column('units', width=60)
        self.parts_tree.column('name', width=150)
        self.parts_tree.column('notes', width=200)

        scrollbar = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.parts_tree.yview)
        self.parts_tree.configure(yscrollcommand=scrollbar.set)

        self.parts_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=10)
        self._refresh_parts()

    def _refresh_parts(self):
        for item in self.parts_tree.get_children():
            self.parts_tree.delete(item)

        parts = self.db.get_all_parts()
        for p in parts:
            self.parts_tree.insert('', tk.END, values=(
                p['part_no'], p['allowable_vm'], p['safety_factor'],
                p['units'], p['name'], p['notes']
            ))

    def _add_part(self):
        dialog = PartDialog(self, title="Add Parts")
        if dialog.result:
            self.db.add_part(**dialog.result)
            self._refresh_parts()

    def _edit_part(self):
        selection = self.parts_tree.selection()
        if not selection:
            messagebox.showwarning(title="WARNING", message="SELECT A PART FIRST")
            return
        values = self.parts_tree.item(selection[0])['values']
        data = {
            'part_no': values[0],
            'allowable_vm': values[1],
            'safety_factor': values[2],
            'units': values[3],
            'name': values[4],
            'notes': values[5]
        }
        dialog = PartDialog(self, title="Edit Parts", data=data)
        if dialog.result:
            self.db.update_part(**dialog.result)
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

    def _create_mapping_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Map")
        toolbar = ttk.Frame(tab)
        toolbar.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(toolbar, text="Add", command=self._add_mapping).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Delete", command=self._delete_mapping).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Refresh", command=self._refresh_mappings).pack(side=tk.RIGHT, padx=2)

        columns = ('map_type', 'map_value', 'part_no')
        self.mapping_tree = ttk.Treeview(tab, columns=columns, show='headings')
        self.mapping_tree.heading('map_type', text='Map Type')
        self.mapping_tree.heading('map_value', text='Map Value')
        self.mapping_tree.heading('part_no', text='Part Number')

        self.mapping_tree.column('map_type', width=100)
        self.mapping_tree.column('map_value', width=200)
        self.mapping_tree.column('part_no', width=150)

        scrollbar = ttk.Scrollbar(tab, orient=tk.VERTICAL, command=self.mapping_tree.yview)
        self.mapping_tree.configure(yscrollcommand=scrollbar.set)

        self.mapping_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 10), pady=10)

        self._refresh_mappings()

    def _refresh_mappings(self):
        for item in self.mapping_tree.get_children():
            self.mapping_tree.delete(item)
        mappings = self.db.get_all_mappings()
        for m in mappings:
            self.mapping_tree.insert('', tk.END, values=(
                m['map_type'], m['map_value'], m['part_no']
            ))

    def _add_mapping(self):
        parts = self.db.get_all_parts()
        if not parts:
            messagebox.showwarning(title="WARNING", message="Add Parts Specification")
            return
        dialog = MappingDialog(self, title="Add Map", parts=parts)

        if dialog.result:
            self.db.add_mapping(**dialog.result)
            self._refresh_mappings()

    def _delete_mapping(self):
        selection = self.mapping_tree.selection()
        if not selection:
            messagebox.showwarning(title="WARNING", message="Select Map First")
            return
        if messagebox.askyesno(title="Confirm", message="Are you sure you want to delete the selected parts?This action can not be undone"):
            for sel in selection:
                values = self.mapping_tree.item(sel)['values']
                self.db.delete_mapping(values[0], values[1])
            self._refresh_mappings()

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
        self.orchestrator.shutdown()
        self.destroy()


class PartDialog(tk.Toplevel):
    def __init__(self, parent, title, data=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x300")
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

        ttk.Label(frame, text="Part Number").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.part_no_entry = ttk.Entry(frame, width=30)
        self.part_no_entry.grid(row=0, column=1, pady=5)
        if self.data.get('part_no'):
            self.part_no_entry.insert(0, self.data.get('part_no', ''))
            self.part_no_entry.config(state=tk.DISABLED)

        ttk.Label(frame, text="Allowable Stress").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.allowable_entry = ttk.Entry(frame, width=30)
        self.allowable_entry.grid(row=1, column=1, pady=5)
        self.allowable_entry.insert(0, self.data.get('allowable_vm', ''))

        ttk.Label(frame, text="Safety Factor").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.safety_factor = ttk.Entry(frame, width=30)
        self.safety_factor.grid(row=2, column=1, pady=5)
        self.safety_factor.insert(0, self.data.get('safety_factor', '1.0'))

        ttk.Label(frame, text="Unit").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.units_entry = ttk.Entry(frame, width=30)
        self.units_entry.grid(row=3, column=1, pady=5)
        self.units_entry.insert(0, self.data.get('units', 'Mpa'))

        ttk.Label(frame, text="Name").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.name_entry = ttk.Entry(frame, width=30)
        self.name_entry.grid(row=4, column=1, pady=5)
        self.name_entry.insert(0, self.data.get('name', ''))

        ttk.Label(frame, text="Notes").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.notes_entry = ttk.Entry(frame, width=30)
        self.notes_entry.grid(row=5, column=1, pady=5)
        self.notes_entry.insert(0, self.data.get('notes', ''))

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text="Confirm", command=self._ok).pack(side=tk.LEFT, padx=10)

    def _ok(self):
        try:
            self.result = {
                'part_no': self.part_no_entry.get().strip(),
                'allowable_vm': float(self.allowable_entry.get()),
                'safety_factor': float(self.safety_factor.get() or 1.0),
                'units': self.units_entry.get().strip() or 'MPa',
                'name': self.name_entry.get().strip(),
                'notes': self.notes_entry.get().strip()
            }
            if not self.result['part_no']:
                raise ValueError('Part Number is Required')
            self.destroy()
        except ValueError as e:
            messagebox.showerror(title="Error", message=str(e))


class MappingDialog(tk.Toplevel):

    def __init__(self, parent, title, parts):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x200")
        self.resizable(width=False, height=False)
        self.transient(parent)
        self.grab_set()

        self.result = None
        self.parts = parts
        self._create_ui()
        self.wait_window()

    def _create_ui(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Mapping Type").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.type_combo = ttk.Combobox(frame, values=['component', 'part', 'property'], width=27)
        self.type_combo.grid(row=0, column=1, pady=5)
        self.type_combo.current(0)

        ttk.Label(frame, text="Mapping Value:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.value_entry = ttk.Entry(frame, width=30)
        self.value_entry.grid(row=1, column=1, pady=5)

        ttk.Label(frame, text="Part Number:").grid(row=2, column=0, sticky=tk.W, pady=5)
        part_nos = [p['part_no'] for p in self.parts]
        self.part_combo = ttk.Combobox(frame, values=part_nos, width=27)
        self.part_combo.grid(row=2, column=1, pady=5)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text="Confirm", command=self._ok).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.LEFT, padx=10)

    def _ok(self):
        map_type = self.type_combo.get()
        map_value = self.value_entry.get().strip()
        part_no = self.part_combo.get().strip()
        if not map_value or not part_no:
            messagebox.showerror(title="Error", message="Enter Full Details")
            return
        self.result = {
            'map_type': map_type,
            'map_value': map_value,
            'part_no': part_no
        }
        self.destroy()


class ContourOptionDialog(tk.Toplevel):
    """云图参数设置对话框"""

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

    def __init__(self, parent, orchestrator=None, on_execute=None):
        super().__init__(parent)
        self.title("Contour Settings")
        self.geometry("450x250")
        self.resizable(width=False, height=False)
        self.transient(parent)
        self.grab_set()

        self.orchestrator = orchestrator
        self.on_execute = on_execute
        self.result = None
        self._create_ui()
        self.wait_window()

    def _create_ui(self):
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Category:").grid(row=0, column=0, sticky=tk.W, pady=8)
        cats = list(self.CATEGORIES.keys())
        self.cat_var = tk.StringVar(value=cats[0])
        self.cat_cb = ttk.Combobox(frame, textvariable=self.cat_var, values=cats, width=35, state="readonly")
        self.cat_cb.grid(row=0, column=1, pady=8, padx=5)
        self.cat_cb.bind("<<ComboboxSelected>>", self._on_cat_changed)

        ttk.Label(frame, text="Data Type:").grid(row=1, column=0, sticky=tk.W, pady=8)
        self.type_var = tk.StringVar()
        self.type_cb = ttk.Combobox(frame, textvariable=self.type_var, width=35, state="readonly")
        self.type_cb.grid(row=1, column=1, pady=8, padx=5)
        self.type_cb.bind("<<ComboboxSelected>>", self._on_type_changed)

        ttk.Label(frame, text="Component:").grid(row=2, column=0, sticky=tk.W, pady=8)
        self.comp_var = tk.StringVar()
        self.comp_cb = ttk.Combobox(frame, textvariable=self.comp_var, width=35, state="readonly")
        self.comp_cb.grid(row=2, column=1, pady=8, padx=5)

        self._update_types()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="Confirm", command=self._on_confirm, width=12).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Apply", command=self._on_apply, width=12).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy, width=12).pack(side=tk.LEFT, padx=10)

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
        """执行 apply_contour + report Run"""
        if not self.orchestrator:
            return
        result_type = self.type_var.get()
        component = self.comp_var.get()
        label = f"{result_type} - {component}"
        config = {'type': result_type, 'component': component}

        def run():
            print(f"[ContourOptionDialog] Executing apply_contour: {label}")
            self.orchestrator.apply_contour(result_type, component, label)
            print("[ContourOptionDialog] apply_contour done, now calling report_run")
            self.orchestrator.report_run()
            print("[ContourOptionDialog] report_run done")
            if self.on_execute:
                self.on_execute(config)
            if close_after:
                self.after(0, self.destroy)

        threading.Thread(target=run, daemon=True).start()

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

        self.chk_contour = tk.BooleanVar(value=True)
        self.chk_stress_peak = tk.BooleanVar(value=False)
        self.chk_compare = tk.BooleanVar(value=False)

        row1 = ttk.Frame(opt_frame)
        row1.pack(fill=tk.X, pady=4)
        ttk.Checkbutton(row1, text="Plot Contour",
                        variable=self.chk_contour).pack(side=tk.LEFT)
        self.opt_btn_contour = ttk.Button(row1, text="Option", width=8, state=tk.DISABLED,
                                          command=self._open_contour_option)
        self.opt_btn_contour.pack(side=tk.RIGHT)
        ttk.Label(opt_frame, text="    Plot contour on the model",
                  foreground='gray').pack(anchor=tk.W)

        row2 = ttk.Frame(opt_frame)
        row2.pack(fill=tk.X, pady=4)
        ttk.Checkbutton(row2, text="Stress Peak Analysis",
                        variable=self.chk_stress_peak).pack(side=tk.LEFT)
        self.opt_btn_stress = ttk.Button(row2, text="Option", width=8, state=tk.DISABLED,
                                          command=self._run_stress_peak)
        self.opt_btn_stress.pack(side=tk.RIGHT)
        ttk.Label(opt_frame, text="    Find maximum Von Mises stress location and value",
                  foreground='gray').pack(anchor=tk.W)

        row3 = ttk.Frame(opt_frame)
        row3.pack(fill=tk.X, pady=4)
        ttk.Checkbutton(row3, text="Compare with Material Standards",
                        variable=self.chk_compare).pack(side=tk.LEFT)
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
        self.run_btn = ttk.Button(btn_frame, text="Run", command=self._export_report, width=15, state=tk.DISABLED)
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
        """Create Report 完成后解锁 Option 按钮和 Run/Close"""
        self.run_btn.config(state=tk.NORMAL)
        self.close_btn.config(state=tk.NORMAL)
        if self.chk_contour.get():
            self.opt_btn_contour.config(state=tk.NORMAL)
        if self.chk_stress_peak.get():
            self.opt_btn_stress.config(state=tk.NORMAL)
        if self.chk_compare.get():
            self.opt_btn_compare.config(state=tk.NORMAL)
        self._set_status("Step 2: Click Option to configure, then Step 3: Run to export PPT")

    # ── Step 2: 自由配置分析项 ──

    def _open_contour_option(self):
        """打开云图参数设置对话框，Apply/Confirm 都会执行 hwc 指令"""
        ContourOptionDialog(self, orchestrator=self.orchestrator,
                            on_execute=self._on_contour_executed)

    def _on_contour_executed(self, config):
        """每次 Apply/Confirm 执行后的回调"""
        self._completed_results.append({
            'type': 'contour', 'success': True, 'config': config
        })

    def _run_stress_peak(self):
        """执行 Stress Peak 分析 + report Run"""
        self.opt_btn_stress.config(state=tk.DISABLED)
        self._set_status("Running stress peak analysis...")

        def run():
            result = self.orchestrator.run_analysis(self.model_path, self.result_path)
            if result and result.get('success'):
                self.orchestrator.report_run()
                self.after(0, lambda: self._completed_results.append({
                    'type': 'stress_peak', 'success': True, 'result': result
                }))
            self.after(0, lambda: self.opt_btn_stress.config(state=tk.NORMAL))
            self.after(0, lambda: self._set_status("Stress peak done. Continue or Run to export."))

        threading.Thread(target=run, daemon=True).start()

    def _run_compare(self):
        """执行 Material Compare 分析 + report Run"""
        self.opt_btn_compare.config(state=tk.DISABLED)
        self._set_status("Comparing with material standards...")

        def run():
            result = self.orchestrator.run_analysis(self.model_path, self.result_path)
            if result and result.get('success'):
                self.orchestrator.report_run()
                self.after(0, lambda: self._completed_results.append({
                    'type': 'compare', 'success': True, 'result': result
                }))
            self.after(0, lambda: self.opt_btn_compare.config(state=tk.NORMAL))
            self.after(0, lambda: self._set_status("Compare done. Continue or Run to export."))

        threading.Thread(target=run, daemon=True).start()

    # ── Step 3: 导出 PPT ──

    def _export_report(self):
        """Step 3: 导出最终 PPT"""
        self.run_btn.config(state=tk.DISABLED)
        self.close_btn.config(state=tk.DISABLED)
        self._set_status("Step 3: Exporting report...")

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

            elif r['type'] == 'stress_peak':
                a = r['result']['analysis']
                lines.append(f"  [Stress Peak]  {a.peak_value:.4f} MPa  (Entity {a.peak_entity_id})\n")
                if not report_path:
                    report_path = r['result'].get('report_path')

            elif r['type'] == 'compare':
                a = r['result']['analysis']
                status = "PASSED" if a.passed else "FAILED"
                allowable = f"{a.allowable:.2f}" if a.allowable else "N/A"
                lines.append(f"  [Material Compare]  {status}  "
                             f"Peak={a.peak_value:.4f}  Allowable={allowable} MPa\n")
                if not report_path:
                    report_path = r['result'].get('report_path')

        lines.append(f"\nModel: {os.path.basename(self.model_path)}")
        lines.append("\nPPT Report exported to C:/Temp/HyperView_Report")

        self.parent.result_text.config(state=tk.NORMAL)
        self.parent.result_text.delete(1.0, tk.END)
        self.parent.result_text.insert(tk.END, "".join(lines))
        self.parent.result_text.config(state=tk.DISABLED)

        if report_path:
            self.parent.current_report_path = report_path
            self.parent.report_btn.config(state=tk.NORMAL)


def main():
    app = Application()
    app.mainloop()


if __name__ == '__main__':
    main()
