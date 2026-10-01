# Renders every slide of a presentation to PNG with the installed PowerPoint (read-only, no window).
# Used for visual formatting checks of translated test decks.
#   powershell -File scripts/render_slides.ps1 -Pptx deck.pptx -OutDir out\
param([Parameter(Mandatory)] [string]$Pptx, [Parameter(Mandatory)] [string]$OutDir)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $OutDir | Out-Null
$app = New-Object -ComObject PowerPoint.Application
try {
    # Open(FileName, ReadOnly, Untitled, WithWindow)
    $pres = $app.Presentations.Open((Resolve-Path $Pptx).Path, -1, 0, 0)
    try {
        foreach ($slide in $pres.Slides) {
            $slide.Export((Join-Path (Resolve-Path $OutDir) ("slide{0:D2}.png" -f $slide.SlideIndex)), "PNG", 960, 540)
        }
    } finally { $pres.Close() }
} finally {
    $app.Quit()
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($app)
}
