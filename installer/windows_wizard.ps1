param(
    [ValidateSet("", "Install", "Uninstall")]
    [string]$InitialAction = "",
    [string]$InstallDir = ""
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$InstallerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir = Split-Path -Parent $InstallerDir
$UninstallKey = "Registry::HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Uninstall\AuroraBorealis"
$DefaultDir = Join-Path $env:LOCALAPPDATA "Aurora Borealis\app"

try {
    $DetectedInstalled = $false
    $DetectedDir = $DefaultDir
    if (Test-Path $UninstallKey) {
        $regLoc = (Get-ItemProperty -Path $UninstallKey -Name "InstallLocation" -ErrorAction SilentlyContinue).InstallLocation
        if (-not [string]::IsNullOrWhiteSpace($regLoc)) {
            $DetectedDir = $regLoc
            $DetectedInstalled = $true
        }
    }
    if (Test-Path (Join-Path $DetectedDir "aurora_borealis")) {
        $DetectedInstalled = $true
    }
    if ([string]::IsNullOrWhiteSpace($InstallDir)) {
        $InstallDir = $DetectedDir
    }

    # Colors matching Aurora Borealis Dark theme
    $BgDark = [System.Drawing.Color]::FromArgb(14, 15, 17)
    $Surface = [System.Drawing.Color]::FromArgb(24, 25, 29)
    $CardBg = [System.Drawing.Color]::FromArgb(29, 31, 36)
    $BorderColor = [System.Drawing.Color]::FromArgb(44, 47, 54)
    $InputBg = [System.Drawing.Color]::FromArgb(18, 19, 22)
    $FgLight = [System.Drawing.Color]::FromArgb(238, 240, 243)
    $FgMuted = [System.Drawing.Color]::FromArgb(154, 160, 166)
    $Accent = [System.Drawing.Color]::FromArgb(52, 211, 153)
    $DangerBg = [System.Drawing.Color]::FromArgb(127, 29, 29)

    $Form = New-Object System.Windows.Forms.Form
    $Form.Text = "Aurora Borealis - Windows Setup Wizard"
    $Form.Size = New-Object System.Drawing.Size(760, 620)
    $Form.MinimumSize = New-Object System.Drawing.Size(700, 560)
    $Form.StartPosition = "CenterScreen"
    $Form.BackColor = $BgDark
    $Form.ForeColor = $FgLight
    $Form.Font = New-Object System.Drawing.Font("Segoe UI", 10)

    $IcoPath = Join-Path $RepoDir "aurora_borealis\assets\aurora-borealis.ico"
    if (Test-Path $IcoPath) {
        try { $Form.Icon = New-Object System.Drawing.Icon($IcoPath) } catch {}
    }

    # Top banner
    $Header = New-Object System.Windows.Forms.Panel
    $Header.Dock = "Top"
    $Header.AutoSize = $true
    $Header.MinimumSize = New-Object System.Drawing.Size(0, 66)
    $Header.BackColor = $Surface
    $Header.Padding = New-Object System.Windows.Forms.Padding(18, 10, 18, 10)

    $HeaderLayout = New-Object System.Windows.Forms.TableLayoutPanel
    $HeaderLayout.Dock = "Fill"
    $HeaderLayout.AutoSize = $true
    $HeaderLayout.ColumnCount = 1
    $HeaderLayout.RowCount = 2
    $HeaderLayout.BackColor = $Surface
    $HeaderLayout.Margin = New-Object System.Windows.Forms.Padding(0)
    [void]$HeaderLayout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100)))
    [void]$HeaderLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$HeaderLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))

    $LblHeader = New-Object System.Windows.Forms.Label
    $LblHeader.Text = "Aurora Borealis Setup Wizard (Windows)"
    $LblHeader.Font = New-Object System.Drawing.Font("Segoe UI", 13, [System.Drawing.FontStyle]::Bold)
    $LblHeader.ForeColor = $Accent
    $LblHeader.AutoSize = $true
    $LblHeader.UseMnemonic = $false
    $LblHeader.Margin = New-Object System.Windows.Forms.Padding(0, 0, 0, 2)

    $LblStep = New-Object System.Windows.Forms.Label
    $LblStep.Text = "Step 1 of 4 - Welcome & Action"
    $LblStep.ForeColor = $FgMuted
    $LblStep.AutoSize = $true
    $LblStep.UseMnemonic = $false
    $LblStep.Margin = New-Object System.Windows.Forms.Padding(0)

    $HeaderLayout.Controls.Add($LblHeader, 0, 0)
    $HeaderLayout.Controls.Add($LblStep, 0, 1)
    $Header.Controls.Add($HeaderLayout)

    # Bottom nav bar using TableLayoutPanel so Next/Back never clip or disappear off-screen
    $Footer = New-Object System.Windows.Forms.Panel
    $Footer.Dock = "Bottom"
    $Footer.Height = 60
    $Footer.BackColor = $Surface
    $Footer.Padding = New-Object System.Windows.Forms.Padding(18, 10, 18, 10)

    $FooterLayout = New-Object System.Windows.Forms.TableLayoutPanel
    $FooterLayout.Dock = "Fill"
    $FooterLayout.ColumnCount = 4
    $FooterLayout.RowCount = 1
    $FooterLayout.BackColor = $Surface
    $FooterLayout.Margin = New-Object System.Windows.Forms.Padding(0)
    [void]$FooterLayout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$FooterLayout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100)))
    [void]$FooterLayout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$FooterLayout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$FooterLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 100)))

    $BtnCancel = New-Object System.Windows.Forms.Button
    $BtnCancel.Text = "Cancel"
    $BtnCancel.AutoSize = $true
    $BtnCancel.AutoSizeMode = "GrowAndShrink"
    $BtnCancel.MinimumSize = New-Object System.Drawing.Size(110, 36)
    $BtnCancel.Padding = New-Object System.Windows.Forms.Padding(12, 4, 12, 4)
    $BtnCancel.Margin = New-Object System.Windows.Forms.Padding(0)
    $BtnCancel.Anchor = "Left"
    $BtnCancel.BackColor = $CardBg
    $BtnCancel.ForeColor = $FgLight
    $BtnCancel.FlatStyle = "Flat"
    $BtnCancel.FlatAppearance.BorderSize = 1
    $BtnCancel.FlatAppearance.BorderColor = $BorderColor
    $BtnCancel.Add_Click({ $Form.Close() })

    $BtnBack = New-Object System.Windows.Forms.Button
    $BtnBack.Text = "< Back"
    $BtnBack.AutoSize = $true
    $BtnBack.AutoSizeMode = "GrowAndShrink"
    $BtnBack.MinimumSize = New-Object System.Drawing.Size(110, 36)
    $BtnBack.Padding = New-Object System.Windows.Forms.Padding(12, 4, 12, 4)
    $BtnBack.Margin = New-Object System.Windows.Forms.Padding(0, 0, 10, 0)
    $BtnBack.Anchor = "Right"
    $BtnBack.BackColor = $CardBg
    $BtnBack.ForeColor = $FgLight
    $BtnBack.FlatStyle = "Flat"
    $BtnBack.FlatAppearance.BorderSize = 1
    $BtnBack.FlatAppearance.BorderColor = $BorderColor

    $BtnNext = New-Object System.Windows.Forms.Button
    $BtnNext.Text = "Next >"
    $BtnNext.AutoSize = $true
    $BtnNext.AutoSizeMode = "GrowAndShrink"
    $BtnNext.MinimumSize = New-Object System.Drawing.Size(140, 36)
    $BtnNext.Padding = New-Object System.Windows.Forms.Padding(14, 4, 14, 4)
    $BtnNext.Margin = New-Object System.Windows.Forms.Padding(0)
    $BtnNext.Anchor = "Right"
    $BtnNext.BackColor = $Accent
    $BtnNext.ForeColor = $BgDark
    $BtnNext.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
    $BtnNext.FlatStyle = "Flat"
    $BtnNext.FlatAppearance.BorderSize = 0

    $FooterLayout.Controls.Add($BtnCancel, 0, 0)
    $FooterLayout.Controls.Add($BtnBack, 2, 0)
    $FooterLayout.Controls.Add($BtnNext, 3, 0)
    $Footer.Controls.Add($FooterLayout)

    # Content Host
    $Body = New-Object System.Windows.Forms.Panel
    $Body.Dock = "Fill"
    $Body.Padding = New-Object System.Windows.Forms.Padding(20)

    $Form.Controls.Add($Body)
    $Form.Controls.Add($Header)
    $Form.Controls.Add($Footer)

    # Page 0: Welcome & Action
    $Page0 = New-Object System.Windows.Forms.Panel
    $Page0.Dock = "Fill"

    $Page0Layout = New-Object System.Windows.Forms.TableLayoutPanel
    $Page0Layout.Dock = "Fill"
    $Page0Layout.ColumnCount = 1
    $Page0Layout.RowCount = 6
    [void]$Page0Layout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100)))
    [void]$Page0Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$Page0Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$Page0Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$Page0Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$Page0Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$Page0Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 100)))

    $LblStatus = New-Object System.Windows.Forms.Label
    $LblStatus.Text = if ($DetectedInstalled) { "Status: Installed in $DetectedDir" } else { "Status: Not currently installed" }
    $LblStatus.ForeColor = [System.Drawing.Color]::FromArgb(125, 211, 252)
    $LblStatus.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
    $LblStatus.AutoSize = $true
    $LblStatus.UseMnemonic = $false
    $LblStatus.Margin = New-Object System.Windows.Forms.Padding(0, 6, 0, 18)

    $RadInstall = New-Object System.Windows.Forms.RadioButton
    $RadInstall.Text = "Install / Repair Aurora Borealis"
    $RadInstall.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
    $RadInstall.AutoSize = $true
    $RadInstall.UseMnemonic = $false
    $RadInstall.Margin = New-Object System.Windows.Forms.Padding(0, 4, 0, 4)

    $LblInDesc = New-Object System.Windows.Forms.Label
    $LblInDesc.Text = "Checks/installs Python 3.10+ (via winget if missing), creates an isolated .venv with PySide6/lxml/pypdf, generates Start Menu & Desktop shortcuts, and associates .dnd5e, .dnd55e, and .dndcomp files."
    $LblInDesc.ForeColor = $FgMuted
    $LblInDesc.AutoSize = $true
    $LblInDesc.MaximumSize = New-Object System.Drawing.Size(660, 0)
    $LblInDesc.UseMnemonic = $false
    $LblInDesc.Margin = New-Object System.Windows.Forms.Padding(24, 0, 0, 16)

    $RadUninstall = New-Object System.Windows.Forms.RadioButton
    $RadUninstall.Text = "Uninstall Aurora Borealis"
    $RadUninstall.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
    $RadUninstall.AutoSize = $true
    $RadUninstall.UseMnemonic = $false
    $RadUninstall.Margin = New-Object System.Windows.Forms.Padding(0, 4, 0, 4)

    $LblUnDesc = New-Object System.Windows.Forms.Label
    $LblUnDesc.Text = "Removes Aurora Borealis application files, Start Menu & Desktop shortcuts, file associations, and Windows Apps & Features registration. Your saved characters in Documents are preserved."
    $LblUnDesc.ForeColor = $FgMuted
    $LblUnDesc.AutoSize = $true
    $LblUnDesc.MaximumSize = New-Object System.Drawing.Size(660, 0)
    $LblUnDesc.UseMnemonic = $false
    $LblUnDesc.Margin = New-Object System.Windows.Forms.Padding(24, 0, 0, 0)

    if ($InitialAction -eq "Uninstall") {
        $RadUninstall.Checked = $true
    } else {
        $RadInstall.Checked = $true
    }
    $Page0Layout.Controls.Add($LblStatus, 0, 0)
    $Page0Layout.Controls.Add($RadInstall, 0, 1)
    $Page0Layout.Controls.Add($LblInDesc, 0, 2)
    $Page0Layout.Controls.Add($RadUninstall, 0, 3)
    $Page0Layout.Controls.Add($LblUnDesc, 0, 4)
    $Page0.Controls.Add($Page0Layout)

    # Page 1: Options
    $Page1 = New-Object System.Windows.Forms.Panel
    $Page1.Dock = "Fill"

    $Page1Layout = New-Object System.Windows.Forms.TableLayoutPanel
    $Page1Layout.Dock = "Fill"
    $Page1Layout.ColumnCount = 1
    $Page1Layout.RowCount = 3
    [void]$Page1Layout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100)))
    [void]$Page1Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$Page1Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$Page1Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 100)))

    $LblDir = New-Object System.Windows.Forms.Label
    $LblDir.Text = "Target Installation Directory:"
    $LblDir.AutoSize = $true
    $LblDir.UseMnemonic = $false
    $LblDir.Margin = New-Object System.Windows.Forms.Padding(0, 6, 0, 6)

    $DirRow = New-Object System.Windows.Forms.TableLayoutPanel
    $DirRow.Dock = "Top"
    $DirRow.AutoSize = $true
    $DirRow.ColumnCount = 2
    $DirRow.RowCount = 1
    $DirRow.Margin = New-Object System.Windows.Forms.Padding(0, 0, 0, 12)
    [void]$DirRow.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100)))
    [void]$DirRow.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$DirRow.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))

    $TxtDir = New-Object System.Windows.Forms.TextBox
    $TxtDir.Text = $InstallDir
    $TxtDir.BackColor = $InputBg
    $TxtDir.ForeColor = $FgLight
    $TxtDir.Dock = "Fill"
    $TxtDir.Margin = New-Object System.Windows.Forms.Padding(0, 2, 10, 2)

    $BtnBrowse = New-Object System.Windows.Forms.Button
    $BtnBrowse.Text = "Browse..."
    $BtnBrowse.AutoSize = $true
    $BtnBrowse.AutoSizeMode = "GrowAndShrink"
    $BtnBrowse.MinimumSize = New-Object System.Drawing.Size(105, 28)
    $BtnBrowse.Margin = New-Object System.Windows.Forms.Padding(0)
    $BtnBrowse.BackColor = $CardBg
    $BtnBrowse.ForeColor = $FgLight
    $BtnBrowse.FlatStyle = "Flat"
    $BtnBrowse.FlatAppearance.BorderSize = 1
    $BtnBrowse.FlatAppearance.BorderColor = $BorderColor
    $BtnBrowse.Add_Click({
        $fbd = New-Object System.Windows.Forms.FolderBrowserDialog
        $fbd.SelectedPath = $TxtDir.Text
        if ($fbd.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { $TxtDir.Text = $fbd.SelectedPath }
    })

    $DirRow.Controls.Add($TxtDir, 0, 0)
    $DirRow.Controls.Add($BtnBrowse, 1, 0)

    $OptsHost = New-Object System.Windows.Forms.Panel
    $OptsHost.Dock = "Fill"
    $OptsHost.AutoScroll = $true

    # Install options
    $InstallOptsPanel = New-Object System.Windows.Forms.Panel
    $InstallOptsPanel.Dock = "Fill"
    $InstallOptsPanel.AutoScroll = $true

    $InstallFlow = New-Object System.Windows.Forms.FlowLayoutPanel
    $InstallFlow.Dock = "Fill"
    $InstallFlow.FlowDirection = "TopDown"
    $InstallFlow.WrapContents = $false
    $InstallFlow.AutoScroll = $true

    $ChkInPlace = New-Object System.Windows.Forms.CheckBox
    $ChkInPlace.Text = "Install in-place inside the current folder instead of copying"
    $ChkInPlace.AutoSize = $true
    $ChkInPlace.UseMnemonic = $false
    $ChkInPlace.Margin = New-Object System.Windows.Forms.Padding(0, 4, 0, 6)
    $ChkInPlace.Add_CheckedChanged({ $TxtDir.Enabled = -not $ChkInPlace.Checked; $BtnBrowse.Enabled = -not $ChkInPlace.Checked })

    $ChkDesktop = New-Object System.Windows.Forms.CheckBox
    $ChkDesktop.Text = "Create Desktop shortcut (Start Menu shortcuts are always created)"
    $ChkDesktop.Checked = $true
    $ChkDesktop.AutoSize = $true
    $ChkDesktop.UseMnemonic = $false
    $ChkDesktop.Margin = New-Object System.Windows.Forms.Padding(0, 2, 0, 6)

    $ChkAssoc = New-Object System.Windows.Forms.CheckBox
    $ChkAssoc.Text = "Associate .dnd5e, .dnd55e, and .dndcomp file extensions"
    $ChkAssoc.Checked = $true
    $ChkAssoc.AutoSize = $true
    $ChkAssoc.UseMnemonic = $false
    $ChkAssoc.Margin = New-Object System.Windows.Forms.Padding(0, 2, 0, 6)

    $ChkWinget = New-Object System.Windows.Forms.CheckBox
    $ChkWinget.Text = "Allow winget to install missing Python 3.12 / 7-Zip automatically"
    $ChkWinget.Checked = $true
    $ChkWinget.AutoSize = $true
    $ChkWinget.UseMnemonic = $false
    $ChkWinget.Margin = New-Object System.Windows.Forms.Padding(0, 2, 0, 12)

    $GrpContentPacks = New-Object System.Windows.Forms.GroupBox
    $GrpContentPacks.Text = "D&&D Content Packs (Download during Setup)"
    $GrpContentPacks.ForeColor = $FgLight
    $GrpContentPacks.AutoSize = $true
    $GrpContentPacks.MinimumSize = New-Object System.Drawing.Size(650, 96)
    $GrpContentPacks.Padding = New-Object System.Windows.Forms.Padding(12, 8, 12, 10)

    $PacksLayout = New-Object System.Windows.Forms.TableLayoutPanel
    $PacksLayout.Dock = "Fill"
    $PacksLayout.AutoSize = $true
    $PacksLayout.ColumnCount = 1
    $PacksLayout.RowCount = 2
    [void]$PacksLayout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100)))
    [void]$PacksLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$PacksLayout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))

    $ChkAuroraLegacy = New-Object System.Windows.Forms.CheckBox
    $ChkAuroraLegacy.Text = "Install official Aurora Legacy content (PHB / SRD / Supplements from GitHub)"
    $ChkAuroraLegacy.Checked = $true
    $ChkAuroraLegacy.AutoSize = $true
    $ChkAuroraLegacy.UseMnemonic = $false
    $ChkAuroraLegacy.Margin = New-Object System.Windows.Forms.Padding(2, 4, 2, 4)

    $ChkFiveTools = New-Object System.Windows.Forms.CheckBox
    $ChkFiveTools.Text = "Install 5e.tools D&D 5e / 5.5e content (Classes, Spells, Items, Feats from GitHub)"
    $ChkFiveTools.Checked = $true
    $ChkFiveTools.AutoSize = $true
    $ChkFiveTools.UseMnemonic = $false
    $ChkFiveTools.Margin = New-Object System.Windows.Forms.Padding(2, 4, 2, 2)

    $PacksLayout.Controls.Add($ChkAuroraLegacy, 0, 0)
    $PacksLayout.Controls.Add($ChkFiveTools, 0, 1)
    $GrpContentPacks.Controls.Add($PacksLayout)
    $InstallFlow.Controls.AddRange(@($ChkInPlace, $ChkDesktop, $ChkAssoc, $ChkWinget, $GrpContentPacks))
    $InstallOptsPanel.Controls.Add($InstallFlow)

    # Uninstall options
    $UninstallOptsPanel = New-Object System.Windows.Forms.Panel
    $UninstallOptsPanel.Dock = "Fill"
    $UninstallOptsPanel.AutoScroll = $true

    $UninstallFlow = New-Object System.Windows.Forms.FlowLayoutPanel
    $UninstallFlow.Dock = "Fill"
    $UninstallFlow.FlowDirection = "TopDown"
    $UninstallFlow.WrapContents = $false
    $UninstallFlow.AutoScroll = $true

    $LblUnNote = New-Object System.Windows.Forms.Label
    $LblUnNote.Text = "Removes application folder, virtual environment, shortcuts, registry Uninstall entry, and file associations.`r`nSaved characters in your Documents folder will NOT be deleted."
    $LblUnNote.ForeColor = $FgMuted
    $LblUnNote.AutoSize = $true
    $LblUnNote.MaximumSize = New-Object System.Drawing.Size(660, 0)
    $LblUnNote.UseMnemonic = $false
    $LblUnNote.Margin = New-Object System.Windows.Forms.Padding(0, 4, 0, 14)

    $ChkPurge = New-Object System.Windows.Forms.CheckBox
    $ChkPurge.Text = "Also delete configuration and downloaded XML/5e.tools caches (%APPDATA% & %LOCALAPPDATA%\Aurora Borealis)"
    $ChkPurge.Checked = $false
    $ChkPurge.AutoSize = $true
    $ChkPurge.UseMnemonic = $false

    $UninstallFlow.Controls.AddRange(@($LblUnNote, $ChkPurge))
    $UninstallOptsPanel.Controls.Add($UninstallFlow)

    $OptsHost.Controls.Add($InstallOptsPanel)
    $OptsHost.Controls.Add($UninstallOptsPanel)
    $Page1Layout.Controls.Add($LblDir, 0, 0)
    $Page1Layout.Controls.Add($DirRow, 0, 1)
    $Page1Layout.Controls.Add($OptsHost, 0, 2)
    $Page1.Controls.Add($Page1Layout)

    # Page 2: Progress
    $Page2 = New-Object System.Windows.Forms.Panel
    $Page2.Dock = "Fill"

    $Page2Layout = New-Object System.Windows.Forms.TableLayoutPanel
    $Page2Layout.Dock = "Fill"
    $Page2Layout.ColumnCount = 1
    $Page2Layout.RowCount = 3
    [void]$Page2Layout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100)))
    [void]$Page2Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$Page2Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$Page2Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 100)))

    $LblProg = New-Object System.Windows.Forms.Label
    $LblProg.Text = "Running setup..."
    $LblProg.AutoSize = $true
    $LblProg.UseMnemonic = $false
    $LblProg.Margin = New-Object System.Windows.Forms.Padding(0, 4, 0, 6)

    $ProgBar = New-Object System.Windows.Forms.ProgressBar
    $ProgBar.Dock = "Top"
    $ProgBar.Height = 22
    $ProgBar.Style = "Marquee"
    $ProgBar.Margin = New-Object System.Windows.Forms.Padding(0, 0, 0, 10)

    $TxtLog = New-Object System.Windows.Forms.TextBox
    $TxtLog.Multiline = $true
    $TxtLog.ReadOnly = $true
    $TxtLog.ScrollBars = "Vertical"
    $TxtLog.BackColor = $InputBg
    $TxtLog.ForeColor = $FgLight
    $TxtLog.Font = New-Object System.Drawing.Font("Consolas", 9.5)
    $TxtLog.Dock = "Fill"

    $Page2Layout.Controls.Add($LblProg, 0, 0)
    $Page2Layout.Controls.Add($ProgBar, 0, 1)
    $Page2Layout.Controls.Add($TxtLog, 0, 2)
    $Page2.Controls.Add($Page2Layout)

    # Page 3: Finish
    $Page3 = New-Object System.Windows.Forms.Panel
    $Page3.Dock = "Fill"

    $Page3Layout = New-Object System.Windows.Forms.TableLayoutPanel
    $Page3Layout.Dock = "Fill"
    $Page3Layout.ColumnCount = 1
    $Page3Layout.RowCount = 4
    [void]$Page3Layout.ColumnStyles.Add((New-Object System.Windows.Forms.ColumnStyle([System.Windows.Forms.SizeType]::Percent, 100)))
    [void]$Page3Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$Page3Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$Page3Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::AutoSize)))
    [void]$Page3Layout.RowStyles.Add((New-Object System.Windows.Forms.RowStyle([System.Windows.Forms.SizeType]::Percent, 100)))

    $LblFinishTitle = New-Object System.Windows.Forms.Label
    $LblFinishTitle.Font = New-Object System.Drawing.Font("Segoe UI", 13, [System.Drawing.FontStyle]::Bold)
    $LblFinishTitle.AutoSize = $true
    $LblFinishTitle.UseMnemonic = $false
    $LblFinishTitle.Margin = New-Object System.Windows.Forms.Padding(0, 8, 0, 10)

    $LblFinishDesc = New-Object System.Windows.Forms.Label
    $LblFinishDesc.AutoSize = $true
    $LblFinishDesc.MaximumSize = New-Object System.Drawing.Size(660, 0)
    $LblFinishDesc.Dock = "Top"
    $LblFinishDesc.UseMnemonic = $false
    $LblFinishDesc.Margin = New-Object System.Windows.Forms.Padding(0, 0, 0, 12)

    $ChkLaunch = New-Object System.Windows.Forms.CheckBox
    $ChkLaunch.Text = "Launch Aurora Borealis now"
    $ChkLaunch.Checked = $true
    $ChkLaunch.AutoSize = $true
    $ChkLaunch.UseMnemonic = $false
    $ChkLaunch.Margin = New-Object System.Windows.Forms.Padding(0, 0, 0, 12)

    $TxtFinishLog = New-Object System.Windows.Forms.TextBox
    $TxtFinishLog.Multiline = $true
    $TxtFinishLog.ReadOnly = $true
    $TxtFinishLog.ScrollBars = "Vertical"
    $TxtFinishLog.BackColor = $InputBg
    $TxtFinishLog.ForeColor = $FgLight
    $TxtFinishLog.Font = New-Object System.Drawing.Font("Consolas", 9.0)
    $TxtFinishLog.Dock = "Fill"
    $TxtFinishLog.Visible = $false

    $Page3Layout.Controls.Add($LblFinishTitle, 0, 0)
    $Page3Layout.Controls.Add($LblFinishDesc, 0, 1)
    $Page3Layout.Controls.Add($ChkLaunch, 0, 2)
    $Page3Layout.Controls.Add($TxtFinishLog, 0, 3)
    $Page3.Controls.Add($Page3Layout)

    $Body.Controls.AddRange(@($Page0, $Page1, $Page2, $Page3))

    $Script:CurrentPage = 0
    $Script:LastSucceeded = $false
    $Script:ChildProc = $null
    $Script:OutLog = ""
    $Script:ErrLog = ""
    $Script:OutPos = [long]0
    $Script:ErrPos = [long]0
    $Script:PollTimer = New-Object System.Windows.Forms.Timer
    $Script:PollTimer.Interval = 250

    function Read-NewLogChunk([string]$Path, [long]$Offset) {
        if ([string]::IsNullOrEmpty($Path) -or -not (Test-Path $Path)) {
            return @("", $Offset)
        }
        $fs = $null
        try {
            $fs = New-Object System.IO.FileStream(
                $Path,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Read,
                [System.IO.FileShare]::ReadWrite
            )
            if ($fs.Length -le $Offset) {
                return @("", $Offset)
            }
            $fs.Seek($Offset, [System.IO.SeekOrigin]::Begin) | Out-Null
            $sr = New-Object System.IO.StreamReader($fs, [System.Text.Encoding]::UTF8, $true)
            $chunk = $sr.ReadToEnd()
            $newOffset = $fs.Position
            return @($chunk, $newOffset)
        } catch {
            return @("", $Offset)
        } finally {
            if ($fs -ne $null) { $fs.Dispose() }
        }
    }

    function Append-RawText([string]$Chunk) {
        if ([string]::IsNullOrEmpty($Chunk) -or $Form.IsDisposed) { return }
        $norm = $Chunk -replace "`r?`n", "`r`n"
        $TxtLog.AppendText($norm)
    }

    function Show-Page([int]$Idx) {
        $Script:CurrentPage = $Idx
        $Page0.Visible = ($Idx -eq 0)
        $Page1.Visible = ($Idx -eq 1)
        $Page2.Visible = ($Idx -eq 2)
        $Page3.Visible = ($Idx -eq 3)

        $isUn = $RadUninstall.Checked
        switch ($Idx) {
            0 {
                $LblStep.Text = "Step 1 of 4 - Welcome & Action"
                $BtnBack.Visible = $false
                $BtnCancel.Visible = $true
                $BtnNext.Visible = $true
                $BtnNext.Enabled = $true
                $BtnNext.Text = "Next >"
                $BtnNext.BackColor = $Accent
                $BtnNext.ForeColor = $BgDark
                $Form.AcceptButton = $BtnNext
            }
            1 {
                $LblStep.Text = if ($isUn) { "Step 2 of 4 - Uninstall Options" } else { "Step 2 of 4 - Install Options" }
                $LblDir.Text = if ($isUn) { "Installation Directory to Remove:" } else { "Target Installation Directory:" }
                $InstallOptsPanel.Visible = (-not $isUn)
                $UninstallOptsPanel.Visible = $isUn
                $BtnBack.Visible = $true
                $BtnCancel.Visible = $true
                $BtnNext.Visible = $true
                $BtnNext.Enabled = $true
                if ($isUn) {
                    $BtnNext.Text = "Uninstall Now"
                    $BtnNext.BackColor = $DangerBg
                    $BtnNext.ForeColor = $FgLight
                } else {
                    $BtnNext.Text = "Install Now"
                    $BtnNext.BackColor = $Accent
                    $BtnNext.ForeColor = $BgDark
                }
                $Form.AcceptButton = $BtnNext
            }
            2 {
                $LblStep.Text = "Step 3 of 4 - Executing Setup"
                $BtnBack.Visible = $false
                $BtnCancel.Visible = $false
                $BtnNext.Visible = $false
                $Form.AcceptButton = $null
            }
            3 {
                $LblStep.Text = "Step 4 of 4 - Finish"
                $BtnBack.Visible = $false
                $BtnCancel.Visible = $false
                $BtnNext.Visible = $true
                $BtnNext.Enabled = $true
                $BtnNext.Text = "Finish"
                $BtnNext.BackColor = $Accent
                $BtnNext.ForeColor = $BgDark
                $Form.AcceptButton = $BtnNext
            }
        }
        $FooterLayout.PerformLayout()
    }

    $Script:PollTimer.Add_Tick({
        $resOut = Read-NewLogChunk $Script:OutLog $Script:OutPos
        $Script:OutPos = [long]$resOut[1]
        Append-RawText ([string]$resOut[0])

        $resErr = Read-NewLogChunk $Script:ErrLog $Script:ErrPos
        $Script:ErrPos = [long]$resErr[1]
        Append-RawText ([string]$resErr[0])

        if ($Script:ChildProc -ne $null -and $Script:ChildProc.HasExited) {
            $Script:PollTimer.Stop()
            $Script:ChildProc.WaitForExit()
            $resOut2 = Read-NewLogChunk $Script:OutLog $Script:OutPos
            $Script:OutPos = [long]$resOut2[1]
            Append-RawText ([string]$resOut2[0])

            $resErr2 = Read-NewLogChunk $Script:ErrLog $Script:ErrPos
            $Script:ErrPos = [long]$resErr2[1]
            Append-RawText ([string]$resErr2[0])

            $ec = $Script:ChildProc.ExitCode
            try { Remove-Item -Force $Script:OutLog, $Script:ErrLog -ErrorAction SilentlyContinue } catch {}
            $Script:ChildProc = $null

            $ProgBar.Style = "Continuous"
            $ProgBar.Value = 100
            $Script:LastSucceeded = ($ec -eq 0)
            if ($Script:LastSucceeded) {
                $TxtFinishLog.Visible = $false
                $TxtFinishLog.Text = ""
                $LblFinishTitle.ForeColor = $Accent
                if ($RadUninstall.Checked) {
                    $LblFinishTitle.Text = "Aurora Borealis Uninstalled"
                    $LblFinishDesc.Text = "Application files, shortcuts, and file associations were removed.`r`nYour saved characters in Documents were preserved."
                    $ChkLaunch.Visible = $false
                    $ChkLaunch.Checked = $false
                } else {
                    $tgt = if ($ChkInPlace.Checked) { $RepoDir } else { $TxtDir.Text.Trim() }
                    $packs = @()
                    if ($ChkAuroraLegacy.Checked) { $packs += "Aurora Legacy" }
                    if ($ChkFiveTools.Checked) { $packs += "5e.tools" }
                    $packInfo = if ($packs.Count -gt 0) { $packs -join ", " } else { "On-demand in app" }
                    $LblFinishTitle.Text = "Aurora Borealis Installation Complete"
                    $LblFinishDesc.Text = "Installed in: $tgt`r`nStart Menu shortcut created and file associations updated.`r`nContent Packs: $packInfo"
                    $ChkLaunch.Visible = $true
                    $ChkLaunch.Checked = $true
                }
            } else {
                $LblFinishTitle.ForeColor = [System.Drawing.Color]::FromArgb(252, 165, 165)
                $LblFinishTitle.Text = "Setup exited with code $ec"
                $LblFinishDesc.Text = "Please inspect the log output below or run installer\install-windows.ps1 / installer\uninstall-windows.ps1 directly."
                $ChkLaunch.Visible = $false
                $ChkLaunch.Checked = $false
                $TxtFinishLog.Text = $TxtLog.Text
                $TxtFinishLog.Visible = $true
            }
            Show-Page 3
        }
    })

    function Start-SetupProcess() {
        Show-Page 2
        $TxtLog.Clear()
        $ProgBar.Style = "Marquee"
        $isUn = $RadUninstall.Checked

        $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File")
        if ($isUn) {
            $LblProg.Text = "Uninstalling Aurora Borealis..."
            $unScript = Join-Path $InstallerDir "uninstall-windows.ps1"
            $argList += "`"$unScript`""
            if (-not [string]::IsNullOrWhiteSpace($TxtDir.Text)) {
                $argList += "-InstallDir"; $argList += "`"$($TxtDir.Text.Trim())`""
            }
            if ($ChkPurge.Checked) { $argList += "-PurgeConfig" }
        } else {
            $LblProg.Text = "Installing Aurora Borealis (Python venv, dependencies & content)..."
            $inScript = Join-Path $InstallerDir "install-windows.ps1"
            $argList += "`"$inScript`""
            if ($ChkInPlace.Checked) {
                $argList += "-InPlace"
            } elseif (-not [string]::IsNullOrWhiteSpace($TxtDir.Text)) {
                $argList += "-InstallDir"; $argList += "`"$($TxtDir.Text.Trim())`""
            }
            if ($ChkDesktop.Checked) { $argList += "-CreateDesktopShortcut" } else { $argList += "-NoDesktopShortcut" }
            if ($ChkAssoc.Checked) { $argList += "-RegisterFileAssociations" } else { $argList += "-NoFileAssociations" }
            if (-not $ChkWinget.Checked) { $argList += "-SkipWinget" }
            if ($ChkAuroraLegacy.Checked) { $argList += "-InstallAuroraLegacy" }
            if ($ChkFiveTools.Checked) { $argList += "-InstallFiveTools" }
        }

        $Stamp = [System.Guid]::NewGuid().ToString("N")
        $Script:OutLog = Join-Path $env:TEMP "aurora_setup_${Stamp}.out.log"
        $Script:ErrLog = Join-Path $env:TEMP "aurora_setup_${Stamp}.err.log"
        $Script:OutPos = [long]0
        $Script:ErrPos = [long]0
        "" | Out-File -FilePath $Script:OutLog -Encoding utf8
        "" | Out-File -FilePath $Script:ErrLog -Encoding utf8

        $argString = $argList -join " "
        Append-RawText ("powershell.exe " + $argString + "`r`n")
        $Script:ChildProc = Start-Process -FilePath "powershell.exe" `
            -ArgumentList $argString `
            -RedirectStandardOutput $Script:OutLog `
            -RedirectStandardError $Script:ErrLog `
            -WindowStyle Hidden `
            -PassThru
        $null = $Script:ChildProc.Handle
        $Script:PollTimer.Start()
    }

    $BtnBack.Add_Click({
        if ($Script:CurrentPage -eq 1) { Show-Page 0 }
    })

    $BtnNext.Add_Click({
        switch ($Script:CurrentPage) {
            0 { Show-Page 1 }
            1 { Start-SetupProcess }
            3 {
                if ($Script:LastSucceeded -and (-not $RadUninstall.Checked) -and $ChkLaunch.Checked) {
                    $tgt = if ($ChkInPlace.Checked) { $RepoDir } else { $TxtDir.Text.Trim() }
                    $bat = Join-Path $tgt "aurora-borealis.bat"
                    if (Test-Path $bat) {
                        Start-Process -FilePath $bat -WorkingDirectory $tgt
                    }
                }
                $Form.Close()
            }
        }
    })

    $Form.Add_FormClosing({
        $Script:PollTimer.Stop()
    })

    Show-Page 0
    [void]$Form.ShowDialog()
} catch {
    [System.Windows.Forms.MessageBox]::Show(
        $_.Exception.ToString(),
        "Aurora Borealis Setup Error",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}
