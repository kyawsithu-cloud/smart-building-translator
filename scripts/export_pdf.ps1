# Exports a presentation to PDF with the installed PowerPoint (read-only, no window). Test-set helper.
# Safe with your own PowerPoint open: PowerPoint is quit only if this script started it.
param([Parameter(Mandatory)] [string]$Pptx, [Parameter(Mandatory)] [string]$Pdf)

$ErrorActionPreference = "Stop"
$wasRunning = [bool](Get-Process POWERPNT -ErrorAction SilentlyContinue)
$app = New-Object -ComObject PowerPoint.Application
try {
    $pres = $app.Presentations.Open((Resolve-Path $Pptx).Path, -1, 0, 0)
    try { $pres.SaveAs($Pdf, 32) } finally { $pres.Close() }     # 32 = ppSaveAsPDF
} finally {
    if (-not $wasRunning -and $app.Presentations.Count -eq 0) { $app.Quit() }
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($app)
}
