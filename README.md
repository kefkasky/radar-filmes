# Radar de Filmes

Robô que acompanha os catálogos de streaming no Brasil (Netflix, Prime Video,
Disney+, HBO Max, Globoplay, Apple TV+, Paramount+) e avisa o que entrou e
o que saiu.

**Fase 1 (atual):** só coleta e envia um relatório diário no Telegram.
Nada é publicado em redes sociais ainda.

## Como funciona

1. Todo dia às 06:47 (Brasília) o GitHub Actions roda `python -m radar`.
2. O robô baixa o catálogo de cada plataforma pela API do TMDB.
3. Compara com o retrato do dia anterior (`data/catalogo.json`).
4. Manda o relatório no Telegram e salva o novo retrato no repositório.

Travas de segurança:
- Se uma plataforma "perder" mais de 30% do catálogo de uma vez, é tratado
  como falha da fonte: nada é reportado e o retrato anterior é mantido.
- Se a coleta de uma plataforma falhar, as outras seguem normalmente.

## Segredos necessários (Settings > Secrets and variables > Actions)

| Nome | O que é |
|---|---|
| `TMDB_TOKEN` | "Token de Leitura da API" do TMDB |
| `TELEGRAM_TOKEN` | Token do bot, dado pelo @BotFather |
| `TELEGRAM_CHAT_ID` | ID do seu chat com o bot (veja abaixo) |

### Descobrir o TELEGRAM_CHAT_ID
1. Mande um "oi" para o seu bot no Telegram.
2. Aba **Actions** > **Descobrir chat ID do Telegram** > **Run workflow**.
3. Abra a execução: o ID aparece no log. Salve como `TELEGRAM_CHAT_ID`.

### Rodar na hora
Aba **Actions** > **Radar diário** > **Run workflow**. A primeira execução só
cria a base de comparação; as novidades aparecem a partir da segunda.

## Testes

```
pip install pytest requests
python -m pytest -q
```

Dados de disponibilidade: TMDB / JustWatch. Uso não comercial.
