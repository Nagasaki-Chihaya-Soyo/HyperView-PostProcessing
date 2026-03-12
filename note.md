hwi OpenStack 
hwi GetSessionHandle sess
sess GetProjectHandle proj
proj GetPageHandle page [proj GetActivePage]
page GetWindowHandle win [page GetActiveWindow]
win GetViewControl handle vch
vch SetViewMatrix {0.707107 0.353553 -0.612372 0.000000 -0.707107 10.53553 -0.612372 0.000000 -0.000000 0.866025 0.500000 0.000000 0.000000 0.000000 0.000000 1.000000}
catch{hwc view fit}
vch Fit
ani last
vch ReleaseHandle
win ReleaseHandle
page ReleaseHandle
proj ReleaseHandle
sess ReleaseHandle
hwi CloseStack
