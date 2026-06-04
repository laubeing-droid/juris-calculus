@echo off
chcp 65001 >nul
echo ============================================
echo  juris-calculus L3 规则迁移回滚脚本
echo  恢复所有 .yaml.bak 备份文件
echo ============================================
echo.
set /p CONFIRM="确认回滚？(输入 YES 继续): "
if not "%CONFIRM%"=="YES" (
    echo 已取消。
    pause
    exit /b
)

set count=0
for /r %%f in (*.yaml.bak) do (
    echo 恢复: %%~dpnf
    move /y "%%f" "%%~dpnf" >nul
    set /a count+=1
)

echo.
echo ============================================
echo  回滚完成！共恢复 %count% 个文件。
echo ============================================
pause
