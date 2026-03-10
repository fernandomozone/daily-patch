# Daily Patch — Memória do Projeto

## O que é

Podcast diário gerado por IA em PT-BR. Tom descontraído, caótico, com discussões, zoeiras e interrupções naturais entre personagens de TI. Publicação: segunda a sexta.

## Stack Atual

- **TTS**: Chatterbox Multilingual (local, GPU) — substituiu ElevenLabs
- **LLM**: Claude (roteiro + orquestração)
- **Áudio**: ffmpeg (loudnorm, concat, speed, mumble) + pydub (crossfade, trim silence)
- **GPU**: NVIDIA RTX 2070 Max-Q (7.6 GB VRAM)
- **Performance**: ~4-7s por frase, episódio completo em ~10-15 min

## IMPORTANTE — Migração Cowork → Claude Code

Este projeto era gerido pelo Claude Cowork (desktop). A partir do ep5 (2026-03-05), **tudo passa a ser feito pelo Claude Code** porque:

1. O Claude Code roda na máquina do user, com acesso direto à GPU (Chatterbox precisa de CUDA)
2. O Cowork roda numa VM sem GPU — só conseguia preparar ficheiros, não executar TTS
3. O fluxo completo (buscar notícias → roteiro → hints TTS → gerar áudio) fica numa só ferramenta

### O que o Claude Code assume:

1. **Buscar notícias** — pesquisar web por notícias do dia (mundo, Brasil, tech, games)
2. **Escrever roteiro** — criar `guiao.json` seguindo `config/prompt-guiao.md`
3. **Aplicar hints fonéticos TTS** — substituir termos em inglês/estrangeiros por fonética PT-BR (ver secção abaixo)
4. **Gerar áudio** — executar `scripts/gerar_episodio.py` com o Chatterbox
5. **Manter estado** — atualizar banco de erros do Pasqualino, histórico de episódios

---

## Fluxo Completo de Geração de Episódio

```
1. Buscar notícias do dia (6+ queries: guerra/mundo, Brasil/economia, tech, games, IA, outros)
2. Compilar notícias e criar episodes/YYYY-MM-DD-epN/guiao.json
   → Seguir TODAS as regras de config/prompt-guiao.md
   → Verificar: intro fixa, Pasqualino (erro novo), Estagiário, Claude (4ª parede)
   → Verificar: duração alvo 1800-2200 palavras
3. Aplicar hints fonéticos TTS ao guiao.json (ver secção BOAS PRÁTICAS TTS)
4. Executar:
   cd <project-root>
   source .venv-chatterbox/bin/activate
   python scripts/gerar_episodio.py episodes/YYYY-MM-DD-epN/guiao.json
5. Verificar duração do MP3 (mínimo 9:30)
6. Atualizar banco de erros do Pasqualino em config/prompt-guiao.md (marcar ✅)
```

---

## Boas Práticas TTS (Chatterbox PT-BR)

O Chatterbox Multilingual com `language_id="pt"` lê texto literalmente.

### Regra principal: maioria das palavras EN o Chatterbox já pronuncia bem

- EN -> EN: "Daily Patch", "Game Pass", "deploy", "remake", "Steam", "housing"
- JP -> JP: "Dattebayo", "Hokage"
- PT -> PT: tudo o resto

**TESTADO**: deploy, remake, housing, Steam, Anthropic, containers, Docker, Firefox, PlayStation, Sony, Bloomberg — todos soam bem sem fonética.

### Dicionário fonético (`config/pronuncia.json`)

Aplicado automaticamente pelo script antes do TTS. Duas categorias:

**Siglas** (soletradas em PT-BR):
- IA→I.A., PC→P.C., GDC→G.D.C., CPU→C.P.U., SSH→S.S.H., DJ→D.J., etc.

**Palavras que precisam fonética** (testado e confirmado):
- feature→fítcher, htop→êitchtóp, Bungie→Bânji
- Testes em andamento — ver resultados completos em auto-memory

### Palavras que NÃO precisam fonética

