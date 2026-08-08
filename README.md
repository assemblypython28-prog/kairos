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

## 3. Configuração local

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

## 4. Deploy no Streamlit Community Cloud

1. Suba esta pasta para um repositório no GitHub.
2. Em https://share.streamlit.io, "New app" apontando para `app.py`.
3. Em **Settings > Secrets**, cole o conteúdo do seu `secrets.toml` (DATABASE_URL e GEMINI_API_KEY).
4. Adicione um arquivo `packages.txt` na raiz com uma linha `ffmpeg` — o Streamlit Cloud
   instala pacotes apt listados ali (já incluído neste projeto).

## Fluxo do app

1. **Login/cadastro** simples (usuário + senha, bcrypt).
2. **Upload** do vídeo → player mostra o vídeo carregado.
3. **Transcrever com IA** → Gemini transcreve com timestamps; progresso aparece em tempo real.
4. **Editar transcrição** → cada trecho é editável, salva individualmente no Neon.
5. **Sugerir cortes com IA** → Gemini lê a transcrição e sugere trechos de destaque.
6. Selecione os cortes desejados e **exporte** (ffmpeg corta localmente) → baixe o(s) clipe(s).
7. **Descartar vídeo** → apaga o arquivo do disco; transcrição e cortes seguem no Neon.

## O que foi removido em relação ao Kairos original

- FastAPI, Celery, Redis, Alembic, SQLAlchemy, multi-tenant middleware
- Whisper local (GPU) → substituído por transcrição via Gemini na nuvem
- Ollama local (`llama3.2:3b`) → substituído por sugestão de cortes via Gemini
- Cliente desktop separado (`kairos_desktop`) — o Streamlit já cobre o fluxo web

Se depois você precisar de fila de processamento assíncrono (vídeos muito longos,
múltiplos usuários simultâneos), dá pra evoluir sem reescrever tudo de novo — mas
para o fluxo atual (login → upload → transcrever → cortar) essa versão já resolve
com bem menos peça girando.
