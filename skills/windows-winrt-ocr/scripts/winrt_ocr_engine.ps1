param (
    [switch]$ListLangs,
    [string]$InputPath = "",
    [string]$LangTag = "tr",
    [string]$OutputJson = ""
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
}

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.Media.Ocr.OcrEngine, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Foundation.UniversalApiContract, ContentType = WindowsRuntime] | Out-Null

if ($ListLangs) {
    $langs = @(
        [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object {
            [PSCustomObject]@{
                tag = $_.LanguageTag
                display_name = $_.DisplayName
            }
        }
    )
    $langs | ConvertTo-Json -Depth 3
    exit 0
}

if ([string]::IsNullOrWhiteSpace($InputPath) -or -not (Test-Path $InputPath)) {
    Write-Error "InputPath not found: $InputPath"
    exit 1
}

$engine = $null
try {
    $lang = [Windows.Globalization.Language]::new($LangTag)
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
} catch {
    $engine = $null
}

if ($null -eq $engine) {
    $prefix = $LangTag.Split('-')[0]
    foreach ($avail in [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages) {
        if ($avail.LanguageTag.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($avail)
            if ($null -ne $engine) { break }
        }
    }
}

if ($null -eq $engine) {
    $availList = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages)
    if ($availList.Count -gt 0) {
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($availList[0])
    }
}

if ($null -eq $engine) {
    Write-Error "No Windows.Media.Ocr language pack available for '$LangTag'."
    exit 1
}

$supportedExt = @('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp')
$item = Get-Item $InputPath
if ($item.PSIsContainer) {
    $files = @(Get-ChildItem $InputPath -File | Where-Object { $supportedExt -contains $_.Extension.ToLowerInvariant() } | Sort-Object Name)
} else {
    $files = @($item)
}

$results = [System.Collections.Generic.List[Object]]::new()
$sw = [System.Diagnostics.Stopwatch]::StartNew()

foreach ($f in $files) {
    $pageNum = $null
    if ($f.BaseName -match 'page_(\d+)$') {
        $pageNum = [int]$Matches[1]
    }
    try {
        $sf = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($f.FullName)) ([Windows.Storage.StorageFile])
        $stream = Await ($sf.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bmp = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])

        $linesList = [System.Collections.Generic.List[string]]::new()
        foreach ($line in $res.Lines) {
            $linesList.Add($line.Text)
        }
        $results.Add([PSCustomObject]@{
            file = $f.Name
            page = $pageNum
            language = $engine.RecognizerLanguage.LanguageTag
            text = $res.Text
            lines = $linesList
        })

        $stream.Dispose()
        $bmp.Dispose()
    }
    catch {
        $results.Add([PSCustomObject]@{
            file = $f.Name
            page = $pageNum
            language = $engine.RecognizerLanguage.LanguageTag
            text = ""
            lines = @()
            error = $_.Exception.Message
        })
    }
}

$sw.Stop()
$payload = [PSCustomObject]@{
    engine = "windows-winrt-ocr"
    language = $engine.RecognizerLanguage.LanguageTag
    elapsed_ms = $sw.ElapsedMilliseconds
    count = $results.Count
    results = $results
}
$json = $payload | ConvertTo-Json -Depth 6

if (-not [string]::IsNullOrWhiteSpace($OutputJson)) {
    $outParent = Split-Path -Parent $OutputJson
    if ($outParent -and -not (Test-Path $outParent)) {
        New-Item -ItemType Directory -Path $outParent -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($OutputJson, $json, [System.Text.Encoding]::UTF8)
} else {
    Write-Output $json
}
