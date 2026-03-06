# Chatterbox TTS — Instalacao e Configuracao

## Status: TESTADO E FUNCIONANDO (2026-03-05)

## Contexto

TTS local para o Daily Patch, substituindo ElevenLabs API (paga).
Usa voice cloning com referencias dos episodios anteriores (gerados via ElevenLabs).

- **GPU:** NVIDIA RTX 2070 Max-Q (7.6 GB VRAM)
- **VRAM usada pelo modelo:** ~3.6 GB pico (sobra bastante)
- **Sistema:** Ubuntu 24.04, kernel 6.18
- **Python:** 3.12.3
- **Modelo:** Chatterbox Multilingual (500M params), suporta PT-BR
- **Performance:** ~40 tokens/s, ~4-7s por frase na RTX 2070

## Instalacao (testada)

### 1. Criar venv

```bash
cd <project-root>
python3 -m venv .venv-chatterbox
source .venv-chatterbox/bin/activate
```

### 2. Instalar PyTorch com CUDA 12.4

Driver NVIDIA 580+ suporta ate CUDA 13. PyTorch mais recente estavel tem cu124.

```bash
pip install --upgrade pip "setuptools<81" wheel
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
```

Nota: `setuptools<81` e necessario porque `resemble-perth` usa `pkg_resources`.

### 3. Instalar dependencias manualmente

O pacote PyPI `chatterbox-tts==0.1.6` pede `numpy<1.26` que nao compila em Python 3.12.
A solucao e instalar deps na mao e depois o chatterbox com `--no-deps`.

```bash
pip install numpy librosa "transformers==4.46.3" "diffusers>=0.29.0" \
    "safetensors==0.5.3" resemble-perth omegaconf conformer s3tokenizer pyloudnorm
pip install chatterbox-tts --no-deps
```

### 4. Verificar

```bash
python -c "
import torch
print(f'PyTorch {torch.__version__}')
print(f'CUDA: {torch.cuda.is_available()}')
print(f'GPU: {torch.cuda.get_device_name(0)}')
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
print('Chatterbox Multilingual: OK')
"
```

## Voice References

Sempre usar voice cloning — sem referencia a voz generica nao tem qualidade.

Referencias extraidas do ep4 (ElevenLabs) e guardadas em `assets/voice_refs/`:

| Personagem | Ficheiro | Duracao |
|---|---|---|
| BYTE | `byte_ref.mp3` | 22.9s |
| PIXEL | `pixel_ref.mp3` | 21.3s |
| PASQUALINO | `pasqualino_ref.mp3` | 18.4s |
| ESTAGIARIO | `estagiario_ref.mp3` | 8.5s |
| CLAUDE | `claude_ref.mp3` | 27.6s |

Recomendado: 10s+ de audio limpo por referencia. Estagiario tem 8.5s (unico segmento longo disponivel).

## Perfis de Voz (testados e aprovados)

Configuracao completa em `config/vozes_chatterbox.json`.

| Personagem | Estilo | exaggeration | cfg_weight | temperature | speed |
|---|---|---|---|---|---|
| BYTE | expressive | 0.7 | 0.3 | 1.0 | 1.15x |
| PIXEL | default | 0.5 | 0.5 | 0.8 | 1.0x |
| PASQUALINO | grumpy | 0.7 | 0.3 | 1.0 | 1.15x |
| ESTAGIARIO | nervous | 0.6 | 0.4 | 0.9 | 1.0x |
| CLAUDE | expressive | 0.7 | 0.3 | 1.0 | 1.25x |

## API

### Carregar modelo

```python
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
# device: "cuda", "cpu" ou "mps" (Mac)
# Primeiro run baixa ~2GB para ~/.cache/huggingface/
# Depois carrega em ~10s
```

### Gerar fala (uma frase)

```python
import torchaudio as ta

wav = model.generate(
    text="Fala galera, Daily Patch no ar.",
    language_id="pt",
    audio_prompt_path="assets/voice_refs/byte_ref.mp3",
    exaggeration=0.7,
    cfg_weight=0.3,
    temperature=1.0,
)
ta.save("output.wav", wav, model.sr)
# wav: tensor shape (1, num_samples)
# model.sr: sample rate do modelo (usado no ta.save)
```

