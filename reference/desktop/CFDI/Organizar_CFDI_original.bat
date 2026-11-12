@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ==================================================
echo                 ORGANIZADOR DE CFDI
echo ==================================================
echo.

set "RFC="
set /p "RFC=INGRESA EL RFC: "
if not defined RFC goto ERROR_RFC

set "EJERCICIO=2026"
set /p "EJERCICIO=INGRESA EL EJERCICIO [2026]: "
if not defined EJERCICIO set "EJERCICIO=2026"

set "ORIGEN_BASE="
set /p "ORIGEN_BASE=RUTA DE ORIGEN [C:\elcfdi\DescargaMasiva]: "
if not defined ORIGEN_BASE set "ORIGEN_BASE=C:\elcfdi\DescargaMasiva"
set "ORIGEN_BASE=%ORIGEN_BASE:"=%"
if not "%ORIGEN_BASE:~-1%"=="\" set "ORIGEN_BASE=%ORIGEN_BASE%\"

set "DESTINO_BASE="
set /p "DESTINO_BASE=RUTA DE DESTINO [CARPETA DEL BAT: %~dp0]: "
if not defined DESTINO_BASE set "DESTINO_BASE=%~dp0"
set "DESTINO_BASE=%DESTINO_BASE:"=%"
if not "%DESTINO_BASE:~-1%"=="\" set "DESTINO_BASE=%DESTINO_BASE%\"
set "RUTA_REPORTES=%ORIGEN_BASE%Reportes"

set "TOTAL_SELECCION=0"
echo.
echo QUE CARPETAS DE MES QUIERES CREAR Y PROCESAR?
echo 1. TODOS LOS MESES
 echo 2. SELECCIONAR MESES MANUALMENTE
choice /C 12 /N /M "ELIGE 1 O 2: "
if errorlevel 2 goto SELECCION_MANUAL
call :SELECCIONAR_TODOS
 goto CONFIRMAR

:SELECCION_MANUAL
call :PREGUNTAR_MES "01" "ENERO"
call :PREGUNTAR_MES "02" "FEBRERO"
call :PREGUNTAR_MES "03" "MARZO"
call :PREGUNTAR_MES "04" "ABRIL"
call :PREGUNTAR_MES "05" "MAYO"
call :PREGUNTAR_MES "06" "JUNIO"
call :PREGUNTAR_MES "07" "JULIO"
call :PREGUNTAR_MES "08" "AGOSTO"
call :PREGUNTAR_MES "09" "SEPTIEMBRE"
call :PREGUNTAR_MES "10" "OCTUBRE"
call :PREGUNTAR_MES "11" "NOVIEMBRE"
call :PREGUNTAR_MES "12" "DICIEMBRE"
if !TOTAL_SELECCION! EQU 0 goto SIN_MESES

echo.
echo REVISA LOS DATOS:
echo RFC: %RFC%
echo EJERCICIO: %EJERCICIO%
echo ORIGEN EMITIDOS: %ORIGEN_BASE%Emitidos\%RFC%
echo ORIGEN RECIBIDOS: %ORIGEN_BASE%Recibidos\%RFC%
echo ORIGEN REPORTES: %RUTA_REPORTES%
echo DESTINO: %DESTINO_BASE%
echo MESES SELECCIONADOS:
if "!SEL_01!"=="1" echo 01.- ENERO
if "!SEL_02!"=="1" echo 02.- FEBRERO
if "!SEL_03!"=="1" echo 03.- MARZO
if "!SEL_04!"=="1" echo 04.- ABRIL
if "!SEL_05!"=="1" echo 05.- MAYO
if "!SEL_06!"=="1" echo 06.- JUNIO
if "!SEL_07!"=="1" echo 07.- JULIO
if "!SEL_08!"=="1" echo 08.- AGOSTO
if "!SEL_09!"=="1" echo 09.- SEPTIEMBRE
if "!SEL_10!"=="1" echo 10.- OCTUBRE
if "!SEL_11!"=="1" echo 11.- NOVIEMBRE
if "!SEL_12!"=="1" echo 12.- DICIEMBRE

goto CONFIRMAR

