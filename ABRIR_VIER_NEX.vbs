Set shell = CreateObject("WScript.Shell")
folder = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
cmd = "pythonw """ & folder & "\VIERNEX_Video_Downloader.py"""
shell.Run cmd, 0, False

