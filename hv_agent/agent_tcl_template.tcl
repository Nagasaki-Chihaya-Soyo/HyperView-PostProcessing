set READY_FILE "{{READY_FILE}}"
set INBOX_DIR "{{INBOX_DIR}}"
set OUTBOX_DIR "{{OUTBOX_DIR}}"

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

    # --- 简易 JSON 解析 ---
    foreach {key varname offset} {
        {"id"}          job_id       4
        {"cmd"}         cmd          5
        {"model_path"}  model_path  12
        {"result_path"} result_path 13
    } {
        set idx [string first $key $content]
        if {$idx >= 0} {
            set start [string first {"} $content [expr {$idx + $offset}]]
            set end   [string first {"} $content [expr {$start + 1}]]
            if {$start >= 0 && $end > $start} {
                set $varname [string range $content [expr {$start + 1}] [expr {$end - 1}]]
            } else {
                set $varname ""
            }
        } else {
            set $varname ""
        }
    }

    puts "TCL>>> process_job: job_id=$job_id cmd=$cmd"

    if { [catch {
        switch $cmd {
            "load_model" {
                puts "TCL>>> rea geo $model_path"
                rea geo $model_path
                if {$result_path ne ""} {
                    puts "TCL>>> rea res $result_path"
                    rea res $result_path
                }
                catch {hwc result animation load all}
                write_result $job_id {{"success":true}}
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
