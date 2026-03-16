set READY_FILE "{{READY_FILE}}"
set INBOX_DIR "{{INBOX_DIR}}"
set OUTBOX_DIR "{{OUTBOX_DIR}}"

# ── 截图计数器 & 临时目录 ──
set CAPTURE_SEQ 0
set CAPTURE_DIR "C:/temp/HyperView_Captures"

proc escape_json_string {str} {
    set str [string map {\\ \\\\ \" \\" \n \\n \r \\r \t \\t} $str]
    return $str
}

proc cleanup_capture_dir {} {
    global CAPTURE_DIR
    # 清空截图目录（删除所有 png 文件），防止上次结果污染
    if {[file isdirectory $CAPTURE_DIR]} {
        foreach f [glob -nocomplain -directory $CAPTURE_DIR "*.png"] {
            catch { file delete -force $f }
        }
        puts "TCL>>> Capture directory cleaned: $CAPTURE_DIR"
    }
    file mkdir $CAPTURE_DIR
    puts "TCL>>> Capture directory ready: $CAPTURE_DIR"
}

proc write_ready {} {
    global READY_FILE
    set f [open $READY_FILE w]
    puts $f "ready"
    close $f
    puts "TCL>>> Agent Ready"
}

proc write_result {job_id result_json} {
    global OUTBOX_DIR
    set result_file [file join $OUTBOX_DIR "job_${job_id}.result.json"]
    set f [open $result_file w]
    puts $f $result_json
    close $f
}

# ── 统一截图过程：sess CaptureScreenToSize + 自增序号 ──
proc do_capture_screen {} {
    global CAPTURE_SEQ CAPTURE_DIR
    incr CAPTURE_SEQ
    set img_path [file join $CAPTURE_DIR "capture ($CAPTURE_SEQ).png"]

    hwi OpenStack
    hwi GetSessionHandle sess
    sess CaptureScreenToSize png $img_path 1920 1080 100
    sess ReleaseHandle
    hwi CloseStack

    puts "TCL>>> Screen captured ($CAPTURE_SEQ): $img_path"
    return $img_path
}

