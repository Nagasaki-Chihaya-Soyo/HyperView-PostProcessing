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
        self.logs_dir = os.path.join(base_dir, self.config['workdir']['logs'])
        # 用户结果文件输出到 Documents/HyperView-PostProcessing，与程序安装位置解耦
        self.output_dir = os.path.join(os.path.expanduser("~"), "Documents", "HyperView-PostProcessing")
        self.runs_dir = os.path.join(self.output_dir, "runs")
        for d in [self.inbox_dir, self.outbox_dir, self.logs_dir, self.output_dir, self.runs_dir]:
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
set REPORT_DIR "C:/Temp/HyperView_Report"
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
    set str [string map [list \\ \\\\ \" \\" \n \\n \r \\r \t \\t] $str]
    return $str
}

proc cleanup_handles {} {
    # 清理可能存在的旧句柄，防止重复定义错误
    catch { legendH ReleaseHandle }
    catch { selSet ReleaseHandle }
    catch { my_post ReleaseHandle }
    catch { model1 ReleaseHandle }
    catch { contourCtrl ReleaseHandle }
    catch { resultCtrl ReleaseHandle }
    catch { qc ReleaseHandle }
    catch { win1 ReleaseHandle }
    catch { page1 ReleaseHandle }
    catch { proj ReleaseHandle }
    catch { sess ReleaseHandle }
    catch { hwi CloseStack }
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

    # 清理可能存在的旧句柄
    cleanup_handles

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

        # 获取模型句柄并设置云图
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
    puts "=== cmd_display_contour (native TCL) ==="
    if { [catch {
        puts "dc Step 1: OpenStack + GetSessionHandle"
        hwi OpenStack
        hwi GetSessionHandle sess_dc
        puts "dc Step 2: GetProjectHandle"
        sess_dc GetProjectHandle proj_dc
        set pageId_dc [proj_dc GetActivePage]
        puts "dc Step 3: GetPageHandle pageId=$pageId_dc"
        proj_dc GetPageHandle page_dc $pageId_dc
        set winId_dc [page_dc GetActiveWindow]
        puts "dc Step 4: GetWindowHandle winId=$winId_dc"
        page_dc GetWindowHandle win_dc $winId_dc
        win_dc SetClientType animation
        puts "dc Step 5: GetClientHandle (post)"
        win_dc GetClientHandle post_dc
        puts "dc Step 6: GetContourCtrlHandle"
        post_dc GetContourCtrlHandle cc_dc
        puts "dc Step 7: SetDataType Element Stresses"
        cc_dc SetDataType "Element Stresses (2D & 3D)"
        puts "dc Step 8: SetDataComponent vonMises"
        cc_dc SetDataComponent "vonMises"
        puts "dc Step 9: Apply"
        cc_dc Apply
        cc_dc ReleaseHandle
        puts "dc Step 10: Draw"
        post_dc Draw
        post_dc ReleaseHandle
        win_dc ReleaseHandle
        page_dc ReleaseHandle
        proj_dc ReleaseHandle
        sess_dc ReleaseHandle
        hwi CloseStack
    } err] } {
        puts "cmd_display_contour FAILED: $err"
        catch { hwi CloseStack }
        return 0
    }
    puts "=== cmd_display_contour completed ==="
    return 1
}

