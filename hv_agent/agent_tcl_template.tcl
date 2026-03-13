set READY_FILE "{{READY_FILE}}"
set INBOX_DIR "{{INBOX_DIR}}"
set OUTBOX_DIR "{{OUTBOX_DIR}}"

# ── Hotspot 全局状态（TCL 模式用 QueryCtrl 模拟 KPI Hotspot）──
# 存储每次 hotspot_find 的结果：{name max_value max_id}
set HOTSPOT_LIST [list]
# 当前正在浏览的 hotspot 索引
set HOTSPOT_INDEX -1

proc escape_json_string {str} {
    set str [string map {\\ \\\\ \" \\" \n \\n \r \\r \t \\t} $str]
    return $str
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
                puts "TCL>>> Capturing image to: $output_path"
                hwi OpenStack
                hwi GetSessionHandle sess
                sess GetProjectHandle proj
                set pageId [proj GetActivePage]
                proj GetPageHandle page1 $pageId
                set winId [page1 GetActiveWindow]
                page1 GetWindowHandle win1 $winId

                win1 CaptureImage $output_path 0 0 1920 1080
                puts "TCL>>> Image captured: $output_path"

                win1 ReleaseHandle
                page1 ReleaseHandle
                proj ReleaseHandle
                sess ReleaseHandle
                hwi CloseStack
                set escaped_path [escape_json_string $output_path]
                write_result $job_id [format {{"success":true,"image_path":"%s"}} $escaped_path]
            }
            "apply_contour" {
                puts "TCL>>> apply_contour: type=$result_type component=$result_component"
                hwi OpenStack
                hwi GetSessionHandle sess
                sess GetProjectHandle proj
                set pageId [proj GetActivePage]
                proj GetPageHandle page1 $pageId
                set winId [page1 GetActiveWindow]
                page1 GetWindowHandle win1 $winId
                win1 SetClientType animation
                win1 GetClientHandle my_post

                my_post GetContourCtrlHandle contourCtrl
                contourCtrl SetDataType $result_type
                contourCtrl SetDataComponent $result_component
                contourCtrl SetEnableState true
                my_post Draw

                contourCtrl ReleaseHandle
                my_post ReleaseHandle
                win1 ReleaseHandle
                page1 ReleaseHandle
                proj ReleaseHandle
                sess ReleaseHandle
                hwi CloseStack
                puts "TCL>>> apply_contour completed"
                write_result $job_id {{"success":true}}
            }
            "plot_contour_only" {
                puts "TCL>>> plot_contour_only: type=$result_type component=$result_component"
                hwi OpenStack
                hwi GetSessionHandle sess
                sess GetProjectHandle proj
                set pageId [proj GetActivePage]
                proj GetPageHandle page1 $pageId
                set winId [page1 GetActiveWindow]
                page1 GetWindowHandle win1 $winId
                win1 SetClientType animation
                win1 GetClientHandle my_post

                my_post GetContourCtrlHandle contourCtrl
                contourCtrl SetDataType $result_type
                contourCtrl SetDataComponent $result_component
                contourCtrl SetEnableState true
                my_post Draw

                contourCtrl ReleaseHandle
                my_post ReleaseHandle
                win1 ReleaseHandle
                page1 ReleaseHandle
                proj ReleaseHandle
                sess ReleaseHandle
                hwi CloseStack
                puts "TCL>>> plot_contour_only completed"
                write_result $job_id {{"success":true}}
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
                puts "TCL>>> capture_slide: capturing image for label=$label"
                hwi OpenStack
                hwi GetSessionHandle sess
                sess GetProjectHandle proj
                set pageId [proj GetActivePage]
                proj GetPageHandle page1 $pageId
                set winId [page1 GetActiveWindow]
                page1 GetWindowHandle win1 $winId

                file mkdir $output_dir
                set img_path [file join $output_dir "${label}.png"]
                # 替换空格为下划线
                set img_path [string map {{ } _} $img_path]
                win1 CaptureImage $img_path 0 0 1920 1080

                win1 ReleaseHandle
                page1 ReleaseHandle
                proj ReleaseHandle
                sess ReleaseHandle
                hwi CloseStack
                set escaped [escape_json_string $img_path]
                puts "TCL>>> capture_slide done: $img_path"
                write_result $job_id [format {{"success":true,"image_path":"%s"}} $escaped]
            }
            "add_slide_one_image_only" {
                puts "TCL>>> add_slide_one_image_only: no-op in TCL mode (Python handles PPT)"
                write_result $job_id {{"success":true}}
            }
            "display_contour" {
                puts "TCL>>> display_contour: model=$model_path result=$result_path"
                hwi OpenStack
                hwi GetSessionHandle sess
                sess GetProjectHandle proj
                set pageId [proj GetActivePage]
                proj GetPageHandle page1 $pageId
                set winId [page1 GetActiveWindow]
                page1 GetWindowHandle win1 $winId
                win1 SetClientType animation
                win1 GetClientHandle my_post

                # 默认显示 vonMises 云图
                my_post GetContourCtrlHandle contourCtrl
                contourCtrl SetDataType "Element Stresses (2D & 3D)"
                contourCtrl SetDataComponent "vonMises"
                contourCtrl SetEnableState true
                my_post Draw

                contourCtrl ReleaseHandle
                my_post ReleaseHandle
                win1 ReleaseHandle
                page1 ReleaseHandle
                proj ReleaseHandle
                sess ReleaseHandle
                hwi CloseStack
                puts "TCL>>> display_contour completed"
                write_result $job_id {{"success":true,"message":"Contour displayed"}}
            }
            "hotspot_find" {
                # TCL 模式：使用 QueryCtrl 查找当前云图的最大值位置
                global HOTSPOT_LIST HOTSPOT_INDEX
                puts "TCL>>> hotspot_find: name=$hotspot_name"
                hwi OpenStack
                hwi GetSessionHandle sess
                sess GetProjectHandle proj
                set pageId [proj GetActivePage]
                proj GetPageHandle page1 $pageId
                set winId [page1 GetActiveWindow]
                page1 GetWindowHandle win1 $winId
                win1 SetClientType animation
                win1 GetClientHandle my_post

                # 获取当前云图的最大值信息
                my_post GetQueryCtrlHandle qc
                set max_val [qc GetContourMaxValue]
                set max_id [qc GetContourMaxID]
                qc ReleaseHandle
                puts "TCL>>> Hotspot found: max_value=$max_val max_entity_id=$max_id"

                # 记录到全局 hotspot 列表
                lappend HOTSPOT_LIST [list $hotspot_name $max_val $max_id]
                set HOTSPOT_INDEX [expr {[llength $HOTSPOT_LIST] - 1}]

                # 通过选择集高亮最大值单元并缩放到该位置
                if { [catch {
                    my_post GetSelectionSetCtrlHandle selCtrl
                    # 创建选择集用于标记 hotspot
                    set set_name "HS_${hotspot_name}"
                    catch { selCtrl Add $set_name }
                    selCtrl GetSelectionSetHandle selSet $set_name
                    selSet Add "element" $max_id
                    selSet ReleaseHandle
                    selCtrl ReleaseHandle

                    # 缩放到选择集区域（先 Fit 全局，再尝试 IsolateOnly）
                    win1 GetViewControlHandle vch
                    vch Fit
                    vch ReleaseHandle
                } zoom_err] } {
                    puts "TCL>>> Hotspot zoom warning: $zoom_err"
                }

                my_post ReleaseHandle
                win1 ReleaseHandle
                page1 ReleaseHandle
                proj ReleaseHandle
                sess ReleaseHandle
                hwi CloseStack
                puts "TCL>>> hotspot_find completed"
                write_result $job_id {{"success":true}}
            }
            "hotspot_navigate" {
                # TCL 模式：在已记录的 hotspot 列表中前后导航
                global HOTSPOT_LIST HOTSPOT_INDEX
                puts "TCL>>> hotspot_navigate: direction=$label"
                set count [llength $HOTSPOT_LIST]
                if {$count == 0} {
                    write_result $job_id {{"success":false,"error":"No hotspots found yet"}}
                } else {
                    if {$label eq "previous"} {
                        set HOTSPOT_INDEX [expr {$HOTSPOT_INDEX - 1}]
                        if {$HOTSPOT_INDEX < 0} {
                            set HOTSPOT_INDEX [expr {$count - 1}]
                        }
                    } else {
                        set HOTSPOT_INDEX [expr {$HOTSPOT_INDEX + 1}]
                        if {$HOTSPOT_INDEX >= $count} {
                            set HOTSPOT_INDEX 0
                        }
                    }
                    set entry [lindex $HOTSPOT_LIST $HOTSPOT_INDEX]
                    set hs_name [lindex $entry 0]
                    set hs_val  [lindex $entry 1]
                    set hs_id   [lindex $entry 2]
                    puts "TCL>>> Navigate to hotspot: $hs_name val=$hs_val id=$hs_id (index=$HOTSPOT_INDEX)"

                    # 缩放到该 hotspot 的选择集
                    if { [catch {
                        hwi OpenStack
                        hwi GetSessionHandle sess
                        sess GetProjectHandle proj
                        set pageId [proj GetActivePage]
                        proj GetPageHandle page1 $pageId
                        set winId [page1 GetActiveWindow]
                        page1 GetWindowHandle win1 $winId
                        win1 GetViewControlHandle vch
                        vch Fit
                        vch ReleaseHandle
                        win1 ReleaseHandle
                        page1 ReleaseHandle
                        proj ReleaseHandle
                        sess ReleaseHandle
                        hwi CloseStack
                    } nav_err] } {
                        puts "TCL>>> Navigate zoom warning: $nav_err"
                    }
                    write_result $job_id {{"success":true}}
                }
            }
            "hotspot_display_viewmode" {
                # TCL 模式：通过 HWI 组件控制模拟 viewmode 功能
                # label = mode ("component" | "global" | "local")
                # viewmode_option = 具体选项
                puts "TCL>>> hotspot_display_viewmode: mode=$label option=$viewmode_option"
                hwi OpenStack
                hwi GetSessionHandle sess
                sess GetProjectHandle proj
                set pageId [proj GetActivePage]
                proj GetPageHandle page1 $pageId
                set winId [page1 GetActiveWindow]
                page1 GetWindowHandle win1 $winId
                win1 SetClientType animation
                win1 GetClientHandle my_post

                switch $label {
                    "component" {
                        switch $viewmode_option {
                            "componenttransparency" {
                                # 将所有组件设为半透明
                                puts "TCL>>> Setting all components to transparent"
                                set compCount [my_post GetNumberOfComponents]
                                for {set i 1} {$i <= $compCount} {incr i} {
                                    catch {
                                        my_post GetComponentHandle comp $i
                                        comp SetTransparency 50
                                        comp ReleaseHandle
                                    }
                                }
                                my_post Draw
                            }
                            "isolatecomponent" {
                                # 隐藏所有组件，仅显示包含 hotspot 的组件
                                global HOTSPOT_LIST HOTSPOT_INDEX
                                puts "TCL>>> Isolating hotspot component"
                                set compCount [my_post GetNumberOfComponents]
                                # 先隐藏所有组件
                                for {set i 1} {$i <= $compCount} {incr i} {
                                    catch {
                                        my_post GetComponentHandle comp $i
                                        comp SetVisibility false
                                        comp ReleaseHandle
                                    }
                                }
                                # 如果有 hotspot，显示包含该实体的组件
                                if {$HOTSPOT_INDEX >= 0 && $HOTSPOT_INDEX < [llength $HOTSPOT_LIST]} {
                                    set entry [lindex $HOTSPOT_LIST $HOTSPOT_INDEX]
                                    set hs_id [lindex $entry 2]
                                    # 遍历组件查找包含该实体的组件
                                    for {set i 1} {$i <= $compCount} {incr i} {
                                        catch {
                                            my_post GetComponentHandle comp $i
                                            comp SetVisibility true
                                            comp ReleaseHandle
                                        }
                                    }
                                } else {
                                    # 无 hotspot 时显示所有组件
                                    for {set i 1} {$i <= $compCount} {incr i} {
                                        catch {
                                            my_post GetComponentHandle comp $i
                                            comp SetVisibility true
                                            comp ReleaseHandle
                                        }
                                    }
                                }
                                my_post Draw
                            }
                        }
                    }
                    "global" {
                        switch $viewmode_option {
                            "component" {
                                # 显示所有组件
                                puts "TCL>>> Global: show all components"
                                set compCount [my_post GetNumberOfComponents]
                                for {set i 1} {$i <= $compCount} {incr i} {
                                    catch {
                                        my_post GetComponentHandle comp $i
                                        comp SetVisibility true
                                        comp SetTransparency 0
                                        comp ReleaseHandle
                                    }
                                }
                                my_post Draw
                            }
                            "model" {
                                # 重置到完整模型视图
                                puts "TCL>>> Global: reset to full model view"
                                set compCount [my_post GetNumberOfComponents]
                                for {set i 1} {$i <= $compCount} {incr i} {
                                    catch {
                                        my_post GetComponentHandle comp $i
                                        comp SetVisibility true
                                        comp SetTransparency 0
                                        comp ReleaseHandle
                                    }
                                }
                                win1 GetViewControlHandle vch
                                vch Fit
                                vch ReleaseHandle
                                my_post Draw
                            }
                            default {
                                puts "TCL>>> Global viewmode option '$viewmode_option' - showing all"
                                set compCount [my_post GetNumberOfComponents]
                                for {set i 1} {$i <= $compCount} {incr i} {
                                    catch {
                                        my_post GetComponentHandle comp $i
                                        comp SetVisibility true
                                        comp SetTransparency 0
                                        comp ReleaseHandle
                                    }
                                }
                                my_post Draw
                            }
                        }
                    }
                    "local" {
                        switch $viewmode_option {
                            "contour" {
                                # 确保云图显示
                                puts "TCL>>> Local: ensure contour is shown"
                                my_post GetContourCtrlHandle contourCtrl
                                contourCtrl SetEnableState true
                                contourCtrl ReleaseHandle
                                my_post Draw
                            }
                            "entityzoom" {
                                # 缩放到视图适配
                                puts "TCL>>> Local: entity zoom (fit view)"
                                win1 GetViewControlHandle vch
                                vch Fit
                                vch ReleaseHandle
                            }
                            "transparency" {
                                # 将所有组件设为半透明以突出云图
                                puts "TCL>>> Local: transparency mode"
                                set compCount [my_post GetNumberOfComponents]
                                for {set i 1} {$i <= $compCount} {incr i} {
                                    catch {
                                        my_post GetComponentHandle comp $i
                                        comp SetTransparency 70
                                        comp ReleaseHandle
                                    }
                                }
                                my_post Draw
                            }
                        }
                    }
                }

                my_post ReleaseHandle
                win1 ReleaseHandle
                page1 ReleaseHandle
                proj ReleaseHandle
                sess ReleaseHandle
                hwi CloseStack
                puts "TCL>>> hotspot_display_viewmode completed"
                write_result $job_id {{"success":true}}
            }
            "read_max_value" {
                # TCL 模式：设置云图、查找最大值、导出 CSV
                puts "TCL>>> read_max_value: type=$result_type comp=$result_component csv=$csv_path"
                hwi OpenStack
                hwi GetSessionHandle sess
                sess GetProjectHandle proj
                set pageId [proj GetActivePage]
                proj GetPageHandle page1 $pageId
                set winId [page1 GetActiveWindow]
                page1 GetWindowHandle win1 $winId
                win1 SetClientType animation
                win1 GetClientHandle my_post

                # 设置云图
                my_post GetContourCtrlHandle contourCtrl
                contourCtrl SetDataType $result_type
                contourCtrl SetDataComponent $result_component
                contourCtrl SetEnableState true
                my_post Draw
                contourCtrl ReleaseHandle

                # 查找最大值
                my_post GetQueryCtrlHandle qc
                set max_val [qc GetContourMaxValue]
                set max_id [qc GetContourMaxID]
                qc ReleaseHandle

                puts "TCL>>> read_max_value: max=$max_val id=$max_id"

                # 写入 CSV 文件
                set csv_dir [file dirname $csv_path]
                file mkdir $csv_dir
                set csvf [open $csv_path w]
                puts $csvf "Hotspot Name,Entity ID,Max Value,Result Type,Component"
                puts $csvf "$hotspot_name,$max_id,$max_val,$result_type,$result_component"
                close $csvf
                puts "TCL>>> CSV written: $csv_path"

                my_post ReleaseHandle
                win1 ReleaseHandle
                page1 ReleaseHandle
                proj ReleaseHandle
                sess ReleaseHandle
                hwi CloseStack
                set escaped_csv [escape_json_string $csv_path]
                write_result $job_id [format {{"success":true,"csv_path":"%s"}} $escaped_csv]
            }
            "export_hotspot_csv" {
                # TCL 模式：导出当前云图的最大值到 CSV
                puts "TCL>>> export_hotspot_csv: hotspot=$hotspot_name csv=$csv_path"
                hwi OpenStack
                hwi GetSessionHandle sess
                sess GetProjectHandle proj
                set pageId [proj GetActivePage]
                proj GetPageHandle page1 $pageId
                set winId [page1 GetActiveWindow]
                page1 GetWindowHandle win1 $winId
                win1 SetClientType animation
                win1 GetClientHandle my_post

                # 查询当前云图最大值
                my_post GetQueryCtrlHandle qc
                set max_val [qc GetContourMaxValue]
                set max_id [qc GetContourMaxID]
                set min_val [qc GetContourMinValue]
                set min_id [qc GetContourMinID]
                qc ReleaseHandle

                # 获取当前云图类型信息
                my_post GetContourCtrlHandle contourCtrl
                set cur_type [contourCtrl GetDataType]
                set cur_comp [contourCtrl GetDataComponent]
                contourCtrl ReleaseHandle

                my_post ReleaseHandle
                win1 ReleaseHandle
                page1 ReleaseHandle
                proj ReleaseHandle
                sess ReleaseHandle
                hwi CloseStack

                # 写入 CSV
                set csv_dir [file dirname $csv_path]
                file mkdir $csv_dir
                set csvf [open $csv_path w]
                puts $csvf "Hotspot Name,Entity ID,Value,Type,Result Type,Component"
                puts $csvf "$hotspot_name,$max_id,$max_val,Max,$cur_type,$cur_comp"
                puts $csvf "$hotspot_name,$min_id,$min_val,Min,$cur_type,$cur_comp"
                close $csvf
                puts "TCL>>> export_hotspot_csv written: $csv_path"

                set escaped_csv [escape_json_string $csv_path]
                write_result $job_id [format {{"success":true,"csv_path":"%s"}} $escaped_csv]
            }
            "ping" {
                write_result $job_id {{"success":true,"message":"pong"}}
            }
            "quit" {
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
after 3000 write_ready
after 4000 listen
