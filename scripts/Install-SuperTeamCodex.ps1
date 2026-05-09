param(
  [string]$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$PluginRoot = (Join-Path $env:USERPROFILE "plugins\superteam_codex"),
  [string]$MarketplacePath = (Join-Path $env:USERPROFILE ".agents\plugins\marketplace.json"),
  [string]$CacheRoot = (Join-Path $env:USERPROFILE ".codex\plugins\cache\frankie-local\superteam-codex"),
  [string]$RepositoryUrl = "https://github.com/frankiezheng110/superteam_codex",
  [switch]$SkipCacheRefresh
)

$ErrorActionPreference = "Stop"

function Assert-UnderHome {
  param([string]$PathValue)
  $resolved = [System.IO.Path]::GetFullPath($PathValue)
  $homeRoot = [System.IO.Path]::GetFullPath($env:USERPROFILE)
  if (-not $resolved.StartsWith($homeRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to write outside user profile: $resolved"
  }
}

Assert-UnderHome $PluginRoot
Assert-UnderHome $MarketplacePath
Assert-UnderHome $CacheRoot

$source = [System.IO.Path]::GetFullPath($SourceRoot)
$target = [System.IO.Path]::GetFullPath($PluginRoot)
$cacheRootResolved = [System.IO.Path]::GetFullPath($CacheRoot)

$manifestPath = Join-Path $source ".codex-plugin\plugin.json"
if (-not (Test-Path $manifestPath)) {
  throw "Source root is not a Codex plugin: $source"
}

$pluginManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$pluginVersion = [string]$pluginManifest.version
if ([string]::IsNullOrWhiteSpace($pluginVersion)) {
  throw "Plugin version is missing in $manifestPath"
}

function Test-SkipPluginItem {
  param([System.IO.FileSystemInfo]$Item)
  $excludedNames = @(".git", "__pycache__", ".pytest_cache", ".superteam_codex", ".hook-trace-tests", "build", "dist")
  if ($excludedNames -contains $Item.Name) {
    return $true
  }
  return $Item.Name.EndsWith(".egg-info", [System.StringComparison]::OrdinalIgnoreCase)
}

function Copy-PluginTree {
  param(
    [string]$From,
    [string]$To
  )
  New-Item -ItemType Directory -Path $To -Force | Out-Null
  Get-ChildItem -LiteralPath $From -Force | ForEach-Object {
    if (-not (Test-SkipPluginItem $_)) {
      $destination = Join-Path $To $_.Name
      if ($_.PSIsContainer) {
        Copy-PluginTree -From $_.FullName -To $destination
      } else {
        Copy-Item -LiteralPath $_.FullName -Destination $destination -Force
      }
    }
  }
}

if (Test-Path $target) {
  $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
  $backup = "$target.backup-$stamp"
  Move-Item -LiteralPath $target -Destination $backup
  Write-Host "Backed up existing plugin to $backup"
}

Copy-PluginTree -From $source -To $target

if (-not $SkipCacheRefresh) {
  $cacheTarget = Join-Path $cacheRootResolved $pluginVersion
  if (Test-Path $cacheTarget) {
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $backup = "$cacheTarget.backup-$stamp"
    Move-Item -LiteralPath $cacheTarget -Destination $backup
    Write-Host "Backed up existing runtime cache to $backup"
  }
  Copy-PluginTree -From $source -To $cacheTarget
}

$marketplaceDir = Split-Path -Parent $MarketplacePath
New-Item -ItemType Directory -Path $marketplaceDir -Force | Out-Null

if (Test-Path $MarketplacePath) {
  $marketplace = Get-Content -LiteralPath $MarketplacePath -Raw | ConvertFrom-Json
} else {
  $marketplace = [pscustomobject]@{
    name = "frankie-local"
    interface = [pscustomobject]@{ displayName = "frankie-local" }
    plugins = @()
  }
}

$entry = [pscustomobject]@{
  name = "superteam-codex"
  source = [pscustomobject]@{
    source = "local"
    path = "./plugins/superteam_codex"
  }
  policy = [pscustomobject]@{
    installation = "AVAILABLE"
    authentication = "ON_INSTALL"
  }
  category = "Productivity"
}

$plugins = @($marketplace.plugins | Where-Object { $_.name -ne "superteam-codex" })
$plugins += $entry
$marketplace.plugins = $plugins
$json = $marketplace | ConvertTo-Json -Depth 20
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($MarketplacePath, $json + [Environment]::NewLine, $utf8NoBom)

Write-Host "Installed SuperTeam Codex to $target"
Write-Host "Updated marketplace at $MarketplacePath"
if (-not $SkipCacheRefresh) {
  Write-Host "Refreshed runtime cache at $(Join-Path $cacheRootResolved $pluginVersion)"
}
Write-Host "Canonical update source: $RepositoryUrl"