:SELECCIONAR_TODOS
set "SEL_01=1"
set "SEL_02=1"
set "SEL_03=1"
set "SEL_04=1"
set "SEL_05=1"
set "SEL_06=1"
set "SEL_07=1"
set "SEL_08=1"
set "SEL_09=1"
set "SEL_10=1"
set "SEL_11=1"
set "SEL_12=1"
set "TOTAL_SELECCION=12"
echo.
echo SE SELECCIONARON LOS DOCE MESES.
exit /b

:PREGUNTAR_MES
choice /C SN /N /M "INCLUIR %~1.- %~2? (S/N): "
if errorlevel 2 exit /b
set "SEL_%~1=1"
set /a TOTAL_SELECCION+=1
exit /b

:CONFIRMAR
echo.
echo RFC: %RFC%   EJERCICIO: %EJERCICIO%
echo ORIGEN: %ORIGEN_BASE%
echo DESTINO: %DESTINO_BASE%
echo SE CREARAN LAS CARPETAS SELECCIONADAS Y SE MOVERAN LOS ARCHIVOS EN UNA SOLA EJECUCION.
echo LOS ARCHIVOS DUPLICADOS EN EL DESTINO SE OMITIRAN.
echo.
choice /C SN /N /M "CONFIRMAS INICIAR? (S/N): "
if errorlevel 2 goto CANCELAR

if "!SEL_01!"=="1" call :CREAR_MES "01" "ENERO"
if "!SEL_02!"=="1" call :CREAR_MES "02" "FEBRERO"
if "!SEL_03!"=="1" call :CREAR_MES "03" "MARZO"
if "!SEL_04!"=="1" call :CREAR_MES "04" "ABRIL"
if "!SEL_05!"=="1" call :CREAR_MES "05" "MAYO"
if "!SEL_06!"=="1" call :CREAR_MES "06" "JUNIO"
if "!SEL_07!"=="1" call :CREAR_MES "07" "JULIO"
if "!SEL_08!"=="1" call :CREAR_MES "08" "AGOSTO"
if "!SEL_09!"=="1" call :CREAR_MES "09" "SEPTIEMBRE"
if "!SEL_10!"=="1" call :CREAR_MES "10" "OCTUBRE"
if "!SEL_11!"=="1" call :CREAR_MES "11" "NOVIEMBRE"
if "!SEL_12!"=="1" call :CREAR_MES "12" "DICIEMBRE"

if "!SEL_01!"=="1" call :PROCESAR_MES "01" "ENERO"
if "!SEL_02!"=="1" call :PROCESAR_MES "02" "FEBRERO"
if "!SEL_03!"=="1" call :PROCESAR_MES "03" "MARZO"
if "!SEL_04!"=="1" call :PROCESAR_MES "04" "ABRIL"
if "!SEL_05!"=="1" call :PROCESAR_MES "05" "MAYO"
if "!SEL_06!"=="1" call :PROCESAR_MES "06" "JUNIO"
if "!SEL_07!"=="1" call :PROCESAR_MES "07" "JULIO"
if "!SEL_08!"=="1" call :PROCESAR_MES "08" "AGOSTO"
if "!SEL_09!"=="1" call :PROCESAR_MES "09" "SEPTIEMBRE"
if "!SEL_10!"=="1" call :PROCESAR_MES "10" "OCTUBRE"
if "!SEL_11!"=="1" call :PROCESAR_MES "11" "NOVIEMBRE"
if "!SEL_12!"=="1" call :PROCESAR_MES "12" "DICIEMBRE"

echo.
echo PROCESO TERMINADO.
echo DESTINO: %DESTINO_BASE%
echo.
timeout /t 8 /nobreak >nul
endlocal
exit /b

:CREAR_MES
if not exist "%DESTINO_BASE%%~1.- %~2\EMITIDOS\" mkdir "%DESTINO_BASE%%~1.- %~2\EMITIDOS" 2>nul
if not exist "%DESTINO_BASE%%~1.- %~2\RECIBIDOS\" mkdir "%DESTINO_BASE%%~1.- %~2\RECIBIDOS" 2>nul
exit /b

