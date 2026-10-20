import streamlit as st
import random
import json
import os
import uuid
from datetime import datetime
from supabase import create_client, Client

# Configuração da Página para Mobile e Desktop (Layout Responsivo)
st.set_page_config(
    page_title="Simulado Subaquático - ABENDI",
    page_icon="🌊",
    layout="centered"
)

# --- CONFIGURAÇÃO DO SUPABASE ---
SUPABASE_URL = "https://xjmfinkltpsexxljzndy.supabase.co"
SUPABASE_KEY = "sb_publishable_ojfqSCiUn3oGntqUWdK6w_3Jkxw..."

@st.cache_resource
def init_supabase():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        return None

supabase: Client = init_supabase()

MODULOS = {
    "EV": {
        "nome": "Inspeção Visual (SM-EV)",
        "json": "questoes_ev.json"
    },
    "PE": {
        "nome": "Potencial Eletroquímico (SM-PE)",
        "json": "questoes_pe.json"
    },
    "ME": {
        "nome": "Medição de Espessura (SM-ME)",
        "json": "questoes_me.json"
    }
}

# --- GERENCIAMENTO DE IDENTIDADE DO DISPOSITIVO (UUID) ---
if "device_id" not in st.session_state:
    st.session_state.device_id = str(uuid.uuid4())

# --- FUNÇÕES DE BANCO DE DADOS (SUPABASE) ---

def carregar_banco(modulo_atual):
    arquivo_json = MODULOS[modulo_atual]["json"]
    if os.path.exists(arquivo_json):
        try:
            with open(arquivo_json, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.error(f"Erro ao ler o arquivo {arquivo_json}: {e}")
    return []

def carregar_historico_nuvem(modulo_atual):
    if not supabase:
        return []
    try:
        response = supabase.table("historico_usuarios") \
            .select("historico_json") \
            .eq("device_id", st.session_state.device_id) \
            .eq("modulo", modulo_atual) \
            .execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0].get("historico_json", [])
    except Exception as e:
        print(f"Erro ao carregar do Supabase: {e}")
    return []

def salvar_historico_nuvem_unico(modulo_atual, novo_registro):
    """Salva no Supabase garantindo que o mesmo registro não seja duplicado na sessão."""
    if not supabase:
        return
    try:
        historico_atual = carregar_historico_nuvem(modulo_atual)
        
        # Evita duplicidade estrita se já foi salvo nesta mesma sessão de resultado
        if historico_atual and historico_atual[-1].get("data") == novo_registro.get("data") and historico_atual[-1].get("acertos") == novo_registro.get("acertos"):
            return

        historico_atual.append(novo_registro)
        
        response = supabase.table("historico_usuarios") \
            .select("id") \
            .eq("device_id", st.session_state.device_id) \
            .eq("modulo", modulo_atual) \
            .execute()
        
        if response.data and len(response.data) > 0:
            supabase.table("historico_usuarios") \
                .update({"historico_json": historico_atual, "updated_at": datetime.now().isoformat()}) \
                .eq("device_id", st.session_state.device_id) \
                .eq("modulo", modulo_atual) \
                .execute()
        else:
            supabase.table("historico_usuarios") \
                .insert({
                    "device_id": st.session_state.device_id,
                    "modulo": modulo_atual,
                    "historico_json": historico_atual
                }) \
                .execute()
    except Exception as e:
        st.error(f"Erro ao salvar histórico na nuvem: {e}")

def limpar_historico_nuvem(modulo_atual):
    if not supabase:
        return
    try:
        supabase.table("historico_usuarios") \
            .delete() \
            .eq("device_id", st.session_state.device_id) \
            .eq("modulo", modulo_atual) \
            .execute()
    except Exception as e:
        st.error(f"Erro ao limpar histórico: {e}")

