import os
import json
from enum import Enum, auto
from typing import Optional, Callable, Dict, Any
from datetime import datetime
from .hv_process import HVProcess
from .hv_bridge import HVBridge, ReadySignal
from .db_store import DBStore
from .analysis import Analyzer
from .report_html import HTMLReporter
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
        self.runs_dir = os.path.join(base_dir, self.config['workdir']['runs'])
        self.logs_dir = os.path.join(base_dir, self.config['workdir']['logs'])
        for d in [self.inbox_dir, self.outbox_dir, self.runs_dir, self.logs_dir]:
            os.makedirs(d, exist_ok=True)
        self.hv_process = HVProcess(self.config['hyperview'])
        self.bridge = HVBridge(self.inbox_dir, self.outbox_dir,
                               self.config['hyperview'].get('job_timeout', 300))
        self.ready_signal = ReadySignal(os.path.join(base_dir, 'workdir/ready.flag'))
        self.db = DBStore(os.path.join(base_dir, self.config['database']['path']))
        self.analyzer = Analyzer(self.db)
        self.reporter = HTMLReporter()
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

    def _generate_agent_tcl(self) -> str:
        agent_dir = os.path.join(self.base_dir, 'hv_agent')
        os.makedirs(agent_dir, exist_ok=True)
        agent_path = os.path.join(agent_dir, 'agent.tcl')
        ready_file = self.ready_signal.ready_file.replace('\\', '/')
        inbox_dir = self.inbox_dir.replace('\\', '/')
        outbox_dir = self.outbox_dir.replace('\\', '/')
        tcl_code = '''\
package require Tk
set READY_FILE "''' + ready_file + '''"
set INBOX_DIR "''' + inbox_dir + '''"
set OUTBOX_DIR "''' + outbox_dir + '''"
set MAX_VALUE 0.0
set MAX_ID 0
proc write_ready {} {
    global READY_FILE
    if { [catch {
        hwi OpenStack
        hwi GetSessionHandle sess
        sess ReleaseHandle
        hwi CloseStack
    } err] } {
        after 2000 write_ready
        return
    }

    set f [open $READY_FILE w]
    puts $f "ready"
    close $f
    puts "Agent Ready"
}

proc write_result {job_id result_json} {
    global OUTBOX_DIR
    set result_file [file join $OUTBOX_DIR "job_${job_id}.result.json"]
    set f [open $result_file w]
    puts $f $result_json
    close $f
}

proc cmd_export_contour_and_peak_vm {model_path result_path output_dir } {
    global MAX_VALUE MAX_ID
    set MAX_VALUE 0.0
    set MAX_ID 0
    set image_path ""

    if { [catch {
        hwi OpenStack
        hwi GetSessionHandle sess
        sess GetProjectHandle proj
        proj GetPageHandle page1
        page1 GetWindowHandle win1
        win1 SetClientType Animation
        win1 GetClientHandle my_post

        my_post AddModel $model_path
        if { $result_path ne "" && [file exists $result_path] } {
            my_post SetResult $result_path
        }

        my_post Draw
        my_post GetContourCtrlHandle cc
        cc SetDataType "Stress"
        cc SetDataComponent "vonMises"
        cc SetEnableState true
        cc ReleaseHandle

        my_post Draw

        my_post GetQueryCtrlHandle qc
        set MAX_VALUE [qc GetContourMaxValue]
        set MAX_ID [qc GetContourMaxID]
        qc ReleaseHandle

        file mkdir $output_dir
        set image_path [file join $output_dir "vonmises.png"]
        win CaptureImage $image_path 0 0 1920 1080

        my_post ReleaseHandle
        win1 ReleaseHandle
        page1 ReleaseHandle
        proj ReleaseHandle
        sess ReleaseHandle
        hwi CloseStack
    } err] } {
        catch { hwi CloseStack }
        error "Failed: $err"
    }

    return [list $MAX_VALUE $MAX_ID $image_path]
}

proc process_job {job_file} {
    global MAX_VALUE MAX_ID
    set f [open $job_file r]
    set content [read $f]
    close $f

    regexp {"id"\\s*:\\s*"([^"]*)"} $content -> job_id
    regexp {"cmd"\\s*:\\s*"([^"]*)"} $content -> cmd
    regexp {"model_path"\\s*:\\s*"([^"]*)"} $content -> model_path
    regexp {"result_path"\\s*:\\s*"([^"]*)"} $content -> result_path
    regexp {"output_dir"\\s*:\\s*"([^"]*)"} $content -> output_dir

    puts "Processing: $job_id $cmd"

    if { [catch {
        switch $cmd {
            "export_contour_and_peak_vm" {
                set res [cmd_export_contour_and_peak_vm $model_path $result_path $output_dir]
                set pv [lindex $res 0]
                set pi [lindex $res 1]
                set ip [lindex $res 2]
                set json [format {{"success":true,"images":["%s"],"peak":{"value":%s,"entity_id":%s,"coords":[0,0,0],"tags":{"component":"","part":"","property":""}}}} $ip $pv $pi]
                write_result $job_id $json
            }
            "ping" {
                write_result $job_id {{"success":true,"message":"pong"}}
            }
            "load_model" {
                if { [catch {
                    hwi OpenStack
                    hwi GetSessionHandle sess
                    sess GetProjectHandle proj
                    proj GetPageHandle page1
                    page1 GetWindowHandle win1
                    win1 SetClientType Animation
                    win1 GetClientHandle my_post
                    my_post AddModel $model_path
                    if { $result_path ne "" && [file exists $result_path] } {
                        my_post SetResult $result_path
                    }
                    my_post Draw
                    my_post ReleaseHandle
                    win1 ReleaseHandle
                    page1 ReleaseHandle
                    proj ReleaseHandle
                    hwi CloseStack
                } err] } {
                    catch { hwi CloseStack }
                    set err_json [format {{"success":false,"error":"%s"}} $err]
                    write_result $job_id $err_json
                    return
                }
                write_result $job_id {{"success":true}}
            }
            default {
                write_result $job_id [format {{"success":false,"error":"Unknown cmd: %s"}} $cmd]
            }
        }
    } err] } {
        write_result $job_id [format {{"success":false,"error":"%s"}} $err]
    }
    catch { file delete $job_file }
}

proc listen {} {
    global INBOX_DIR
    if { [catch {
        set files [glob -nocomplain -directory $INBOX_DIR "job_*.json"]
        foreach f $files {
            if {[string match "*.tmp" $f]} {continue}
            process_job $f
        }
    } err] } {
        puts "Listen error : $err"
    }
    after 500 listen
}
puts "Starting Agent"
after 3000 write_ready
after 4000 listen
'''
        with open(agent_path, 'w', encoding='utf-8') as f:
            f.write(tcl_code)
        return agent_path

    def start_hyperview(self) -> bool:
        if self.state == State.AGENT_READY and not self.hv_process.is_running():
            self._set_state(State.IDLE)
        if self.state not in (State.IDLE, State.FAILED, State.EXITED):
            self._log("Unable to Start Now")
            return False
        self._set_state(State.STARTING)
        self.ready_signal.clear()
        self.bridge.clear_inbox()
        self.bridge.clear_outbox()
        agent_path = self._generate_agent_tcl()
        self._log(f"Generate Agent:{agent_path}")
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
        if self.state != State.AGENT_READY:
            self._log("HyperView NOT Ready,Start First")
            return None
        self._set_state(State.RUNNING)
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = os.path.join(self.runs_dir, run_id)
        os.makedirs(run_dir, exist_ok=True)
        self._log(f"Begin Analysing:{model_path}")
        result = self.bridge.send_job(cmd="export_contour_and_peak_vm", params={
            "model_path": model_path.replace('\\', '/'),
            "result_path": result_path.replace('\\', '/') if result_path else "",
            "output_dir": run_dir.replace('\\', '/')
        })
        if not result.get('success', False):
            self._set_state(State.AGENT_READY)
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
        self._set_state(State.AGENT_READY)
        self._log(f"Analyzing Complete,Report:{report_path}")
        return {
            'success': True,
            'analysis': analysis_result,
            'report_path': report_path,
            'run_dir': run_dir
        }

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

    def shutdown(self):
        self._log("closing now")
        self.hv_process.terminate()
        self._set_state(State.EXITED)