:PROCESAR_MES
set "MM=%~1"
set "NOMBRE_MES=%~2"
set "PERIODO=%EJERCICIO%-%MM%"
set "PERIODO_COMPACTO=%EJERCICIO%%MM%"
set "DESTINO_MES=%DESTINO_BASE%%MM%.- %NOMBRE_MES%"
echo.
echo REVISANDO PERIODO %PERIODO%...

set "ORIGEN=%ORIGEN_BASE%Emitidos\%RFC%\%PERIODO%"
set "DESTINO=%DESTINO_MES%\EMITIDOS"
call :MOVER_PDF_XML "EMITIDOS"

set "ORIGEN=%ORIGEN_BASE%Recibidos\%RFC%\%PERIODO%"
set "DESTINO=%DESTINO_MES%\RECIBIDOS"
call :MOVER_PDF_XML "RECIBIDOS"

call :MOVER_REPORTE "EMITIDOS"
call :MOVER_REPORTE "RECIBIDOS"
exit /b

:MOVER_PDF_XML
if not exist "%ORIGEN%\" (
    echo NO SE ENCONTRO LA CARPETA DE ORIGEN: %ORIGEN%
    exit /b
)
set "HAY_ARCHIVOS=NO"
for %%F in ("%ORIGEN%\*.pdf" "%ORIGEN%\*.xml") do (
    if exist "%%~fF" if not exist "%%~fF\" set "HAY_ARCHIVOS=SI"
)
if /I "!HAY_ARCHIVOS!"=="NO" (
    echo SIN PDF/XML DIRECTOS EN %ORIGEN%. SE OMITEN SUBCARPETAS.
    exit /b
)
echo MOVIENDO PDF/XML DE %~1: %ORIGEN%
for %%F in ("%ORIGEN%\*.pdf" "%ORIGEN%\*.xml") do (
    if exist "%%~fF" if not exist "%%~fF\" (
        if exist "%DESTINO%\%%~nxF" (
            echo OMITIDO POR DUPLICADO: %%~nxF
        ) else (
            move /Y "%%~fF" "%DESTINO%\" >nul
            if errorlevel 1 echo ERROR AL MOVER: %%~nxF
        )
    )
)
exit /b

:MOVER_REPORTE
set "TIPO_REPORTE=%~1"
set "HAY_ARCHIVOS=NO"
for %%F in ("%RUTA_REPORTES%\%TIPO_REPORTE%-%RFC%-%PERIODO_COMPACTO%.xls" "%RUTA_REPORTES%\%TIPO_REPORTE%-%RFC%-%PERIODO_COMPACTO%.xlsx" "%RUTA_REPORTES%\%TIPO_REPORTE%-%RFC%-%PERIODO_COMPACTO%.xlsm") do (
    if exist "%%~fF" if not exist "%%~fF\" set "HAY_ARCHIVOS=SI"
)
if /I "!HAY_ARCHIVOS!"=="NO" exit /b
echo MOVIENDO REPORTE %TIPO_REPORTE% DEL PERIODO %PERIODO% A LA RAIZ DEL MES...
for %%F in ("%RUTA_REPORTES%\%TIPO_REPORTE%-%RFC%-%PERIODO_COMPACTO%.xls" "%RUTA_REPORTES%\%TIPO_REPORTE%-%RFC%-%PERIODO_COMPACTO%.xlsx" "%RUTA_REPORTES%\%TIPO_REPORTE%-%RFC%-%PERIODO_COMPACTO%.xlsm") do (
    if exist "%%~fF" if not exist "%%~fF\" (
        if exist "%DESTINO_MES%\%%~nxF" (
            echo OMITIDO POR DUPLICADO: %%~nxF
        ) else (
            move /Y "%%~fF" "%DESTINO_MES%\" >nul
            if errorlevel 1 echo ERROR AL MOVER: %%~nxF
        )
    )
)
exit /b

:ERROR_RFC
echo DEBES INGRESAR UN RFC.
timeout /t 8 /nobreak >nul
endlocal
exit /b 1

:SIN_MESES
echo NO SE SELECCIONO NINGUN MES. NO SE REALIZARON CAMBIOS.
timeout /t 8 /nobreak >nul
endlocal
exit /b

:CANCELAR
echo OPERACION CANCELADA. NO SE MOVIERON ARCHIVOS.
timeout /t 8 /nobreak >nul
endlocal
exit /b
