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
        ttk.Button(file_frame, text="View...", command=self._browse_model).grid(row=0, column=2, pady=5)

        ttk.Label(file_frame, text="Result Files:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.result_entry = ttk.Entry(file_frame, width=60)
        self.result_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(file_frame, text="View...", command=self._browse_result).grid(row=1, column=2, pady=5)

        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        self.load_btn = ttk.Button(btn_frame, text="Load Model", padding=10, command=self._load_model)
        self.load_btn.pack(side=tk.LEFT, padx=10)

        self.run_btn = ttk.Button(btn_frame, text="Analysing", padding=10, command=self._run_analysis)
        self.run_btn.pack(side=tk.LEFT, padx=20)

        self.progress = ttk.Progressbar(btn_frame, mode='indeterminate', length=200)
        self.progress.pack(side=tk.LEFT, padx=20)

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

    def _browse_result(self):
        filetypes = [
            ("Output Files", "*.out"),
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
        if not model_path:
            messagebox.showwarning(title="WARNING!", message="You Need to Select model files")
            return
        if self.orchestrator.state != State.AGENT_READY:
            messagebox.showwarning(title="WARNING!", message="Unable to Start HyperView")
            return
        result_path = self.result_entry.get().strip()
        # 弹出分析对话框
        AnalysisDialog(self, self.orchestrator, model_path, result_path)

    def _load_model(self):
        model_path = self.model_entry.get().strip()
        if not model_path:
            messagebox.showwarning(title="WARNING!", message="You Need to Select model files")
            return
        if self.orchestrator.state != State.AGENT_READY:
            messagebox.showwarning(title="WARNING!", message="HyperView is not ready")
            return
        result_path = self.result_entry.get().strip()
        self.load_btn.config(state=tk.DISABLED)
        self.progress.start()
        def load():
            success = self.orchestrator.load_model(model_path, result_path)
            self.after(0, lambda: self._on_model_loaded(success))
        threading.Thread(target=load, daemon=True).start()

    def _on_model_loaded(self, success: bool):
        self.progress.stop()
        self.load_btn.config(state=tk.NORMAL)
        if success:
            messagebox.showinfo(title="Success", message="Model loaded successfully")
        else:
            messagebox.showerror(title="Error", message="Failed to load model")

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


class AnalysisDialog(tk.Toplevel):
    """分析功能对话框"""

    def __init__(self, parent, orchestrator, model_path, result_path=""):
        super().__init__(parent)
        self.title("Analysis Options")
        self.geometry("500x400")
        self.resizable(width=False, height=False)
        self.transient(parent)
        self.grab_set()

        self.parent = parent
        self.orchestrator = orchestrator
        self.model_path = model_path
        self.result_path = result_path
        self.result = None

        self._create_ui()

    def _create_ui(self):
        # 主容器
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 标题
        title_frame = ttk.Frame(main_frame, padding=10)
        title_frame.pack(fill=tk.X)
        ttk.Label(title_frame, text="Select Analysis Function", font=('Arial', 12, 'bold')).pack()

        # 模型信息
        info_frame = ttk.LabelFrame(main_frame, text="Model Information", padding=10)
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(info_frame, text=f"Model: {os.path.basename(self.model_path)}", wraplength=450).pack(anchor=tk.W)
        if self.result_path:
            ttk.Label(info_frame, text=f"Result: {os.path.basename(self.result_path)}", wraplength=450).pack(anchor=tk.W)

        # 功能按钮区域
        func_frame = ttk.LabelFrame(main_frame, text="Analysis Functions", padding=10)
        func_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 应力分析按钮
        stress_btn = ttk.Button(func_frame, text="Stress Peak Analysis (Von Mises)",
                                command=self._analyze_stress_peak, width=40)
        stress_btn.pack(pady=10)
        ttk.Label(func_frame, text="Find maximum Von Mises stress location and value",
                  foreground='gray').pack()

        ttk.Separator(func_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # 云图导出按钮
        contour_btn = ttk.Button(func_frame, text="Export Contour Image",
                                 command=self._export_contour, width=40)
        contour_btn.pack(pady=10)
        ttk.Label(func_frame, text="Export stress contour plot as image",
                  foreground='gray').pack()

        ttk.Separator(func_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # 材料对比按钮
        compare_btn = ttk.Button(func_frame, text="Compare with Material Standards",
                                 command=self._compare_material, width=40)
        compare_btn.pack(pady=10)
        ttk.Label(func_frame, text="Compare peak stress with allowable values from database",
                  foreground='gray').pack()

        # 底部区域 (从下往上: 状态栏 -> 进度条 -> 关闭按钮)
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # 状态栏
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(bottom_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=5)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # 进度条
        self.progress = ttk.Progressbar(bottom_frame, mode='indeterminate', length=480)
        self.progress.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=5)

        # 关闭按钮
        btn_frame = ttk.Frame(bottom_frame, padding=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(btn_frame, text="Close", command=self.destroy, width=15).pack(side=tk.RIGHT, padx=5)

    def _set_status(self, msg):
        self.status_var.set(msg)
        self.update()

    def _analyze_stress_peak(self):
        """分析应力峰值"""
        self._set_status("Analyzing stress peak...")
        self.progress.start()

        def run():
            result = self.orchestrator.run_analysis(self.model_path, self.result_path)
            self.after(0, lambda: self._on_analysis_complete(result, "stress_peak"))

        threading.Thread(target=run, daemon=True).start()

    def _export_contour(self):
        """导出云图"""
        self._set_status("Exporting contour image...")
        self.progress.start()

        def run():
            result = self.orchestrator.run_analysis(self.model_path, self.result_path)
            self.after(0, lambda: self._on_analysis_complete(result, "contour"))

        threading.Thread(target=run, daemon=True).start()

    def _compare_material(self):
        """与材料标准对比"""
        self._set_status("Comparing with material standards...")
        self.progress.start()

        def run():
            result = self.orchestrator.run_analysis(self.model_path, self.result_path)
            self.after(0, lambda: self._on_analysis_complete(result, "compare"))

        threading.Thread(target=run, daemon=True).start()

    def _on_analysis_complete(self, result, analysis_type):
        """分析完成回调"""
        self.progress.stop()

        if result is None:
            self._set_status("Analysis failed!")
            messagebox.showerror(title="Error", message="Analysis failed. Check the log for details.")
            return

        self._set_status("Analysis complete!")
        self.result = result

        # 根据分析类型显示不同的结果
        if analysis_type == "stress_peak":
            analysis = result['analysis']
            msg = f"""Stress Peak Analysis Result:

Peak Value: {analysis.peak_value:.4f} MPa
Entity ID: {analysis.peak_entity_id}
Location: {analysis.peak_coords}

{analysis.message}"""
            messagebox.showinfo(title="Stress Peak Analysis", message=msg)

        elif analysis_type == "contour":
            images = result.get('images', [])
            if images:
                messagebox.showinfo(title="Contour Export",
                                    message=f"Contour image saved to:\n{images[0]}")
            else:
                messagebox.showwarning(title="Contour Export", message="No image was generated.")

        elif analysis_type == "compare":
            analysis = result['analysis']
            status = "PASSED" if analysis.passed else "FAILED"
            msg = f"""Material Comparison Result:

Status: {status}
Peak Value: {analysis.peak_value:.4f} MPa
Part No: {analysis.part_no or 'Not Found'}
Allowable: {analysis.allowable:.2f if analysis.allowable else 'N/A'} MPa
Margin: {analysis.margin:.2f if analysis.margin else 'N/A'} MPa
Ratio: {analysis.ratio:.2% if analysis.ratio else 'N/A'}

Report: {result['report_path']}"""
            messagebox.showinfo(title="Material Comparison", message=msg)

        # 通知父窗口更新
        if hasattr(self.parent, '_show_result'):
            self.parent._show_result(result)


def main():
    app = Application()
    app.mainloop()


if __name__ == '__main__':
    main()
