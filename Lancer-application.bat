@echo off
rem Extraction de modele DMN a partir de modele BPMN - lanceur.
rem Double-cliquez : le serveur demarre et le navigateur s'ouvre.
rem Tout fonctionne hors ligne. Fermez cette fenetre (ou Ctrl+C)
rem pour arreter l'application.
rem Pour un acces depuis d'autres ordinateurs du reseau local :
rem   Lancer-application.bat --reseau
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (
    python cli.py servir %*
    goto :fin
if not "%errorlevel%"=="0" pause
)
where py >nul 2>nul
if %errorlevel%==0 (
    py cli.py servir %*
    goto :fin
if not "%errorlevel%"=="0" pause
)
if exist Extraction-DMN.exe (
    Extraction-DMN.exe %*
    goto :fin
if not "%errorlevel%"=="0" pause
)
echo.
echo  Python est introuvable sur cet ordinateur et l'executable
echo  autonome Extraction-DMN.exe n'est pas present dans ce dossier.
echo  Installez Python (python.org) ou copiez Extraction-DMN.exe ici.
echo.
pause
:fin
if not "%errorlevel%"=="0" pause
