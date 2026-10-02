"""Conta as abelhas visiveis em cada janela de observacao.

Entrada: um video da entrada da colmeia ou uma pasta de fotos JPEG baixadas da
ESP32 por capturar_esp32.py. O detector e o YOLO11n do projeto Beehaviour,
treinado na base de Sledevic e Matuzevicius (ver o README).

Para cada janela, o script informa a mediana, o minimo e o maximo de abelhas
por quadro. A renovacao (abelhas que aparecem e somem da imagem) e
experimental: ainda nao foi ajustada contra o gabarito e, no clipe de amostra,
conta as falhas de deteccao de um quadro para o outro como aparecimentos.

Uso (na pasta beehive-monitoring):
    .venv/bin/python analysis/window_counts.py video.mp4 --fps 10 --janela 5
    .venv/bin/python analysis/window_counts.py capturas/2026-09-28_1430 --janela 5
"""

import argparse
import csv
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from ultralytics import YOLO

PASTA = Path(__file__).resolve().parent
PESOS = PASTA / "models" / "bee11n.pt"


def quadros_do_video(caminho, fps_alvo):
    cap = cv2.VideoCapture(str(caminho))
    fps_orig = cap.get(cv2.CAP_PROP_FPS)
    passo = max(1, round(fps_orig / fps_alvo))
    i = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        if i % passo == 0:
            yield i / fps_orig, img
        i += 1


def quadros_da_pasta(caminho):
    # capturar_esp32.py grava cada foto com os milissegundos desde o inicio no nome
    for arq in sorted(caminho.glob("*.jpg")):
        yield int(arq.stem) / 1000, cv2.imread(str(arq))


def detectar(modelo, fonte, conf):
    quadros = []
    for t, img in fonte:
        r = modelo.predict(img, conf=conf, imgsz=640, verbose=False)[0]
        quadros.append((t, r.boxes.xyxy.cpu().numpy(), img if not quadros else None))
    return quadros


def centros(caixas):
    return np.column_stack(((caixas[:, 0] + caixas[:, 2]) / 2, (caixas[:, 1] + caixas[:, 3]) / 2))


def renovacao(quadros, raio, confirmar=2, tolerancia=1):
    """Liga as abelhas de quadros vizinhos pela distancia entre os centros.
    Uma abelha so conta como aparecida depois de vista em `confirmar` quadros,
    e como sumida depois de ausente por mais de `tolerancia` quadros."""
    trilhas = []  # [x, y, vezes_vista, quadros_ausente, confirmada]
    eventos = []
    for t, caixas, _ in quadros:
        pts = centros(caixas) if len(caixas) else np.zeros((0, 2))
        livres = set(range(len(pts)))
        if trilhas and len(pts):
            a = np.array([[tr[0], tr[1]] for tr in trilhas])
            d = np.linalg.norm(a[:, None] - pts[None], axis=2)
            for r, c in zip(*linear_sum_assignment(d)):
                if d[r, c] <= raio:
                    tr = trilhas[r]
                    tr[0], tr[1] = pts[c]
                    tr[2] += 1
                    tr[3] = -1
                    livres.discard(c)
                    if not tr[4] and tr[2] >= confirmar:
                        tr[4] = True
                        eventos.append((t, "aparece"))
        vivas = []
        for tr in trilhas:
            tr[3] += 1
            if tr[3] > tolerancia:
                if tr[4]:
                    eventos.append((t, "some"))
            else:
                vivas.append(tr)
        trilhas = vivas + [[*pts[c], 1, 0, False] for c in livres]
    return eventos


def resumir(quadros, eventos, janela):
    dur = quadros[-1][0] + (quadros[-1][0] - quadros[-2][0])
    linhas, ini = [], 0.0
    while ini + janela <= dur + 1e-6:
        fim = ini + janela
        n = [len(c) for t, c, _ in quadros if ini <= t < fim]
        ap = sum(1 for t, e in eventos if ini <= t < fim and e == "aparece")
        so = sum(1 for t, e in eventos if ini <= t < fim and e == "some")
        linhas.append({
            "inicio_s": round(ini, 1),
            "quadros": len(n),
            "visiveis_mediana": float(np.median(n)),
            "visiveis_min": min(n),
            "visiveis_max": max(n),
            "aparecem": ap,
            "somem": so,
            "renovacao_por_min": round((ap + so) / 2 * 60 / janela, 1),
        })
        ini = fim
    return linhas


def main():
    p = argparse.ArgumentParser()
    p.add_argument("entrada", type=Path, help="video ou pasta de fotos da ESP32")
    p.add_argument("--pesos", type=Path, default=PESOS)
    p.add_argument("--fps", type=float, default=10, help="so para video")
    p.add_argument("--janela", type=float, default=5, help="segundos")
    p.add_argument("--conf", type=float, default=0.40)
    p.add_argument("--csv", type=Path)
    p.add_argument("--figura", type=Path, help="primeiro quadro com as deteccoes")
    a = p.parse_args()

    fonte = quadros_da_pasta(a.entrada) if a.entrada.is_dir() else quadros_do_video(a.entrada, a.fps)
    quadros = detectar(YOLO(a.pesos), fonte, a.conf)
    fps = (len(quadros) - 1) / (quadros[-1][0] - quadros[0][0])
    tamanhos = np.concatenate([np.hypot(c[:, 2] - c[:, 0], c[:, 3] - c[:, 1]) for _, c, _ in quadros if len(c)])
    # a 10 quadros/s, uma abelha andando nao passa do proprio tamanho entre dois quadros
    raio = np.median(tamanhos) * (10 / fps)
    linhas = resumir(quadros, renovacao(quadros, raio), a.janela)

    print(f"{a.entrada}: {len(quadros)} quadros a {fps:.1f} por segundo")
    for l in linhas:
        print(l)
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=linhas[0].keys())
            w.writeheader()
            w.writerows(linhas)
    if a.figura:
        _, caixas, img = quadros[0]
        for x1, y1, x2, y2 in caixas.astype(int):
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 220, 255), 2)
        cv2.imwrite(str(a.figura), img)


if __name__ == "__main__":
    main()
