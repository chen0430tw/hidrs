# kiosk_windows.ps1
# Windows Kiosk模式 - 将设备锁定为只显示广播页面
# 需要管理员权限运行

param(
    [string]$BroadcastUrl = "http://192.168.1.100:5000/broadcast-player",
    [switch]$Simulation = $false
)

Write-Host "======================================" -ForegroundColor Yellow
Write-Host "⚠️  Windows Kiosk模式启动脚本" -ForegroundColor Yellow
Write-Host "======================================" -ForegroundColor Yellow
Write-Host "广播URL: $BroadcastUrl"
Write-Host "模拟模式: $Simulation"
Write-Host "======================================" -ForegroundColor Yellow
Write-Host ""

if ($Simulation) {
    Write-Host "🎭 模拟模式：以下操作将被执行（实际不会执行）" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1. 创建Kiosk用户：" -ForegroundColor Green
    Write-Host "   New-LocalUser 'BroadcastKiosk' -Password (SecureString)"
    Write-Host ""
    Write-Host "2. 配置分配的访问权限（Assigned Access）：" -ForegroundColor Green
    Write-Host "   Set-AssignedAccess -UserName BroadcastKiosk -AppUserModelId Microsoft.MicrosoftEdge"
    Write-Host ""
    Write-Host "3. 启动Edge Kiosk模式：" -ForegroundColor Green
    Write-Host "   msedge.exe --kiosk $BroadcastUrl --edge-kiosk-type=fullscreen --no-first-run"
    Write-Host ""
    Write-Host "4. 禁用任务管理器：" -ForegroundColor Green
    Write-Host "   Set-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\System' -Name DisableTaskMgr -Value 1"
    Write-Host ""
    Write-Host "5. 禁用Alt+Tab：" -ForegroundColor Green
    Write-Host "   通过注册表修改"
    Write-Host ""
    exit 0
}

# 检查管理员权限
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "❌ 需要管理员权限运行此脚本" -ForegroundColor Red
    Write-Host "请右键点击PowerShell，选择 '以管理员身份运行'" -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "⚠️⚠️⚠️ 警告：即将进入Kiosk模式！⚠️⚠️⚠️" -ForegroundColor Red
Write-Host "设备将被锁定，只能通过物理重启退出！" -ForegroundColor Red
Write-Host ""
$confirmation = Read-Host "确定继续吗？(yes/NO)"
if ($confirmation -ne 'yes') {
    Write-Host "已取消" -ForegroundColor Yellow
    exit 0
}

Write-Host "✅ 3秒后启动Kiosk模式..." -ForegroundColor Green
Start-Sleep -Seconds 3

# 1. 创建Kiosk用户（如果不存在）
$KioskUser = "BroadcastKiosk"
$KioskPassword = ConvertTo-SecureString "Kiosk!2026" -AsPlainText -Force

try {
    Get-LocalUser -Name $KioskUser -ErrorAction Stop
    Write-Host "✅ Kiosk用户已存在" -ForegroundColor Green
} catch {
    Write-Host "📝 创建Kiosk用户: $KioskUser" -ForegroundColor Cyan
    New-LocalUser -Name $KioskUser -Password $KioskPassword -FullName "Broadcast Kiosk" -Description "HIDRS广播Kiosk用户"
}

# 2. 禁用任务管理器
Write-Host "🔒 禁用任务管理器..." -ForegroundColor Cyan
$RegPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\System"
if (-not (Test-Path $RegPath)) {
    New-Item -Path $RegPath -Force | Out-Null
}
Set-ItemProperty -Path $RegPath -Name "DisableTaskMgr" -Value 1 -Type DWord

# 3. 禁用Alt+Tab
Write-Host "🔒 禁用Alt+Tab..." -ForegroundColor Cyan
$RegPath2 = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
Set-ItemProperty -Path $RegPath2 -Name "DisableTaskSwitcher" -Value 1 -Type DWord

