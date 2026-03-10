#!/usr/bin/env python3
"""
Daily Patch — Validação fonética TTS v2 (com classificação EN/PT)

Compara texto original vs transcrição Whisper, distinguindo palavras
PT (erro real) de EN (tolerância maior) e siglas (comparação normalizada).

Uso:
    python scripts/validar_tts_v2.py episodes/2026-03-09-ep7/guiao.json [--max-seg N]
"""

import json
import sys
import re
import unicodedata
from pathlib import Path

import enchant

PROJECT_DIR = Path(__file__).resolve().parent.parent
PRONUNCIA_CONFIG = PROJECT_DIR / "config" / "pronuncia.json"

WER_THRESHOLD_PT = 0.15   # palavras PT — threshold normal
WER_THRESHOLD_EN = 0.50   # palavras EN — muito mais tolerante
WER_THRESHOLD_GLOBAL = 0.20  # threshold global do segmento

dict_pt = enchant.Dict("pt_BR")


def load_pronuncia():
    if not PRONUNCIA_CONFIG.exists():
        return {}
    with open(PRONUNCIA_CONFIG) as f:
        data = json.load(f)
    return data.get("replacements", {})


def remove_acentos(text):
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def classificar_palavra(word, siglas_set):
    """Classifica uma palavra como 'PT', 'EN', 'SIGLA' ou 'NUM'."""
    w_clean = re.sub(r'[^\w]', '', word)
    if not w_clean:
        return "SKIP"

    # Números por extenso
    numeros_pt = {
        "um", "uma", "dois", "duas", "tres", "quatro", "cinco", "seis",
        "sete", "oito", "nove", "dez", "onze", "doze", "treze", "quatorze",
        "quinze", "dezesseis", "dezessete", "dezoito", "dezenove", "vinte",
        "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta",
        "noventa", "cem", "mil", "milhao", "milhoes", "bilhao", "bilhoes",
    }
    if remove_acentos(w_clean.lower()) in numeros_pt:
        return "NUM"

    # É dígito?
    if w_clean.isdigit():
        return "NUM"

    # Sigla do pronuncia.json?
    w_upper = w_clean.upper()
    if w_upper in siglas_set or w_clean in siglas_set:
        return "SIGLA"

    # Toda maiúscula e curta (2-5 chars) → provável sigla
    if w_clean.isupper() and 2 <= len(w_clean) <= 5:
        return "SIGLA"

    # Verificar dicionário PT-BR
    if dict_pt.check(w_clean) or dict_pt.check(w_clean.lower()):
        return "PT"

    # Verificar sem acentos (Whisper às vezes não acentua)
    w_sem_acento = remove_acentos(w_clean)
    if dict_pt.check(w_sem_acento) or dict_pt.check(w_sem_acento.lower()):
        return "PT"

    # Não está no dicionário PT → provavelmente EN
    return "EN"


