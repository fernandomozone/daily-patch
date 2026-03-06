#!/bin/bash
# Daily Patch — Gerar áudio a partir do guião
# Uso: ./gerar-audio.sh episodes/2026-03-03/guiao.json

set -euo pipefail

# ── PATH fix: ffmpeg instalado em ~/.local/bin ────────────────────────────────
export PATH="$HOME/.local/bin:$PATH"
# ── Forçar ponto decimal (locale PT usa vírgula) ─────────────────────────────
export LC_NUMERIC=C

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$PROJECT_DIR/config/.env"

VOZES_CONFIG="$PROJECT_DIR/config/vozes.json"
SFX_DIR="$PROJECT_DIR/assets/sfx"

# ── Ler pausas do vozes.json ─────────────────────────────────────────────────
PAUSE_NORMAL_MS=$(jq -r '.pause_normal_ms' "$VOZES_CONFIG")
PAUSE_FAST_MS=$(jq -r '.pause_fast_ms' "$VOZES_CONFIG")
PAUSE_INTERRUPT_MS=$(jq -r '.pause_interrupt_ms' "$VOZES_CONFIG")

PAUSE_NORMAL=$(awk "BEGIN {printf \"%.3f\", $PAUSE_NORMAL_MS / 1000}")
PAUSE_FAST=$(awk "BEGIN {printf \"%.3f\", $PAUSE_FAST_MS / 1000}")
PAUSE_INTERRUPT=$(awk "BEGIN {printf \"%.3f\", $PAUSE_INTERRUPT_MS / 1000}")

# ── Validar argumentos ────────────────────────────────────────────────────────
if [ -z "${1:-}" ]; then
    echo "Uso: $0 <caminho-para-guiao.json>"
    echo "Exemplo: $0 episodes/2026-03-03/guiao.json"
    exit 1
fi

