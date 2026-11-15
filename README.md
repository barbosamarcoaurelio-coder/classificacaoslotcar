# Classificação Geral · GT Racing Slot Car

Sistema web responsivo (Mobile First, iPhone/Safari e Android/Chrome) para gestão de campeonatos de slot car e acompanhamento da classificação geral dos pilotos.

## 🏁 Identidade Visual
- Cores da bandeira da Alemanha: Preto (`#000000`), Vermelho (`#DD0000`) e Amarelo (`#FFCE00`).
- Faixas superior e inferior com o padrão da bandeira.
- Suporte a tema Escuro e Claro.
- Menu inferior fixo com 6 abas: **Classificação**, **Ranking**, **Campeonatos**, **Pilotos**, **Pontuação** e **Categorias**.

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

## Ranking de Pilotos · Copa dos Campeões

Na aba **Ranking**, escolha **Fórmula 1**, **Magneto** ou **Brushless**. O botão
**Como funciona?** explica os critérios. O ranking é recalculado ao abrir a aba,
trocar a categoria ou clicar em **Atualizar ranking**, usando os resultados atuais.

- Entram resultados oficiais desde **01/08/2026**, pela data efetiva da corrida.
- Somente pilotos presentes na ordem de chegada participam; zero pontos conta como
  participação. Ausências não contam. Não há mínimo de corridas.
- Resultados descartados no campeonato entram normalmente no ranking.
- Índice = **100 × soma(pontos da corrida × peso GT) ÷ soma(máximos possíveis)**.
  Pesos históricos, conforme a subdivisão de cada resultado: GT1 = 3, GT2 = 2,
  GT3 = 1. Alterar a subdivisão atual do cadastro não altera resultados anteriores.
- O máximo é 30 por corrida; na última etapa, se configurada em dobro, pontos
  conquistados e máximo dobram (60). A tabela de pontuação do campeonato é usada,
  com valores entre 0 e 30. O teto do índice é 300 pontos, não percentual.
- Ordenação pelo índice exato, depois **menos participações**. Empates completos
  compartilham posição (1º, 2º, 2º, 4º); apenas a exibição é arredondada.

Em **Campeonatos → Editar → Ranking de pilotos**, confirme a identificação.
Inicialmente, categoria Brushless vai para Brushless; para as demais, o início
numa terça identifica Fórmula 1 e numa quinta identifica Magneto, sem usar o nome
do campeonato. A escolha fica gravada e não muda em reagendamentos. Campeonatos
antigos não identificados geram aviso no ranking e precisam de seleção manual.
Backups passam a incluir `ranking_categoria`; backups antigos continuam aceitos,
com identificação pelas mesmas regras. A migração adiciona essa coluna sem apagar
dados, em SQLite ou PostgreSQL, na inicialização.

Testes específicos, em banco temporário:
```bash
python3 -m unittest test_ranking.py
```

## 💾 Como fazer backup dos dados
- **Download do Backup:** Na aba **Categorias**, clique em **"💾 Backup / Restaurar"** > **"Download do Backup (JSON)"**. O arquivo completo é baixado com todas as categorias, pilotos, tabelas, campeonatos e resultados.
- **Restauração:** No mesmo modal, clique em **"Escolher arquivo"** (`.json`) e clique em **"Substituir Banco pelo Arquivo"**.

## 🧪 Testes de Aceitação
Para executar os testes de aceitação e conferir as classificações com as planilhas oficiais:
```bash
python3 test_acceptance.py
```
