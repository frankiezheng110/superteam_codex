param(
  [string]$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$OutputRoot = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..")).Path "dist")
)

$ErrorActionPreference = "Stop"

$source = [System.IO.Path]::GetFullPath($SourceRoot)
$outputRootResolved = [System.IO.Path]::GetFullPath($OutputRoot)
$manifestPath = Join-Path $source ".codex-plugin\plugin.json"

if (-not (Test-Path -LiteralPath $manifestPath)) {
  throw "Source root is not a Codex plugin: $source"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$version = [string]$manifest.version
if ([string]::IsNullOrWhiteSpace($version)) {
  throw "Plugin version is missing in $manifestPath"
}

function Assert-UnderDirectory {
  param(
    [string]$Child,
    [string]$Parent
  )
  $childResolved = [System.IO.Path]::GetFullPath($Child)
  $parentResolved = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
  if (-not $childResolved.StartsWith($parentResolved, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to operate outside output root: $childResolved"
  }
}

function Test-SkipReleaseItem {
  param([System.IO.FileSystemInfo]$Item)
  $excludedNames = @(".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".superteam_codex", ".hook-trace-tests", "build", "dist")
  if ($excludedNames -contains $Item.Name) {
    return $true
  }
  return $Item.Name.EndsWith(".egg-info", [System.StringComparison]::OrdinalIgnoreCase)
}

function Copy-ReleaseTree {
  param(
    [string]$From,
    [string]$To
  )
  New-Item -ItemType Directory -Path $To -Force | Out-Null
  Get-ChildItem -LiteralPath $From -Force | ForEach-Object {
    if (-not (Test-SkipReleaseItem $_)) {
      $destination = Join-Path $To $_.Name
      if ($_.PSIsContainer) {
        Copy-ReleaseTree -From $_.FullName -To $destination
      } else {
        Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
      }
    }
  }
}

New-Item -ItemType Directory -Path $outputRootResolved -Force | Out-Null
$stagingRoot = Join-Path $outputRootResolved "superteam-codex-$version"
$zipPath = Join-Path $outputRootResolved "superteam-codex-$version.zip"

Assert-UnderDirectory -Child $stagingRoot -Parent $outputRootResolved
Assert-UnderDirectory -Child $zipPath -Parent $outputRootResolved

if (Test-Path -LiteralPath $stagingRoot) {
  Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}
if (Test-Path -LiteralPath $zipPath) {
  Remove-Item -LiteralPath $zipPath -Force
}

Copy-ReleaseTree -From $source -To $stagingRoot
Compress-Archive -LiteralPath $stagingRoot -DestinationPath $zipPath -Force
Remove-Item -LiteralPath $stagingRoot -Recurse -Force

Write-Host "Created release archive: $zipPath"