### Gerar multiplas frases do mesmo personagem (otimizado)

Usar `prepare_conditionals()` para carregar a referencia uma vez
e gerar varias frases sem recarregar o audio de referencia a cada chamada:

```python
# Carregar referencia uma vez
model.prepare_conditionals("assets/voice_refs/byte_ref.mp3", exaggeration=0.7)

# Gerar multiplas frases (nao passar audio_prompt_path)
for i, frase in enumerate(frases):
    wav = model.generate(
        text=frase,
        language_id="pt",
        cfg_weight=0.3,
        temperature=1.0,
    )
    ta.save(f"seg_{i:03d}.wav", wav, model.sr)
```

### Aplicar speed com ffmpeg

```python
import subprocess

# Acelerar sem alterar pitch
subprocess.run([
    "ffmpeg", "-y", "-i", "input.wav",
    "-af", "atempo=1.15",
    "output.wav"
])
```

### Idiomas suportados

23 idiomas: ar, da, de, el, en, es, fi, fr, he, hi, it, ja, ko, ms, nl, no, pl, **pt**, ru, sv, sw, tr, zh

## Parametros do generate()

| Parametro | Default | Descricao |
|---|---|---|
| `text` | (obrigatorio) | Texto a sintetizar. Acentuacao correta afeta pronuncia |
| `language_id` | (obrigatorio) | Codigo do idioma. `"pt"` para portugues |
| `audio_prompt_path` | `None` | Audio de referencia para voice cloning. Ignorado se `prepare_conditionals()` ja foi chamado |
| `exaggeration` | `0.5` | Expressividade: 0.3=contido, 0.5=neutro, 0.7+=expressivo |
| `cfg_weight` | `0.5` | Aderencia a referencia: 0.3=mais natural, 0.7+=mais fiel |
| `temperature` | `0.8` | Variacao: 0.5=previsivel, 0.8=neutro, 1.0=criativo |
| `repetition_penalty` | `2.0` | Penalidade para tokens repetidos |
| `min_p` | `0.05` | Filtro de probabilidade minima |
| `top_p` | `1.0` | Nucleus sampling |

### Retorno

`generate()` retorna um `torch.Tensor` shape `(1, num_samples)`.
Usar `model.sr` como sample rate ao salvar com `torchaudio.save()`.

## Pipeline de Geracao de Episodio

Guia para gerar o script Python que converte `guiao.json` em audio final.

### Estrutura do guiao.json (input)

```json
{
  "episode_number": 4,
  "date": "2026-03-04",
  "title": "Titulo do episodio",
  "news_of_the_day": "Noticia principal",
  "segments": [
    {"speaker": "BYTE", "text": "Fala do personagem.", "emotion": "neutral", "pace": "normal"},
    {"speaker": "BYTE", "text": "", "sfx": "glass_knock"},
    {"speaker": "PIXEL", "text": "", "sfx": "transition_jump", "pause_before": 1.0, "pause_after": 1.0},
    {"speaker": "PASQUALINO", "text": "resmungo ininteligivel", "filter": "mumble"}
  ]
}
```

### Campos de cada segmento

| Campo | Descricao |
|---|---|
| `speaker` | BYTE, PIXEL, PASQUALINO, ESTAGIARIO ou CLAUDE |
| `text` | Texto a sintetizar. Vazio se for so SFX |
| `sfx` | (opcional) glass_knock, disco_rigido, transition_jump ou applause |
| `pause_before` | (opcional) segundos de silencio ANTES do segmento |
| `pause_after` | (opcional) segundos de silencio DEPOIS do segmento |
| `pace` | (opcional) "normal", "fast" ou "interrupt" |
| `filter` | (opcional) "mumble" para resmungo ininteligivel |
| `emotion` | (opcional) "neutral", "excited", "sarcastic", "surprised", "thoughtful" |

### Logica do script (passo a passo)

