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

proc escape_json_string {str} {
    set str [string map {\\ \\\\ \" \\" \n \\n \r \\r \t \\t} $str]
    return $str
}

proc write_result {job_id result_json} {
    global OUTBOX_DIR
    set result_file [file join $OUTBOX_DIR "job_${job_id}.result.json"]
    puts "Writing result to: $result_file"
    set f [open $result_file w]
    puts $f $result_json
    close $f
    puts "Result written successfully"
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
        set pageId [proj GetActivePage]
        proj GetPageHandle page1 $pageId
        set winId [page1 GetActiveWindow]
        page1 GetWindowHandle win1 $winId
        win1 SetClientType animation
        win1 GetClientHandle my_post

        # 检查是否已有模型加载，如果没有才加载
        set modelCount [my_post GetNumberOfModels]
        if {$modelCount == 0} {
            my_post AddModel $model_path
            my_post Draw
            set modelCount [my_post GetNumberOfModels]
        }

        # 获取模型句柄并设置结果类型
        if {$modelCount > 0} {
            my_post GetModelHandle model1 1

            # 如果有结果文件，检查文件类型并加载
            if {$result_path ne ""} {
                set ext [string tolower [file extension $result_path]]
                if {$ext eq ".h3d" || $ext eq ".op2" || $ext eq ".pch" || $ext eq ".rst" || $ext eq ".d3plot"} {
                    puts "Loading result file for analysis: $result_path"
                    if { [catch {
                        model1 AddResult $result_path
                    } addResultErr] } {
                        puts "Warning: Could not load result file: $addResultErr"
                    }
                } else {
                    puts "Note: Result file type '$ext' is not directly supported."
                }
            }

            if { [catch {
                model1 GetResultCtrlHandle resultCtrl

                # 设置结果类型为应力
                set numDataTypes [resultCtrl GetNumberOfDataTypes]
                for {set i 1} {$i <= $numDataTypes} {incr i} {
                    set dtype [resultCtrl GetDataTypeLabel $i]
                    if {[string match -nocase "*stress*" $dtype]} {
                        resultCtrl SetCurrentDataType $i
                        break
                    }
                }

                # 设置分量为vonMises
                set numComponents [resultCtrl GetNumberOfDataComponents]
                for {set j 1} {$j <= $numComponents} {incr j} {
                    set comp [resultCtrl GetDataComponentLabel $j]
                    if {[string match -nocase "*mises*" $comp] || [string match -nocase "*von*" $comp]} {
                        resultCtrl SetCurrentDataComponent $j
                        break
                    }
                }

                # 应用结果设置
                resultCtrl Apply

                resultCtrl ReleaseHandle
            } resultErr] } {
                puts "Result control error: $resultErr"
            }

            model1 ReleaseHandle
        }

        # 刷新显示
        my_post Draw

        # 获取最大值
        if { [catch {
            my_post GetQueryCtrlHandle qc
            set MAX_VALUE [qc GetContourMaxValue]
            set MAX_ID [qc GetContourMaxID]
            qc ReleaseHandle
        } qerr] } {
            puts "Query error (using defaults): $qerr"
            set MAX_VALUE 0.0
            set MAX_ID 0
        }

        file mkdir $output_dir
        set image_path [file join $output_dir "vonmises.png"]
        win1 CaptureImage $image_path 0 0 1920 1080

        my_post ReleaseHandle
        win1 ReleaseHandle
        page1 ReleaseHandle
        proj ReleaseHandle
        sess ReleaseHandle
        hwi CloseStack
    } err] } {
        puts "cmd_export_contour_and_peak_vm error: $err"
        catch { hwi CloseStack }
        # 返回默认值而不是抛出错误，避免错误传播问题
        return [list 0.0 0 ""]
    }

    return [list $MAX_VALUE $MAX_ID $image_path]
}