GUIAO_PATH="$1"
if [[ "$GUIAO_PATH" != /* ]]; then
    GUIAO_PATH="$PROJECT_DIR/$GUIAO_PATH"
fi

EPISODE_DIR="$(dirname "$GUIAO_PATH")"
SEGMENTS_DIR="$EPISODE_DIR/segments"
mkdir -p "$SEGMENTS_DIR"

echo "🎙️  Daily Patch — A gerar áudio..."
echo "📄 Guião: $GUIAO_PATH"
echo "📂 Segmentos: $SEGMENTS_DIR"

SEGMENT_COUNT=$(jq '.segments | length' "$GUIAO_PATH")
echo "📊 Total de segmentos: $SEGMENT_COUNT"
echo ""

# ── Helper: gerar silêncio ────────────────────────────────────────────────────
make_silence() {
    local dur="$1" out="$2"
    if (( $(echo "$dur <= 0" | bc -l) )); then
        ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=mono -t 0.001 -q:a 9 "$out" 2>/dev/null
    else
        ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=mono -t "$dur" -q:a 9 "$out" 2>/dev/null
    fi
}

# ── Loop principal: gerar cada segmento ──────────────────────────────────────
for i in $(seq 0 $((SEGMENT_COUNT - 1))); do
    SPEAKER=$(jq -r ".segments[$i].speaker" "$GUIAO_PATH")
    TEXT=$(jq -r ".segments[$i].text" "$GUIAO_PATH")
    EMOTION=$(jq -r ".segments[$i].emotion" "$GUIAO_PATH")
    PACE=$(jq -r ".segments[$i].pace // \"normal\"" "$GUIAO_PATH")
    SFX=$(jq -r ".segments[$i].sfx // \"\"" "$GUIAO_PATH")
    FILTER=$(jq -r ".segments[$i].filter // \"\"" "$GUIAO_PATH")

    # Pular segmentos sem texto (só SFX ou pausas)
    if [ -z "$TEXT" ]; then
        echo "  [$((i+1))/$SEGMENT_COUNT] $SPEAKER (SFX/pausa${SFX:+: $SFX})"
        continue
    fi

    # Determinar voice_id
    case "$SPEAKER" in
        BYTE)        VOICE_ID="$BYTE_VOICE_ID" ;;
        PIXEL)       VOICE_ID="$PIXEL_VOICE_ID" ;;
        PASQUALINO)  VOICE_ID="$PASQUALINO_VOICE_ID" ;;
        ESTAGIARIO)  VOICE_ID="$ESTAGIARIO_VOICE_ID" ;;
        CLAUDE)      VOICE_ID="$CLAUDE_VOICE_ID" ;;
        *)           echo "  ⚠️ Speaker desconhecido: $SPEAKER — a ignorar"; continue ;;
    esac

    # Obter voice settings
    STABILITY=$(jq -r ".voices.$SPEAKER.emotion_overrides.$EMOTION.stability // .voices.$SPEAKER.settings.stability" "$VOZES_CONFIG")
    STYLE=$(jq -r ".voices.$SPEAKER.emotion_overrides.$EMOTION.style // .voices.$SPEAKER.settings.style" "$VOZES_CONFIG")
    SIMILARITY=$(jq -r ".voices.$SPEAKER.settings.similarity_boost" "$VOZES_CONFIG")
    MODEL=$(jq -r ".model_id" "$VOZES_CONFIG")

    PAD=$(printf '%03d' $i)
    RAW_VOICE="$SEGMENTS_DIR/voice_raw_${PAD}.mp3"
    NORM_VOICE="$SEGMENTS_DIR/voice_norm_${PAD}.mp3"

    echo "  [$((i+1))/$SEGMENT_COUNT] $SPEAKER ($EMOTION/$PACE${SFX:+ sfx:$SFX}${FILTER:+ filter:$FILTER}): ${TEXT:0:60}..."

    # ── 1. Chamar ElevenLabs API ──────────────────────────────────────────────
    HTTP_CODE=$(curl -s -w "%{http_code}" -X POST \
        "https://api.elevenlabs.io/v1/text-to-speech/$VOICE_ID" \
        -H "xi-api-key: $ELEVENLABS_API_KEY" \
        -H "Content-Type: application/json" \
        -d "$(jq -n \
            --arg text "$TEXT" \
            --arg model "$MODEL" \
            --argjson stability "$STABILITY" \
            --argjson similarity "$SIMILARITY" \
            --argjson style "$STYLE" \
            '{
                text: $text,
                model_id: $model,
                voice_settings: {
                    stability: $stability,
                    similarity_boost: $similarity,
                    style: $style,
                    use_speaker_boost: true
                }
            }')" \
        --output "$RAW_VOICE")

    if [ "$HTTP_CODE" != "200" ] || [ ! -s "$RAW_VOICE" ]; then
        echo "  ❌ Erro HTTP $HTTP_CODE ao gerar segmento $i ($SPEAKER)"
        if file "$RAW_VOICE" 2>/dev/null | grep -q "JSON"; then
            cat "$RAW_VOICE"
        fi
        exit 1
    fi

    # ── 2. Normalizar + aplicar filtros ───────────────────────────────────────
    AUDIO_FILTER="loudnorm=I=-16:TP=-1.5:LRA=11,highpass=f=80,equalizer=f=200:t=o:w=200:g=-2"

    # Filtro "mumble": volume baixo + lowpass (resmungo ininteligível)
    if [ "$FILTER" = "mumble" ]; then
        AUDIO_FILTER="${AUDIO_FILTER},lowpass=f=600,volume=0.25"
    fi

    # Filtro "lowpass": voz abafada (atrás do vidro)
    if [ "$FILTER" = "lowpass" ]; then
        AUDIO_FILTER="${AUDIO_FILTER},lowpass=f=1200"
    fi

    ffmpeg -y -i "$RAW_VOICE" \
        -af "$AUDIO_FILTER" \
        -b:a 128k -ar 44100 -ac 1 \
        "$NORM_VOICE" 2>/dev/null
    rm -f "$RAW_VOICE"

done

echo ""
echo "🔧 A montar episódio..."

# ── Construir lista de concatenação ──────────────────────────────────────────
CONCAT_LIST="$SEGMENTS_DIR/concat.txt"
> "$CONCAT_LIST"

# Intro (asset externo, se existir)
INTRO="$PROJECT_DIR/assets/intro.mp3"
if [ -f "$INTRO" ]; then
    echo "file '$INTRO'" >> "$CONCAT_LIST"
    make_silence 0.800 "$SEGMENTS_DIR/pause_intro.mp3"
    echo "file '$SEGMENTS_DIR/pause_intro.mp3'" >> "$CONCAT_LIST"
fi

# Segmentos + SFX + pausas customizadas
for i in $(seq 0 $((SEGMENT_COUNT - 1))); do
    PAD=$(printf '%03d' $i)
    NORM_VOICE="$SEGMENTS_DIR/voice_norm_${PAD}.mp3"

    SFX=$(jq -r ".segments[$i].sfx // \"\"" "$GUIAO_PATH")
    TEXT=$(jq -r ".segments[$i].text" "$GUIAO_PATH")
    PAUSE_BEFORE=$(jq -r ".segments[$i].pause_before // 0" "$GUIAO_PATH")
    PAUSE_AFTER=$(jq -r ".segments[$i].pause_after // 0" "$GUIAO_PATH")

    # ── pause_before (silêncio ANTES deste segmento) ─────────────────────────
    if (( $(echo "$PAUSE_BEFORE > 0" | bc -l) )); then
        make_silence "$PAUSE_BEFORE" "$SEGMENTS_DIR/pb_${PAD}.mp3"
        echo "file '$SEGMENTS_DIR/pb_${PAD}.mp3'" >> "$CONCAT_LIST"
    fi

    # ── SFX (toca antes da fala) ─────────────────────────────────────────────
    if [ -n "$SFX" ]; then
        SFX_FILE="$SFX_DIR/${SFX}.mp3"
        if [ -f "$SFX_FILE" ]; then
            echo "file '$SFX_FILE'" >> "$CONCAT_LIST"
            # Micro-pausa entre SFX e fala (50ms)
            if [ -n "$TEXT" ]; then
                make_silence 0.050 "$SEGMENTS_DIR/pause_sfx_${PAD}.mp3"
                echo "file '$SEGMENTS_DIR/pause_sfx_${PAD}.mp3'" >> "$CONCAT_LIST"
            fi
        else
            echo "  ⚠️ SFX não encontrado: $SFX_FILE"
        fi
    fi

    # ── Fala do personagem (se existir texto E ficheiro) ─────────────────────
    if [ -n "$TEXT" ] && [ -f "$NORM_VOICE" ]; then
        echo "file '$NORM_VOICE'" >> "$CONCAT_LIST"
    fi

    # ── pause_after (silêncio DEPOIS deste segmento) ─────────────────────────
    if (( $(echo "$PAUSE_AFTER > 0" | bc -l) )); then
        make_silence "$PAUSE_AFTER" "$SEGMENTS_DIR/pa_${PAD}.mp3"
        echo "file '$SEGMENTS_DIR/pa_${PAD}.mp3'" >> "$CONCAT_LIST"
    fi

    # ── Pausa padrão baseada em pace do PRÓXIMO segmento ─────────────────────
    if [ $i -lt $((SEGMENT_COUNT - 1)) ]; then
        # Só adiciona pausa padrão se não houve pause_after customizado
        if (( $(echo "$PAUSE_AFTER <= 0" | bc -l) )); then
            NEXT_PACE=$(jq -r ".segments[$((i+1))].pace // \"normal\"" "$GUIAO_PATH")
            case "$NEXT_PACE" in
                interrupt) PAUSE_DUR="$PAUSE_INTERRUPT" ;;
                fast)      PAUSE_DUR="$PAUSE_FAST" ;;
                *)         PAUSE_DUR="$PAUSE_NORMAL" ;;
            esac
            make_silence "$PAUSE_DUR" "$SEGMENTS_DIR/pause_${PAD}.mp3"
            echo "file '$SEGMENTS_DIR/pause_${PAD}.mp3'" >> "$CONCAT_LIST"
        fi
    fi
done

# Outro (asset externo, se existir)
OUTRO="$PROJECT_DIR/assets/outro.mp3"
if [ -f "$OUTRO" ]; then
    make_silence 0.800 "$SEGMENTS_DIR/pause_outro.mp3"
    echo "file '$SEGMENTS_DIR/pause_outro.mp3'" >> "$CONCAT_LIST"
    echo "file '$OUTRO'" >> "$CONCAT_LIST"
fi

# ── Concatenar tudo ───────────────────────────────────────────────────────────
RAW_OUTPUT="$EPISODE_DIR/episode_raw.mp3"
ffmpeg -y -f concat -safe 0 -i "$CONCAT_LIST" -c copy "$RAW_OUTPUT" 2>/dev/null

# ── Normalização final ────────────────────────────────────────────────────────
FINAL_OUTPUT="$EPISODE_DIR/episode.mp3"
ffmpeg -y -i "$RAW_OUTPUT" \
    -af "loudnorm=I=-16:TP=-1.5:LRA=11" \
    -b:a 128k -ar 44100 \
    "$FINAL_OUTPUT" 2>/dev/null

# ── Metadata ID3 ──────────────────────────────────────────────────────────────
TITLE=$(jq -r '.title' "$GUIAO_PATH")
EPISODE_NUM=$(jq -r '.episode_number' "$GUIAO_PATH")
DATE=$(jq -r '.date' "$GUIAO_PATH")

ffmpeg -y -i "$FINAL_OUTPUT" \
    -metadata title="Daily Patch #$EPISODE_NUM — $TITLE" \
    -metadata artist="Byte & Pixel" \
    -metadata album="Daily Patch" \
    -metadata genre="Podcast" \
    -metadata date="$DATE" \
    -metadata comment="Gerado por IA" \
    -c copy "$EPISODE_DIR/episode_final.mp3" 2>/dev/null
mv "$EPISODE_DIR/episode_final.mp3" "$FINAL_OUTPUT"

# ── Limpeza ───────────────────────────────────────────────────────────────────
rm -f "$RAW_OUTPUT"
# rm -rf "$SEGMENTS_DIR"  # TEMPORARIAMENTE desabilitado para debug

# ── Stats finais ──────────────────────────────────────────────────────────────
DURATION=$(ffprobe -i "$FINAL_OUTPUT" -show_entries format=duration -v quiet -of csv="p=0" 2>/dev/null | cut -d. -f1)
SIZE=$(du -h "$FINAL_OUTPUT" | cut -f1)

echo ""
echo "✅ Episódio gerado com sucesso!"
echo "📁 Ficheiro: $FINAL_OUTPUT"
echo "⏱️  Duração: ${DURATION}s (~$((DURATION/60))m$((DURATION%60))s)"
echo "💾 Tamanho: $SIZE"