proc process_job {job_file} {
    set f [open $job_file r]
    set content [read $f]
    close $f

    # --- 简易 JSON 解析 (通用 helper) ---
    proc parse_json_field {content key} {
        set needle "\"$key\""
        set idx [string first $needle $content]
        if {$idx < 0} { return "" }
        set colon_idx [string first ":" $content [expr {$idx + [string length $needle]}]]
        if {$colon_idx < 0} { return "" }
        set start [string first {"} $content [expr {$colon_idx + 1}]]
        set end   [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            return [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
        return ""
    }

    set job_id       [parse_json_field $content "id"]
    set cmd          [parse_json_field $content "cmd"]
    set model_path   [parse_json_field $content "model_path"]
    set result_path  [parse_json_field $content "result_path"]
    set output_dir   [parse_json_field $content "output_dir"]
    set output_path  [parse_json_field $content "output_path"]
    set result_type  [parse_json_field $content "result_type"]
    set result_component [parse_json_field $content "result_component"]
    set label        [parse_json_field $content "label"]
    set hotspot_name [parse_json_field $content "hotspot_name"]
    set viewmode_option [parse_json_field $content "viewmode_option"]
    set csv_path     [parse_json_field $content "csv_path"]
    set position     [parse_json_field $content "position"]
    set file_path    [parse_json_field $content "file_path"]

    puts "TCL>>> process_job: job_id=$job_id cmd=$cmd"

    if { [catch {
        switch $cmd {
            "load_model" {
                puts "TCL>>> Loading model: $model_path"
                hwi OpenStack
                hwi GetSessionHandle sess
                sess GetProjectHandle proj
                set pageId [proj GetActivePage]
                proj GetPageHandle page1 $pageId
                set winId [page1 GetActiveWindow]
                page1 GetWindowHandle win1 $winId
                win1 SetClientType animation
                win1 GetClientHandle my_post

                my_post AddModel $model_path
                my_post Draw

                if {$result_path ne ""} {
                    puts "TCL>>> Loading result: $result_path"
                    set modelCount [my_post GetNumberOfModels]
                    if {$modelCount > 0} {
                        my_post GetModelHandle model1 1
                        catch { model1 AddResult $result_path }
                        model1 ReleaseHandle
                    }
                }

                catch {hwc result animation load all}

                my_post ReleaseHandle
                win1 ReleaseHandle
                page1 ReleaseHandle
                proj ReleaseHandle
                sess ReleaseHandle
                hwi CloseStack
                write_result $job_id {{"success":true}}
            }
            "setup_view" {
                puts "TCL>>> Executing setup_view command"
                hwi OpenStack
                hwi GetSessionHandle sess
                sess GetProjectHandle proj
                proj GetPageHandle page [proj GetActivePage]
                page GetWindowHandle win [page GetActiveWindow]
                win GetViewControlHandle vch

                # 设置等轴测视角矩阵
                vch SetViewMatrix {0.707107 0.353553 -0.612372 0.000000 -0.707107 0.353553 -0.612372 0.000000 0.000000 0.866025 0.500000 0.000000 0.000000 0.000000 0.000000 1.000000}
                puts "TCL>>> View matrix set"

                # 适配视图
                catch {hwc view fit}
                vch Fit
                puts "TCL>>> View fitted"

                puts "TCL>>> Executing ani last"
                if { [catch { ani last } ani_err] } {
                    puts "TCL>>> ani last failed: $ani_err"
                } else {
                    puts "TCL>>> ani last completed successfully"
                }

                vch ReleaseHandle
                win ReleaseHandle
                page ReleaseHandle
                proj ReleaseHandle
                sess ReleaseHandle
                hwi CloseStack
                puts "TCL>>> setup_view completed successfully"
                write_result $job_id {{"success":true}}
            }
            "capture_image" {
                # 使用 sess CaptureScreenToSize 统一截图
                puts "TCL>>> capture_image"
                set img_path [do_capture_screen]
                set escaped_path [escape_json_string $img_path]
                write_result $job_id [format {{"success":true,"image_path":"%s"}} $escaped_path]
            }
            "apply_contour" {
                # ── 从 agent_hwc_template.tcl 复制，去掉 hwc report 行 ──
                # 原 HWC: hwc report Report add slide "One Image with Caption" label=$label
                # 截图由 Python 侧 _capture_and_add_slide(label) 完成，caption = label
                puts "TCL>>> apply_contour: type=$result_type component=$result_component"
                hwc result scalar edit "Current Contour" type=$result_type component=$result_component
                hwc result scalar plot "Current Contour"
                puts "TCL>>> apply_contour completed"
                write_result $job_id {{"success":true}}
            }
            "plot_contour_only" {
                # ── 从 agent_hwc_template.tcl 复制 ──
                puts "TCL>>> plot_contour_only: type=$result_type component=$result_component"
                hwc result scalar edit "Current Contour" type=$result_type component=$result_component
                hwc result scalar plot "Current Contour"
                puts "TCL>>> plot_contour_only completed"
                write_result $job_id {{"success":true}}
            }
            "display_contour" {
                # ── 从 agent_hwc_template.tcl 复制 ──
                puts "TCL>>> display_contour"
                hwc result scalar edit "Current Contour" type="Element Stresses (2D & 3D)" component=vonMises
                hwc result scalar plot "Current Contour"
                puts "TCL>>> display_contour completed"
                write_result $job_id {{"success":true,"message":"Contour displayed"}}
            }
            "hotspot_find" {
                # ── 从 agent_hwc_template.tcl 复制 ──
                puts "TCL>>> hotspot_find: hotspot_name=$hotspot_name"
                hwc kpi hotspot create $hotspot_name
                hwc kpi hotspot $hotspot_name findhotspots
                hwc kpi hotspot $hotspot_name review
                puts "TCL>>> hotspot_find completed"
                write_result $job_id {{"success":true}}
            }
            "hotspot_navigate" {
                # ── 从 agent_hwc_template.tcl 复制 ──
                puts "TCL>>> hotspot_navigate: direction=$label"
                hwc kpi hotspot display $label
                puts "TCL>>> hotspot_navigate completed"
                write_result $job_id {{"success":true}}
            }
            "hotspot_display_viewmode" {
                # ── 从 agent_hwc_template.tcl 复制 ──
                puts "TCL>>> hotspot_display_viewmode: mode=$label option=$viewmode_option"
                hwc kpi hotspot display viewmode $label $viewmode_option
                puts "TCL>>> hotspot_display_viewmode completed"
                write_result $job_id {{"success":true}}
            }
            "read_max_value" {
                # ── 从 agent_hwc_template.tcl 复制 ──
                puts "TCL>>> read_max_value: type=$result_type comp=$result_component"
                hwc result scalar edit "Current Contour" type=$result_type component=$result_component
                hwc result scalar plot "Current Contour"
                hwc kpi hotspot create $hotspot_name
                hwc kpi hotspot $hotspot_name findhotspots
                hwc kpi hotspot $hotspot_name review
                hwc show component all
                hwc hide component all
                hwc show element all
                hwc kpi hotspot $hotspot_name export $csv_path
                puts "TCL>>> read_max_value completed"
                set escaped_csv [escape_json_string $csv_path]
                write_result $job_id [format {{"success":true,"csv_path":"%s"}} $escaped_csv]
            }
            "export_hotspot_csv" {
                # ── 从 agent_hwc_template.tcl 复制 ──
                puts "TCL>>> export_hotspot_csv: hotspot=$hotspot_name csv=$csv_path"
                hwc show component all
                hwc hide component all
                hwc show element all
                hwc kpi hotspot $hotspot_name export $csv_path
                puts "TCL>>> export_hotspot_csv completed"
                set escaped_csv [escape_json_string $csv_path]
                write_result $job_id [format {{"success":true,"csv_path":"%s"}} $escaped_csv]
            }
            "create_report" {
                puts "TCL>>> create_report: no-op in TCL mode (Python handles PPT)"
                write_result $job_id {{"success":true}}
            }
            "report_export" {
                puts "TCL>>> report_export: no-op in TCL mode (Python handles PPT)"
                write_result $job_id {{"success":true}}
            }
            "report_run" {
                puts "TCL>>> report_run: no-op in TCL mode"
                write_result $job_id {{"success":true}}
            }
            "report_run_position" {
                puts "TCL>>> report_run_position: no-op in TCL mode"
                write_result $job_id {{"success":true}}
            }
            "capture_slide" {
                # TCL 截图 → Python PPT，caption = label
                # (HWC 原代码: hwc report Report add slide "One Image with Caption" label=$label)
                puts "TCL>>> capture_slide: label=$label"
                set img_path [do_capture_screen]
                set escaped [escape_json_string $img_path]
                puts "TCL>>> capture_slide done: $img_path"
                write_result $job_id [format {{"success":true,"image_path":"%s"}} $escaped]
            }
            "add_slide_one_image_only" {
                puts "TCL>>> add_slide_one_image_only: no-op in TCL mode (Python handles PPT)"
                write_result $job_id {{"success":true}}
            }
            "ping" {
                write_result $job_id {{"success":true,"message":"pong"}}
            }
            "quit" {
                # 退出前清空截图目录
                cleanup_capture_dir
                write_result $job_id {{"success":true}}
                exit
            }
            default {
                puts "TCL>>> Unknown cmd: $cmd"
                write_result $job_id [format {{"success":false,"error":"Unknown cmd: %s"}} $cmd]
            }
        }
    } err] } {
        puts "TCL>>> process_job error: $err"
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
            set processing_file "${f}.processing"
            if {[catch {file rename -force $f $processing_file}]} {
                continue
            }
            process_job $processing_file
        }
    } err] } {
        puts "TCL>>> Listen error: $err"
    }
    after 500 listen
}

puts "=========================================="
puts "TCL>>> Starting Agent (TCL mode)"
puts "=========================================="
# 启动时清空截图目录，计数器从 1 开始
cleanup_capture_dir
after 3000 write_ready
after 4000 listen