proc cmd_display_contour {model_path result_path} {
    if { [catch {
        hwi OpenStack
        hwi GetSessionHandle sess
        sess GetProjectHandle proj
        set pageId [proj GetActivePage]
        proj GetPageHandle page1 $pageId
        set winId [page1 GetActiveWindow]
        page1 GetWindowHandle win1 $winId
        win1 SetClientType animation
        win1 GetClientHandle my_post

        # 检查是否已有模型加载，如果没有才加载
        set modelCount [my_post GetNumberOfModels]
        if {$modelCount == 0} {
            my_post AddModel $model_path
            my_post Draw
            set modelCount [my_post GetNumberOfModels]
        }

        # 获取模型句柄
        if {$modelCount > 0} {
            my_post GetModelHandle model1 1

            # 如果有结果文件，检查文件类型并加载
            if {$result_path ne ""} {
                set ext [string tolower [file extension $result_path]]
                if {$ext eq ".h3d" || $ext eq ".op2" || $ext eq ".pch" || $ext eq ".rst" || $ext eq ".d3plot"} {
                    puts "Loading result file for contour: $result_path"
                    if { [catch {
                        model1 AddResult $result_path
                    } addResultErr] } {
                        puts "Warning: Could not load result file: $addResultErr"
                    }
                } else {
                    puts "Note: Result file type '$ext' is not directly supported."
                }
            }

            if { [catch {
                model1 GetResultCtrlHandle resultCtrl

                # 设置结果类型为应力
                set numDataTypes [resultCtrl GetNumberOfDataTypes]
                for {set i 1} {$i <= $numDataTypes} {incr i} {
                    set dtype [resultCtrl GetDataTypeLabel $i]
                    if {[string match -nocase "*stress*" $dtype]} {
                        resultCtrl SetCurrentDataType $i
                        break
                    }
                }

                # 设置分量为vonMises
                set numComponents [resultCtrl GetNumberOfDataComponents]
                for {set j 1} {$j <= $numComponents} {incr j} {
                    set comp [resultCtrl GetDataComponentLabel $j]
                    if {[string match -nocase "*mises*" $comp] || [string match -nocase "*von*" $comp]} {
                        resultCtrl SetCurrentDataComponent $j
                        break
                    }
                }

                # 应用结果设置 - 这会自动启用云图显示
                resultCtrl Apply

                resultCtrl ReleaseHandle
            } resultErr] } {
                puts "Result control error: $resultErr"
            }

            model1 ReleaseHandle
        }

        # 刷新显示
        my_post Draw

        my_post ReleaseHandle
        win1 ReleaseHandle
        page1 ReleaseHandle
        proj ReleaseHandle
        sess ReleaseHandle
        hwi CloseStack
    } err] } {
        puts "cmd_display_contour error: $err"
        catch { hwi CloseStack }
        return 0
    }

    return 1
}

