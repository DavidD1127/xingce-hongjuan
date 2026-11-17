# 把行测红卷装成"登录即启动"的计划任务。
# 登录 Windows 后自动在后台起服务，崩了 1 分钟内自动重启，
# 不再依赖黑窗口或命令行会话。
# 换路径时改下面两个变量再跑一次。

$ErrorActionPreference = "Stop"

$Python = "$env:LOCALAPPDATA\Programs\Python\Python312\pythonw.exe"
$Server = "D:\AI\xingce-hongjuan\server.py"
$TaskName = "HongJuanServer"

if (-not (Test-Path $Python)) { throw "missing pythonw.exe" }
if (-not (Test-Path $Server)) { throw "missing server.py" }

Get-Process pythonw -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq $Python } | Stop-Process -Force

$action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Server`"" -WorkingDirectory "D:\AI\xingce-hongjuan"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Limited -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 3

$listening = Get-NetTCPConnection -LocalPort 8400 -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    Write-Output "OK port 8400 listening, task $TaskName registered"
} else {
    Write-Output "Task registered but port not up yet. Wait a few seconds and refresh."
}
