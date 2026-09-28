# Monitoramento de colmeias de baixo custo

Protótipo da disciplina IBM3118, Sistemas Embarcados e IoT (Ibmec, 2026), do Grupo 4:
Igor Costa, Jorge Alves, Ian Dias e Davi Ito.

O objetivo é uma estação barata, presa à colmeia, que registra a atividade na entrada
e a temperatura sem abrir a caixa e sem depender de rede. Uma câmera fotografa a
entrada em janelas curtas, um sensor mede a temperatura dentro da colmeia e outro
mede temperatura e umidade do lado de fora. Tudo vai para um cartão microSD, que é
recolhido uma vez por semana. No computador, um detector conta as abelhas visíveis
em cada janela, e cada contagem fica ao lado da temperatura do mesmo horário.

A estação conta abelhas visíveis. Ela não conta entradas e saídas, não segue uma
abelha de uma janela para outra (a câmera fica desligada entre as janelas) e não
detecta pólen, *Varroa*, rainha ou enxameação.

**O grupo não tem acesso a uma colmeia.** Com a aprovação do professor, o detector é
avaliado em vídeos públicos de colmeias reais, com as abelhas marcadas à mão, e a
instalação em campo fica para trabalho futuro. O experimento central é filmar esses
vídeos com a câmera da estação e medir quanto a câmera barata atrapalha a contagem.

## Estado atual

| Parte | Situação |
|---|---|
| Temperatura e umidade com horário (bancada) | Funcionando no Arduino Uno: DHT11 e DS1302 geram o CSV na serial |
| Câmera OV2640 e DS18B20 na ESP32 | Sketch de teste pronto e compilando; ainda não rodou na placa |
| Detector de abelhas | Funcionando no computador, no clipe de amostra público |
| Abelhas visíveis por janela | Funcionando; o valor quase não muda entre 25, 10 e 5 quadros por segundo |
| Renovação (abelhas que aparecem e somem) | Experimental; os números ainda não fazem sentido, ver "Resultados" |
| Gravação no cartão, DS3231 e AHT20 | Dependem de compra, feita depois da AP1 (`lista-de-compras.md`) |
| Comparação com o gabarito | Pendente; depende da base completa (7,8 GB) |

## Hardware

### Estação

| Componente | Função |
|---|---|
| ESP32-WROVER-DEV v1.6 | Placa principal; tem PSRAM, necessária para a câmera em 1280 × 720 |
| Câmera OV2640 | Entrada da colmeia, 1280 × 720, JPEG |
| DS18B20 (TO-92), selado | Temperatura dentro da colmeia |
| AHT20 | Temperatura e umidade do lado de fora, na sombra |
| DS3231 com CR2032 | Data e hora sem rede |
| Leitor de microSD sem conversor de nível e cartão de 32 GB | Imagens e CSV |
| Power bank ou carregador de celular | Alimentação do protótipo |

### Ligações na ESP32-WROVER-DEV

A câmera, a PSRAM e a flash ocupam quase todos os pinos. Sobram 2, 12, 13, 14, 15,
32 e 33.

| Função | Pinos |
|---|---|
| Cartão microSD, modo 1 bit: CLK, CMD, D0 | 14, 15, 2 |
| I2C: DS3231 e AHT20 | 32, 33 |
| DS18B20, 1-Wire | 13, com 4,7 kΩ para o 3,3 V |
| Livre, só para algo que fique em nível baixo no boot | 12 |

Com a face plana do DS18B20 virada para você e os terminais para baixo, a ordem é
GND, dados e 3,3 V.

### Bancada no Arduino Uno

| De | Para |
|---|---|
| DHT11 VCC / dados / GND | 5 V / pino 2 / GND, com 10 kΩ entre VCC e dados |
| DS1302 VCC / GND | 5 V / GND |
| DS1302 CLK / DAT / RST | pinos 5 / 4 / 3 |

Fotos da bancada em `assets/`.

## Software

Placas na Arduino IDE: "ESP32 Wrover Module", com PSRAM em "Enabled", e "Arduino Uno".
Bibliotecas: OneWire e DallasTemperature (ESP32); DHT sensor library, da Adafruit, e
Rtc by Makuna (Uno).

No computador: Python 3 com `ultralytics`, `opencv-python`, `numpy`, `scipy` e
`matplotlib` (lista em `analysis/requirements.txt`).

| Firmware (`firmware/`) | Para que serve |
|---|---|
| `sensor_dht11` | Primeiro teste do DHT11 no Uno |
| `sensor_dht11_rtc` | DHT11 e DS1302 no Uno, gerando o CSV com data e hora |
| `estacao_teste` | Câmera e DS18B20 na ESP32: a placa cria a rede `colmeia-g4` e serve as fotos e a temperatura |

