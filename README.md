# Classificação Geral · GT Racing Slot Car

Sistema web responsivo (Mobile First, iPhone/Safari e Android/Chrome) para gestão de campeonatos de slot car e acompanhamento da classificação geral dos pilotos.

## 🏁 Identidade Visual
- Cores da bandeira da Alemanha: Preto (`#000000`), Vermelho (`#DD0000`) e Amarelo (`#FFCE00`).
- Faixas superior e inferior com o padrão da bandeira.
- Suporte a tema Escuro e Claro.
- Menu inferior fixo com 5 abas: **Classificação**, **Campeonatos**, **Pilotos**, **Pontuação** e **Categorias**.

## 🚀 Publicação no Render.com (1 Clique)
O repositório já inclui o arquivo `render.yaml` (Blueprint) e `Procfile`:
1. Acesse **[dashboard.render.com](https://dashboard.render.com/)** e faça login com seu GitHub.
2. Clique em **New +** > **Blueprint** (ou **Web Service**).
3. Selecione o repositório `barbosamarcoaurelio-coder/classificacaoslotcar`.
4. O Render detectará automaticamente o `render.yaml` e publicará o site com HTTPS gratuito e URL pública (ex.: `https://classificacaoslotcar.onrender.com`).

### 🐘 Persistência com PostgreSQL (Recomendado)
Para persistir os dados permanentemente em produção (sem depender do ciclo de vida efêmero do container):
1. Crie um banco PostgreSQL gratuito (ex.: [Supabase](https://supabase.com/), [Neon.tech](https://neon.tech/) ou o PostgreSQL do Render).
2. No painel do seu Web Service no Render, vá em **Environment** e adicione a variável:
   - **Key:** `DATABASE_URL`
   - **Value:** `postgresql://usuario:senha@host:5432/banco`
3. O sistema detectará o PostgreSQL automaticamente na inicialização, criará as tabelas e fará a carga inicial de `dados-iniciais-slot-car.json`.
4. *Em ambiente local (sem `DATABASE_URL`), o sistema continuará usando SQLite (`slotcar.db`) normalmente.*

## 🔑 Acesso de Administrador
- **E-mail:** `alegt@gtracing.com.br`
- **Senha:** `gtracing2026`
*(Visitantes acessam em modo somente leitura sem login).*

## ⚡ Como lançar uma nova etapa em 3 passos
1. **Selecione o campeonato** e clique no botão **"⚡ Lançar / Importar Etapa"**.
2. **Cole o link do post do blog** (ou cole o texto da página) e clique em **"Ler do Blog"**. O sistema extrai automaticamente a tabela de resultados das subdivisões (GT1, GT2, GT3), lê o número da etapa e faz o reconhecimento inteligente dos pilotos (por nome exato, apelidos e prefixos).
3. **Confira a lista de chegada** (vincule pilotos não reconhecidos ou confirme novos pilotos com 1 clique) e clique em **"Salvar Resultado Oficial"**.

## 💾 Como fazer backup dos dados
- **Download do Backup:** Na aba **Categorias**, clique em **"💾 Backup / Restaurar"** > **"Download do Backup (JSON)"**. O arquivo completo é baixado com todas as categorias, pilotos, tabelas, campeonatos e resultados.
- **Restauração:** No mesmo modal, clique em **"Escolher arquivo"** (`.json`) e clique em **"Substituir Banco pelo Arquivo"**.

## 🧪 Testes de Aceitação
Para executar os testes de aceitação e conferir as classificações com as planilhas oficiais:
```bash
python3 test_acceptance.py
```
