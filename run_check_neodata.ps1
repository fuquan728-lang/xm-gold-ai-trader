# PowerShell脚本包装Python脚本，避免中文路径问题
# 使用方法: .\run_check_neodata.ps1

# 设置控制台编码为UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# 切换到项目目录
Set-Location "d:\搬家文件夹\XM Global MT5"

# 运行Python脚本
$pythonPath = Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $pythonPath) {
    $pythonPath = Get-Command python3 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
}

if ($pythonPath) {
    Write-Host "使用Python: $pythonPath"
    Write-Host "运行NeoData技能路径检查..." -ForegroundColor Green
    Write-Host "=" * 70
    
    # 获取Python版本
    $pythonVersion = & $pythonPath --version 2>&1
    Write-Host "Python版本: $pythonVersion"
    
    # 运行检查脚本
    & $pythonPath "check_neodata_path.py"
    $exitCode = $LASTEXITCODE
    
    Write-Host "=" * 70
    if ($exitCode -eq 0) {
        Write-Host "NeoData检查脚本执行成功" -ForegroundColor Green
    } else {
        Write-Host "NeoData检查脚本执行失败 (退出代码: $exitCode)" -ForegroundColor Red
    }
    
    # 等待用户按键
    Write-Host "`n按任意键继续..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
} else {
    Write-Host "错误: 未找到Python，请确保Python已安装并在PATH中" -ForegroundColor Red
    # 等待用户按键
    Write-Host "按任意键退出..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}