def calcular_estatisticas(modulo_atual):
    historico = carregar_historico_nuvem(modulo_atual)
    stats = {
        "10 Questões": {"qtd": 0, "soma_aproveitamento": 0.0},
        "20 Questões": {"qtd": 0, "soma_aproveitamento": 0.0},
        "40 Questões": {"qtd": 0, "soma_aproveitamento": 0.0},
        "Revisão de Erros": {"qtd": 0, "soma_aproveitamento": 0.0},
        "Completos/Outros": {"qtd": 0, "soma_aproveitamento": 0.0}
    }

    for item in historico:
        t = item.get("total")
        tipo_str = item.get("tipo", "")
        aprov = item.get("aproveitamento", 0)
        if "Revisão" in tipo_str:
            stats["Revisão de Erros"]["qtd"] += 1
            stats["Revisão de Erros"]["soma_aproveitamento"] += aprov
        elif t == 10:
            stats["10 Questões"]["qtd"] += 1
            stats["10 Questões"]["soma_aproveitamento"] += aprov
        elif t == 20:
            stats["20 Questões"]["qtd"] += 1
            stats["20 Questões"]["soma_aproveitamento"] += aprov
        elif t == 40:
            stats["40 Questões"]["qtd"] += 1
            stats["40 Questões"]["soma_aproveitamento"] += aprov
        else:
            stats["Completos/Outros"]["qtd"] += 1
            stats["Completos/Outros"]["soma_aproveitamento"] += aprov

    resultado = {}
    for chave, val in stats.items():
        q = val["qtd"]
        media = round(val["soma_aproveitamento"] / q, 1) if q > 0 else 0.0
        resultado[chave] = {"qtd": q, "media": media}
        
    return resultado

def calcular_pesos_questoes(modulo_atual, questoes):
    historico = carregar_historico_nuvem(modulo_atual)
    estatisticas_topicos = {}
    
    for item in historico:
        dep_topicos = item.get("desempenho_por_topico", {})
        for topico, res in dep_topicos.items():
            if topico not in estatisticas_topicos:
                estatisticas_topicos[topico] = {"acertos": 0, "erros": 0}
            estatisticas_topicos[topico]["acertos"] += res.get("acertos", 0)
            estatisticas_topicos[topico]["erros"] += res.get("erros", 0)

    pesos = []
    for q in questoes:
        topico_q = q.get("topico", "Conceitos Gerais de Inspeção")
        if topico_q in estatisticas_topicos:
            dados = estatisticas_topicos[topico_q]
            total_respostas = dados["acertos"] + dados["erros"]
            if total_respostas > 0:
                taxa_erro = dados["erros"] / total_respostas
                peso = 1.0 + (taxa_erro * 4.0)
            else:
                peso = 1.0
        else:
            peso = 1.0
        pesos.append(peso)

    return pesos

# --- GERENCIAMENTO DE ESTADO DA SESSÃO ---
if "modulo_atual" not in st.session_state:
    st.session_state.modulo_atual = "EV"

if "tela" not in st.session_state:
    st.session_state.tela = "menu"

if "questoes_selecionadas" not in st.session_state:
    st.session_state.questoes_selecionadas = []

if "indice_atual" not in st.session_state:
    st.session_state.indice_atual = 0

if "pontuacao" not in st.session_state:
    st.session_state.pontuacao = 0

if "respostas_sessao" not in st.session_state:
    st.session_state.respostas_sessao = []

if "modo_revisao_ativo" not in st.session_state:
    st.session_state.modo_revisao_ativo = False

if "resultado_salvo" not in st.session_state:
    st.session_state.resultado_salvo = False