# 4. 隐藏任务栏
Write-Host "🔒 隐藏任务栏..." -ForegroundColor Cyan
$RegPath3 = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StuckRects3"
# 注意：隐藏任务栏需要重启资源管理器

# 5. 配置分配的访问权限（Windows 10/11专业版及以上）
Write-Host "📝 配置分配的访问权限..." -ForegroundColor Cyan

$ConfigXml = @"
<?xml version="1.0" encoding="utf-8" ?>
<AssignedAccessConfiguration xmlns="http://schemas.microsoft.com/AssignedAccess/2017/config">
  <Profiles>
    <Profile Id="{9A2A490F-10F6-4764-974A-43B19E722C23}">
      <AllAppsList>
        <AllowedApps>
          <App AppUserModelId="Microsoft.MicrosoftEdge_8wekyb3d8bbwe!MicrosoftEdge" />
        </AllowedApps>
      </AllAppsList>
      <StartLayout>
        <![CDATA[<LayoutModificationTemplate xmlns="http://schemas.microsoft.com/Start/2014/LayoutModification">
          <RequiredStartGroupsCollection>
            <RequiredStartGroups>
              <AppendGroup Name="广播">
                <start:DesktopApplicationTile DesktopApplicationID="MSEdge" />
              </AppendGroup>
            </RequiredStartGroups>
          </RequiredStartGroupsCollection>
        </LayoutModificationTemplate>]]>
      </StartLayout>
      <Taskbar ShowTaskbar="false"/>
    </Profile>
  </Profiles>
  <Configs>
    <Config>
      <Account>$KioskUser</Account>
      <DefaultProfile Id="{9A2A490F-10F6-4764-974A-43B19E722C23}"/>
    </Config>
  </Configs>
</AssignedAccessConfiguration>
"@

$ConfigFile = "$env:TEMP\AssignedAccess.xml"
$ConfigXml | Out-File -FilePath $ConfigFile -Encoding utf8

try {
    Set-AssignedAccess -Configuration $ConfigFile
    Write-Host "✅ 分配的访问权限已配置" -ForegroundColor Green
} catch {
    Write-Host "⚠️ 无法配置分配的访问权限（可能不支持此版本的Windows）" -ForegroundColor Yellow
}

# 6. 启动Edge Kiosk模式
Write-Host "🚀 启动Edge Kiosk模式..." -ForegroundColor Green
Write-Host "按 Ctrl+Alt+Del 然后选择 '注销' 可以退出" -ForegroundColor Yellow
Write-Host ""

# 查找Edge路径
$EdgePath = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $EdgePath)) {
    $EdgePath = "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
}

if (Test-Path $EdgePath) {
    & $EdgePath --kiosk $BroadcastUrl --edge-kiosk-type=fullscreen --no-first-run --disable-features=TranslateUI --disable-pinch
} else {
    Write-Host "❌ 未找到Microsoft Edge" -ForegroundColor Red
    Write-Host "尝试使用Chrome..." -ForegroundColor Yellow

    $ChromePath = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
    if (Test-Path $ChromePath) {
        & $ChromePath --kiosk $BroadcastUrl --no-first-run --disable-infobars
    } else {
        Write-Host "❌ 未找到Chrome或Edge" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "✅ Kiosk模式已启动" -ForegroundColor Green
Write-Host ""
Write-Host "要退出Kiosk模式，请执行以下步骤：" -ForegroundColor Yellow
Write-Host "1. 按 Ctrl+Alt+Del" -ForegroundColor Yellow
Write-Host "2. 选择 '注销'" -ForegroundColor Yellow
Write-Host "3. 以管理员身份运行PowerShell" -ForegroundColor Yellow
Write-Host "4. 执行: Clear-AssignedAccess" -ForegroundColor Yellow
Write-Host "5. 删除注册表项以恢复任务管理器和Alt+Tab" -ForegroundColor Yellow
