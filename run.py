"""
Script de execucao local do Brain Format
Inicia o servidor FastAPI servindo tanto os endpoints da API quanto a interface web em public/
"""
import sys
import uvicorn

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print("\n[+] Iniciando Brain Format (FastAPI + Modern Web UI)...")
    print("[+] Acesse a aplicacao no seu navegador em: http://127.0.0.1:8000\n")
    uvicorn.run("api.index:app", host="127.0.0.1", port=8000, reload=True)