# --- TELA 1: MENU PRINCIPAL ---
if st.session_state.tela == "menu":
    st.title("🌊 Simulado Subaquático - ABENDI")
    
    col_mod1, col_mod2, col_mod3 = st.columns(3)
    with col_mod1:
        if st.button("EV (Visual)", use_container_width=True):
            st.session_state.modulo_atual = "EV"
            st.rerun()
    with col_mod2:
        if st.button("PE (Potencial)", use_container_width=True):
            st.session_state.modulo_atual = "PE"
            st.rerun()
    with col_mod3:
        if st.button("ME (Espessura)", use_container_width=True):
            st.session_state.modulo_atual = "ME"
            st.rerun()

    questoes = carregar_banco(st.session_state.modulo_atual)
    total_q = len(questoes)
    
    st.info(f"**Módulo Ativo:** {MODULOS[st.session_state.modulo_atual]['nome']} | **Banco:** {total_q} questões.")
    
    st.markdown("### Escolha a modalidade de estudo:")
    
    quantidades = [10, 20, 40]
    for q in quantidades:
        if total_q >= q:
            if st.button(f"📝 Simulado com {q} Questões", use_container_width=True):
                pesos = calcular_pesos_questoes(st.session_state.modulo_atual, questoes)
                indices = set()
                tentativas = 0
                while len(indices) < q and tentativas < (q * 20):
                    idx = random.choices(range(len(questoes)), weights=pesos, k=1)[0]
                    indices.add(idx)
                    tentativas += 1
                while len(indices) < q:
                    indices.add(random.randint(0, len(questoes) - 1))
                
                st.session_state.questoes_selecionadas = [questoes[i] for i in indices]
                random.shuffle(st.session_state.questoes_selecionadas)
                st.session_state.indice_atual = 0
                st.session_state.pontuacao = 0
                st.session_state.respostas_sessao = []
                st.session_state.modo_revisao_ativo = False
                st.session_state.resultado_salvo = False
                st.session_state.tela = "questao"
                st.rerun()

    if total_q > 0:
        if st.button(f"📚 Simulado Completo ({total_q} Questões)", use_container_width=True):
            st.session_state.questoes_selecionadas = list(questoes)
            random.shuffle(st.session_state.questoes_selecionadas)
            st.session_state.indice_atual = 0
            st.session_state.pontuacao = 0
            st.session_state.respostas_sessao = []
            st.session_state.modo_revisao_ativo = False
            st.session_state.resultado_salvo = False
            st.session_state.tela = "questao"
            st.rerun()

    if st.button("🔄 Revisar Questões Erradas (Erros Pendentes)", use_container_width=True):
        historico = carregar_historico_nuvem(st.session_state.modulo_atual)
        contagem_erros = {}
        for item in historico:
            for q_id in item.get("questoes_erradas_ids", []):
                contagem_erros[q_id] = contagem_erros.get(q_id, 0) + 1
            if "Revisão" in item.get("tipo", ""):
                for q_id_acerto in item.get("questoes_acertadas_revisao_ids", []):
                    if q_id_acerto in contagem_erros:
                        contagem_erros[q_id_acerto] -= 1
                        if contagem_erros[q_id_acerto] <= 0:
                            del contagem_erros[q_id_acerto]
        
        ids_para_revisar = [q_id for q_id, saldo in contagem_erros.items() if saldo > 0]
        questoes_para_revisar = [q for q in questoes if q.get("id") in ids_para_revisar]

        if not questoes_para_revisar:
            st.warning("Parabéns! Não há questões pendentes de revisão neste módulo.")
        else:
            st.session_state.questoes_selecionadas = questoes_para_revisar
            random.shuffle(st.session_state.questoes_selecionadas)
            st.session_state.indice_atual = 0
            st.session_state.pontuacao = 0
            st.session_state.respostas_sessao = []
            st.session_state.modo_revisao_ativo = True
            st.session_state.resultado_salvo = False
            st.session_state.tela = "questao"
            st.rerun()

    with st.expander("⚙️ Ferramentas e Estatísticas"):
        estatisticas = calcular_estatisticas(st.session_state.modulo_atual)
        for tipo, dados in estatisticas.items():
            st.write(f"• **{tipo}** ➔ Realizados: {dados['qtd']} | Média: {dados['media']}%")
        
        if st.button("🗑️ Limpar Histórico do Módulo Atual"):
            limpar_historico_nuvem(st.session_state.modulo_atual)
            st.success("Histórico limpo com sucesso!")
            st.rerun()

    st.markdown("---")
    st.caption("O Simulado não substitui as fontes oficiais de informações da Abendi - dev. Beto")