deploy, remake, housing, Steam, Anthropic, containers, Docker, Firefox, PlayStation, Sony, Bloomberg, God of War, Spider-Man

### Ferramentas de fonética instaladas

- `phonemizer` + `espeak-ng` — converte texto→IPA (100+ idiomas)
- `g2p-en` — grapheme-to-phoneme para inglês
- Pipeline: EN word → IPA (phonemizer) → PT-BR hint (conversão manual)
- Conversão automática IPA→PT-BR precisa refinamento (preferir fonéticas simples)

### Dicas de pronuncia

- Acentos afetam pronuncia: "manha" soa errado, "manhã" soa correto
- Numeros sempre por extenso: "tres" e nao "3"
- Truque para enfase: usar acento falso (ex: "nessa" -> "néssa" para forcar enfase)
- Pontuacao afeta ritmo: ponto final = pausa, virgula = pausa curta, reticencias = trailing

---

## Personagens e Vozes Chatterbox

Configuração completa em `config/vozes_chatterbox.json`.

| Personagem | Ref | exaggeration | cfg_weight | temperature | speed |
|---|---|---|---|---|---|
| BYTE | byte_ref.mp3 (22.9s) | 0.7 | 0.3 | 1.0 | 1.15x |
| PIXEL | pixel_ref.mp3 (21.3s) | 0.5 | 0.5 | 0.8 | 1.0x |
| PASQUALINO | pasqualino_ref.mp3 (18.4s) | 0.7 | 0.3 | 1.0 | 1.15x |
| ESTAGIARIO | estagiario_ref.mp3 (8.5s) | 0.6 | 0.4 | 0.9 | 1.0x |
| CLAUDE | claude_ref.mp3 (27.6s) | 0.7 | 0.3 | 1.0 | 1.25x |

Voice refs em `assets/voice_refs/` — extraídas do ep4 (ElevenLabs). Usar sempre voice cloning.

---

## ElevenLabs (histórico, eps 1-4)

Voice IDs e API keys em `config/.env` (não commitado). Não usar para novos episódios.

---

## Estrutura de Ficheiros

```
daily-patch/
  CLAUDE.md                    # ← ESTE FICHEIRO (memória do projeto)
  CHATTERBOX_SETUP.md          # Documentação completa da API Chatterbox
  config/
    .env                       # API keys (ElevenLabs — histórico)
    prompt-guiao.md            # Master prompt para geração de roteiro
    pronuncia.json             # Dicionário fonético TTS (siglas + palavras)
    vozes_chatterbox.json      # Perfis de voz Chatterbox (USAR ESTE)
    vozes.json                 # Perfis ElevenLabs (histórico)
  scripts/
    gerar_episodio.py          # Script principal — Chatterbox TTS (USAR ESTE)
    gerar-audio.sh             # Script v2 ElevenLabs (DEPRECADO)
    publicar-telegram.sh       # Publicação no Telegram
    testar_tts_local.sh        # Testes de voz Chatterbox
  assets/
    voice_refs/                # Referências de voz para cloning
      byte_ref.mp3
      pixel_ref.mp3
      pasqualino_ref.mp3
      estagiario_ref.mp3
      claude_ref.mp3
    sfx/                       # Efeitos sonoros
      glass_knock.mp3          # Batida no vidro
      disco_rigido.mp3         # Vinheta de abertura
      transition_jump.mp3      # Transição entre blocos
      applause.mp3             # Aplausos (cena do Estagiário)
  episodes/
    YYYY-MM-DD-epN/
      guiao.json               # Roteiro com hints fonéticos
      segments/                # Segmentos WAV individuais (gerados)
      episode.mp3              # Áudio final
  .venv-chatterbox/            # Python venv com Chatterbox + PyTorch CUDA
```

---

## Banco de Erros do Pasqualino

Manter atualizado em `config/prompt-guiao.md`. Sortear 1 por episódio, NUNCA repetir.

