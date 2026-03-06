#!/bin/bash
# =============================================================================
# Daily Patch — Teste de TTS Local (Kokoro + F5-TTS-pt-br)
# Corre isto no teu terminal (não no Cowork)
# Requer: Python 3.10+, NVIDIA GPU com CUDA
# =============================================================================

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DIR="$PROJECT_DIR/testes_tts"
VENV_DIR="$PROJECT_DIR/.venv"
mkdir -p "$TEST_DIR"

echo "============================================"
echo "  Daily Patch — Teste de TTS Local"
echo "  GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || echo 'N/A')"
echo "============================================"
echo ""

# ── Criar/ativar venv ───────────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Criando virtual environment em .venv..."
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
echo "✅ venv ativado: $(which python3)"

# ── Instalar PyTorch com CUDA ───────────────────────────────────────────────
echo "🔍 Verificando PyTorch + CUDA..."
if ! python3 -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
    echo "📦 Instalando PyTorch com CUDA 12.1..."
    pip install -q torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
fi
python3 -c "import torch; print(f'  CUDA OK: {torch.cuda.get_device_name(0)}')"

# ── Frases de teste (intro do Daily Patch) ──────────────────────────────────
FRASE_BYTE_1="Eita, chegou o patch de hoje. Vamos lá."
FRASE_PIXEL_1="Aff Maria, essa pauta tá pesada de novo."
FRASE_PIXEL_2="Quer café?"
FRASE_BYTE_2="Quero."
FRASE_BYTE_3="Ó Estagiário! Dois cafés!"
FRASE_BYTE_4="Fala galera, Daily Patch no ar. Byte aqui, e hoje o changelog do mundo veio com patch de emergência."
FRASE_PIXEL_3="Pixel na área! Gente, segura que hoje tem guerra, iPhone novo e robô que dança. Tudo no mesmo episódio."

# ═══════════════════════════════════════════════════════════════════════════════
# TESTE 1: KOKORO 82M
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════"
echo "  TESTE 1: Kokoro 82M"
echo "═══════════════════════════════════════════"

KOKORO_DIR="$TEST_DIR/kokoro"
mkdir -p "$KOKORO_DIR"

# Instalar kokoro
echo "📦 Instalando kokoro..."
pip install -q kokoro>=0.9 soundfile 2>/dev/null || pip install -q kokoro soundfile

echo "🎙️ Gerando áudio com Kokoro..."
python3 << 'KOKORO_EOF'
import kokoro
import soundfile as sf
import time, os

test_dir = os.environ.get('KOKORO_DIR', 'testes_tts/kokoro')

# Vozes PT-BR disponíveis
voices = {
    'byte': 'pm_alex',     # masculina
    'pixel': 'pf_dora',    # feminina
    'pasqualino': 'pm_santa',  # masculina 2
}

frases = [
    ('byte', "Eita, chegou o patch de hoje. Vamos lá."),
    ('pixel', "Aff Maria, essa pauta tá pesada de novo."),
    ('pixel', "Quer café?"),
    ('byte', "Quero."),
    ('byte', "Ó Estagiário! Dois cafés!"),
    ('byte', "Fala galera, Daily Patch no ar. Byte aqui, e hoje o changelog do mundo veio com patch de emergência."),
    ('pixel', "Pixel na área! Gente, segura que hoje tem guerra, iPhone novo e robô que dança. Tudo no mesmo episódio."),
]

# Inicializar pipeline
print("  Carregando modelo Kokoro...")
pipeline = kokoro.KPipeline(lang_code='p')  # 'p' = português

all_audio = []
sample_rate = 24000

for i, (personagem, texto) in enumerate(frases):
    voice = voices[personagem]
    print(f"  [{i+1}/{len(frases)}] {personagem} ({voice}): {texto[:50]}...")

    start = time.time()
    # Gerar audio
    generator = pipeline(texto, voice=voice, speed=1.0)
    for _, _, audio in generator:
        # Salvar individual
        filename = f"{test_dir}/kokoro_{i:02d}_{personagem}.wav"
        sf.write(filename, audio, sample_rate)
        all_audio.append(audio)
    elapsed = time.time() - start
    print(f"    OK ({elapsed:.1f}s)")

# Concatenar tudo
import numpy as np
silence = np.zeros(int(sample_rate * 0.15))  # 150ms entre falas
full_audio = []
for i, audio in enumerate(all_audio):
    full_audio.append(audio)
    if i < len(all_audio) - 1:
        full_audio.append(silence)

combined = np.concatenate(full_audio)
output = f"{test_dir}/kokoro_intro_completa.wav"
sf.write(output, combined, sample_rate)
print(f"\n✅ Intro Kokoro completa: {output}")
print(f"   Duração: {len(combined)/sample_rate:.1f}s")
KOKORO_EOF

export KOKORO_DIR="$KOKORO_DIR"

# ═══════════════════════════════════════════════════════════════════════════════
# TESTE 2: F5-TTS-pt-br (com voice cloning)
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════"
echo "  TESTE 2: F5-TTS-pt-br"
echo "═══════════════════════════════════════════"