# --- TELA 2: RESPONDENDO A QUESTÃO ---
elif st.session_state.tela == "questao":
    idx = st.session_state.indice_atual
    total = len(st.session_state.questoes_selecionadas)
    q = st.session_state.questoes_selecionadas[idx]
    
    modo_txt = " | 🔄 MODO REVISÃO" if st.session_state.modo_revisao_ativo else ""
    st.caption(f"[{st.session_state.modulo_atual}] Questão {idx + 1} de {total} | Tópico: {q.get('topico', 'Geral')}{modo_txt}")
    
    st.subheader(q["pergunta"])
    
    opcoes = q["opcoes"]
    escolha = st.radio("Selecione a alternativa:", opcoes, key=f"q_{idx}")
    
    col_btn1, col_btn2 = st.columns([1, 1])
    with col_btn1:
        if st.button("Confirmar Resposta", use_container_width=True):
            if not escolha:
                st.warning("Selecione uma alternativa!")
            else:
                letra_escolhida = escolha[0].upper()
                letra_correta = q["resposta"].upper()
                acertou = (letra_escolhida == letra_correta)
                
                st.session_state.ultima_resposta_correta = acertou
                st.session_state.gabarito_letra = letra_correta
                st.session_state.ultima_explicacao = q.get("explicacao", "Sem explicação detalhada.")
                
                st.session_state.respostas_sessao.append({
                    "id": q.get("id"),
                    "topico": q.get("topico", "Geral"),
                    "acertou": acertou
                })
                
                if acertou:
                    st.session_state.pontuacao += 1
                
                st.session_state.tela = "feedback"
                st.rerun()
                
    with col_btn2:
        if st.button("← Voltar ao Menu", use_container_width=True):
            st.session_state.tela = "menu"
            st.rerun()


# --- TELA 3: FEEDBACK DA RESPOSTA ---
elif st.session_state.tela == "feedback":
    acertou = st.session_state.ultima_resposta_correta
    
    if acertou:
        st.success("### ✅ RESPOSTA CORRETA!")
    else:
        st.error("### ❌ RESPOSTA INCORRETA!")
        st.warning(f"A alternativa correta era: **{st.session_state.gabarito_letra}**")
        
    st.markdown("#### Explicação / Justificativa:")
    st.info(st.session_state.ultima_explicacao)
    
    if st.button("Próxima Questão →", use_container_width=True):
        st.session_state.indice_atual += 1
        if st.session_state.indice_atual < len(st.session_state.questoes_selecionadas):
            st.session_state.tela = "questao"
        else:
            st.session_state.tela = "resultado"
        st.rerun()


# --- TELA 4: RESULTADO FINAL ---
elif st.session_state.tela == "resultado":
    total = len(st.session_state.questoes_selecionadas)
    pontos = st.session_state.pontuacao
    aproveitamento = (pontos / total) * 100 if total > 0 else 0
    
    st.balloons()
    st.title("🏆 Simulado Concluído!")
    
    st.metric(label="Aproveitamento Geral", value=f"{aproveitamento:.1f}%", delta=f"{pontos} acertos de {total}")
    
    # Executa o salvamento apenas uma única vez utilizando a flag de controle
    if not st.session_state.resultado_salvo:
        desempenho_topicos = {}
        questoes_erradas_ids = []
        questoes_acertadas_revisao_ids = []

        for item in st.session_state.respostas_sessao:
            t = item["topico"]
            q_id = item["id"]
            if t not in desempenho_topicos:
                desempenho_topicos[t] = {"acertos": 0, "erros": 0}
            
            if item["acertou"]:
                desempenho_topicos[t]["acertos"] += 1
                if st.session_state.modo_revisao_ativo and q_id is not None:
                    questoes_acertadas_revisao_ids.append(q_id)
            else:
                desempenho_topicos[t]["erros"] += 1
                if q_id is not None:
                    questoes_erradas_ids.append(q_id)

        tipo_str = "Revisão de Erros" if st.session_state.modo_revisao_ativo else f"{total} Questões"
        
        novo_registro = {
            "data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "modulo": st.session_state.modulo_atual,
            "tipo": tipo_str,
            "acertos": pontos,
            "total": total,
            "aproveitamento": round(aproveitamento, 1),
            "desempenho_por_topico": desempenho_topicos,
            "questoes_erradas_ids": questoes_erradas_ids,
            "questoes_acertadas_revisao_ids": questoes_acertadas_revisao_ids
        }
        
        salvar_historico_nuvem_unico(st.session_state.modulo_atual, novo_registro)
        st.session_state.resultado_salvo = True  # Trava para impedir duplicações

    if aproveitamento >= 70:
        st.success("Excelente! Pronto para a certificação ABENDI. 🚀")
    else:
        st.warning("Atenção: Revise os pontos fracos e utilize a Revisão de Erros para fixar o conteúdo!")

    if st.button("Voltar ao Menu Principal", use_container_width=True):
        st.session_state.tela = "menu"
        st.rerun()