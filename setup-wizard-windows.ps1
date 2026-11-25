param(
    [ValidateSet("", "Install", "Uninstall")]
    [string]$InitialAction = "",
    [string]$InstallDir = ""
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
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

    $IcoPath = Join-Path $ScriptDir "aurora_borealis\assets\aurora-borealis.ico"
    if (Test-Path $IcoPath) {
        try { $Form.Icon = New-Object System.Drawing.Icon($IcoPath) } catch {}
    }

    # Top banner
    $Header = New-Object System.Windows.Forms.Panel
    $Header.Dock = "Top"
    $Header.Height = 62
    $Header.BackColor = $Surface
    $Header.Padding = New-Object System.Windows.Forms.Padding(18, 10, 18, 10)

    $LblHeader = New-Object System.Windows.Forms.Label
    $LblHeader.Text = "Aurora Borealis Setup Wizard (Windows)"
    $LblHeader.Font = New-Object System.Drawing.Font("Segoe UI", 13, [System.Drawing.FontStyle]::Bold)
    $LblHeader.ForeColor = $Accent
    $LblHeader.AutoSize = $true
    $LblHeader.Location = New-Object System.Drawing.Point(18, 10)

    $LblStep = New-Object System.Windows.Forms.Label
    $LblStep.Text = "Step 1 of 4 - Welcome & Action"
    $LblStep.ForeColor = $FgMuted
    $LblStep.AutoSize = $true
    $LblStep.Location = New-Object System.Drawing.Point(20, 36)

    $Header.Controls.Add($LblHeader)
    $Header.Controls.Add($LblStep)

    # Bottom nav bar
    $Footer = New-Object System.Windows.Forms.Panel
    $Footer.Dock = "Bottom"
    $Footer.Height = 56
    $Footer.BackColor = $Surface

    $BtnCancel = New-Object System.Windows.Forms.Button
    $BtnCancel.Text = "Cancel"
    $BtnCancel.Width = 110
    $BtnCancel.Height = 34
    $BtnCancel.Location = New-Object System.Drawing.Point(18, 11)
    $BtnCancel.BackColor = $CardBg
    $BtnCancel.FlatStyle = "Flat"
    $BtnCancel.Add_Click({ $Form.Close() })

    $BtnBack = New-Object System.Windows.Forms.Button
    $BtnBack.Text = "< Back"
    $BtnBack.Width = 110
    $BtnBack.Height = 34
    $BtnBack.Anchor = "Top,Right"
    $BtnBack.Location = New-Object System.Drawing.Point(470, 11)
    $BtnBack.BackColor = $CardBg
    $BtnBack.FlatStyle = "Flat"

    $BtnNext = New-Object System.Windows.Forms.Button
    $BtnNext.Text = "Next >"
    $BtnNext.Width = 140
    $BtnNext.Height = 34
    $BtnNext.Anchor = "Top,Right"
    $BtnNext.Location = New-Object System.Drawing.Point(592, 11)
    $BtnNext.BackColor = $Accent
    $BtnNext.ForeColor = $BgDark
    $BtnNext.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
    $BtnNext.FlatStyle = "Flat"

    $Footer.Controls.AddRange(@($BtnCancel, $BtnBack, $BtnNext))

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

    $LblStatus = New-Object System.Windows.Forms.Label
    $LblStatus.Text = if ($DetectedInstalled) { "Status: Installed in $DetectedDir" } else { "Status: Not currently installed" }
    $LblStatus.ForeColor = [System.Drawing.Color]::FromArgb(125, 211, 252)
    $LblStatus.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
    $LblStatus.AutoSize = $true
    $LblStatus.Location = New-Object System.Drawing.Point(6, 12)

    $RadInstall = New-Object System.Windows.Forms.RadioButton
    $RadInstall.Text = "Install / Repair Aurora Borealis"
    $RadInstall.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
    $RadInstall.AutoSize = $true
    $RadInstall.Location = New-Object System.Drawing.Point(6, 62)

    $LblInDesc = New-Object System.Windows.Forms.Label
    $LblInDesc.Text = "Checks/installs Python 3.10+ (via winget if missing), creates an isolated .venv with PySide6/lxml/pypdf, generates Start Menu & Desktop shortcuts, and associates .dnd5e, .dnd55e, and .dndcomp files."
    $LblInDesc.ForeColor = $FgMuted
    $LblInDesc.Size = New-Object System.Drawing.Size(660, 48)
    $LblInDesc.Location = New-Object System.Drawing.Point(28, 92)

    $RadUninstall = New-Object System.Windows.Forms.RadioButton
    $RadUninstall.Text = "Uninstall Aurora Borealis"
    $RadUninstall.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
    $RadUninstall.AutoSize = $true
    $RadUninstall.Location = New-Object System.Drawing.Point(6, 168)

    $LblUnDesc = New-Object System.Windows.Forms.Label
    $LblUnDesc.Text = "Removes Aurora Borealis application files, Start Menu & Desktop shortcuts, file associations, and Windows Apps & Features registration. Your saved characters in Documents are preserved."
    $LblUnDesc.ForeColor = $FgMuted
    $LblUnDesc.Size = New-Object System.Drawing.Size(660, 48)
    $LblUnDesc.Location = New-Object System.Drawing.Point(28, 198)

    if ($InitialAction -eq "Uninstall") {
        $RadUninstall.Checked = $true
    } else {
        $RadInstall.Checked = $true
    }
    $Page0.Controls.AddRange(@($LblStatus, $RadInstall, $LblInDesc, $RadUninstall, $LblUnDesc))

    # Page 1: Options
    $Page1 = New-Object System.Windows.Forms.Panel
    $Page1.Dock = "Fill"

    $LblDir = New-Object System.Windows.Forms.Label
    $LblDir.Text = "Target Installation Directory:"
    $LblDir.AutoSize = $true
    $LblDir.Location = New-Object System.Drawing.Point(6, 14)

    $TxtDir = New-Object System.Windows.Forms.TextBox
    $TxtDir.Text = $InstallDir
    $TxtDir.BackColor = $InputBg
    $TxtDir.ForeColor = $FgLight
    $TxtDir.Width = 540
    $TxtDir.Location = New-Object System.Drawing.Point(6, 42)

    $BtnBrowse = New-Object System.Windows.Forms.Button
    $BtnBrowse.Text = "Browse..."
    $BtnBrowse.Width = 110
    $BtnBrowse.Height = 28
    $BtnBrowse.Location = New-Object System.Drawing.Point(558, 40)
    $BtnBrowse.BackColor = $CardBg
    $BtnBrowse.FlatStyle = "Flat"
    $BtnBrowse.Add_Click({
        $fbd = New-Object System.Windows.Forms.FolderBrowserDialog
        $fbd.SelectedPath = $TxtDir.Text
        if ($fbd.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { $TxtDir.Text = $fbd.SelectedPath }
    })

    # Install checkboxes
    $InstallOptsPanel = New-Object System.Windows.Forms.Panel
    $InstallOptsPanel.Location = New-Object System.Drawing.Point(6, 92)
    $InstallOptsPanel.Size = New-Object System.Drawing.Size(670, 310)

    $ChkInPlace = New-Object System.Windows.Forms.CheckBox
    $ChkInPlace.Text = "Install in-place inside the current folder instead of copying"
    $ChkInPlace.AutoSize = $true
    $ChkInPlace.Location = New-Object System.Drawing.Point(0, 6)
    $ChkInPlace.Add_CheckedChanged({ $TxtDir.Enabled = -not $ChkInPlace.Checked; $BtnBrowse.Enabled = -not $ChkInPlace.Checked })

    $ChkDesktop = New-Object System.Windows.Forms.CheckBox
    $ChkDesktop.Text = "Create Desktop shortcut (Start Menu shortcuts are always created)"
    $ChkDesktop.Checked = $true
    $ChkDesktop.AutoSize = $true
    $ChkDesktop.Location = New-Object System.Drawing.Point(0, 40)

    $ChkAssoc = New-Object System.Windows.Forms.CheckBox
    $ChkAssoc.Text = "Associate .dnd5e, .dnd55e, and .dndcomp file extensions"
    $ChkAssoc.Checked = $true
    $ChkAssoc.AutoSize = $true
    $ChkAssoc.Location = New-Object System.Drawing.Point(0, 74)

    $ChkWinget = New-Object System.Windows.Forms.CheckBox
    $ChkWinget.Text = "Allow winget to install missing Python 3.12 / 7-Zip automatically"
    $ChkWinget.Checked = $true
    $ChkWinget.AutoSize = $true
    $ChkWinget.Location = New-Object System.Drawing.Point(0, 108)

    $GrpContentPacks = New-Object System.Windows.Forms.GroupBox
    $GrpContentPacks.Text = "D&D Content Packs (Download during Setup)"
    $GrpContentPacks.ForeColor = $FgLight
    $GrpContentPacks.Location = New-Object System.Drawing.Point(0, 146)
    $GrpContentPacks.Size = New-Object System.Drawing.Size(660, 108)

    $ChkAuroraLegacy = New-Object System.Windows.Forms.CheckBox
    $ChkAuroraLegacy.Text = "Install official Aurora Legacy content (PHB / SRD / Supplements from GitHub)"
    $ChkAuroraLegacy.Checked = $true
    $ChkAuroraLegacy.AutoSize = $true
    $ChkAuroraLegacy.Location = New-Object System.Drawing.Point(14, 28)

    $ChkFiveTools = New-Object System.Windows.Forms.CheckBox
    $ChkFiveTools.Text = "Install 5e.tools D&D 5e / 5.5e content (Classes, Spells, Items, Feats from GitHub)"
    $ChkFiveTools.Checked = $true
    $ChkFiveTools.AutoSize = $true
    $ChkFiveTools.Location = New-Object System.Drawing.Point(14, 62)

    $GrpContentPacks.Controls.AddRange(@($ChkAuroraLegacy, $ChkFiveTools))
    $InstallOptsPanel.Controls.AddRange(@($ChkInPlace, $ChkDesktop, $ChkAssoc, $ChkWinget, $GrpContentPacks))

    # Uninstall checkboxes
    $UninstallOptsPanel = New-Object System.Windows.Forms.Panel
    $UninstallOptsPanel.Location = New-Object System.Drawing.Point(6, 92)
    $UninstallOptsPanel.Size = New-Object System.Drawing.Size(670, 210)

    $LblUnNote = New-Object System.Windows.Forms.Label
    $LblUnNote.Text = "Removes application folder, virtual environment, shortcuts, registry Uninstall entry, and file associations.`r`nSaved characters in your Documents folder will NOT be deleted."
    $LblUnNote.ForeColor = $FgMuted
    $LblUnNote.Size = New-Object System.Drawing.Size(660, 50)
    $LblUnNote.Location = New-Object System.Drawing.Point(0, 6)

    $ChkPurge = New-Object System.Windows.Forms.CheckBox
    $ChkPurge.Text = "Also delete configuration and downloaded XML/5e.tools caches (%APPDATA% & %LOCALAPPDATA%\Aurora Borealis)"
    $ChkPurge.Checked = $false
    $ChkPurge.AutoSize = $true
    $ChkPurge.Location = New-Object System.Drawing.Point(0, 72)

    $UninstallOptsPanel.Controls.AddRange(@($LblUnNote, $ChkPurge))
    $Page1.Controls.AddRange(@($LblDir, $TxtDir, $BtnBrowse, $InstallOptsPanel, $UninstallOptsPanel))

    # Page 2: Progress
    $Page2 = New-Object System.Windows.Forms.Panel
    $Page2.Dock = "Fill"

    $LblProg = New-Object System.Windows.Forms.Label
    $LblProg.Text = "Running setup..."
    $LblProg.AutoSize = $true
    $LblProg.Location = New-Object System.Drawing.Point(6, 6)

    $ProgBar = New-Object System.Windows.Forms.ProgressBar
    $ProgBar.Location = New-Object System.Drawing.Point(6, 34)
    $ProgBar.Size = New-Object System.Drawing.Size(680, 20)
    $ProgBar.Style = "Marquee"

    $TxtLog = New-Object System.Windows.Forms.TextBox
    $TxtLog.Multiline = $true
    $TxtLog.ReadOnly = $true
    $TxtLog.ScrollBars = "Vertical"
    $TxtLog.BackColor = $InputBg
    $TxtLog.ForeColor = $FgLight
    $TxtLog.Font = New-Object System.Drawing.Font("Consolas", 9.5)
    $TxtLog.Location = New-Object System.Drawing.Point(6, 66)
    $TxtLog.Size = New-Object System.Drawing.Size(680, 360)
    $TxtLog.Anchor = "Top,Bottom,Left,Right"

    $Page2.Controls.AddRange(@($LblProg, $ProgBar, $TxtLog))

    # Page 3: Finish
    $Page3 = New-Object System.Windows.Forms.Panel
    $Page3.Dock = "Fill"

    $LblFinishTitle = New-Object System.Windows.Forms.Label
    $LblFinishTitle.Font = New-Object System.Drawing.Font("Segoe UI", 13, [System.Drawing.FontStyle]::Bold)
    $LblFinishTitle.AutoSize = $true
    $LblFinishTitle.Location = New-Object System.Drawing.Point(6, 16)

    $LblFinishDesc = New-Object System.Windows.Forms.Label
    $LblFinishDesc.Size = New-Object System.Drawing.Size(660, 120)
    $LblFinishDesc.Location = New-Object System.Drawing.Point(6, 56)

    $ChkLaunch = New-Object System.Windows.Forms.CheckBox
    $ChkLaunch.Text = "Launch Aurora Borealis now"
    $ChkLaunch.Checked = $true
    $ChkLaunch.AutoSize = $true
    $ChkLaunch.Location = New-Object System.Drawing.Point(6, 190)

    $Page3.Controls.AddRange(@($LblFinishTitle, $LblFinishDesc, $ChkLaunch))

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
            }
            2 {
                $LblStep.Text = "Step 3 of 4 - Executing Setup"
                $BtnBack.Visible = $false
                $BtnCancel.Visible = $false
                $BtnNext.Visible = $false
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
            }
        }
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
                $LblFinishTitle.ForeColor = $Accent
                if ($RadUninstall.Checked) {
                    $LblFinishTitle.Text = "Aurora Borealis Uninstalled"
                    $LblFinishDesc.Text = "Application files, shortcuts, and file associations were removed.`r`nYour saved characters in Documents were preserved."
                    $ChkLaunch.Visible = $false
                    $ChkLaunch.Checked = $false
                } else {
                    $tgt = if ($ChkInPlace.Checked) { $ScriptDir } else { $TxtDir.Text.Trim() }
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
                $LblFinishDesc.Text = "Please inspect the log output above or run install-windows.bat / uninstall-windows.ps1 directly."
                $ChkLaunch.Visible = $false
                $ChkLaunch.Checked = $false
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
            $unScript = Join-Path $ScriptDir "uninstall-windows.ps1"
            $argList += "`"$unScript`""
            if (-not [string]::IsNullOrWhiteSpace($TxtDir.Text)) {
                $argList += "-InstallDir"; $argList += "`"$($TxtDir.Text.Trim())`""
            }
            if ($ChkPurge.Checked) { $argList += "-PurgeConfig" }
        } else {
            $LblProg.Text = "Installing Aurora Borealis (Python venv, dependencies & content)..."
            $inScript = Join-Path $ScriptDir "install-windows.ps1"
            $argList += "`"$inScript`""
            if ($ChkInPlace.Checked) {
                $argList += "-InPlace"
            } elseif (-not [string]::IsNullOrWhiteSpace($TxtDir.Text)) {
                $argList += "-InstallDir"; $argList += "`"$($TxtDir.Text.Trim())`""
            }
            if ($ChkDesktop.Checked) { $argList += "-CreateDesktopShortcut" } else { $argList += "-CreateDesktopShortcut:`$false" }
            if ($ChkAssoc.Checked) { $argList += "-RegisterFileAssociations" } else { $argList += "-RegisterFileAssociations:`$false" }
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
                    $tgt = if ($ChkInPlace.Checked) { $ScriptDir } else { $TxtDir.Text.Trim() }
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
