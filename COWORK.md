# Daily Patch — Instruções Cowork

## O que é este projeto

Podcast diário de 5-10 minutos gerado por IA. Dois apresentadores (Byte e Pixel) discutem o mundo com humor geek — mas sem forçar a barra. Conversa real, com debates, zoeiras e interrupções. Língua: Português do Brasil (PT-BR).

## Personagens

### Byte (Voz Masculina)
- Dev sênior, pragmático, direto. Analítico, fala com dados
- Referências nerd ESPORÁDICAS — só quando encaixa naturalmente
- Quando discorda da Pixel, fala. Quando ela exagera, zoa
- Voice ID ElevenLabs: {{BYTE_VOICE_ID}}

### Pixel (Voz Feminina)
- Criativa, energética, fã de games e anime
- Piadas e analogias nerds ESPORÁDICAS — não em toda fala
- Quando o assunto é sério, ela também fica séria. Provoca o Byte quando ele fica chato
- Voice ID ElevenLabs: {{PIXEL_VOICE_ID}}

### Pasqualino (Voz Masculina) — Alívio cômico
- O corretor gramatical do podcast
- Aparece EXATAMENTE 1x por episódio — bate no vidro, corrige, vai embora
- SFX obrigatório: glass_knock
- Exemplo: "É 'menos', não 'menas'. Com licença."
- Voice ID ElevenLabs: {{PASQUALINO_VOICE_ID}}

### Estagiário (Voz Masculina — nome a definir) — Alívio cômico
- O desastre técnico da produção — acidentes ao vivo com SFX reais
- Aparece 1-2x por episódio, sempre no pior momento
- SFX disponíveis: windows_crash, wrong_buzzer, glass_break, applause, door_slam, static_noise
- Exemplo: [applause] "Opa, foi mal, apertei o botão errado..."
- Voice ID ElevenLabs: {{ESTAGIARIO_VOICE_ID}}

### Personagens futuros (ainda não ativos)

#### [Músico] (Voz Masculina — nome a definir)
- O músico maconheiro do grupo — filosófico, viajandão, zen
- Faz comentários profundos (ou que ele acha profundos) completamente fora de contexto
- Às vezes toca um violãozinho de fundo
- Participação: aparições aleatórias, geralmente nos momentos mais inesperados
- Exemplo: "Cara... mas tipo... se a IA é inteligente, ela sabe que não sabe nada, saca? Sócrates já manjava..."

## Temas a cobrir

### Proporção de conteúdo por episódio
- **50% mundo**: política, economia, sociedade, internacional
- **30% tech e IA**: IA, devops, infra, programação, segurança
- **10% games / geek**: gaming, entretenimento, cultura nerd
- **10% interatividade**: Pasqualino (1x obrigatório) + Estagiário (1-2x)

### Mix geográfico das notícias
- ~80% Brasil + mundo
- ~20% Portugal (sempre contextualizado para audiência brasileira)

## Fontes de notícias (usar Claude in Chrome)

### Tech / Nerd / Gaming (internacionais)
- Hacker News (https://news.ycombinator.com)
- TechCrunch (https://techcrunch.com)
- Ars Technica (https://arstechnica.com)
- The Verge (https://theverge.com)
- NASA (https://nasa.gov/news)

### Brasil
- Tecnoblog (https://tecnoblog.net)
- Olhar Digital (https://olhardigital.com.br)
- Folha de S.Paulo (https://folha.uol.com.br)
- G1 (https://g1.globo.com)
- IGN Brasil (https://br.ign.com)
- The Enemy (https://theenemy.com.br)

### Portugal
- Observador (https://observador.pt)
- Público (https://publico.pt)
- ECO (https://eco.sapo.pt)
- Eurogamer PT (https://eurogamer.pt)

## Workflow para gerar um episódio

### Passo 1: Recolher notícias
- Navegar as fontes acima com Claude in Chrome
- Selecionar 4-6 notícias relevantes do dia
- Guardar resumos em `episodes/YYYY-MM-DD/noticias.json`

### Passo 2: Gerar guião
- Usar o prompt de `config/prompt-guiao.md`
- Output em `episodes/YYYY-MM-DD/guiao.json`
- Validar que tem entre 900-1200 palavras

### Passo 3: Gerar áudio
- Executar `scripts/gerar-audio.sh` com o guião
- Requer ELEVENLABS_API_KEY em `config/.env`
- Output em `episodes/YYYY-MM-DD/episode.mp3`

### Passo 4: Publicar
- Enviar para Telegram via `scripts/publicar-telegram.sh`
- Requer TELEGRAM_BOT_TOKEN e TELEGRAM_CHANNEL_ID em `config/.env`

## Comandos rápidos

- "Gera o episódio de hoje" → Executa os 4 passos completos
- "Só recolhe notícias" → Só Passo 1
- "Gera guião para estas notícias" → Só Passo 2
- "Publica o último episódio" → Só Passo 4

## Estrutura de pastas

```
daily-patch/
├── COWORK.md          ← (este ficheiro)
├── config/
│   ├── .env           ← API keys (NÃO partilhar)
│   ├── prompt-guiao.md ← System prompt para gerar guiões
│   └── vozes.json     ← Configuração das vozes TTS
├── scripts/
│   ├── gerar-audio.sh  ← Pipeline TTS + ffmpeg
│   └── publicar-telegram.sh ← Envio para canal
├── assets/
│   ├── intro.mp3      ← Jingle de abertura
│   └── outro.mp3      ← Jingle de fecho
└── episodes/
    └── YYYY-MM-DD/
        ├── noticias.json
        ├── guiao.json
        └── episode.mp3
```
