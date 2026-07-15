<#
.SYNOPSIS
  Validate momjr CSV image schema
.DESCRIPTION
  Checks that every icon/sprite/sound reference in the momjr CSV files
  follows the naming convention and has no empty/broken values.
#>

$root = Split-Path -Parent $PSScriptRoot
$csvDir = Join-Path $root "momjr_csv"

$errors = @()
$warnings = @()

function Validate-CSV {
    param($Path, $Col, $PrefixExpected)
    if (-not (Test-Path $Path)) {
        $errors += "MISSING: $Path"
        return
    }
    $rows = Import-Csv $Path
    $i = 0
    foreach ($row in $rows) {
        $i++
        $val = $row.$Col
        $name = $row.name
        if ([string]::IsNullOrWhiteSpace($val)) {
            $errors += "$Path line $i ($name): $Col is empty"
        } elseif (-not $val.StartsWith($PrefixExpected)) {
            $errors += "$Path line $i ($name): $Col '$val' should start with '$PrefixExpected'"
        }
    }
    Write-Host "[OK] $Path : $i rows, $Col column validated" -ForegroundColor Green
}

# --- units.csv ---
Validate-CSV (Join-Path $csvDir "units.csv") "icon" "ICON_UNIT_"
Validate-CSV (Join-Path $csvDir "units.csv") "sprite" "SPRITE_"
Validate-CSV (Join-Path $csvDir "units.csv") "sound_select1" "SOUND_SELECT1_"
Validate-CSV (Join-Path $csvDir "units.csv") "sound_move" "SOUND_MOVE_"
Validate-CSV (Join-Path $csvDir "units.csv") "sound_attack" "SOUND_ATTACK_"

# --- improvements.csv ---
Validate-CSV (Join-Path $csvDir "improvements.csv") "icon" "ICON_IMPROVE_"

# --- advances.csv ---
Validate-CSV (Join-Path $csvDir "advances.csv") "icon" "ICON_ADVANCE_"
Validate-CSV (Join-Path $csvDir "advances.csv") "gameplay_str" "ADVANCE_"
Validate-CSV (Join-Path $csvDir "advances.csv") "historical_str" "ADVANCE_"
Validate-CSV (Join-Path $csvDir "advances.csv") "prereq_str" "ADVANCE_"
Validate-CSV (Join-Path $csvDir "advances.csv") "vari_str" "ADVANCE_"
Validate-CSV (Join-Path $csvDir "advances.csv") "stattext_str" "ADVANCE_"

# --- tileimp.csv already has icon ---
Validate-CSV (Join-Path $csvDir "tileimp.csv") "icon" "ICON_TILEIMP_"

# --- Report ---
Write-Host "`n=== Validation Summary ===" -ForegroundColor Cyan
if ($errors.Count -eq 0) {
    Write-Host "PASS: No errors" -ForegroundColor Green
} else {
    Write-Host "FAIL: $($errors.Count) errors" -ForegroundColor Red
    foreach ($e in $errors) { Write-Host "  ERROR: $e" -ForegroundColor Red }
}
if ($warnings.Count -gt 0) {
    Write-Host "WARNINGS: $($warnings.Count)" -ForegroundColor Yellow
    foreach ($w in $warnings) { Write-Host "  WARN: $w" -ForegroundColor Yellow }
}
