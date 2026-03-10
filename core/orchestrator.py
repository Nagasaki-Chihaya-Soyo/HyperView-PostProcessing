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
    set str [string map {\\ \\\\ \" \\" \n \\n \r \\r \t \\t} $str]
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
    puts "=== Display Contour V3 (HWC) ==="

    if { [catch {
        # 使用HWC指令显示云图
        puts "Setting contour type to Element Stresses vonMises..."
        hwc result scalar edit "Current Contour" type="Element Stresses (2D & 3D)" component=vonMises
        puts "Plotting contour using HWC command..."
        hwc result scalar plot "Current Contour"
        puts "Contour plotted successfully"
    } err] } {
        puts "cmd_display_contour error: $err"
        return 0
    }

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
            "apply_contour" {
                puts "Executing apply_contour command"
                puts "result_type=$result_type result_component=$result_component label=$label"
                if { [catch {
                    hwc result scalar edit "Current Contour" type=$result_type component=$result_component
                    hwc result scalar plot "Current Contour"
                    hwc report Report add slide "One Image with Caption" label=$label
                } err] } {
                    puts "apply_contour error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "apply_contour completed successfully"
                write_result $job_id {{"success":true}}
            }
            "report_run_position" {
                puts "Executing report_run_position: label=$label"
                if { [catch {
                    hwc report Report run position=$label
                } err] } {
                    puts "report_run_position error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "report_run_position completed"
                write_result $job_id {{"success":true}}
            }
            "capture_slide" {
                puts "Executing capture_slide: label=$label"
                if { [catch {
                    hwc report Report add slide "One Image with Caption" label=$label
                    hwc report Report run position=$label
                } err] } {
                    puts "capture_slide error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "capture_slide completed"
                write_result $job_id {{"success":true}}
            }

            "report_run" {
                puts "Executing report_run command"
                if { [catch {
                    hwc report Report run
                } err] } {
                    puts "report_run error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "report_run completed successfully"
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
                puts "Executing setup_view command"
                if { [catch {
                    hwc view orientation iso
                    hwc animate frame last
                } err] } {
                    puts "setup_view error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "setup_view completed successfully"
                write_result $job_id {{"success":true}}
            }
            "create_report" {
                puts "Executing create_report command"
                if { [catch {
                    hwc report create presentation Report layouttemplate=$REPORT_DIR
                    hwc report create presentation "Report"
                } err] } {
                    puts "create_report error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "create_report completed successfully"
                write_result $job_id {{"success":true}}
            }
            "hotspot_find" {
                puts "Executing hotspot_find: hotspot_name=$hotspot_name"
                if { [catch {
                    hwc kpi hotspot create $hotspot_name
                } err] } {
                    puts "hwc kpi create error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"kpi create failed: %s"}} $escaped_err]
                    return
                }
                puts "hwc kpi create $hotspot_name done"
                if { [catch {
                    hwc kpi hotspot $hotspot_name findhotspots
                } err] } {
                    puts "hwc kpi hotspot findhotspot error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"findhotspot failed: %s"}} $escaped_err]
                    return
                }
                puts "hwc kpi hotspot $hotspot_name findhotspot done"
                if { [catch {
                    hwc kpi hotspot $hotspot_name review
                } err] } {
                    puts "hwc kpi hotspot review error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"review failed: %s"}} $escaped_err]
                    return
                }
                puts "hwc kpi hotspot $hotspot_name review done"
                puts "hotspot_find completed successfully"
                write_result $job_id {{"success":true}}
            }
            "hotspot_navigate" {
                puts "Executing hotspot_navigate: direction=$label"
                if { [catch {
                    hwc kpi hotspot display $label
                } err] } {
                    puts "hotspot_navigate error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "hotspot_navigate completed"
                write_result $job_id {{"success":true}}
            }
            "hotspot_display_viewmode" {
                puts "Executing hotspot_display_viewmode: mode=$label option=$viewmode_option"
                if { [catch {
                    hwc kpi hotspot display viewmode $label $viewmode_option
                } err] } {
                    puts "hotspot_display_viewmode error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "hotspot_display_viewmode completed"
                write_result $job_id {{"success":true}}
            }
            "plot_contour_only" {
                puts "Executing plot_contour_only: type=$result_type component=$result_component"
                if { [catch {
                    hwc result scalar edit "Current Contour" type=$result_type component=$result_component
                    hwc result scalar plot "Current Contour"
                } err] } {
                    puts "plot_contour_only error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "plot_contour_only completed"
                write_result $job_id {{"success":true}}
            }
            "export_hotspot_csv" {
                puts "Executing export_hotspot_csv: hotspot_name=$hotspot_name csv_path=$csv_path"
                if { [catch {
                    hwc show component all
                    hwc hide component all
                    hwc show element all
                    hwc kpi hotspot $hotspot_name export $csv_path
                } err] } {
                    puts "export_hotspot_csv error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "export_hotspot_csv completed"
                set escaped_csv [escape_json_string $csv_path]
                write_result $job_id [format {{"success":true,"csv_path":"%s"}} $escaped_csv]
            }
            "read_max_value" {
                puts "Executing read_max_value"
                puts "result_type=$result_type result_component=$result_component"
                puts "hotspot_name=$hotspot_name csv_path=$csv_path"
                if { [catch {
                    hwc result scalar edit "Current Contour" type=$result_type component=$result_component
                    hwc result scalar plot "Current Contour"
                    hwc kpi hotspot create $hotspot_name
                    hwc kpi hotspot $hotspot_name findhotspots
                    hwc kpi hotspot $hotspot_name review
                    hwc show component all
                    hwc hide component all
                    hwc show element all
                    hwc kpi hotspot $hotspot_name export $csv_path
                } err] } {
                    puts "read_max_value error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "read_max_value completed successfully"
                set escaped_csv [escape_json_string $csv_path]
                write_result $job_id [format {{"success":true,"csv_path":"%s"}} $escaped_csv]
            }
            "quit" {
                puts "Executing quit command"
                write_result $job_id {{"success":true}}
                hwc hwd exit
            }
            "load_model" {
                puts "Executing load_model command"
                puts "Model path: $model_path"
                puts "Result path: $result_path"
                if { [catch {
                    hwc open animation model $model_path
                    if {$result_path ne ""} {
                        hwc open animation result $result_path
                    }
                    hwc result animation load all
                } err] } {
                    puts "load_model error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "load_model completed successfully"
                write_result $job_id {{"success":true}}
            }
            "add_slide_one_image_only" {
                puts "Executing add_slide_one_image_only: label=$label position=$position file_path=$file_path"
                if { [catch {
                    hwc report Report add slide "One Image only" "label=$label"
                    after 300
                    hwc report Report edit items image "position=$label,Image1" source=file
                    after 300
                    set file_arg "file="
                    append file_arg $file_path
                    hwc report Report edit items image "position=$position" source=file $file_arg
                    after 300
                    hwc report Report edit items slide "position=$file_path" "label=Analyst [lindex $label end]"
                    after 300
                } err] } {
                    puts "add_slide_one_image_only error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "add_slide_one_image_only completed"
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

    def _generate_agent_hwc(self) -> str:
        """生成 HWC agent 脚本框架（待实现具体业务逻辑）。"""
        agent_dir = os.path.join(self.base_dir, 'hv_agent')
        os.makedirs(agent_dir, exist_ok=True)
        agent_path = os.path.join(agent_dir, 'agent.hwc')
        ready_file = self.ready_signal.ready_file.replace('\\', '/')
        inbox_dir = self.inbox_dir.replace('\\', '/')
        outbox_dir = self.outbox_dir.replace('\\', '/')

        # TODO: 实现 HWC agent 业务逻辑
        hwc_code = f'''# HyperView HWC Agent - Auto Generated
# Ready File: {ready_file}
# Inbox Dir:  {inbox_dir}
# Outbox Dir: {outbox_dir}

# TODO: Implement HWC agent with the following structure:
# 1. Initialize HyperView session
# 2. Write ready signal to: {ready_file}
# 3. Poll {inbox_dir} for job_*.json files
# 4. Parse job JSON and dispatch commands
# 5. Write results to {outbox_dir}
'''
        with open(agent_path, 'w', encoding='utf-8') as f:
            f.write(hwc_code)
        return agent_path

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
        # 根据模式生成对应 agent
        if agent_mode == "hwc":
            agent_path = self._generate_agent_hwc()
        else:
            agent_path = self._generate_agent_tcl()
        self._log(f"Generate Agent ({agent_mode.upper()}): {agent_path}")
        if not self.hv_process.start(agent_path, mode=agent_mode):
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