```
1. Carregar guiao.json
2. Carregar vozes_chatterbox.json
3. Carregar modelo: ChatterboxMultilingualTTS.from_pretrained(device="cuda")
4. Para cada segmento:
   a. Se tem pause_before > 0: gerar silencio com ffmpeg (anullsrc)
   b. Se tem sfx: copiar o ficheiro de assets/sfx/{sfx}.mp3
   c. Se tem text (nao vazio):
      - Buscar config do speaker em vozes_chatterbox.json
      - Gerar TTS com model.generate()
      - Salvar WAV temporario
      - Se speed != 1.0: aplicar atempo com ffmpeg
      - Se filter == "mumble": aplicar lowpass com ffmpeg
   d. Se tem pause_after > 0: gerar silencio com ffmpeg
   e. Adicionar ficheiro a lista de concat
5. Concatenar tudo com ffmpeg concat + loudnorm
6. Converter para MP3 128kbps 44100Hz
```

### Gerar silencio (para pausas)

```python
subprocess.run([
    "ffmpeg", "-y", "-f", "lavfi",
    "-i", f"anullsrc=r=44100:cl=mono",
    "-t", str(seconds),
    "-c:a", "libmp3lame", "-b:a", "128k",
    output_path
])
```

### Aplicar filtro mumble (para Pasqualino resmungando)

```python
subprocess.run([
    "ffmpeg", "-y", "-i", input_path,
    "-af", "lowpass=f=400,volume=0.6",
    output_path
])
```

### Controle de pausas por pace

| pace | Pausa entre segmentos |
|---|---|
| "normal" | 0.4s |
| "fast" | 0.1s |
| "interrupt" | 0.0s (sem pausa) |

Estas pausas sao ADICIONAIS as pause_before/pause_after do segmento.

### Concatenar tudo no final

```python
# Gerar ficheiro concat.txt
with open("concat.txt", "w") as f:
    for path in segment_files:
        f.write(f"file '{path}'\n")

# Concatenar com loudnorm + converter para MP3
subprocess.run([
    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
    "-i", "concat.txt",
    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
    "-b:a", "128k", "-ar", "44100",
    "episode.mp3"
])
```

### SFX disponiveis

Ficheiros em `assets/sfx/`:
- `glass_knock.mp3` — batida no vidro
- `disco_rigido.mp3` — som de disco (vinheta de abertura)
- `transition_jump.mp3` — transicao entre blocos
- `applause.mp3` — aplausos (cena do estagiario)

### Caminhos importantes

| O que | Caminho |
|---|---|
| Projeto | `<project-root>` |
| Venv | `.venv-chatterbox/` |
| Config vozes | `config/vozes_chatterbox.json` |
| Voice refs | `assets/voice_refs/` |
| SFX | `assets/sfx/` |
| Episodios | `episodes/YYYY-MM-DD-epN/` |
| Output | `episodes/YYYY-MM-DD-epN/episode.mp3` |

### Executar

```bash
cd <project-root>
source .venv-chatterbox/bin/activate
python scripts/gerar_episodio.py episodes/2026-03-05-ep5/guiao.json
```

### Resume support

O script deve verificar se cada segmento WAV ja existe antes de gerar.
Isso permite retomar geracao interrompida sem repetir segmentos.

```python
output_path = f"segments/seg_{i:03d}.wav"
if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
    print(f"[{i}] cached")
else:
    # gerar TTS
```

## Dicas de Pronuncia

- O modelo le o texto literalmente — acentos afetam pronuncia
- Sem acento: "manha" soa errado. Com acento: "manhã" soa correto
- Truque: usar acentos falsos como hints (ex: "nessa" -> "néssa" para forcar enfase)
- Numeros: escrever por extenso ("três" em vez de "3")

## Notas

- Primeiro run baixa ~2GB de modelos para `~/.cache/huggingface/`
- Modelo ja em cache, carrega em ~10s
- Geracao: ~4-7s por frase curta na RTX 2070
- Output: WAV (converter para MP3 com ffmpeg no pipeline final)
- Speed via `ffmpeg -af atempo=X` — preserva pitch, nao distorce
- Warnings de deprecacao (sdp_kernel, LoRA, pkg_resources) sao inofensivos
- Testes de voz organizados em `tests/chatterbox/`
