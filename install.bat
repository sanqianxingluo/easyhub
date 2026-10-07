@echo off
chcp 65001 >nul
echo === EasyHub 依赖安装 ===
where python >nul 2>nul
if errorlevel 1 (
  echo [!] 没找到 python，请先装 Python 3.11+ 并勾选 Add to PATH
  pause & exit /b 1
)
python -m pip install --upgrade pip
python -m pip install PySide6 python-mpv -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.
echo [ok] 运行依赖装好了。
echo.
echo 想打包 exe 的话再执行：
echo   python -m pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
echo   python -m PyInstaller --noconfirm --clean --windowed --name EasyHub --onedir main.py
echo   copy libmpv-2.dll dist\EasyHub\
echo.
echo 注意：libmpv-2.dll 必须和 EasyHub.exe（或 main.py）在同一目录。
pause
