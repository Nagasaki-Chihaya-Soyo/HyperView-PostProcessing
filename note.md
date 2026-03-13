hwi OpenStack 
hwi GetSessionHandle sess
sess GetProjectHandle proj
proj GetPageHandle page [proj GetActivePage]
page GetWindowHandle win [page GetActiveWindow]
win GetViewControl handle vch
vch SetViewMatrix {0.707107 0.353553 -0.612372 0.000000 -0.707107 0.353553 -0.612372 0.000000 0.000000 0.866025 0.500000 0.000000 0.000000 0.000000 0.000000 1.000000}
catch{hwc view fit}
vch Fit
ani last
vch ReleaseHandle
win ReleaseHandle
page ReleaseHandle
proj ReleaseHandle
sess ReleaseHandle
hwi CloseStack

set m [.hw_report.hw_hw_report.mainwardMainWidget0.toolbar.mbcreate cget -menu]
puts "menu path: $m"
set last [$m index end]
for {set i 0} {$i <= $last} {incr i} {
    catch {set lbl [$m entrycget $i -label]} 
    catch {set typ [$m type $i]}
    puts "$i: $typ - $lbl"
}