F5_DIR="$TEST_DIR/f5tts"
mkdir -p "$F5_DIR"

echo "📦 Instalando f5-tts..."
pip install -q f5-tts safetensors num2words 2>/dev/null || echo "⚠️ Instalação pode precisar de ajustes"

echo "🎙️ Gerando áudio com F5-TTS..."
echo "   (Este modelo usa voice cloning — sem referência usa voz padrão)"

python3 << 'F5_EOF'
import time, os, soundfile as sf, numpy as np

test_dir = os.environ.get('F5_DIR', 'testes_tts/f5tts')

try:
    from f5_tts.api import F5TTS

    print("  Carregando modelo F5-TTS (base multilingual)...")
    tts = F5TTS(device="cuda")

    # Encontrar audio de referencia do pacote
    import glob, site
    search_paths = site.getsitepackages() + [site.getusersitepackages()]
    ref_audio = None
    ref_text = "Some call me nature, others call me mother nature."

    for sp in search_paths:
        candidate = os.path.join(sp, "f5_tts", "infer", "examples", "basic", "basic_ref_en.wav")
        if os.path.exists(candidate):
            ref_audio = candidate
            break

    # Se nao encontrou, procurar qualquer wav no pacote
    if not ref_audio:
        for sp in search_paths:
            wavs = glob.glob(os.path.join(sp, "f5_tts", "**", "*.wav"), recursive=True)
            if wavs:
                ref_audio = wavs[0]
                ref_text = ""
                break

    if not ref_audio:
        # Ultima tentativa: find no venv
        import subprocess
        result = subprocess.run(
            ["find", os.environ.get("VIRTUAL_ENV", "/"), "-path", "*/f5_tts/infer/examples/*.wav"],
            capture_output=True, text=True
        )
        wavs = result.stdout.strip().split("\n")
        if wavs and wavs[0]:
            ref_audio = wavs[0]
            ref_text = ""

    if not ref_audio:
        raise FileNotFoundError("Nenhum audio de referencia encontrado")

    print(f"  Ref audio: {ref_audio}")

    frases = [
        "Eita, chegou o patch de hoje. Vamos lá.",
        "Aff Maria, essa pauta tá pesada de novo.",
        "Quer café?",
        "Quero.",
        "Ó Estagiário! Dois cafés!",
        "Fala galera, Daily Patch no ar. Byte aqui, e hoje o changelog do mundo veio com patch de emergência.",
        "Pixel na área! Gente, segura que hoje tem guerra, iPhone novo e robô que dança. Tudo no mesmo episódio.",
    ]

    all_audio = []
    sample_rate = None

    for i, texto in enumerate(frases):
        print(f"  [{i+1}/{len(frases)}] {texto[:50]}...")
        start = time.time()

        wav, sr, _ = tts.infer(
            ref_file=ref_audio,
            ref_text=ref_text,
            gen_text=texto,
        )

        outfile = f"{test_dir}/f5_{i:02d}.wav"
        sf.write(outfile, wav, sr)
        all_audio.append(wav)
        if sample_rate is None:
            sample_rate = sr

        elapsed = time.time() - start
        print(f"    OK ({elapsed:.1f}s)")

    # Concatenar tudo
    silence = np.zeros(int(sample_rate * 0.15))
    full = []
    for i, audio in enumerate(all_audio):
        full.append(audio)
        if i < len(all_audio) - 1:
            full.append(silence)

    combined = np.concatenate(full)
    output = f"{test_dir}/f5_intro_completa.wav"
    sf.write(output, combined, sample_rate)
    print(f"\n✅ Intro F5-TTS completa: {output}")
    print(f"   Duração: {len(combined)/sample_rate:.1f}s")

except ImportError as e:
    print(f"  ❌ f5-tts não instalou correctamente: {e}")
    print("  Tenta: pip install f5-tts soundfile")
except Exception as e:
    print(f"  ❌ Erro: {e}")
    import traceback
    traceback.print_exc()
F5_EOF

export F5_DIR="$F5_DIR"

# ═══════════════════════════════════════════════════════════════════════════════
# RESUMO
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════"
echo "  RESULTADOS"
echo "═══════════════════════════════════════════"
echo ""
echo "📂 Ficheiros gerados em: $TEST_DIR/"
echo ""
echo "🎧 Para ouvir:"
echo "   Kokoro intro: $KOKORO_DIR/kokoro_intro_completa.wav"
echo "   F5-TTS:       $F5_DIR/f5_*.wav"
echo ""
echo "📊 Comparação:"
echo "   - ElevenLabs v3: $PROJECT_DIR/episodes/2026-03-03-ep3/teste_v3_intro.mp3"
echo "   - Kokoro:        $KOKORO_DIR/kokoro_intro_completa.wav"
echo "   - F5-TTS:        $F5_DIR/f5_*.wav"
echo ""
echo "Ouve os 3 e decide qual preferes!"
