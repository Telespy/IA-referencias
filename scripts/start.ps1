$ErrorActionPreference = 'Stop'
Push-Location (Split-Path -Parent $PSScriptRoot)
try {
    python scripts/setup_local.py
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar configuracao local.' }
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao iniciar os containers.' }
    docker compose exec -T --user hermes hermes hermes plugins enable brain-format --no-allow-tool-override
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao ativar a integracao Hermes.' }
    docker compose exec -T --user hermes hermes hermes config set gateway.multiplex_profiles false
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao configurar perfil unico do bot.' }
    docker compose exec -T --user hermes hermes hermes config set telegram.typing_indicator true
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao ativar indicador de processamento.' }
    docker compose exec -T --user hermes hermes hermes config set platform_toolsets.telegram '[brain_format]'
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao configurar ferramentas do Telegram.' }
    docker compose exec -T --user hermes hermes hermes config set platform_toolsets.api_server '[brain_format]'
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao configurar ferramentas do painel.' }
    docker compose exec -T --user hermes hermes hermes config set model.context_length 64000
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao configurar contexto do modelo.' }
    docker compose exec -T --user hermes hermes hermes config set tools.tool_search.enabled off
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao configurar chamada direta de ferramentas.' }
    docker compose exec -T --user hermes hermes hermes config set agent.reasoning_effort false
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao configurar o modelo Hermes 3.' }
    docker compose restart hermes
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao reiniciar o Hermes.' }
    Write-Host 'Corretor: http://localhost:8000'
    Write-Host 'Painel Hermes: http://localhost:9119'
} finally {
    Pop-Location
}
