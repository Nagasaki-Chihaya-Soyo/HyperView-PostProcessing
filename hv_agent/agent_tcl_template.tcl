package require Tk
set READY_FILE "{{READY_FILE}}"
set INBOX_DIR "{{INBOX_DIR}}"
set OUTBOX_DIR "{{OUTBOX_DIR}}"
set REPORT_DIR "C:/Temp/HyperView_Report"
set MAX_VALUE 0.0
set MAX_ID 0
proc write_ready {} {
    global READY_FILE
    if { [catch {
        puts "TCL>>> hwi OpenStack"
        hwi OpenStack
        puts "TCL>>> hwi GetSessionHandle sess"
        hwi GetSessionHandle sess
        puts "TCL>>> sess ReleaseHandle"
        sess ReleaseHandle
        puts "TCL>>> hwi CloseStack"
        hwi CloseStack
    } err] } {
        puts "TCL>>> write_ready failed: $err, retry in 2s"
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
    puts "TCL>>> cleanup_handles"
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
    puts "TCL>>> Writing result to: $result_file"
    set f [open $result_file w]
    puts $f $result_json
    close $f
    puts "TCL>>> Result written successfully"
}

proc cmd_export_contour_and_peak_vm {model_path result_path output_dir } {
    global MAX_VALUE MAX_ID
    set MAX_VALUE 0.0
    set MAX_ID 0
    set image_path ""

    cleanup_handles

    if { [catch {
        puts "TCL>>> hwi OpenStack"
        hwi OpenStack
        puts "TCL>>> hwi GetSessionHandle sess"
        hwi GetSessionHandle sess
        puts "TCL>>> sess GetProjectHandle proj"
        sess GetProjectHandle proj
        puts "TCL>>> proj GetActivePage"
        set pageId [proj GetActivePage]
        puts "TCL>>> proj GetPageHandle page1 $pageId"
        proj GetPageHandle page1 $pageId
        puts "TCL>>> page1 GetActiveWindow"
        set winId [page1 GetActiveWindow]
        puts "TCL>>> page1 GetWindowHandle win1 $winId"
        page1 GetWindowHandle win1 $winId
        puts "TCL>>> win1 SetClientType animation"
        win1 SetClientType animation
        puts "TCL>>> win1 GetClientHandle my_post"
        win1 GetClientHandle my_post

        puts "TCL>>> my_post GetNumberOfModels"
        set modelCount [my_post GetNumberOfModels]
        puts "TCL>>> modelCount=$modelCount"
        if {$modelCount == 0} {
            puts "TCL>>> my_post AddModel $model_path"
            my_post AddModel $model_path
            puts "TCL>>> my_post Draw"
            my_post Draw
            set modelCount [my_post GetNumberOfModels]
        }

        if {$modelCount > 0} {
            puts "TCL>>> my_post GetModelHandle model1 1"
            my_post GetModelHandle model1 1

            if {$result_path ne ""} {
                set ext [string tolower [file extension $result_path]]
                if {$ext eq ".h3d" || $ext eq ".op2" || $ext eq ".pch" || $ext eq ".rst" || $ext eq ".d3plot"} {
                    puts "TCL>>> model1 AddResult $result_path"
                    if { [catch {
                        model1 AddResult $result_path
                    } addResultErr] } {
                        puts "TCL>>> Warning: Could not load result file: $addResultErr"
                    }
                } else {
                    puts "TCL>>> Note: Result file type '$ext' is not directly supported."
                }
            }

            puts "TCL>>> model1 ReleaseHandle"
            model1 ReleaseHandle
        }

        puts "TCL>>> my_post Draw"
        my_post Draw

        if { [catch {
            puts "TCL>>> my_post GetQueryCtrlHandle qc"
            my_post GetQueryCtrlHandle qc
            puts "TCL>>> qc GetContourMaxValue"
            set MAX_VALUE [qc GetContourMaxValue]
            puts "TCL>>> qc GetContourMaxID"
            set MAX_ID [qc GetContourMaxID]
            puts "TCL>>> MAX_VALUE=$MAX_VALUE MAX_ID=$MAX_ID"
            puts "TCL>>> qc ReleaseHandle"
            qc ReleaseHandle
        } qerr] } {
            puts "TCL>>> Query error (using defaults): $qerr"
            set MAX_VALUE 0.0
            set MAX_ID 0
        }

        file mkdir $output_dir
        set image_path [file join $output_dir "vonmises.png"]
        puts "TCL>>> win1 CaptureImage $image_path 0 0 1920 1080"
        win1 CaptureImage $image_path 0 0 1920 1080

        puts "TCL>>> releasing handles..."
        my_post ReleaseHandle
        win1 ReleaseHandle
        page1 ReleaseHandle
        proj ReleaseHandle
        sess ReleaseHandle
        hwi CloseStack
    } err] } {
        puts "TCL>>> cmd_export_contour_and_peak_vm error: $err"
        catch { hwi CloseStack }
        return [list 0.0 0 ""]
    }

    return [list $MAX_VALUE $MAX_ID $image_path]
}

proc process_job {job_file} {
    global MAX_VALUE MAX_ID REPORT_DIR
    set f [open $job_file r]
    set content [read $f]
    close $f

    set job_id ""
    set cmd ""
    set model_path ""
    set result_path ""
    set output_dir ""

    # JSON parsing
    set idx [string first {"id"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 4}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set job_id [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    set idx [string first {"cmd"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 5}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set cmd [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    set idx [string first {"model_path"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 12}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set model_path [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    set idx [string first {"result_path"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 13}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set result_path [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    set idx [string first {"output_dir"} $content]
    if {$idx >= 0} {
        set start [string first {"} $content [expr {$idx + 12}]]
        set end [string first {"} $content [expr {$start + 1}]]
        if {$start >= 0 && $end > $start} {
            set output_dir [string range $content [expr {$start + 1}] [expr {$end - 1}]]
        }
    }

    puts "=========================================="
    puts "TCL>>> process_job: job_id=$job_id cmd=$cmd"
    puts "TCL>>> model_path=$model_path"
    puts "TCL>>> result_path=$result_path"
    puts "=========================================="

    if { [catch {
        switch $cmd {
            "export_contour_and_peak_vm" {
                puts "TCL>>> calling cmd_export_contour_and_peak_vm (pure HWI)"
                set res [cmd_export_contour_and_peak_vm $model_path $result_path $output_dir]
                set pv [lindex $res 0]
                set pi [lindex $res 1]
                set ip [lindex $res 2]
                if {$ip eq "" || $pv == 0.0} {
                    write_result $job_id {{"success":false,"error":"Analysis failed - no valid results"}}
                } else {
                    set json [format {{"success":true,"images":["%s"],"peak":{"value":%s,"entity_id":%s,"coords":[0,0,0],"tags":{"component":"","part":"","property":""}}}} $ip $pv $pi]
                    write_result $job_id $json
                }
            }
            "ping" {
                puts "TCL>>> ping -> pong"
                write_result $job_id {{"success":true,"message":"pong"}}
            }
            "report_export" {
                puts "TCL>>> .hw_report.hw_hw_report.mainwardMainWidget1.toolbar.export invoke"
                if { [catch {
                    .hw_report.hw_hw_report.mainwardMainWidget1.toolbar.export invoke
                } err] } {
                    puts "TCL>>> report_export error: $err"
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "TCL>>> report_export completed"
                write_result $job_id {{"success":true}}
            }
            "quit" {
                puts "TCL>>> quit (exit)"
                write_result $job_id {{"success":true}}
                exit
            }
            "load_model" {
                puts "TCL>>> load_model (pure HWI, NO hwc commands)"
                puts "TCL>>> Model path: $model_path"
                puts "TCL>>> Result path: $result_path"
                cleanup_handles
                if { [catch {
                    puts "TCL>>> hwi OpenStack"
                    hwi OpenStack
                    puts "TCL>>> hwi GetSessionHandle sess"
                    hwi GetSessionHandle sess
                    puts "TCL>>> sess GetProjectHandle proj"
                    sess GetProjectHandle proj
                    puts "TCL>>> proj GetPageHandle page \[proj GetActivePage\]"
                    proj GetPageHandle page [proj GetActivePage]
                    puts "TCL>>> page GetWindowHandle win \[page GetActiveWindow\]"
                    page GetWindowHandle win [page GetActiveWindow]
                    puts "TCL>>> win GetClientHandle poster"
                    win GetClientHandle poster

                    puts "TCL>>> poster AddModel $model_path"
                    poster AddModel $model_path
                    puts "TCL>>> poster Draw"
                    poster Draw

                    if {$result_path ne ""} {
                        puts "TCL>>> poster GetModelHandle mdl \[poster GetActiveModel\]"
                        poster GetModelHandle mdl [poster GetActiveModel]
                        puts "TCL>>> mdl AddResult $result_path"
                        mdl AddResult $result_path
                        puts "TCL>>> mdl ReleaseHandle"
                        mdl ReleaseHandle
                    }

                    puts "TCL>>> releasing handles (poster, win, page, proj, sess)..."
                    poster ReleaseHandle
                    win ReleaseHandle
                    page ReleaseHandle
                    proj ReleaseHandle
                    sess ReleaseHandle
                    puts "TCL>>> hwi CloseStack"
                    hwi CloseStack
                } err] } {
                    puts "TCL>>> load_model error: $err"
                    catch { hwi CloseStack }
                    set escaped_err [escape_json_string $err]
                    write_result $job_id [format {{"success":false,"error":"%s"}} $escaped_err]
                    return
                }
                puts "TCL>>> load_model completed successfully"
                write_result $job_id {{"success":true}}
            }
            "apply_contour" -
            "report_run_position" -
            "capture_slide" -
            "report_run" -
            "display_contour" -
            "setup_view" -
            "create_report" -
            "hotspot_find" -
            "hotspot_navigate" -
            "hotspot_display_viewmode" -
            "plot_contour_only" -
            "export_hotspot_csv" -
            "read_max_value" -
            "add_slide_one_image_only" {
                puts "TCL>>> $cmd: NOT IMPLEMENTED in TCL mode (requires hwc)"
                write_result $job_id [format {{"success":false,"error":"%s not implemented in TCL mode"}} $cmd]
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
        puts "TCL>>> Listen error : $err"
    }
    after 500 listen
}
puts "=========================================="
puts "TCL>>> Starting Agent (TCL mode)"
puts "TCL>>> This agent uses ONLY hwi commands"
puts "TCL>>> NO hwc commands will be executed"
puts "=========================================="
after 3000 write_ready
after 4000 listen