| Análise (`analysis/`) | Para que serve |
|---|---|
| `janelas.py` | Roda o detector num vídeo ou numa pasta de fotos e resume cada janela |
| `capturar_esp32.py` | Baixa uma janela de fotos da ESP32 pelo Wi-Fi da placa |
| `figura_arquitetura.py` | Diagrama do método usado no artigo |

## Modelo

**Detector.** YOLO11n do projeto [Beehaviour](https://github.com/jordicalsinabaldoma/beehavior-upc)
(UPC, 2026), com uma classe, "bee", entrada de 640 pixels e confiança mínima de 0,40.
Os autores o treinaram com 1.756 quadros da base de Sledevič e Matuzevičius e
deixaram três colmeias fora do treino. Nessas três, relatam precisão de 0,81 a 0,90 e
recall de 0,80 a 0,91 por quadro.

**Base de dados.** Sledevič e Matuzevičius, *Labeled dataset for bee detection and
direction estimation on entrance to beehive*, Data in Brief, v. 52, 2024,
[doi:10.1016/j.dib.2024.110060](https://doi.org/10.1016/j.dib.2024.110060). São 7.200
quadros de 8 colmeias na Lituânia, filmados com celular a 30 cm da tábua de pouso, em
1920 × 1080 e 50 quadros por segundo, com as abelhas marcadas à mão.

**O que fazemos com ele.** Do Beehaviour usamos só a detecção. O rastreio e a
contagem de entradas e saídas deles ficam de fora: eles mesmos relatam que essa
contagem erra de 30% a 75% para menos quando há muitas abelhas na tábua. No lugar,
`janelas.py` reduz o vídeo para a taxa de quadros da estação e calcula, para cada
janela:

- **abelhas visíveis**: mediana, mínimo e máximo do número de abelhas por quadro;
- **renovação** (experimental): quantas abelhas aparecem e somem da imagem, ligando
  as detecções de quadros vizinhos pela distância entre os centros. Uma abelha só
  conta como aparecida depois de vista em dois quadros, e como sumida depois de dois
  quadros ausente.

## Resultados até agora

Clipe de amostra do Beehaviour: 15 s da colmeia `20230711b`, que ficou fora do treino,
em 1280 × 720, a mesma resolução da estação. Janelas de 5 s. Saída completa em
`results/janelas_amostra.txt`.

| Janela | Visíveis a 25 quadros/s | a 10 quadros/s | a 5 quadros/s |
|---|---|---|---|
| 0 a 5 s | 33 | 33 | 34 |
| 5 a 10 s | 32 | 32 | 31 |
| 10 a 15 s | 24 | 24 | 25 |

A contagem de visíveis quase não muda com a taxa de quadros, o que sugere que 10
quadros por segundo bastam para ela. Ainda não foi comparada com o gabarito.

A renovação não funciona ainda: deu de 1.530 a 5.088 por minuto, com cerca de 30
abelhas na imagem, e triplica quando a taxa de quadros sobe. Quando o detector perde
uma abelha num quadro e a encontra no seguinte, o script registra um sumiço e um
aparecimento que não aconteceram. A correção depende das trajetórias marcadas à mão
da base completa.

No quadro de `results/deteccao_amostra.jpg`, o detector acha as abelhas espalhadas
pela tábua e pela grama, mas perde a maior parte das que estão amontoadas na fenda,
deixa passar uma abelha sobre a madeira clara e marca uma mesma abelha com três
caixas sobrepostas.

## Como usar

### Análise no computador

Dentro de `beehive-monitoring/`, uma vez só:

```
python3 -m venv .venv
.venv/bin/pip install -r analysis/requirements.txt
mkdir -p analysis/models
curl -L -o analysis/models/bee11n.pt \
  https://github.com/jordicalsinabaldoma/beehavior-upc/raw/master/models/bee11n.pt
```

Os pesos (21 MB) não vão para o repositório. Depois:

```
.venv/bin/python analysis/janelas.py video.mp4 --fps 10 --janela 5 --csv saida.csv
```

O clipe de amostra fica em `media/entrada_cenital_muestra.mp4` no repositório do
Beehaviour. A base completa está no [Mendeley](https://doi.org/10.17632/8gb9r2yhfc.6).

### Teste da câmera e do DS18B20

1. Ligar o DS18B20 no GPIO 13, com o resistor de 4,7 kΩ para o 3,3 V.
2. Gravar `firmware/estacao_teste` na ESP32 e abrir o monitor serial a 115200. A
   temperatura aparece a cada 3 s.
3. Conectar o computador à rede `colmeia-g4`, senha `<ap-password>`, e abrir
   `http://192.168.4.1`.
4. Passar um vídeo da base num celular ou monitor, com a câmera apontada para a tela.
5. `.venv/bin/python analysis/capturar_esp32.py --segundos 5` baixa uma janela de fotos
   para `capturas/`, e `janelas.py` roda o detector sobre a pasta.

## Customizações

O que foi desenvolvido além do uso padrão das bibliotecas, dos exemplos e do modelo
pronto:

- **Distribuição de pinos da ESP32-WROVER-DEV.** A câmera deixa sete pinos livres, e
  o GPIO 12 impede o boot se tiver pull-up. O DS1302 do laboratório gastaria três
  pinos, e um segundo DHT11 não teria onde ligar, porque o protocolo dele não tem
  endereço. A solução foi pôr o DS3231 e o AHT20 no mesmo I2C e o DS18B20 no 1-Wire,
  deixando um pino de sobra.
- **Sensor interno selado.** O DS18B20 mede só temperatura e pode ser coberto por
  inteiro, sem terminal exposto ao própolis. Um sensor de umidade precisa de contato
  com o ar. A umidade passou a ser medida só do lado de fora.
- **Mapeamento da câmera.** Os exemplos da Espressif usam por padrão a placa
  AI-Thinker. A WROVER-DEV usa o mapeamento do WROVER-KIT, e com o errado a câmera não
  inicia.
- **Firmware de teste sem rede externa.** A placa cria a própria rede Wi-Fi, porque a
  rede da faculdade exige login pelo navegador. A foto é tirada na hora do pedido, com
  o quadro mais novo. A conversão do DS18B20, de 750 ms, roda sem travar o servidor.
- **Relógio DS1302 na bancada.** O módulo do laboratório não é I2C; usa a biblioteca
  Rtc by Makuna com `ThreeWire`, e o sketch acerta a hora pela data de compilação.
- **Contagem por janela no lugar do rastreio.** Do Beehaviour usamos só o detector. A
  contagem de entradas e saídas deles foi trocada pela mediana de abelhas visíveis na
  janela, que não depende de seguir cada abelha.
- **Taxa de quadros da estação.** O script reduz os vídeos da base, gravados a 50
  quadros por segundo, para a taxa da estação, para avaliar o detector nas condições
  em que ela vai capturar.
- **Fotos da ESP32 como entrada.** O script lê uma pasta de fotos com o tempo em
  milissegundos no nome, no formato que `capturar_esp32.py` grava.
- **Renovação experimental.** Ligação entre quadros vizinhos com confirmação em dois
  quadros e tolerância de um quadro ausente. Ainda não funciona, como descrito acima.

## Limitações

- Não há colmeia. Os resultados vêm de vídeos públicos filmados com celular, e a
  câmera da estação ainda não foi testada.
- A contagem ainda não foi comparada com o gabarito.
- O detector erra em aglomerações na fenda e pode marcar a mesma abelha mais de uma
  vez.
- A renovação ainda não funciona.
- Sem cartão, DS3231 e AHT20, a estação ainda não grava nada sozinha.
- A alimentação é por power bank; o painel solar e a bateria ficaram para uma versão
  futura.

## Créditos e licenças

- Detector: pesos `bee11n.pt` do projeto Beehaviour (J. Calsina, L. Santamaria, G.
  Biosca e V. Abelló, UPC), sob AGPL-3.0.
- Imagens e marcações: base de Sledevič e Matuzevičius, sob CC BY 4.0. O quadro de
  `results/deteccao_amostra.jpg` vem dessa base.
- Método de contagem por imagem com registro de horário também usado por M. Rovai
  no tutorial [Counting objects with YOLO](https://mjrovai.github.io/EdgeML_Made_Ease_ebook/raspi/counting_objects_yolo/counting_objects_yolo.html).

## Organização da pasta

| Pasta | Conteúdo |
|---|---|
| `firmware/` | Sketches do Uno e o teste da ESP32 |
| `analysis/` | Contagem por janela, captura da ESP32 e figura do artigo |
| `results/` | Saída do detector no clipe de amostra |
| `assets/` | Fotos da bancada e o diagrama do método |

## Documentos

| Arquivo | Conteúdo |
|---|---|
| `beehive-monitoring.tex` | Artigo, em inglês, no modelo do SBrT |
| `beehive-monitoring-pt.md` | Tradução de apoio do artigo |
| `refs.bib` | Referências do artigo e a entrada do repositório |
| `decisoes-do-projeto.md` | Decisões tomadas, com o porquê, e o que está em aberto |
| `plano-do-prototipo.md` | Etapas da montagem e materiais |
| `lista-de-compras.md` | O que falta comprar, com preços |
| `requirements.md`, `specifications.md` | Requisitos e especificação iniciais |
| `research-notes.md`, `reference-contributions.md` | Notas sobre as referências |
| `guia-geral.md` | Checklist das atividades da disciplina |
