$ErrorActionPreference = 'Stop'
$baseUrl = 'https://servicodados.ibge.gov.br/api/v1/localidades'
$states = Invoke-RestMethod -Uri "$baseUrl/estados" -TimeoutSec 60
$municipalities = Invoke-RestMethod -Uri "$baseUrl/municipios" -TimeoutSec 60
if ($states.Count -ne 27 -or $municipalities.Count -lt 5500) {
    throw 'Resposta IBGE incompleta; nenhuma base local foi substituida.'
}

$stateNames = [ordered]@{}
foreach ($state in ($states | Sort-Object sigla)) {
    if ($state.sigla -cnotmatch '^[A-Z]{2}$' -or -not $state.nome) {
        throw 'UF invalida na resposta IBGE.'
    }
    $stateNames[$state.sigla] = [string]$state.nome
}
$rows = @(
    foreach ($city in ($municipalities | Sort-Object id)) {
        $uf = $city.'regiao-imediata'.'regiao-intermediaria'.UF.sigla
        if (-not $uf) { $uf = $city.microrregiao.mesorregiao.UF.sigla }
        if (-not $city.nome -or [string]$city.id -notmatch '^\d{7}$' -or -not $stateNames.Contains($uf)) {
            throw 'Municipio invalido na resposta IBGE.'
        }
        ,@([int]$city.id, [string]$city.nome, [string]$uf)
    }
)
if (@($rows | ForEach-Object { $_[0] } | Sort-Object -Unique).Count -ne $rows.Count) {
    throw 'Identificadores duplicados na resposta IBGE.'
}
$data = [ordered]@{
    schema_version = 1
    source = 'IBGE - API de Localidades'
    source_urls = @("$baseUrl/estados", "$baseUrl/municipios")
    retrieved_at = [DateTime]::UtcNow.ToString('o')
    scope = 'Current Brazilian municipalities; not publication places or a worldwide gazetteer.'
    columns = @('ibge_id', 'name', 'uf')
    states = $stateNames
    cities = $rows
}
$directory = Join-Path (Split-Path $PSScriptRoot -Parent) 'data'
[void][IO.Directory]::CreateDirectory($directory)
$destination = Join-Path $directory 'brazilian_places.json'
$temporary = Join-Path $directory 'brazilian_places.json.tmp'
$json = ConvertTo-Json -InputObject $data -Depth 6 -Compress -EscapeHandling EscapeNonAscii
[IO.File]::WriteAllText($temporary, $json + "`n", [Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $temporary -Destination $destination -Force
Write-Output "Base local atualizada: $($rows.Count) municipios, $($states.Count) UFs."
