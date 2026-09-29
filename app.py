import streamlit as st
import re
from main import process_reference_line

# Configuração da página no Streamlit
st.set_page_config(
    page_title="Formatador Acadêmico (ABNT & APA)",
    page_icon="📚",
    layout="wide"
)

# Estilização visual com suporte nativo a Tema Claro e Escuro (Dark Mode)
st.markdown("""
<style>
    .main-title {
        font-size: 2.3rem;
        font-weight: 700;
        text-align: center;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.1rem;
        text-align: center;
        margin-bottom: 2rem;
        opacity: 0.8;
    }
    .ref-box {
        background-color: rgba(59, 130, 246, 0.08);
        border-left: 5px solid #3B82F6;
        padding: 1.2rem;
        border-radius: 8px;
        margin-bottom: 1.2rem;
        font-size: 1.05rem;
        line-height: 1.6;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">📚 Sistema de Formatação de Referências</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">Formatação automática e enriquecimento de dados em normas <b>ABNT (NBR 6023)</b> e <b>APA (7ª Edição)</b></div>', unsafe_allow_html=True)

# Sidebar com informações e atalhos
st.sidebar.header("💡 Como utilizar")
st.sidebar.info(
    "Cole sua lista de referências na caixa de texto. Você pode colar:\n\n"
    "• **DOIs:** `10.1016/j.biopsych.2026.05.012`\n"
    "• **URLs:** `https://doi.org/10.1038/s41586-020-2649-2`\n"
    "• **ISBNs:** `9788535208030`\n"
    "• **Texto livre:** `Gates or No Gates? A Cross-European Enquiry into the Driving Forces behind Gated Communities`"
)

st.sidebar.header("⚙️ APIs Conectadas")
st.sidebar.markdown(
    "- 🟢 **Crossref API** (Artigos de periódicos)\n"
    "- 🟢 **Google Books API** (Livros)\n"
    "- 🟢 **Open Library API** (Livros internacionais)"
)

# Exemplos predefinidos
EXAMPLE_TEXT = """Gates or No Gates? A Cross-European Enquiry into the Driving Forces behind Gated Communities
10.1016/j.biopsych.2026.05.012
https://doi.org/10.1038/s41586-020-2649-2
10.1016/j.brs.2026.103030
9788535208030"""

col1, col2 = st.columns([3, 1])
with col2:
    if st.button("📋 Carregar Exemplo", use_container_width=True):
        st.session_state["input_text"] = EXAMPLE_TEXT

default_value = st.session_state.get("input_text", "")

user_input = st.text_area(
    "Insira a lista de referências brutas (uma por linha):",
    value=default_value,
    height=200,
    placeholder="Cole seus DOIs, URLs, ISBNs ou títulos de trabalhos aqui..."
)

if st.button("✨ Formatar Referências Agora", type="primary", use_container_width=True):
    if not user_input.strip():
        st.warning("Por favor, insira pelo menos uma referência ou DOI para processar.")
    else:
        lines = [line.strip() for line in user_input.split("\n") if line.strip()]
        
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, line in enumerate(lines):
            status_text.text(f"Processando [{idx+1}/{len(lines)}]: {line[:40]}...")
            res = process_reference_line(line)
            if res:
                results.append(res)
            progress_bar.progress((idx + 1) / len(lines))
            
        status_text.empty()
        progress_bar.empty()
        st.success(f"✔ Processamento concluído! **{len(results)}** referências formatadas.")
        
        # Gerar strings completas para cópia/download
        abnt_full = "\n\n".join([r['abnt'] for r in results])
        apa_full = "\n\n".join([r['apa'] for r in results])
        
        comp_full = "# Relatório Comparativo de Referências (Original vs. ABNT vs. APA)\n\n"
        for idx, r in enumerate(results, start=1):
            type_label = r.get('item_type_label', '📄 Referência')
            comp_full += f"## Referência #{idx} [{type_label}]\n\n"
            comp_full += f"**Versão Original (Antes da Correção):**\n> {r['raw']}\n\n"
            comp_full += f"### ABNT (NBR 6023):\n{r['abnt']}\n\n"
            comp_full += f"### APA (7ª Edição):\n{r['apa']}\n\n---\n\n"

        tab_abnt, tab_apa, tab_comp = st.tabs(["📄 Padrão ABNT", "🌐 Padrão APA", "🔍 Comparativo Lado a Lado"])
        
        with tab_abnt:
            st.subheader("Referências no Padrão ABNT (NBR 6023)")
            c1, c2 = st.columns([1, 1])
            with c1:
                st.download_button("⬇️ Baixar ABNT (.md)", abnt_full, file_name="referencias_ABNT.md", mime="text/markdown", use_container_width=True)
            with c2:
                with st.popover("📋 Copiar Lista de Referências ABNT", use_container_width=True):
                    st.caption("Clique no ícone de cópia no canto do bloco ou selecione o texto abaixo:")
                    st.code(abnt_full, language=None)
                    st.text_area("Texto bruto sequenciado (ABNT):", abnt_full, height=180)

            st.markdown("---")
            for r in results:
                with st.container(border=True):
                    type_label = r.get('item_type_label', '📄 Referência')
                    st.markdown(f"<div style='display: inline-flex; align-items: center; gap: 6px; margin-bottom: 8px; font-size: 0.82rem; font-weight: 600; color: #3b82f6; background-color: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.25); border-radius: 6px; padding: 3px 10px;'><span>🏷️ Tipo:</span> <span>{type_label}</span></div>", unsafe_allow_html=True)
                    st.markdown(r['abnt'])
                    with st.expander("📝 Ver referência antes da correção", expanded=False):
                        st.caption(r['raw'])
                    missing = r.get('missing_fields', [])
                    if missing:
                        st.markdown("<div style='margin-top: 10px; font-size: 0.9rem; color: #d97706; font-weight: 600;'>⚠️ Elementos não encontrados para compor esta referência:</div>", unsafe_allow_html=True)
                        for item in missing:
                            st.markdown(f"- <span style='font-size: 0.88rem;'>{item}</span>", unsafe_allow_html=True)
                
        with tab_apa:
            st.subheader("Referências no Padrão APA (7ª Edição)")
            c1, c2 = st.columns([1, 1])
            with c1:
                st.download_button("⬇️ Baixar APA (.md)", apa_full, file_name="referencias_APA.md", mime="text/markdown", use_container_width=True)
            with c2:
                with st.popover("📋 Copiar Lista de Referências APA", use_container_width=True):
                    st.caption("Clique no ícone de cópia no canto do bloco ou selecione o texto abaixo:")
                    st.code(apa_full, language=None)
                    st.text_area("Texto bruto sequenciado (APA):", apa_full, height=180)

            st.markdown("---")
            for r in results:
                with st.container(border=True):
                    type_label = r.get('item_type_label', '📄 Referência')
                    st.markdown(f"<div style='display: inline-flex; align-items: center; gap: 6px; margin-bottom: 8px; font-size: 0.82rem; font-weight: 600; color: #3b82f6; background-color: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.25); border-radius: 6px; padding: 3px 10px;'><span>🏷️ Tipo:</span> <span>{type_label}</span></div>", unsafe_allow_html=True)
                    st.markdown(r['apa'])
                    with st.expander("📝 Ver referência antes da correção", expanded=False):
                        st.caption(r['raw'])
                    missing = r.get('missing_fields', [])
                    if missing:
                        st.markdown("<div style='margin-top: 10px; font-size: 0.9rem; color: #d97706; font-weight: 600;'>⚠️ Elementos não encontrados para compor esta referência:</div>", unsafe_allow_html=True)
                        for item in missing:
                            st.markdown(f"- <span style='font-size: 0.88rem;'>{item}</span>", unsafe_allow_html=True)
                
        with tab_comp:
            st.subheader("Relatório Comparativo Lado a Lado")
            st.download_button("⬇️ Baixar Relatório Comparativo (.md)", comp_full, file_name="referencias_completas.md", mime="text/markdown")
            for idx, r in enumerate(results, start=1):
                type_label = r.get('item_type_label', '📄 Referência')
                with st.expander(f"#{idx} [{type_label}] {r['raw'][:80]}...", expanded=True):
                    st.markdown(f"<div style='display: inline-flex; align-items: center; gap: 6px; margin-bottom: 12px; font-size: 0.82rem; font-weight: 600; color: #3b82f6; background-color: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.25); border-radius: 6px; padding: 3px 10px;'><span>🏷️ Tipo Identificado:</span> <span>{type_label}</span></div>", unsafe_allow_html=True)
                    
                    st.markdown("**📝 Versão Original (Antes da Correção):**")
                    st.markdown(
                        f"<div style='background-color: rgba(148, 163, 184, 0.08); border: 1px solid rgba(148, 163, 184, 0.22); border-left: 4px solid #94a3b8; border-radius: 6px; padding: 10px 14px; margin-bottom: 16px; font-size: 0.92rem; line-height: 1.5; color: inherit; word-break: break-word;'>"
                        f"{r['raw']}"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                    
                    c_a, c_b = st.columns(2)
                    with c_a:
                        st.markdown("**ABNT (NBR 6023):**")
                        st.info(r['abnt'])
                    with c_b:
                        st.markdown("**APA (7ª Edição):**")
                        st.success(r['apa'])
                    missing = r.get('missing_fields', [])
                    if missing:
                        st.markdown("<div style='margin-top: 5px; font-size: 0.9rem; color: #d97706; font-weight: 600;'>⚠️ Elementos não encontrados:</div>", unsafe_allow_html=True)
                        for item in missing:
                            st.markdown(f"- <span style='font-size: 0.88rem;'>{item}</span>", unsafe_allow_html=True)
