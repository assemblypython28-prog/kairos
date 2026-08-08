# Kairos (versão simplificada)

Reescrita do Kairos original trocando a stack pesada (FastAPI + Celery + Redis +
Whisper local + Ollama local) por algo enxuto:

- **Streamlit** — front-end e back-end no mesmo processo, fluxo síncrono com progresso visível
- **Neon (Postgres)** — usuários, transcrição editável e cortes sugeridos
- **Gemini API** — transcrição com timestamps + sugestão de cortes (uma API só)
- **ffmpeg** — corte e export dos clipes (via `subprocess`, sem wrapper extra)

O vídeo em si **nunca é salvo no Neon** — fica em disco temporário durante o
processamento e você pode descartá-lo manualmente a qualquer momento (o texto
transcrito e os cortes continuam salvos).

## 1. Banco (Neon)

1. Crie um projeto em https://neon.tech (grátis).
2. Copie a connection string (formato `postgresql://usuario:senha@ep-xxxx.neon.tech/dbname?sslmode=require`).
3. O schema (`schema.sql`) é criado automaticamente na primeira execução do app.

## 2. Chave Gemini

1. Gere uma chave em https://aistudio.google.com/apikey (tem tier gratuito).

## 3. Cloudflare R2 (upload direto do navegador)

O Streamlit tem limite de upload pelo próprio servidor (RAM/tamanho de requisição).
Pra vídeos grandes, o navegador envia direto pro R2 via URL pré-assinada — o
arquivo nunca passa pelo corpo da requisição do Streamlit.

1. Crie uma conta em https://dash.cloudflare.com (R2 tem tier grátis: 10GB, sem
   custo de saída de dados).
2. Vá em **R2 Object Storage** → **Create bucket** → nomeie (ex: `kairos-videos`).
3. Em **Manage R2 API Tokens** → **Create API Token**, permissão de leitura/escrita
   nesse bucket. Anote: Account ID, Access Key ID, Secret Access Key.
4. Preencha `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
   `R2_BUCKET_NAME` no `secrets.toml` (veja o exemplo abaixo).

Vídeos ficam no R2 só durante o processamento — o app baixa pro disco local,
processa, e apaga o objeto do R2 automaticamente.

## 4. Configuração local

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edite .streamlit/secrets.toml com DATABASE_URL e GEMINI_API_KEY
```

Instale as dependências (o `ffmpeg` precisa estar instalado no sistema — no
Ubuntu: `sudo apt install ffmpeg`):

```bash
pip install -r requirements.txt
```

Rode:

```bash
streamlit run app.py
```

## 5. Deploy no Streamlit Community Cloud

1. Suba esta pasta para um repositório no GitHub.
2. Em https://share.streamlit.io, "New app" apontando para `app.py`.
3. Em **Settings > Secrets**, cole o conteúdo do seu `secrets.toml` (todas as chaves,
   incluindo as do R2).
4. `packages.txt` (ffmpeg) e `.streamlit/config.toml` já estão incluídos neste projeto.

## Fluxo do app

1. **Login/cadastro** simples (usuário + senha, bcrypt).
2. **Upload** → o navegador envia o vídeo direto pro Cloudflare R2 (sem limite prático de
   tamanho); clique em "Já enviei, continuar" quando a barra chegar a 100%.
3. O servidor baixa o vídeo do R2 pro disco local (streaming) e já dispara a transcrição.
4. **Transcrever com IA** → Gemini transcreve com timestamps; progresso aparece em tempo real.
5. **Editar transcrição** → cada trecho é editável, salva individualmente no Neon.
6. **Sugerir cortes com IA** → Gemini lê a transcrição e sugere trechos de destaque.
7. Selecione os cortes desejados e **exporte** (ffmpeg corta localmente) → baixe o(s) clipe(s).
8. **Descartar vídeo** → apaga o arquivo do disco; transcrição e cortes seguem no Neon.
   (O objeto no R2 já é apagado automaticamente assim que o download pro servidor termina.)

## O que foi removido em relação ao Kairos original

- FastAPI, Celery, Redis, Alembic, SQLAlchemy, multi-tenant middleware
- Whisper local (GPU) → substituído por transcrição via Gemini na nuvem
- Ollama local (`llama3.2:3b`) → substituído por sugestão de cortes via Gemini
- Cliente desktop separado (`kairos_desktop`) — o Streamlit já cobre o fluxo web

Se depois você precisar de fila de processamento assíncrono (vídeos muito longos,
múltiplos usuários simultâneos), dá pra evoluir sem reescrever tudo de novo — mas
para o fluxo atual (login → upload → transcrever → cortar) essa versão já resolve
com bem menos peça girando.
