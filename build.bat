@echo off
cd /d "%~dp0"
python -m pip install --upgrade pyinstaller pillow tkinterdnd2
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name HeroQuestEditor ^
  --collect-all tkinterdnd2 ^
  --add-data "enc.exe;." ^
  --add-data "dec.exe;." ^
  --add-data "heroquest.fnt;." ^
  --add-data "background1.png;." ^
  --add-data "background2.png;." ^
  --add-data "background3.png;." ^
  --paths . ^
  main.py
echo.
echo Fatto: dist\HeroQuestEditor.exe
pause
