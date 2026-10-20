param(
    [ValidateSet('Import', 'Export', 'Inspect')][string]$Mode = 'Import',
    [string]$Path,
    [string]$Destination,
    [string]$SetupNote = '',
    [switch]$Json,
    [switch]$LibraryOnly
)

$ErrorActionPreference = 'Stop'
if (-not ('MoonshineStateShare.Files' -as [type])) {
    Add-Type -Path (Join-Path $PSScriptRoot 'StateShare.cs') -ReferencedAssemblies @(
        'System.dll', 'System.Core.dll', 'System.IO.Compression.dll', 'System.IO.Compression.FileSystem.dll'
    )
}
if ($LibraryOnly) { return }

$interactive = -not $Path -or ($Mode -ne 'Inspect' -and -not $Destination)
try {
    if ($interactive) { Add-Type -AssemblyName System.Windows.Forms }
    if (-not $Path) {
        $picker = New-Object System.Windows.Forms.OpenFileDialog
        $picker.Title = if ($Mode -eq 'Export') { 'Choose the saved state to share' } else { 'Choose the state or ZIP you received' }
        $picker.Filter = 'Moonshine states and shared ZIPs (*.mss;*.zip)|*.mss;*.zip'
        if ($picker.ShowDialog() -ne 'OK') { return }
        $Path = $picker.FileName
    }
    $state = [MoonshineStateShare.Files]::Read($Path)
    if ($Mode -eq 'Inspect') {
        if ($Json) { $state | ConvertTo-Json } else { $state | Format-List }
        return
    }
    if (-not $Destination -and $Mode -eq 'Import') {
        $picker = New-Object System.Windows.Forms.FolderBrowserDialog
        $picker.Description = 'Choose the root of your Wii SD card (for example E:). Your existing states will be kept.'
        $picker.ShowNewFolderButton = $false
        if ($picker.ShowDialog() -ne 'OK') { return }
        $Destination = $picker.SelectedPath
    }
    if (-not $Destination -and $Mode -eq 'Export') {
        $picker = New-Object System.Windows.Forms.SaveFileDialog
        $picker.Title = 'Save a ZIP to send to your friend'
        $picker.Filter = 'Shared state ZIP (*.zip)|*.zip'
        $picker.FileName = ($state.Name -replace '[^a-zA-Z0-9 _-]', '_') + ' - ' + $state.Region + '.zip'
        $picker.OverwritePrompt = $true
        if ($picker.ShowDialog() -ne 'OK') { return }
        $Destination = $picker.FileName
        Add-Type -AssemblyName Microsoft.VisualBasic
        $SetupNote = [Microsoft.VisualBasic.Interaction]::InputBox(
            'Optional: write the level/episode name, Moonshine version, video mode and launcher settings your friend should use.',
            'Notes for your friend', $SetupNote)
    }
    if ($Mode -eq 'Import') {
        $result = [MoonshineStateShare.Files]::Import($Path, $Destination)
        $message = "Copied safely to:`r`n$result`r`n`r`nOn Wii, enter the matching stage, refresh the SD states list, choose this state with Y, then use your Load bind. The game still checks compatibility."
    } else {
        $result = [MoonshineStateShare.Files]::Export($Path, $Destination, $SetupNote)
        $message = "Ready to share:`r`n$result`r`n`r`nSend this ZIP and the state-sharing helper folder. The ZIP includes instructions and keeps the original state unchanged."
    }
    if ($Json) { @{ Path = $result; Region = $state.Region; Name = $state.Name } | ConvertTo-Json }
    else { Write-Output $message }
    if ($interactive) {
        [void][System.Windows.Forms.MessageBox]::Show($message, 'Moonshine state sharing', 'OK', 'Information')
    }
} catch {
    $message = $_.Exception.GetBaseException().Message
    if ($interactive) {
        [void][System.Windows.Forms.MessageBox]::Show($message, 'State was not imported or shared', 'OK', 'Error')
    }
    Write-Error $message -ErrorAction Continue
    exit 1
}
