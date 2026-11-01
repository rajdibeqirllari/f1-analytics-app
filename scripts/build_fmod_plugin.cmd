@echo off
rem Build the unmodified vendor SDK example for the x64 runtime.
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b 1
set "SDK=%~dp0..\assets\sounds\fmod-api-1.08.12\api\lowlevel"
cl /nologo /LD /EHsc /DWIN32 /I "%SDK%\inc" "%SDK%\examples\plugins\fmod_distance_filter.cpp" /Fo"%SDK%\lib\distance_filter.obj" /link /OUT:"%SDK%\lib\fmod_distance_filter64.dll"