proc process_job {job_file} {
    global MAX_VALUE MAX_ID REPORT_DIR
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
        set start [string first {"} $content [expr {$idx + 4}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set job_id [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "cmd": "value"
    set idx [string first {"cmd"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 5}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set cmd [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "model_path": "value"
    set idx [string first {"model_path"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 12}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set model_path [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "result_path": "value"
    set idx [string first {"result_path"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 13}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set result_path [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "output_dir": "value"
    set idx [string first {"output_dir"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 12}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set output_dir [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "result_type": "value"
    set result_type ""
    set idx [string first {"result_type"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 13}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set result_type [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "result_component": "value"
    set result_component ""
    set idx [string first {"result_component"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 18}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set result_component [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "label": "value"
    set label ""
    set idx [string first {"label"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 7}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set label [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "hotspot_name": "value"
    set hotspot_name ""
    set idx [string first {"hotspot_name"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 14}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set hotspot_name [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "viewmode_option": "value"
    set viewmode_option ""
    set idx [string first {"viewmode_option"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 17}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set viewmode_option [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "csv_path": "value"
    set csv_path ""
    set idx [string first {"csv_path"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 10}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set csv_path [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "position": "value"
    set position ""
    set idx [string first {"position"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 10}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set position [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    # 解析 "file_path": "value"
    set file_path ""
    set idx [string first {"file_path"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 11}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set file_path [string trim [string range $content [expr {$start + 1}] [expr {$end - 1}]]]
        }
    }

    puts "DEBUG: job_id=$job_id cmd=$cmd"
    puts "DEBUG: model_path=$model_path"
    puts "Processing: $job_id $cmd"

    set _proc_code [catch {
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
            "apply_contour" {
                puts "=== apply_contour start: type=$result_type component=$result_component label=$label ==="
                if { [catch {
                    puts "ac Step 1: OpenStack + GetSessionHandle"
                    hwi OpenStack
                    hwi GetSessionHandle sess_ac
                    puts "ac Step 2: GetProjectHandle"
                    sess_ac GetProjectHandle proj_ac
                    set pageId_ac [proj_ac GetActivePage]
                    puts "ac Step 3: GetPageHandle pageId=$pageId_ac"
                    proj_ac GetPageHandle page_ac $pageId_ac
                    set winId_ac [page_ac GetActiveWindow]
                    puts "ac Step 4: GetWindowHandle winId=$winId_ac"
                    page_ac GetWindowHandle win_ac $winId_ac
                    win_ac SetClientType animation
                    puts "ac Step 5: GetClientHandle (post)"
                    win_ac GetClientHandle post_ac
                    puts "ac Step 6: GetContourCtrlHandle"
                    post_ac GetContourCtrlHandle cc_ac
                    puts "ac Step 7: SetDataType $result_type"
                    cc_ac SetDataType $result_type
                    puts "ac Step 8: SetDataComponent $result_component"
                    cc_ac SetDataComponent $result_component
                    puts "ac Step 9: Apply contour"
                    cc_ac Apply
                    cc_ac ReleaseHandle
                    puts "ac Step 10: Draw"
                    post_ac Draw
                    post_ac ReleaseHandle
                    win_ac ReleaseHandle
                    page_ac ReleaseHandle
                    proj_ac ReleaseHandle
                    puts "ac Step 11: GetReportCtrlHandle"
                    sess_ac GetReportCtrlHandle rc_ac
                    puts "ac Step 12: GetReportHandle"
                    rc_ac GetReportHandle rH_ac "Report"
                    puts "ac Step 13: AddSlide One Image with Caption"
                    rH_ac AddSlide sH_ac "One Image with Caption"
                    puts "ac Step 14: SetLabel $label"
                    sH_ac SetLabel $label
                    sH_ac ReleaseHandle
                    rH_ac ReleaseHandle
                    rc_ac ReleaseHandle
                    sess_ac ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "apply_contour FAILED: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "=== apply_contour completed ==="
                write_result $job_id {{"success":true}}
            }
            "report_run_position" {
                puts "=== report_run_position start: label=$label ==="
                if { [catch {
                    puts "rrp Step 1: OpenStack + GetSessionHandle"
                    hwi OpenStack
                    hwi GetSessionHandle sess_rrp
                    puts "rrp Step 2: GetReportCtrlHandle"
                    sess_rrp GetReportCtrlHandle rc_rrp
                    puts "rrp Step 3: GetReportHandle"
                    rc_rrp GetReportHandle rH_rrp "Report"
                    puts "rrp Step 4: Run position=$label"
                    rH_rrp Run $label
                    rH_rrp ReleaseHandle
                    rc_rrp ReleaseHandle
                    sess_rrp ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "report_run_position FAILED: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "=== report_run_position completed ==="
                write_result $job_id {{"success":true}}
            }
            "capture_slide" {
                puts "=== capture_slide start: label=$label ==="
                if { [catch {
                    puts "cs Step 1: OpenStack + GetSessionHandle"
                    hwi OpenStack
                    hwi GetSessionHandle sess_cs
                    puts "cs Step 2: GetReportCtrlHandle"
                    sess_cs GetReportCtrlHandle rc_cs
                    puts "cs Step 3: GetReportHandle"
                    rc_cs GetReportHandle rH_cs "Report"
                    puts "cs Step 4: AddSlide One Image with Caption"
                    rH_cs AddSlide sH_cs "One Image with Caption"
                    puts "cs Step 5: SetLabel $label"
                    sH_cs SetLabel $label
                    sH_cs ReleaseHandle
                    puts "cs Step 6: Run position=$label"
                    rH_cs Run $label
                    rH_cs ReleaseHandle
                    rc_cs ReleaseHandle
                    sess_cs ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "capture_slide FAILED: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "=== capture_slide completed ==="
                write_result $job_id {{"success":true}}
            }

            "report_run" {
                puts "=== report_run start ==="
                if { [catch {
                    puts "rr Step 1: OpenStack + GetSessionHandle"
                    hwi OpenStack
                    hwi GetSessionHandle sess_rr
                    puts "rr Step 2: GetReportCtrlHandle"
                    sess_rr GetReportCtrlHandle rc_rr
                    puts "rr Step 3: GetReportHandle"
                    rc_rr GetReportHandle rH_rr "Report"
                    puts "rr Step 4: Run"
                    rH_rr Run
                    rH_rr ReleaseHandle
                    rc_rr ReleaseHandle
                    sess_rr ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "report_run FAILED: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "=== report_run completed ==="
                write_result $job_id {{"success":true}}
            }
            "report_export" {
                puts "Executing report_export command"
                if { [catch {
                    .hw_report.hw_hw_report.mainwardMainWidget1.toolbar.export invoke
                    puts "report_export completed"
                } err] } {
                    puts "report_export error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                write_result $job_id {{"success":true}}
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
            "setup_view" {
                puts "=== setup_view start ==="
                if { [catch {
                    puts "sv Step 1: OpenStack + GetSessionHandle"
                    hwi OpenStack
                    hwi GetSessionHandle sess_sv
                    puts "sv Step 2: GetProjectHandle"
                    sess_sv GetProjectHandle proj_sv
                    set pageId_sv [proj_sv GetActivePage]
                    puts "sv Step 3: GetPageHandle pageId=$pageId_sv"
                    proj_sv GetPageHandle page_sv $pageId_sv
                    set winId_sv [page_sv GetActiveWindow]
                    puts "sv Step 4: GetWindowHandle winId=$winId_sv"
                    page_sv GetWindowHandle win_sv $winId_sv
                    puts "sv Step 5: GetViewControlHandle"
                    win_sv GetViewControlHandle vc_sv
                    set iso_vm "0.707107 0.353553 -0.612372 0.000000 -0.707107 0.353553 -0.612372 0.000000 0.000000 0.866025 0.500000 0.000000 0.000000 0.000000 0.000000 1.000000"
                    puts "sv Step 6: SetViewMatrix iso"
                    vc_sv SetViewMatrix $iso_vm
                    puts "sv Step 7: Fit"
                    vc_sv Fit
                    vc_sv ReleaseHandle
                    win_sv ReleaseHandle
                    page_sv ReleaseHandle
                    proj_sv ReleaseHandle
                    sess_sv ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "setup_view FAILED: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "=== setup_view completed ==="
                write_result $job_id {{"success":true}}
            }
            "create_report" {
                puts "=== create_report start ==="
                if { [catch {
                    puts "cr Step 1: OpenStack + GetSessionHandle"
                    hwi OpenStack
                    hwi GetSessionHandle sess_cr
                    puts "cr Step 2: GetReportCtrlHandle"
                    sess_cr GetReportCtrlHandle rc_cr
                    puts "cr Step 3: CreateReport Report with layouttemplate=$REPORT_DIR"
                    rc_cr CreateReport rH_cr "Report" $REPORT_DIR
                    puts "cr Step 4: CreateReport Report (no template)"
                    rc_cr CreateReport rH_cr2 "Report"
                    rH_cr ReleaseHandle
                    rH_cr2 ReleaseHandle
                    rc_cr ReleaseHandle
                    sess_cr ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "create_report FAILED: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "=== create_report completed ==="
                write_result $job_id {{"success":true}}
            }
            "hotspot_find" {
                puts "=== hotspot_find start: hotspot_name=$hotspot_name ==="
                if { [catch {
                    puts "hf Step 1: OpenStack + GetSessionHandle"
                    hwi OpenStack
                    hwi GetSessionHandle sess_hf
                    puts "hf Step 2: GetProjectHandle"
                    sess_hf GetProjectHandle proj_hf
                    set pageId_hf [proj_hf GetActivePage]
                    puts "hf Step 3: GetPageHandle pageId=$pageId_hf"
                    proj_hf GetPageHandle page_hf $pageId_hf
                    set winId_hf [page_hf GetActiveWindow]
                    puts "hf Step 4: GetWindowHandle winId=$winId_hf"
                    page_hf GetWindowHandle win_hf $winId_hf
                    win_hf SetClientType animation
                    puts "hf Step 5: GetClientHandle (post)"
                    win_hf GetClientHandle post_hf
                    puts "hf Step 6: GetKPICtrlHandle"
                    post_hf GetKPICtrlHandle kpi_hf
                    puts "hf Step 7: CreateHotspot $hotspot_name"
                    kpi_hf CreateHotspot $hotspot_name
                    puts "hf Step 8: FindHotspots $hotspot_name"
                    kpi_hf FindHotspots $hotspot_name
                    puts "hf Step 9: ReviewHotspots $hotspot_name"
                    kpi_hf ReviewHotspots $hotspot_name
                    kpi_hf ReleaseHandle
                    post_hf ReleaseHandle
                    win_hf ReleaseHandle
                    page_hf ReleaseHandle
                    proj_hf ReleaseHandle
                    sess_hf ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "hotspot_find FAILED: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "=== hotspot_find completed ==="
                write_result $job_id {{"success":true}}
            }
            "hotspot_navigate" {
                puts "=== hotspot_navigate start: direction=$label ==="
                if { [catch {
                    puts "hn Step 1: OpenStack + GetSessionHandle"
                    hwi OpenStack
                    hwi GetSessionHandle sess_hn
                    puts "hn Step 2: GetProjectHandle"
                    sess_hn GetProjectHandle proj_hn
                    set pageId_hn [proj_hn GetActivePage]
                    proj_hn GetPageHandle page_hn $pageId_hn
                    set winId_hn [page_hn GetActiveWindow]
                    puts "hn Step 3: GetWindowHandle winId=$winId_hn"
                    page_hn GetWindowHandle win_hn $winId_hn
                    win_hn SetClientType animation
                    puts "hn Step 4: GetClientHandle (post)"
                    win_hn GetClientHandle post_hn
                    puts "hn Step 5: GetKPICtrlHandle"
                    post_hn GetKPICtrlHandle kpi_hn
                    puts "hn Step 6: NavigateToHotspot $label"
                    kpi_hn NavigateToHotspot $label
                    kpi_hn ReleaseHandle
                    post_hn ReleaseHandle
                    win_hn ReleaseHandle
                    page_hn ReleaseHandle
                    proj_hn ReleaseHandle
                    sess_hn ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "hotspot_navigate FAILED: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "=== hotspot_navigate completed ==="
                write_result $job_id {{"success":true}}
            }
            "hotspot_display_viewmode" {
                puts "=== hotspot_display_viewmode start: mode=$label option=$viewmode_option ==="
                if { [catch {
                    puts "hdv Step 1: OpenStack + GetSessionHandle"
                    hwi OpenStack
                    hwi GetSessionHandle sess_hdv
                    puts "hdv Step 2: GetProjectHandle"
                    sess_hdv GetProjectHandle proj_hdv
                    set pageId_hdv [proj_hdv GetActivePage]
                    proj_hdv GetPageHandle page_hdv $pageId_hdv
                    set winId_hdv [page_hdv GetActiveWindow]
                    puts "hdv Step 3: GetWindowHandle winId=$winId_hdv"
                    page_hdv GetWindowHandle win_hdv $winId_hdv
                    win_hdv SetClientType animation
                    puts "hdv Step 4: GetClientHandle (post)"
                    win_hdv GetClientHandle post_hdv
                    puts "hdv Step 5: GetKPICtrlHandle"
                    post_hdv GetKPICtrlHandle kpi_hdv
                    puts "hdv Step 6: SetViewMode $label $viewmode_option"
                    kpi_hdv SetViewMode $label $viewmode_option
                    kpi_hdv ReleaseHandle
                    post_hdv ReleaseHandle
                    win_hdv ReleaseHandle
                    page_hdv ReleaseHandle
                    proj_hdv ReleaseHandle
                    sess_hdv ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "hotspot_display_viewmode FAILED: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "=== hotspot_display_viewmode completed ==="
                write_result $job_id {{"success":true}}
            }
            "plot_contour_only" {
                puts "=== plot_contour_only start: type=$result_type component=$result_component ==="
                if { [catch {
                    puts "pco Step 1: OpenStack + GetSessionHandle"
                    hwi OpenStack
                    hwi GetSessionHandle sess_pco
                    puts "pco Step 2: GetProjectHandle"
                    sess_pco GetProjectHandle proj_pco
                    set pageId_pco [proj_pco GetActivePage]
                    puts "pco Step 3: GetPageHandle pageId=$pageId_pco"
                    proj_pco GetPageHandle page_pco $pageId_pco
                    set winId_pco [page_pco GetActiveWindow]
                    puts "pco Step 4: GetWindowHandle winId=$winId_pco"
                    page_pco GetWindowHandle win_pco $winId_pco
                    win_pco SetClientType animation
                    puts "pco Step 5: GetClientHandle (post)"
                    win_pco GetClientHandle post_pco
                    puts "pco Step 6: GetContourCtrlHandle"
                    post_pco GetContourCtrlHandle cc_pco
                    puts "pco Step 7: SetDataType $result_type"
                    cc_pco SetDataType $result_type
                    puts "pco Step 8: SetDataComponent $result_component"
                    cc_pco SetDataComponent $result_component
                    puts "pco Step 9: Apply"
                    cc_pco Apply
                    cc_pco ReleaseHandle
                    puts "pco Step 10: Draw"
                    post_pco Draw
                    post_pco ReleaseHandle
                    win_pco ReleaseHandle
                    page_pco ReleaseHandle
                    proj_pco ReleaseHandle
                    sess_pco ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "plot_contour_only FAILED: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "=== plot_contour_only completed ==="
                write_result $job_id {{"success":true}}
            }
            "export_hotspot_csv" {
                puts "=== export_hotspot_csv start: hotspot_name=$hotspot_name csv_path=$csv_path ==="
                if { [catch {
                    puts "ehc Step 1: OpenStack + GetSessionHandle"
                    hwi OpenStack
                    hwi GetSessionHandle sess_ehc
                    puts "ehc Step 2: GetProjectHandle"
                    sess_ehc GetProjectHandle proj_ehc
                    set pageId_ehc [proj_ehc GetActivePage]
                    proj_ehc GetPageHandle page_ehc $pageId_ehc
                    set winId_ehc [page_ehc GetActiveWindow]
                    puts "ehc Step 3: GetWindowHandle winId=$winId_ehc"
                    page_ehc GetWindowHandle win_ehc $winId_ehc
                    win_ehc SetClientType animation
                    puts "ehc Step 4: GetClientHandle (post)"
                    win_ehc GetClientHandle post_ehc
                    puts "ehc Step 5: ShowAllComponents"
                    post_ehc ShowAllComponents
                    puts "ehc Step 6: HideAllComponents"
                    post_ehc HideAllComponents
                    puts "ehc Step 7: ShowAllElements"
                    post_ehc ShowAllElements
                    puts "ehc Step 8: GetKPICtrlHandle"
                    post_ehc GetKPICtrlHandle kpi_ehc
                    puts "ehc Step 9: ExportHotspots $hotspot_name $csv_path"
                    kpi_ehc ExportHotspots $hotspot_name $csv_path
                    kpi_ehc ReleaseHandle
                    post_ehc ReleaseHandle
                    win_ehc ReleaseHandle
                    page_ehc ReleaseHandle
                    proj_ehc ReleaseHandle
                    sess_ehc ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "export_hotspot_csv FAILED: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "=== export_hotspot_csv completed ==="
                set escaped_csv [escape_json_string $csv_path]
                write_result $job_id [format {{"success":true,"csv_path":"%s"}} $escaped_csv]
            }
            "read_max_value" {
                puts "=== read_max_value start: type=$result_type component=$result_component hotspot=$hotspot_name ==="
                if { [catch {
                    puts "rmv Step 1: OpenStack + GetSessionHandle"
                    hwi OpenStack
                    hwi GetSessionHandle sess_rmv
                    puts "rmv Step 2: GetProjectHandle"
                    sess_rmv GetProjectHandle proj_rmv
                    set pageId_rmv [proj_rmv GetActivePage]
                    puts "rmv Step 3: GetPageHandle pageId=$pageId_rmv"
                    proj_rmv GetPageHandle page_rmv $pageId_rmv
                    set winId_rmv [page_rmv GetActiveWindow]
                    puts "rmv Step 4: GetWindowHandle winId=$winId_rmv"
                    page_rmv GetWindowHandle win_rmv $winId_rmv
                    win_rmv SetClientType animation
                    puts "rmv Step 5: GetClientHandle (post)"
                    win_rmv GetClientHandle post_rmv
                    puts "rmv Step 6: GetContourCtrlHandle"
                    post_rmv GetContourCtrlHandle cc_rmv
                    puts "rmv Step 7: SetDataType $result_type"
                    cc_rmv SetDataType $result_type
                    puts "rmv Step 8: SetDataComponent $result_component"
                    cc_rmv SetDataComponent $result_component
                    puts "rmv Step 9: Apply contour"
                    cc_rmv Apply
                    cc_rmv ReleaseHandle
                    puts "rmv Step 10: Draw"
                    post_rmv Draw
                    puts "rmv Step 11: GetKPICtrlHandle"
                    post_rmv GetKPICtrlHandle kpi_rmv
                    puts "rmv Step 12: CreateHotspot $hotspot_name"
                    kpi_rmv CreateHotspot $hotspot_name
                    puts "rmv Step 13: FindHotspots $hotspot_name"
                    kpi_rmv FindHotspots $hotspot_name
                    puts "rmv Step 14: ReviewHotspots $hotspot_name"
                    kpi_rmv ReviewHotspots $hotspot_name
                    puts "rmv Step 15: ShowAllComponents"
                    post_rmv ShowAllComponents
                    puts "rmv Step 16: HideAllComponents"
                    post_rmv HideAllComponents
                    puts "rmv Step 17: ShowAllElements"
                    post_rmv ShowAllElements
                    puts "rmv Step 18: ExportHotspots $hotspot_name $csv_path"
                    kpi_rmv ExportHotspots $hotspot_name $csv_path
                    kpi_rmv ReleaseHandle
                    post_rmv ReleaseHandle
                    win_rmv ReleaseHandle
                    page_rmv ReleaseHandle
                    proj_rmv ReleaseHandle
                    sess_rmv ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "read_max_value FAILED: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "=== read_max_value completed ==="
                set escaped_csv [escape_json_string $csv_path]
                write_result $job_id [format {{"success":true,"csv_path":"%s"}} $escaped_csv]
            }
            "quit" {
                puts "Executing quit command"
                write_result $job_id {{"success":true}}
                puts "Closing HyperView via session Exit"
                after 300
                if { [catch {
                    hwi OpenStack
                    hwi GetSessionHandle sess_q
                    sess_q Exit
                    sess_q ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "Session Exit failed ($err), falling back to TCL exit"
                    exit 0
                }
            }
            "load_model" {
                puts "=== load_model start: model=$model_path result=$result_path ==="
                if { [catch {
                    puts "lm Step 1: OpenStack + GetSessionHandle"
                    hwi OpenStack
                    hwi GetSessionHandle sess_lm
                    puts "lm Step 2: GetProjectHandle"
                    sess_lm GetProjectHandle proj_lm
                    set pageId_lm [proj_lm GetActivePage]
                    puts "lm Step 3: GetPageHandle pageId=$pageId_lm"
                    proj_lm GetPageHandle page_lm $pageId_lm
                    set winId_lm [page_lm GetActiveWindow]
                    puts "lm Step 4: GetWindowHandle winId=$winId_lm"
                    page_lm GetWindowHandle win_lm $winId_lm
                    win_lm SetClientType animation
                    puts "lm Step 5: GetClientHandle (post)"
                    win_lm GetClientHandle post_lm
                    puts "lm Step 6: AddModel $model_path"
                    post_lm AddModel $model_path
                    puts "lm Step 7: Draw"
                    post_lm Draw
                    if {$result_path ne ""} {
                        set mc_lm [post_lm GetNumberOfModels]
                        puts "lm Step 8: GetModelHandle (count=$mc_lm)"
                        post_lm GetModelHandle mdl_lm $mc_lm
                        puts "lm Step 9: AddResult $result_path"
                        mdl_lm AddResult $result_path
                        mdl_lm ReleaseHandle
                    }
                    puts "lm Step 10: Draw"
                    post_lm Draw
                    post_lm ReleaseHandle
                    win_lm ReleaseHandle
                    page_lm ReleaseHandle
                    proj_lm ReleaseHandle
                    sess_lm ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "load_model FAILED: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "=== load_model completed ==="
                write_result $job_id {{"success":true}}
            }
            "add_slide_one_image_only" {
                puts "=== add_slide_one_image_only start: label=$label file_path=$file_path ==="
                if { [catch {
                    puts "Step 0: OpenStack + GetSessionHandle"
                    hwi OpenStack
                    hwi GetSessionHandle sess_r
                    puts "Step 0 OK"

                    puts "Step 1: GetReportCtrlHandle"
                    sess_r GetReportCtrlHandle rc
                    puts "Step 1 OK"

                    puts "Step 2: GetReportHandle Report"
                    rc GetReportHandle rH "Report"
                    puts "Step 2 OK"

                    puts "Step 3: AddSlide One Image only"
                    rH AddSlide sH "One Image only"
                    puts "Step 3 OK"

                    puts "Step 4: SetLabel $label"
                    sH SetLabel $label
                    puts "Step 4 OK"
                    after 300

                    puts "Step 5: GetItemHandle Image1"
                    sH GetItemHandle imgH "Image1"
                    puts "Step 5 OK"

                    puts "Step 6: SetSourceType file (2)"
                    imgH SetSourceType 2
                    puts "Step 6 OK"
                    after 300

                    puts "Step 7: SetFileName $file_path"
                    imgH SetFileName $file_path
                    puts "Step 7 OK"
                    imgH ReleaseHandle
                    after 300

                    set seq [lindex $label end]
                    set new_label "Analyst $seq"
                    puts "Step 8: SetLabel $new_label"
                    sH SetLabel $new_label
                    puts "Step 8 OK"
                    after 300

                    sH ReleaseHandle
                    rH ReleaseHandle
                    rc ReleaseHandle
                    sess_r ReleaseHandle
                    hwi CloseStack
                } err] } {
                    puts "add_slide_one_image_only FAILED: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "=== add_slide_one_image_only completed ==="
                write_result $job_id {{"success":true}}
            }
            default {
                write_result $job_id [format {{"success":false,"error":"Unknown cmd: %s"}} $cmd]
            }
        }
    } err]
    if { $_proc_code != 0 && $_proc_code != 2 } {
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
            return {'success': True}
        except Exception as e:
            self._log(f"apply_contour error: {str(e)}")
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
            result = self.bridge.send_job(cmd="capture_slide", params={
                "label": label
            })
            if result.get('success', False):
                self._log(f"Capture slide completed: {label}")
                return True
            else:
                self._log(f"Capture slide failed: {result.get('error', 'Unknown')}")
                return False
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
        """通过 TCL 控件触发 HyperView 报告导出"""
        if self.state != State.AGENT_READY:
            self._log("HyperView is not ready")
            return False
        self._set_state(State.RUNNING)
        try:
            self._log("Exporting report...")
            result = self.bridge.send_job(cmd="report_export", params={})
            if result.get('success', False):
                self._log("Report exported successfully")
                return True
            else:
                self._log(f"Report export failed: {result.get('error', 'Unknown')}")
                return False
        finally:
            self._set_state(State.AGENT_READY)

    def create_report(self) -> bool:
        """执行 hwc report create presentation 两条指令"""
        if self.state != State.AGENT_READY:
            self._log("HyperView is not ready")
            return False
        self._log("Creating report presentation...")
        result = self.bridge.send_job(cmd="create_report", params={})
        if result.get('success', False):
            self._log("Report created successfully")
            return True
        else:
            self._log(f"Report creation failed: {result.get('error', 'Unknown')}")
            return False

    def hotspot_find(self, hotspot_name: str) -> bool:
        """Create hotspot, find hotspots, and review"""
        print(f"[hotspot_find] called: name={hotspot_name}, state={self.state}")
        if self.state != State.AGENT_READY:
            self._log(f"HyperView is not ready (state={self.state})")
            return False
        self._set_state(State.RUNNING)
        try:
            self._log(f"Finding hotspot: {hotspot_name}")
            result = self.bridge.send_job(cmd="hotspot_find", params={
                "hotspot_name": hotspot_name,
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
        """执行两条HWC命令: add slide One Image only 并 edit items image"""
        if self.state != State.AGENT_READY:
            self._log("HyperView is not ready")
            return False
        self._set_state(State.RUNNING)
        try:
            self._log(f"add_slide_one_image_only: label={label}")
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
