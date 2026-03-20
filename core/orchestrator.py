import os
import json
import time
from enum import Enum, auto
from typing import Optional, Callable, Dict, Any
from datetime import datetime
from .hv_process import HVProcess
from .hv_bridge import HVBridge, ReadySignal
from .db_store import DBStore
from .analysis import Analyzer
from .report_html import HTMLReporter
from .report_pptx import PPTXReporter
from .logging_util import log_info, log_error, setup_logger


class State(Enum):
    IDLE = auto()
    STARTING = auto()
    AGENT_READY = auto()
    RUNNING = auto()
    FAILED = auto()
    EXITED = auto()


class Orchestrator:

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.base_dir = base_dir
        config_path = os.path.join(base_dir, 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.inbox_dir = os.path.join(base_dir, self.config['workdir']['inbox'])
        self.outbox_dir = os.path.join(base_dir, self.config['workdir']['outbox'])
        # 统一输出根目录（可通过 config.json 的 output.root 配置）
        self.output_root = self.config.get('output', {}).get('root', 'C:/HyperView-PostProcessing')
        self.output_dir = self.output_root  # 向后兼容别名
        # 按功能划分子目录
        self.runs_dir = os.path.join(self.output_root, "runs")
        self.reports_dir = os.path.join(self.output_root, "reports")
        self.captures_dir = os.path.join(self.output_root, "captures")
        self.csv_dir = os.path.join(self.output_root, "csv")
        self.png_dir = os.path.join(self.output_root, "png")
        self.logs_dir = os.path.join(self.output_root, "logs")
        self.hwc_template_dir = os.path.join(self.output_root, "hwc_template")
        for d in [self.inbox_dir, self.outbox_dir,
                  self.runs_dir, self.reports_dir, self.captures_dir,
                  self.csv_dir, self.png_dir, self.logs_dir, self.hwc_template_dir]:
            os.makedirs(d, exist_ok=True)
        self.hv_process = HVProcess(self.config['hyperview'])
        self.bridge = HVBridge(self.inbox_dir, self.outbox_dir,
                               self.config['hyperview'].get('job_timeout', 300))
        self.ready_signal = ReadySignal(os.path.join(base_dir, 'workdir/ready.flag'))
        self.db = DBStore(os.path.join(base_dir, self.config['database']['path']))
        self.analyzer = Analyzer(self.db)
        self.reporter = HTMLReporter()
        self.pptx_reporter = PPTXReporter()
        self.agent_mode: str = "tcl"          # "tcl" or "hwc"
        self.state = State.IDLE
        self.current_job_id: Optional[str] = None
        self.on_state_change = None
        self.on_log = None
        setup_logger(self.logs_dir)

    def _set_state(self, new_state: State):
        old_state = self.state
        self.state = new_state
        log_info(f"状态变更:{old_state.name}->{new_state.name}")
        if self.on_state_change:
            self.on_state_change(new_state)

    def _log(self, msg: str):
        log_info(msg)
        if self.on_log:
            self.on_log(msg)

    def _generate_agent(self, template_name: str, output_name: str) -> str:
        """从模板文件生成 agent 脚本，替换路径占位符。"""
        agent_dir = os.path.join(self.base_dir, 'hv_agent')
        os.makedirs(agent_dir, exist_ok=True)
        template_path = os.path.join(agent_dir, template_name)
        agent_path = os.path.join(agent_dir, output_name)
        with open(template_path, 'r', encoding='utf-8') as f:
            code = f.read()
        code = code.replace('{{READY_FILE}}', self.ready_signal.ready_file.replace('\\', '/'))
        code = code.replace('{{INBOX_DIR}}', self.inbox_dir.replace('\\', '/'))
        code = code.replace('{{OUTBOX_DIR}}', self.outbox_dir.replace('\\', '/'))
        code = code.replace('{{CAPTURE_DIR}}', self.captures_dir.replace('\\', '/'))
        code = code.replace('{{REPORT_DIR}}', self.hwc_template_dir.replace('\\', '/'))
        with open(agent_path, 'w', encoding='utf-8') as f:
            f.write(code)
        return agent_path

    def _generate_agent_tcl(self) -> str:
        """生成纯 TCL/HWI agent 脚本（不含 hwc 命令）。"""
        return self._generate_agent('agent_tcl_template.tcl', 'agent_tcl.tcl')

    def _generate_agent_hwc(self) -> str:
        """生成 HWC agent 脚本（包含完整的 hwc 命令实现）。"""
        return self._generate_agent('agent_hwc_template.tcl', 'agent_hwc.tcl')

    def start_hyperview(self, agent_mode: str = "tcl") -> bool:
        if self.state == State.AGENT_READY and not self.hv_process.is_running():
            self._set_state(State.IDLE)
        if self.state not in (State.IDLE, State.FAILED, State.EXITED):
            self._log("Unable to Start Now")
            return False
        self._set_state(State.STARTING)
        self.ready_signal.clear()
        self.bridge.clear_inbox()
        self.bridge.clear_outbox()
        # 先检测版本
        if not self.hv_process.ensure_shortcut_detected():
            self._set_state(State.FAILED)
            self._log("HyperView shortcut not found")
            return False
        if self.hv_process.version:
            self._log(f"HyperView Version: {self.hv_process.version}")
        else:
            self._log("HyperView Version: unknown")
        # 记录模式，供报告方法判断走 HWC 还是 Python PPT
        self.agent_mode = agent_mode
        # 根据模式生成对应 agent
        if agent_mode == "hwc":
            agent_path = self._generate_agent_hwc()
        else:
            agent_path = self._generate_agent_tcl()
        self._log(f"Generate Agent ({agent_mode.upper()}): {agent_path}")
        if not self.hv_process.start(agent_path):
            return False
        self._log("Waiting HyperView Agent Ready...")
        timeout = self.config['hyperview'].get('startup_timeout')
        if self.ready_signal.wait(timeout):
            self._set_state(State.AGENT_READY)
            self._log("Hyperview is Ready")
            return True
        else:
            self._set_state(State.FAILED)
            self._log("HyperView TimeOut")
            return False

    def run_analysis(self, model_path: str, result_path: str = "") -> Optional[Dict[str, Any]]:
        self._log(f"run_analysis called with model_path={model_path}")
        if self.state != State.AGENT_READY:
            self._log("HyperView NOT Ready,Start First")
            return None
        self._set_state(State.RUNNING)
        try:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_dir = os.path.join(self.runs_dir, run_id)
            os.makedirs(run_dir, exist_ok=True)
            self._log(f"Begin Analysing:{model_path}")
            self._log(f"Output dir:{run_dir}")
            result = self.bridge.send_job(cmd="export_contour_and_peak_vm", params={
                "model_path": model_path.replace('\\', '/'),
                "result_path": result_path.replace('\\', '/') if result_path else "",
                "output_dir": run_dir.replace('\\', '/')
            })
            if not result.get('success', False):
                self._log(f"Tasks Failed:{result.get('error', 'Unknown')}")
                return None
            peak_data = result.get('peak', {})
            analysis_result = self.analyzer.analyze(peak_data)
            report_path = os.path.join(run_dir, 'report.html')
            self.reporter.generate(
                results=[analysis_result],
                images=result.get('images', []),
                model_path=model_path,
                result_path=result_path,
                output_path=report_path
            )
            self._log(f"Analyzing Complete,Report:{report_path}")
            return {
                'success': True,
                'analysis': analysis_result,
                'peak_data': peak_data,
                'report_path': report_path,
                'run_dir': run_dir
            }
        except Exception as e:
            self._log(f"Analysis error: {str(e)}")
            return None
        finally:
            # 确保状态总是恢复到AGENT_READY
            self._set_state(State.AGENT_READY)

    def display_contour(self, model_path: str, result_path: str = "") -> Optional[Dict[str, Any]]:
        """仅显示云图，不进行峰值分析"""
        self._log(f"display_contour called with model_path={model_path}")
        if self.state != State.AGENT_READY:
            self._log("HyperView NOT Ready, Start First")
            return None
        self._set_state(State.RUNNING)
        try:
            self._log(f"Displaying contour for: {model_path}")
            result = self.bridge.send_job(cmd="display_contour", params={
                "model_path": model_path.replace('\\', '/'),
                "result_path": result_path.replace('\\', '/') if result_path else ""
            })
            if not result.get('success', False):
                self._log(f"Display contour failed: {result.get('error', 'Unknown')}")
                return None
            self._log("Contour displayed successfully")
            return {
                'success': True,
                'message': 'Contour displayed'
            }
        except Exception as e:
            self._log(f"Display contour error: {str(e)}")
            return None
        finally:
            self._set_state(State.AGENT_READY)

    def apply_contour(self, result_type: str, component: str, label: str = "") -> Optional[Dict[str, Any]]:
        """按用户选择的 type/component 显示云图并添加 report slide"""
        if not label:
            label = f"{result_type} - {component}"
        self._log(f"apply_contour: type={result_type}, component={component}, label={label}")
        if self.state != State.AGENT_READY:
            self._log("HyperView NOT Ready, Start First")
            return None
        self._set_state(State.RUNNING)
        try:
            result = self.bridge.send_job(cmd="apply_contour", params={
                "result_type": result_type,
                "result_component": component,
                "label": label
            })
            if not result.get('success', False):
                self._log(f"apply_contour failed: {result.get('error', 'Unknown')}")
                return None
            self._log("Contour applied successfully")
            # TCL 模式：额外截图并加入 PPT
            if self.agent_mode != "hwc":
                self._capture_and_add_slide(label)
            return {'success': True}
        except Exception as e:
            self._log(f"apply_contour error: {str(e)}")
            return None
        finally:
            self._set_state(State.AGENT_READY)

    def _capture_and_add_slide(self, label: str):
        """TCL 模式下截取 HyperView 窗口并添加到 python-pptx 报告。"""
        img_dir = self.captures_dir
        os.makedirs(img_dir, exist_ok=True)
        safe_label = label.replace(" ", "_").replace("/", "_")
        img_path = os.path.join(img_dir, f"{safe_label}.png")
        # 注意：此时状态已是 RUNNING，不能调用 capture_image（它会检查 AGENT_READY）
        # 直接通过 bridge 发送 capture_image
        cap_result = self.bridge.send_job(cmd="capture_image", params={
            "output_path": img_path.replace('\\', '/')
        })
        if cap_result.get('success', False):
            actual_path = cap_result.get('image_path', img_path)
            self.pptx_reporter.add_image_slide(label, actual_path)
            self._log(f"Slide captured: {actual_path}")
        else:
            self._log(f"Capture failed: {cap_result.get('error', 'Unknown')}")

    def capture_image(self, output_path: str) -> Optional[str]:
        """截取 HyperView 当前窗口保存到指定路径。返回实际路径或 None。"""
        if self.state != State.AGENT_READY:
            self._log("HyperView is not ready")
            return None
        self._set_state(State.RUNNING)
        try:
            result = self.bridge.send_job(cmd="capture_image", params={
                "output_path": output_path.replace('\\', '/')
            })
            if result.get('success', False):
                path = result.get('image_path', output_path)
                self._log(f"Image captured: {path}")
                return path
            self._log(f"Capture image failed: {result.get('error', 'Unknown')}")
            return None
        finally:
            self._set_state(State.AGENT_READY)

    def report_run_position(self, label: str) -> bool:
        """执行 hwc report Report run position=$label"""
        if self.state != State.AGENT_READY:
            self._log(f"report_run_position: HyperView is not ready (state={self.state})")
            return False
        self._set_state(State.RUNNING)
        try:
            self._log(f"Running report position={label}...")
            result = self.bridge.send_job(cmd="report_run_position", params={
                "label": label
            })
            if result.get('success', False):
                self._log("Report run position completed")
                return True
            else:
                self._log(f"Report run position failed: {result.get('error', 'Unknown')}")
                return False
        finally:
            self._set_state(State.AGENT_READY)

    def capture_slide(self, label: str) -> bool:
        """Add slide and run position: hwc report Report add slide ... + run position=$label"""
        if self.state != State.AGENT_READY:
            self._log(f"capture_slide: HyperView is not ready (state={self.state})")
            return False
        self._set_state(State.RUNNING)
        try:
            self._log(f"Capture slide: {label}")
            if self.agent_mode == "hwc":
                result = self.bridge.send_job(cmd="capture_slide", params={
                    "label": label
                })
                if result.get('success', False):
                    self._log(f"Capture slide completed: {label}")
                    return True
                else:
                    self._log(f"Capture slide failed: {result.get('error', 'Unknown')}")
                    return False
            else:
                # TCL 模式：截图并添加到 PPT
                self._capture_and_add_slide(label)
                return True
        finally:
            self._set_state(State.AGENT_READY)


    def report_run(self) -> bool:
        """执行 hwc report Report Run"""
        if self.state != State.AGENT_READY:
            self._log(f"report_run: HyperView is not ready (state={self.state})")
            return False
        self._set_state(State.RUNNING)
        try:
            self._log("Running report...")
            result = self.bridge.send_job(cmd="report_run", params={})
            if result.get('success', False):
                self._log("Report run completed")
                return True
            else:
                self._log(f"Report run failed: {result.get('error', 'Unknown')}")
                return False
        finally:
            self._set_state(State.AGENT_READY)

    def report_export(self) -> bool:
        """导出报告。TCL 模式用 python-pptx 保存，HWC 模式通过 TCL 控件触发。"""
        if self.state != State.AGENT_READY:
            self._log("HyperView is not ready")
            return False
        self._set_state(State.RUNNING)
        try:
            self._log("Exporting report...")
            if self.agent_mode == "hwc":
                result = self.bridge.send_job(cmd="report_export", params={})
                if result.get('success', False):
                    self._log("Report exported successfully")
                    return True
                else:
                    self._log(f"Report export failed: {result.get('error', 'Unknown')}")
                    return False
            else:
                # TCL 模式：用 python-pptx 导出
                pptx_dir = self.reports_dir
                os.makedirs(pptx_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                pptx_path = os.path.join(pptx_dir, f"Report_{timestamp}.pptx")
                self.pptx_reporter.export(pptx_path)
                self._log(f"Report exported (python-pptx): {pptx_path}")
                return True
        except Exception as e:
            self._log(f"Report export error: {e}")
            return False
        finally:
            self._set_state(State.AGENT_READY)

    def create_report(self) -> bool:
        """创建报告。TCL 模式用 python-pptx，HWC 模式用 hwc report 指令。"""
        if self.state != State.AGENT_READY:
            self._log("HyperView is not ready")
            return False
        self._log("Creating report presentation...")
        if self.agent_mode == "hwc":
            result = self.bridge.send_job(cmd="create_report", params={})
            if result.get('success', False):
                self._log("Report created successfully")
                return True
            else:
                self._log(f"Report creation failed: {result.get('error', 'Unknown')}")
                return False
        else:
            # TCL 模式：初始化 python-pptx 报告
            self.pptx_reporter.create()
            self._log("Report created (python-pptx)")
            return True

    def hotspot_delete(self, hotspot_name: str) -> bool:
        """Delete a hotspot: hwc kpi hotspot delete <name>"""
        if self.state != State.AGENT_READY:
            self._log(f"HyperView is not ready (state={self.state})")
            return False
        self._set_state(State.RUNNING)
        try:
            self._log(f"Deleting hotspot: {hotspot_name}")
            result = self.bridge.send_job(cmd="hotspot_delete", params={
                "hotspot_name": hotspot_name,
            })
            if result.get('success', False):
                self._log(f"Hotspot {hotspot_name} deleted")
                return True
            else:
                self._log(f"Hotspot delete failed: {result.get('error', 'Unknown')}")
                return False
        finally:
            self._set_state(State.AGENT_READY)

    def hotspot_find(self, hotspot_name: str, label: str = "") -> bool:
        """Create hotspot, find hotspots, review, and optionally capture slide"""
        print(f"[hotspot_find] called: name={hotspot_name}, label={label}, state={self.state}")
        if self.state != State.AGENT_READY:
            self._log(f"HyperView is not ready (state={self.state})")
            return False
        self._set_state(State.RUNNING)
        try:
            self._log(f"Finding hotspot: {hotspot_name}")
            result = self.bridge.send_job(cmd="hotspot_find", params={
                "hotspot_name": hotspot_name,
                "label": label,
            })
            print(f"[hotspot_find] result={result}")
            if result.get('success', False):
                self._log(f"Hotspot {hotspot_name} found successfully")
                return True
            else:
                self._log(f"Hotspot find failed: {result.get('error', 'Unknown')}")
                return False
        finally:
            self._set_state(State.AGENT_READY)

    def hotspot_navigate(self, direction: str) -> bool:
        """Navigate hotspots: 'previous' or 'next'"""
        print(f"[hotspot_navigate] called: direction={direction}, state={self.state}")
        if self.state != State.AGENT_READY:
            self._log("HyperView is not ready")
            return False
        self._set_state(State.RUNNING)
        try:
            self._log(f"Hotspot navigate: {direction}")
            result = self.bridge.send_job(cmd="hotspot_navigate", params={
                "label": direction
            })
            print(f"[hotspot_navigate] result={result}")
            if result.get('success', False):
                self._log(f"Hotspot navigate {direction} done")
                return True
            else:
                self._log(f"Hotspot navigate failed: {result.get('error', 'Unknown')}")
                return False
        finally:
            self._set_state(State.AGENT_READY)

    def hotspot_display_viewmode(self, mode: str, option: str) -> bool:
        """Execute: hwc kpi hotspot display viewmode <mode> <option>"""
        print(f"[hotspot_display_viewmode] mode={mode}, option={option}, state={self.state}")
        if self.state != State.AGENT_READY:
            self._log("HyperView is not ready")
            return False
        self._set_state(State.RUNNING)
        try:
            self._log(f"Hotspot display viewmode: {mode} {option}")
            result = self.bridge.send_job(cmd="hotspot_display_viewmode", params={
                "label": mode,
                "viewmode_option": option,
            })
            print(f"[hotspot_display_viewmode] result={result}")
            if result.get('success', False):
                self._log(f"Hotspot display viewmode {mode} {option} done")
                return True
            else:
                self._log(f"Hotspot display viewmode failed: {result.get('error', 'Unknown')}")
                return False
        finally:
            self._set_state(State.AGENT_READY)

    def setup_view(self) -> bool:
        """执行 view orientation iso 和 animate frame last"""
        if self.state != State.AGENT_READY:
            self._log("HyperView is not ready")
            return False
        self._log("Setting up view: iso orientation, last frame")
        result = self.bridge.send_job(cmd="setup_view", params={})
        if result.get('success', False):
            self._log("View setup completed")
            return True
        else:
            self._log(f"View setup failed: {result.get('error', 'Unknown')}")
            return False

    def load_model(self, model_path: str, result_path: str = "") -> bool:
        if self.state != State.AGENT_READY:
            self._log("HyperView is not ready")
            return False
        self._log(f"Loading Model:{model_path}")
        result = self.bridge.send_job(cmd="load_model", params={
            "model_path": model_path.replace('\\', '/'),
            "result_path": result_path.replace('\\', '/') if result_path else ""
        })
        if result.get('success', False):
            self._log("Model loaded successfully")
            return True
        else:
            self._log(f"Load failed:{result.get('error', 'Unknown')}")
            return False

    def add_slide_one_image_only(self, label: str, position: str, file_path: str) -> bool:
        """添加纯图片幻灯片。TCL 模式直接加入 python-pptx，HWC 模式发 hwc 命令。"""
        if self.state != State.AGENT_READY:
            self._log("HyperView is not ready")
            return False
        self._set_state(State.RUNNING)
        try:
            self._log(f"add_slide_one_image_only: label={label}")
            if self.agent_mode == "hwc":
                result = self.bridge.send_job(cmd="add_slide_one_image_only", params={
                    "label": label,
                    "position": position,
                    "file_path": file_path.replace('\\', '/'),
                })
                if result.get('success', False):
                    self._log("add_slide_one_image_only completed")
                    return True
                else:
                    self._log(f"add_slide_one_image_only failed: {result.get('error', 'Unknown')}")
                    return False
            else:
                # TCL 模式：直接添加到 python-pptx
                self.pptx_reporter.add_image_only_slide(label, file_path)
                self._log(f"add_slide_one_image_only (python-pptx): {label}")
                return True
        except Exception as e:
            self._log(f"add_slide_one_image_only error: {e}")
            return False
        finally:
            self._set_state(State.AGENT_READY)

    def plot_contour_only(self, result_type: str, component: str) -> bool:
        """hwc result scalar edit + plot — no report slide."""
        if self.state != State.AGENT_READY:
            self._log("HyperView NOT Ready")
            return False
        self._set_state(State.RUNNING)
        try:
            self._log(f"plot_contour_only: {result_type}/{component}")
            result = self.bridge.send_job(cmd="plot_contour_only", params={
                "result_type": result_type,
                "result_component": component,
            })
            if result.get('success', False):
                self._log("Contour plotted")
                return True
            self._log(f"plot_contour_only failed: {result.get('error', 'Unknown')}")
            return False
        except Exception as e:
            self._log(f"plot_contour_only error: {e}")
            return False
        finally:
            self._set_state(State.AGENT_READY)

    def export_hotspot_csv(self, hotspot_name: str, csv_path: str) -> Optional[Dict[str, Any]]:
        """hwc show/hide components + kpi hotspot export CSV."""
        if self.state != State.AGENT_READY:
            self._log("HyperView NOT Ready")
            return None
        self._set_state(State.RUNNING)
        try:
            self._log(f"export_hotspot_csv: {hotspot_name} → {csv_path}")
            result = self.bridge.send_job(cmd="export_hotspot_csv", params={
                "hotspot_name": hotspot_name,
                "csv_path": csv_path.replace('\\', '/'),
            }, timeout=5)
            if result.get('success', False):
                self._log(f"CSV exported: {csv_path}")
                return {'success': True, 'csv_path': result.get('csv_path', csv_path)}
            # TCL端写完CSV后可能卡在show/hide操作上，不返回ACK。
            # 只要文件已落盘即视为成功，不再等满超时。
            if os.path.exists(csv_path):
                self._log(f"bridge timeout but CSV on disk — treating as success: {csv_path}")
                return {'success': True, 'csv_path': csv_path}
            self._log(f"export_hotspot_csv failed: {result.get('error', 'Unknown')}")
            return None
        except Exception as e:
            self._log(f"export_hotspot_csv error: {e}")
            return None
        finally:
            self._set_state(State.AGENT_READY)

    def read_max_value(self, result_type: str, component: str,
                       hotspot_name: str, csv_path: str) -> Optional[Dict[str, Any]]:
        """Plot contour, find hotspot, export KPI CSV. Returns {'success': True, 'csv_path': ...}."""
        if self.state != State.AGENT_READY:
            self._log("HyperView NOT Ready, Start First")
            return None
        self._set_state(State.RUNNING)
        try:
            self._log(f"read_max_value: {result_type}/{component} → {csv_path}")
            result = self.bridge.send_job(cmd="read_max_value", params={
                "result_type": result_type,
                "result_component": component,
                "hotspot_name": hotspot_name,
                "csv_path": csv_path.replace('\\', '/'),
            })
            if not result.get('success', False):
                self._log(f"read_max_value failed: {result.get('error', 'Unknown')}")
                return None
            self._log(f"read_max_value done, CSV: {csv_path}")
            return {'success': True, 'csv_path': result.get('csv_path', csv_path)}
        except Exception as e:
            self._log(f"read_max_value error: {str(e)}")
            return None
        finally:
            self._set_state(State.AGENT_READY)

    def _send_quit_no_wait(self) -> bool:
        """Best-effort quit injection: write quit job directly, do not wait for response."""
        try:
            job_id = self.bridge._generate_job_id()
            self.bridge._write_job(job_id, {
                "id": job_id,
                "cmd": "quit",
            })
            self._log(f"Quit job injected directly: job_{job_id} (hwd exit)")
            return True
        except Exception as e:
            self._log(f"Failed to inject quit job: {e}")
            return False

    def shutdown(self):
        self._log("closing now")
        if self.ready_signal.is_ready():
            quit_sent = self._send_quit_no_wait()
            if quit_sent:
                # 等待 HyperView TCL agent 轮询并执行 hwc hwd exit（轮询间隔 500ms）
                time.sleep(1.5)
            else:
                try:
                    self.bridge.send_job(cmd="quit", params={})
                    self._log("HyperView quit command sent (hwc hwd exit)")
                except Exception as e:
                    self._log(f"Failed to send quit command: {e}")
        self.hv_process.terminate()
        self._set_state(State.EXITED)