✅ USADO ep3: "menas" → "menos"
✅ USADO ep4: "pra mim mostrar" → "pra eu mostrar"
✅ USADO ep5: "houveram" → "houve"
✅ USADO ep6: "fazem dez anos" → "faz dez anos"
✅ USADO ep7: "a gente vamos" → "a gente vai"
☐ "assistir o filme" → "assistir ao filme"
☐ "entre eu e você" → "entre mim e você"
☐ "a nível de" → "em nível de"
☐ "meio cansada" → "meia cansada" → "meio" é advérbio
☐ "onde você vai?" → "aonde você vai?"
☐ "tem muita gente" → "há muita gente"
☐ "obrigado" (Pixel) → "obrigada"
☐ "eu que fiz" → "fui eu quem fez"
☐ "a maioria acham" → "a maioria acha"
☐ "esse daí" → "esse aí"
☐ "vi ele" → "vi-o" / "o vi"

---

## Histórico de Episódios

| Ep | Data | Dia | TTS | Duração | Notas |
|---|---|---|---|---|---|
| 1 | 2026-03-03 | seg | ElevenLabs v2 | ~8min | Problemas de segmentos sumindo |
| 2 | 2026-03-03 | seg | ElevenLabs v2 | ~8min | Tentativa v2 melhorada |
| 3 | 2026-03-03 | seg | ElevenLabs v3 | ~10min | Migração para text-to-dialogue |
| 4 | 2026-03-04 | qua | GenAIPro | 7:48 | Reseller ElevenLabs, segment-by-segment |
| 5 | 2026-03-05 | qui | Chatterbox | 10:48 | Primeiro ep local, EN->EN |
| 6 | 2026-03-06 | sex | Chatterbox | 11:48 | Sexta-feira TI, duração corrigida |
| 7 | 2026-03-09 | seg | Chatterbox | 10:29 | Dicionário fonético, compact MP3 |

---

## Histórico de Decisões

- **Ep1-2**: ElevenLabs v2 (segment-by-segment + ffmpeg concat) — problemas de segmentos sumindo
- **Ep3**: ElevenLabs v3 (text-to-dialogue) — som mais natural, mas API cara ($22/mês)
- **Ep4**: GenAIPro (reseller ElevenLabs) — $8/250k créditos, mas muito lento (~1.5h por episódio)
- **Ep5**: Chatterbox Multilingual (local) — gratuito, ~10min por episódio, voice cloning com refs do ep4
- **EN->EN**: palavras inglesas escritas em ingles, sem fonetizar (regra a partir do ep5)
- **Crossfade**: pydub crossfade 50ms + fade-in/out 30ms entre segmentos (ep5)
- **Trim silence**: pydub -55dB remove silencio puro no inicio/fim de segmentos TTS (ep5)
- **Speed via ffmpeg**: atempo preserva pitch, não distorce
- **Compact MP3**: versão <18MB gerada automaticamente como episode_compact.mp3
- **Pronúncia**: dicionário fonético em config/pronuncia.json (siglas + palavras problemáticas)
- **Fonética seletiva**: só fonetizar palavras que realmente soam mal (testado: maioria EN→EN funciona)

---

## Comandos Úteis

```bash
# Gerar episódio
cd <project-root>
source .venv-chatterbox/bin/activate
python scripts/gerar_episodio.py episodes/YYYY-MM-DD-epN/guiao.json

# Verificar duração
ffprobe -v quiet -show_entries format=duration -of csv=p=0 episodes/YYYY-MM-DD-epN/episode.mp3

# Verificar CUDA
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# Testar uma frase
python -c "
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
import torchaudio as ta
model = ChatterboxMultilingualTTS.from_pretrained(device='cuda')
wav = model.generate('Fala galera, Dêili Pétchi no ar.', language_id='pt', audio_prompt_path='assets/voice_refs/byte_ref.mp3', exaggeration=0.7, cfg_weight=0.3, temperature=1.0)
ta.save('teste.wav', wav, model.sr)
print('OK')
"

# Limpar segmentos para regerar do zero
rm -rf episodes/YYYY-MM-DD-epN/segments/
```
