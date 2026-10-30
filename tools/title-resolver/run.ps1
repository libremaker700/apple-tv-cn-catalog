[CmdletBinding()]
param([string[]]$Titles,[string[]]$Slugs,[int]$Limit=3,[switch]$Force,[switch]$AsJson,
      [string]$CredentialsPath,[string]$PythonPath)
$ErrorActionPreference='Stop'
$catalogRoot=(Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
if (-not $PythonPath) { $PythonPath=Join-Path $catalogRoot '.venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath)) { throw '请用 -PythonPath 指定已安装 requests/Pillow/OpenCC 的 Python。' }
if ($Titles) {
    $entries=(Get-Content -LiteralPath (Join-Path $catalogRoot 'docs/catalog.json') -Raw -Encoding UTF8 | ConvertFrom-Json).entries
    foreach ($title in $Titles) {
        $entry=@($entries | Where-Object { $_.en -eq $title -or $_.slug -eq $title -or $_.zh.title -eq $title })
        if ($entry.Count -ne 1) { throw "片库内没有唯一对应作品：$title；请使用 Apple 官方 slug。" }
        $Slugs+= $entry[0].slug
    }
}
$resolverArgs=@((Join-Path $catalogRoot 'scripts/resolve_titles.py'),'--limit',([Math]::Min(5,[Math]::Max(0,$Limit))).ToString())
foreach ($slug in @($Slugs | Select-Object -Unique)) { $resolverArgs+=@('--slug',$slug) }
if ($Force) { $resolverArgs+='--force' }
if ($CredentialsPath) { $resolverArgs+=@('--credentials',(Resolve-Path -LiteralPath $CredentialsPath).Path) }
$result=& $PythonPath @resolverArgs
if ($LASTEXITCODE -ne 0) { throw '核名流程失败，已保留上一版有效片库。' }
if ($AsJson) { $result } else { ($result -join "`n" | ConvertFrom-Json) | Format-List }
