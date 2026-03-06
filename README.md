# Daily Patch

Podcast diário gerado por IA em Português do Brasil. Cinco personagens de TI discutem notícias do dia com humor, interrupções e caos controlado. Todo o áudio é gerado localmente via voice cloning — zero custo de API.

AI-generated daily podcast in Brazilian Portuguese. Five IT characters discuss the day's news with humor, interruptions, and controlled chaos. All audio is generated locally via voice cloning — zero API costs.

---

## Personagens / Characters

| Personagem | Papel | Role |
|---|---|---|
| **BYTE** | Apresentador, dev/sysadmin, fanático Linux | Host, dev/sysadmin, Linux enthusiast |
| **PIXEL** | Co-apresentadora, dev, sarcástica, energética | Co-host, dev, sarcastic, energetic |
| **PASQUALINO** | Marketing, corrige português, aparece 1x/ep | Marketing guy, grammar police, 1x/ep |
| **ESTAGIÁRIO** | Estagiário TI, ex-Windows, fanático Naruto | IT intern, ex-Windows, Naruto fan |
| **CLAUDE** | IA que gera o podcast, quebra 4a parede | The AI generating the podcast, breaks 4th wall |

## Stack

| Componente | Tecnologia |
|---|---|
| **TTS** | [Chatterbox Multilingual](https://github.com/resemble-ai/chatterbox) (local, GPU) |
| **Voice Cloning** | Referências de áudio por personagem (~10-30s cada) |
| **LLM** | Claude (roteiro + orquestração via Claude Code) |
| **Áudio** | ffmpeg (loudnorm, speed, filters) + pydub (crossfade, trim) |
| **GPU** | NVIDIA RTX 2070 Max-Q (7.6 GB VRAM) |
| **Custo** | $0 (tudo local) |

## Como Funciona / How It Works

```
Notícias do dia          →  Claude gera guião (JSON)
Today's news                Claude generates script

guião.json               →  Chatterbox TTS (local GPU)
                             Voice cloning per character
                             ~5s per segment

Segmentos WAV            →  ffmpeg + pydub
WAV segments                Crossfade, trim, loudnorm

episode.mp3              →  MP3 320kbps stereo
                             ~10-12 min per episode
```

## Estrutura / Structure

```
daily-patch/
  config/
    prompt-guiao.md            # Master prompt para roteiro / Script generation prompt
    vozes_chatterbox.json      # Voice profiles (exaggeration, cfg, temp, speed)
  scripts/
    gerar_episodio.py          # Main generation script (Chatterbox TTS)
  assets/
    sfx/                       # Sound effects (glass knock, transitions, etc.)
    voice_refs/                # Voice reference audio for cloning (not in repo)
  episodes/
    YYYY-MM-DD-epN/
      guiao.json               # Episode script
      segments/                # Individual WAV segments (generated)
      episode.mp3              # Final audio
```

## Setup

### Requisitos / Requirements

- Python 3.12+
- NVIDIA GPU with CUDA (tested: RTX 2070, ~3.6 GB VRAM)
- ffmpeg
- ~2 GB disk for model weights (cached in `~/.cache/huggingface/`)

### Instalação / Installation

```bash
# Clone
git clone https://github.com/fernandomozone/daily-patch.git
cd daily-patch

# Create venv
python3 -m venv .venv-chatterbox
source .venv-chatterbox/bin/activate

# Install PyTorch with CUDA
pip install --upgrade pip "setuptools<81" wheel
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124

# Install Chatterbox (manual deps due to numpy/Python 3.12 incompatibility)
pip install numpy librosa "transformers==4.46.3" "diffusers>=0.29.0" \
    "safetensors==0.5.3" resemble-perth omegaconf conformer s3tokenizer pyloudnorm pydub
pip install chatterbox-tts --no-deps

# Verify
python -c "
import torch
print(f'PyTorch {torch.__version__}')
print(f'CUDA: {torch.cuda.is_available()}')
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
print('Chatterbox: OK')
"
```

### Voice References

You need voice reference audio files in `assets/voice_refs/` for each character. These are not included in the repo.

- Minimum 10 seconds of clean speech per character
- MP3 or WAV format
- One speaker per file, no background noise
- Configure paths in `config/vozes_chatterbox.json`

### Gerar Episódio / Generate Episode

```bash
source .venv-chatterbox/bin/activate
python scripts/gerar_episodio.py episodes/YYYY-MM-DD-epN/guiao.json
```

The script:
1. Estimates duration before generating (warns if < 9:30)
2. Generates TTS for each segment with voice cloning
3. Applies speed, filters (mumble), and SFX
4. Concatenates with crossfade + trim silence
5. Exports MP3 320kbps stereo with loudnorm

Resume support: previously generated segments (WAV > 1KB) are reused.

## Formato do Guião / Script Format

```json
{
  "episode_number": 6,
  "date": "2026-03-06",
  "title": "Episode Title",
  "segments": [
    {
      "speaker": "BYTE",
      "text": "Fala galera, Daily Patch no ar.",
      "emotion": "neutral",
      "pace": "normal"
    },
    {
      "speaker": "PIXEL",
      "text": "",
      "sfx": "glass_knock",
      "pause_before": 0.5,
      "pause_after": 0.5
    },
    {
      "speaker": "PASQUALINO",
      "text": "resmungo ininteligível",
      "filter": "mumble"
    }
  ]
}
```

### Campos / Fields

| Campo | Descrição | Description |
|---|---|---|
| `speaker` | BYTE, PIXEL, PASQUALINO, ESTAGIARIO, CLAUDE | Character name |
| `text` | Texto a sintetizar (vazio se só SFX) | Text to synthesize |
| `sfx` | glass_knock, disco_rigido, transition_jump, applause | Sound effect |
| `pace` | normal, fast, interrupt | Pacing between segments |
| `pause_before/after` | Segundos de silêncio | Silence in seconds |
| `filter` | mumble (lowpass + volume down) | Audio filter |
| `emotion` | neutral, excited, sarcastic, surprised, thoughtful | For script context |

## Estimativa de Duração / Duration Estimation

The script estimates episode duration before generating:

```
duration ≈ 0.049 × chars + 1.46s per segment (adjusted for character speed)
```

- Minimum: 12,000 TTS characters for 9:30+
- Target: 14,000-16,000 characters for 11-12 min
- Formula accuracy: ~2.7% error

## Licença / License

MIT

## Créditos / Credits

- TTS: [Chatterbox](https://github.com/resemble-ai/chatterbox) by Resemble AI
- LLM: [Claude](https://claude.ai) by Anthropic
- Audio processing: ffmpeg, pydub