proc process_job {job_file} {
    global MAX_VALUE MAX_ID
    set f [open $job_file r]
    set content [read $f]
    close $f

    # 初始化变量
    set job_id ""
    set cmd ""
    set model_path ""
    set result_path ""
    set output_dir ""

    # 使用string first和string range手动解析JSON
    # 解析 "id": "value"
    set idx [string first {"id"} $content]
    if {$idx >= 0} {
        set start [string first {\"} $content [expr {$idx + 4}]]
        set end [string first {\"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set job_id [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "cmd": "value"
    set idx [string first {"cmd"} $content]
    if {$idx >= 0} {
        set start [string first {\"} $content [expr {$idx + 5}]]
        set end [string first {\"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set cmd [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "model_path": "value"
    set idx [string first {"model_path"} $content]
    if {$idx >= 0} {
        set start [string first {\"} $content [expr {$idx + 12}]]
        set end [string first {\"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set model_path [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "result_path": "value"
    set idx [string first {"result_path"} $content]
    if {$idx >= 0} {
        set start [string first {\"} $content [expr {$idx + 13}]]
        set end [string first {\"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set result_path [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "output_dir": "value"
    set idx [string first {"output_dir"} $content]
    if {$idx >= 0} {
        set start [string first {\"} $content [expr {$idx + 12}]]
        set end [string first {\"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set output_dir [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    puts "DEBUG: job_id=$job_id cmd=$cmd"
    puts "DEBUG: model_path=$model_path"
    puts "Processing: $job_id $cmd"

    if { [catch {
        switch $cmd {
            "export_contour_and_peak_vm" {
                set res [cmd_export_contour_and_peak_vm $model_path $result_path $output_dir]
                set pv [lindex $res 0]
                set pi [lindex $res 1]
                set ip [lindex $res 2]
                # 检查结果是否有效
                if {$ip eq "" || $pv == 0.0} {
                    write_result $job_id {{"success":false,"error":"Analysis failed - no valid results"}}
                } else {
                    set json [format {{"success":true,"images":["%s"],"peak":{"value":%s,"entity_id":%s,"coords":[0,0,0],"tags":{"component":"","part":"","property":""}}}} $ip $pv $pi]
                    write_result $job_id $json
                }
            }
            "ping" {
                write_result $job_id {{"success":true,"message":"pong"}}
            }
            "display_contour" {
                puts "Executing display_contour command"
                set res [cmd_display_contour $model_path $result_path]
                if {$res == 1} {
                    write_result $job_id {{"success":true,"message":"Contour displayed"}}
                } else {
                    write_result $job_id {{"success":false,"error":"Failed to display contour"}}
                }
            }
            "load_model" {
                puts "Executing load_model command"
                puts "Model path: $model_path"
                puts "Result path: $result_path"
                if { [catch {
                    hwi OpenStack
                    hwi GetSessionHandle sess
                    sess GetProjectHandle proj
                    set pageId [proj GetActivePage]
                    proj GetPageHandle page1 $pageId
                    set winId [page1 GetActiveWindow]
                    page1 GetWindowHandle win1 $winId
                    win1 SetClientType animation
                    win1 GetClientHandle my_post

                    # 加载模型文件
                    my_post AddModel $model_path
                    my_post Draw

                    # 如果有结果文件，检查文件类型
                    if {$result_path ne ""} {
                        set ext [string tolower [file extension $result_path]]
                        # .h3d文件已包含结果，.op2/.pch/.rst等是支持的结果文件
                        # .out文件通常不被直接支持
                        if {$ext eq ".h3d" || $ext eq ".op2" || $ext eq ".pch" || $ext eq ".rst" || $ext eq ".d3plot"} {
                            puts "Loading result file: $result_path"
                            set modelCount [my_post GetNumberOfModels]
                            if {$modelCount > 0} {
                                my_post GetModelHandle model1 1
                                if { [catch {
                                    model1 AddResult $result_path
                                } resultErr] } {
                                    puts "Warning: Could not load result file: $resultErr"
                                }
                                model1 ReleaseHandle
                            }
                            my_post Draw
                        } else {
                            puts "Note: Result file type '$ext' is not directly supported. Model file should contain results."
                        }
                    }

                    my_post ReleaseHandle
                    win1 ReleaseHandle
                    page1 ReleaseHandle
                    proj ReleaseHandle
                    sess ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "load_model error: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    set err_json [format {{"success":false,"error":"%s"}} $escaped_err]
                    write_result $job_id $err_json
                    return
                }
                puts "load_model completed successfully"
                write_result $job_id {{"success":true}}
            }
            default {
                write_result $job_id [format {{"success":false,"error":"Unknown cmd: %s"}} $cmd]
            }
        }
    } err] } {
        puts "process_job error: $err"
        set escaped_err [escape_json_string $err]
        write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
    }
    catch { file delete $job_file }
}

proc listen {} {
    global INBOX_DIR
    if { [catch {
        set files [glob -nocomplain -directory $INBOX_DIR "job_*.json"]
        foreach f $files {
            if {[string match "*.tmp" $f]} {continue}
            if {[string match "*.processing" $f]} {continue}
            # 重命名文件防止重复处理
            set processing_file "${f}.processing"
            if {[catch {file rename -force $f $processing_file}]} {
                continue
            }
            process_job $processing_file
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
