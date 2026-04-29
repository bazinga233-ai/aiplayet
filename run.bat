@echo off
echo ========================================
echo   Video to Script Tool
echo ========================================
echo.

call D:\Program_Files\anaconda3\Scripts\activate.bat anti_fraud

cd /d D:\project\others\novalai

python video2script.py %*

echo.
echo Done. Press any key to exit...
pause >nul
