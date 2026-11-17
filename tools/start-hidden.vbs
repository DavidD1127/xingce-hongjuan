' 无窗口启动行测红卷的看门程序（登录时由启动文件夹调用）
Set sh = CreateObject("WScript.Shell")
sh.Run """C:\Users\35429\AppData\Local\Programs\Python\Python312\pythonw.exe"" ""D:\AI\xingce-hongjuan\tools\supervise.py""", 0, False