def normalizar_texto(text):
    """Normaliza para comparação: lowercase, sem acentos, sem pontuação."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def normalizar_siglas(text, pronuncia):
    """Reverte hints fonéticos do pronuncia.json para comparar com Whisper."""
    for original, fonetica in pronuncia.items():
        # "I.A." → "ia", "D.J." → "dj"
        text = text.replace(fonetica.lower(), original.lower())
        text = text.replace(remove_acentos(fonetica.lower()), original.lower())
    return text


def comparar_palavras(texto_original, transcricao, pronuncia, siglas_set):
    """Compara palavra a palavra, classificando cada uma como PT/EN/SIGLA/NUM."""
    # Normalizar
    orig_norm = normalizar_texto(texto_original)
    orig_norm = normalizar_siglas(orig_norm, pronuncia)
    trans_norm = normalizar_texto(transcricao)
    trans_norm = normalizar_siglas(trans_norm, pronuncia)

    palavras_orig = orig_norm.split()
    palavras_trans = trans_norm.split()

    # Classificar palavras do original
    classificacoes = []
    for w in palavras_orig:
        cls = classificar_palavra(w, siglas_set)
        classificacoes.append((w, cls))

    # Usar jiwer para alinhamento
    from jiwer import process_words
    pw = process_words(orig_norm, trans_norm)
    global_wer = pw.wer

    erros_pt = []
    erros_en = []
    erros_sigla = []
    erros_num = []

    for chunk in pw.alignments[0]:
        if chunk.type == "equal":
            continue

        ref_words = palavras_orig[chunk.ref_start_idx:chunk.ref_end_idx]
        hyp_words = palavras_trans[chunk.hyp_start_idx:chunk.hyp_end_idx]

        # Classificar pelo tipo das palavras no original
        classes_chunk = set()
        for w in ref_words:
            cls = classificar_palavra(w, siglas_set)
            classes_chunk.add(cls)

        # Se não há palavras ref (insert), classificar pela hipótese
        if not ref_words:
            for w in hyp_words:
                cls = classificar_palavra(w, siglas_set)
                classes_chunk.add(cls)

        erro = {
            "tipo": chunk.type,
            "original": " ".join(ref_words),
            "whisper": " ".join(hyp_words),
            "classes": list(classes_chunk),
        }

        # Ignorar mismatches NUM (Whisper converte "vinte e duas" → "22")
        if classes_chunk == {"NUM"} or (classes_chunk <= {"NUM", "PT"} and any(w.isdigit() for w in hyp_words)):
            erros_num.append(erro)
            continue

        if "SIGLA" in classes_chunk:
            erros_sigla.append(erro)
        elif classes_chunk <= {"EN", "SKIP"}:
            erros_en.append(erro)
        else:
            erros_pt.append(erro)

    return {
        "global_wer": global_wer,
        "erros_pt": erros_pt,
        "erros_en": erros_en,
        "erros_sigla": erros_sigla,
        "erros_num": erros_num,
        "classificacoes": classificacoes,
    }


def main():
    if len(sys.argv) < 2:
        print("Uso: python scripts/validar_tts_v2.py <guiao.json> [--max-seg N]")
        sys.exit(1)

    guiao_path = Path(sys.argv[1])
    if not guiao_path.is_absolute():
        guiao_path = PROJECT_DIR / guiao_path

    max_seg = None
    if "--max-seg" in sys.argv:
        idx = sys.argv.index("--max-seg")
        max_seg = int(sys.argv[idx + 1])

    episode_dir = guiao_path.parent
    segments_dir = episode_dir / "segments"

    with open(guiao_path) as f:
        guiao = json.load(f)

    pronuncia = load_pronuncia()
    siglas_set = set(pronuncia.keys())

    segments = guiao["segments"]
    if max_seg:
        segments = segments[:max_seg]

    tts_segments = []
    for i, seg in enumerate(segments):
        text = seg.get("text", "").strip()
        if text:
            wav_path = segments_dir / f"seg_{i:03d}.wav"
            if wav_path.exists():
                tts_segments.append((i, seg, wav_path))

    if not tts_segments:
        print("Nenhum segmento TTS com áudio encontrado.")
        sys.exit(0)

    print(f"Segmentos TTS: {len(tts_segments)}")
    print(f"Dicionário fonético: {len(pronuncia)} regras")
    print(f"Thresholds — PT: {WER_THRESHOLD_PT}, EN: {WER_THRESHOLD_EN}, Global: {WER_THRESHOLD_GLOBAL}")
    print("=" * 70)

    print("Carregando Whisper medium...")
    import whisper
    whisper_model = whisper.load_model("medium", device="cuda")
    print("Whisper carregado!")

    # Construir initial_prompt com vocabulário do episódio
    # Whisper usa o prompt para contextualizar — nomes, termos técnicos, etc.
    personagens = "Byte, Pixel, Pasqualino, Estagiário, Claude"
    termos_fixos = "Daily Patch, DJ, lo-fi, deploy, open source, hackear, TI"

    # Extrair palavras-chave do guião para contexto
    all_text = " ".join(s.get("text", "") for s in guiao["segments"] if s.get("text", "").strip())
    titulo = guiao.get("title", "")

    initial_prompt = (
        f"Transcrição do podcast Daily Patch em português do Brasil. "
        f"Personagens: {personagens}. "
        f"Título: {titulo}. "
        f"Termos: {termos_fixos}. "
        f"Trecho anterior: {all_text[:300]}"
    )
    # Whisper aceita até ~224 tokens (~890 chars) no prompt
    initial_prompt = initial_prompt[:880]
    print(f"Initial prompt: {len(initial_prompt)} chars")
    print("=" * 70)

    resultados = []

    for idx, (seg_num, seg, wav_path) in enumerate(tts_segments):
        speaker = seg["speaker"]
        texto_original = seg["text"].strip()

        result = whisper_model.transcribe(
            str(wav_path),
            language="pt",
            task="transcribe",
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,  # cada segmento é independente
        )
        transcricao = result["text"].strip()

        analise = comparar_palavras(texto_original, transcricao, pronuncia, siglas_set)

        tem_erro_pt = len(analise["erros_pt"]) > 0
        tem_erro_sigla = len(analise["erros_sigla"]) > 0
        status = "ERRO_PT" if tem_erro_pt else ("ERRO_SIGLA" if tem_erro_sigla else "OK")

        print(f"\n[{seg_num:03d}] {speaker} — WER global: {analise['global_wer']:.0%} → [{status}]")
        print(f"  Original: {texto_original[:90]}")
        print(f"  Whisper:  {transcricao[:90]}")

        if analise["erros_pt"]:
            print(f"  🔴 Erros PT (pronúncia errada):")
            for e in analise["erros_pt"]:
                print(f"     {e['tipo']}: \"{e['original']}\" → \"{e['whisper']}\"")

        if analise["erros_sigla"]:
            print(f"  🟡 Erros SIGLA:")
            for e in analise["erros_sigla"]:
                print(f"     {e['tipo']}: \"{e['original']}\" → \"{e['whisper']}\"")

        if analise["erros_en"]:
            print(f"  🔵 Diffs EN (ignorados):")
            for e in analise["erros_en"]:
                print(f"     {e['tipo']}: \"{e['original']}\" → \"{e['whisper']}\"")

        if analise["erros_num"]:
            print(f"  ⚪ Diffs NUM (ignorados):")
            for e in analise["erros_num"]:
                print(f"     {e['tipo']}: \"{e['original']}\" → \"{e['whisper']}\"")

        resultados.append({
            "segmento": seg_num,
            "speaker": speaker,
            "status": status,
            "wer_global": round(analise["global_wer"], 4),
            "erros_pt": analise["erros_pt"],
            "erros_en": analise["erros_en"],
            "erros_sigla": analise["erros_sigla"],
            "erros_num": analise["erros_num"],
            "texto_original": texto_original,
            "transcricao": transcricao,
        })

    # Resumo
    print("\n" + "=" * 70)
    print("RESUMO")
    print("=" * 70)

    total = len(resultados)
    ok = sum(1 for r in resultados if r["status"] == "OK")
    erro_pt = sum(1 for r in resultados if r["status"] == "ERRO_PT")
    erro_sigla = sum(1 for r in resultados if r["status"] == "ERRO_SIGLA")

    print(f"Total: {total} segmentos")
    print(f"  ✅ OK: {ok}")
    print(f"  🔴 Erros PT: {erro_pt}")
    print(f"  🟡 Erros SIGLA: {erro_sigla}")

    if erro_pt > 0:
        print(f"\nPalavras PT com problema (precisam correção):")
        for r in resultados:
            for e in r["erros_pt"]:
                print(f"  [{r['segmento']:03d}] {e['tipo']}: \"{e['original']}\" → \"{e['whisper']}\"")

    # Salvar log
    log_path = episode_dir / "validacao_tts_v2.json"
    with open(log_path, "w") as f:
        json.dump({"resultados": resultados}, f, indent=2, ensure_ascii=False)
    print(f"\nLog: {log_path}")


if __name__ == "__main__":
    main()
