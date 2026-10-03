# Ground truth for the overflow check: asks the installed PowerPoint how tall the laid-out text of every text box
# really is. Writes one JSON line per text box: file, slide, shape id, box height, text height, auto-fit mode.
#   powershell -File scripts/measure_text.ps1 -Folder some\folder > measurements.jsonl
# Read-only and without a window. Safe with your own PowerPoint open: only the files opened here are closed, and
# PowerPoint itself is quit only if this script started it.
param([Parameter(Mandatory)] [string]$Folder)

$ErrorActionPreference = "Stop"
$wasRunning = [bool](Get-Process POWERPNT -ErrorAction SilentlyContinue)
$app = New-Object -ComObject PowerPoint.Application

function Measure-Shape($shape, $file, $slideNo) {
    if ($shape.Type -eq 6) {                       # group: measure the members
        foreach ($s in $shape.GroupItems) { Measure-Shape $s $file $slideNo }
        return
    }
    if (-not $shape.HasTextFrame) { return }
    $tf = $shape.TextFrame2
    if (-not $tf.HasText) { return }
    $first = $tf.TextRange.Paragraphs(1)
    [pscustomobject]@{
        file = $file; slide = $slideNo; shape = $shape.Id
        box = [math]::Round($shape.Height - $tf.MarginTop - $tf.MarginBottom, 1)
        text = [math]::Round($tf.TextRange.BoundHeight, 1)
        autosize = $tf.AutoSize; wrap = $tf.WordWrap
        lines = $tf.TextRange.Lines().Count; paragraphs = $tf.TextRange.Paragraphs().Count
        size = $first.Font.Size; font = $first.Font.Name; ea = $first.Font.NameFarEast
        before = $first.ParagraphFormat.SpaceBefore; after = $first.ParagraphFormat.SpaceAfter
        within = $first.ParagraphFormat.SpaceWithin; rule = $first.ParagraphFormat.LineRuleWithin
    } | ConvertTo-Json -Compress
}

try {
    foreach ($f in Get-ChildItem -Path $Folder -Filter *.pptx) {
        # Open(FileName, ReadOnly, Untitled, WithWindow)
        $pres = $app.Presentations.Open($f.FullName, -1, 0, 0)
        try {
            foreach ($slide in $pres.Slides) {
                foreach ($shape in $slide.Shapes) { Measure-Shape $shape $f.Name $slide.SlideIndex }
            }
        } finally { $pres.Close() }
    }
} finally {
    if (-not $wasRunning -and $app.Presentations.Count -eq 0) { $app.Quit() }
    [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($app)
}