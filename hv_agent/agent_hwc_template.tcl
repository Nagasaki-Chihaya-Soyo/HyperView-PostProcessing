package require Tk
set READY_FILE "{{READY_FILE}}"
set INBOX_DIR "{{INBOX_DIR}}"
set OUTBOX_DIR "{{OUTBOX_DIR}}"
set REPORT_DIR "{{REPORT_DIR}}"
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
                    hwc report Report run position=$label
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
            "hotspot_clear" {
                puts "Executing hotspot_clear"
                if { [catch {
                    hwc kpi hotspot clear
                } err] } {
                    puts "hotspot_clear error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "hotspot_clear completed"
                write_result $job_id {{"success":true}}
            }
            "hotspot_delete" {
                puts "Executing hotspot_delete: hotspot_name=$hotspot_name"
                if { [catch {
                    hwc kpi hotspot delete $hotspot_name
                } err] } {
                    puts "hotspot_delete error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "hotspot_delete completed"
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
                if { $label ne "" } {
                    hwc report Report add slide "One Image with Caption" label=$label
                    hwc report Report run position=$label
                    puts "hotspot_find: captured slide label=$label"
                }
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
puts "Starting Agent (HWC mode)"
after 3000 write_ready
after 4000 listen
