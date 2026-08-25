Set objShell = CreateObject("WScript.Shell")
objShell.Run "cmd /c cd /d D:\session-maintenance-system\backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8081", 0, False
objShell.Run "cmd /c cd /d D:\session-maintenance-system\frontend && pnpm dev", 0, False

WScript.Sleep 1000
MsgBox "服务已启动！" & vbCrLf & _
       "后端: http://localhost:8081" & vbCrLf & _
       "前端: http://localhost:5173" & vbCrLf & _
       vbCrLf & "点击确定关闭此窗口，服务继续运行", vbInformation, "启动成功"