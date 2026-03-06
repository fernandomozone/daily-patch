#!/bin/bash
# Daily Patch — Publicar episódio no Telegram
# Uso: ./publicar-telegram.sh episodes/2026-03-03

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$PROJECT_DIR/config/.env"

# Validar argumentos
if [ -z "${1:-}" ]; then
    echo "Uso: $0 <caminho-para-pasta-episodio>"
    echo "Exemplo: $0 episodes/2026-03-03"
    exit 1
fi

EPISODE_DIR="$1"
GUIAO="$EPISODE_DIR/guiao.json"
AUDIO="$EPISODE_DIR/episode.mp3"

# Validar ficheiros
if [ ! -f "$GUIAO" ]; then
    echo "❌ Guião não encontrado: $GUIAO"
    exit 1
fi

if [ ! -f "$AUDIO" ]; then
    echo "❌ Áudio não encontrado: $AUDIO"
    exit 1
fi

# Extrair info do guião
TITLE=$(jq -r '.title' "$GUIAO")
EPISODE_NUM=$(jq -r '.episode_number' "$GUIAO")
DATE=$(jq -r '.date' "$GUIAO")
NEWS_OF_DAY=$(jq -r '.news_of_the_day' "$GUIAO")
DURATION=$(ffprobe -i "$AUDIO" -show_entries format=duration -v quiet -of csv="p=0" | cut -d. -f1)
DURATION_MIN=$((DURATION / 60))

# Construir caption com resumo das notícias
# Extrair as primeiras falas de cada notícia
CAPTION="🎙️ *Daily Patch #${EPISODE_NUM}* — _${TITLE}_

📅 ${DATE}
⏱️ ${DURATION_MIN} minutos

🏆 *Notícia do dia:* ${NEWS_OF_DAY}

🤖 _Podcast gerado por IA com o Byte & Pixel_
🔗 #DailyPatch #Ep${EPISODE_NUM}"

echo "📤 A publicar no Telegram..."
echo "   Canal: $TELEGRAM_CHANNEL_ID"
echo "   Episódio: #$EPISODE_NUM — $TITLE"

# Enviar áudio para o canal
RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendAudio" \
    -F "chat_id=${TELEGRAM_CHANNEL_ID}" \
    -F "audio=@${AUDIO}" \
    -F "caption=${CAPTION}" \
    -F "parse_mode=Markdown" \
    -F "title=Daily Patch #${EPISODE_NUM} — ${TITLE}" \
    -F "performer=Byte & Pixel" \
    -F "duration=${DURATION}")

# Verificar resposta
OK=$(echo "$RESPONSE" | jq -r '.ok')

if [ "$OK" = "true" ]; then
    MESSAGE_ID=$(echo "$RESPONSE" | jq -r '.result.message_id')
    echo ""
    echo "✅ Publicado com sucesso!"
    echo "📨 Message ID: $MESSAGE_ID"
    
    # Guardar registo de publicação
    echo "$RESPONSE" | jq '.' > "$EPISODE_DIR/telegram_response.json"
else
    ERROR=$(echo "$RESPONSE" | jq -r '.description')
    echo ""
    echo "❌ Erro ao publicar: $ERROR"
    echo "$RESPONSE" | jq '.' > "$EPISODE_DIR/telegram_error.json"
    exit 1
fi
