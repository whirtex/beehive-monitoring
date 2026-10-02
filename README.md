# Low-cost beehive monitoring

Prototype for the course IBM3118, Embedded Systems and IoT (Ibmec, 2026), by
Group 4: Igor Costa, Jorge Alves, Ian Dias and Davi Ito.

This project was developed in a repository shared with another project of the
course, and it was moved here with its commit history filtered. The commits
before the English translation have the files and comments in Portuguese. The
translation is in the commits that follow.

The goal is a cheap station, attached to the hive, that records the activity at
the entrance and the temperature without opening the box and without relying on
a network. A camera photographs the entrance in short windows, one sensor
measures the temperature inside the hive and another measures temperature and
humidity outside. Everything goes to a microSD card, collected once a week. On a
computer, a detector counts the visible bees in each window, and each count sits
next to the temperature of the same time.

The station counts visible bees. It does not count entries and exits, it does not
follow a bee from one window to the next (the camera is off between windows) and
it does not detect pollen, *Varroa*, a queen or swarming.

**The group has no access to a hive.** With the professor's approval, the
detector is evaluated on public videos of real hives, with the bees labelled by
hand, and the field installation is left as future work. The central experiment
is to film those videos with the station's camera and measure how much the cheap
camera hurts the count.

## Current status

| Part | Status |
|---|---|
| Temperature and humidity with time (bench) | Working on the Arduino Uno: a DHT11 and a DS1302 produce the CSV on the serial port |
| OV2640 camera and DS18B20 on the ESP32 | Test sketch ready and compiling; it has not run on the board yet |
| Bee detector | Working on the computer, on the public sample clip |
| Visible bees per window | Working; the value barely changes between 25, 10 and 5 frames per second |
| Turnover (bees that appear and disappear) | Experimental; the numbers do not make sense yet, see "Results so far" |
| Recording to the card, DS3231 and AHT20 | Depend on a purchase, which comes after the first assessment (AP1) |
| Comparison with the ground truth | Pending; it depends on the full dataset (7.8 GB) |

## Hardware

### Station

| Component | Role |
|---|---|
| ESP32-WROVER-DEV v1.6 | Main board; it has PSRAM, which the camera needs at 1280 × 720 |
| OV2640 camera | Hive entrance, 1280 × 720, JPEG |
| DS18B20 (TO-92), sealed | Temperature inside the hive |
| AHT20 | Temperature and humidity outside, in the shade |
| DS3231 with CR2032 | Date and time without a network |
| microSD reader without a level converter, and a 32 GB card | Images and CSV |
| Power bank or phone charger | Power for the prototype |

### Wiring on the ESP32-WROVER-DEV

The camera, the PSRAM and the flash take almost all of the pins. Pins 2, 12, 13,
14, 15, 32 and 33 are left.

| Function | Pins |
|---|---|
| microSD card, 1-bit mode: CLK, CMD, D0 | 14, 15, 2 |
| I2C: DS3231 and AHT20 | 32, 33 |
| DS18B20, 1-Wire | 13, with 4.7 kΩ to 3.3 V |
| Free, only for something that stays low at boot | 12 |

With the flat face of the DS18B20 toward you and the leads pointing down, the
order is GND, data and 3.3 V.

### Bench on the Arduino Uno

| From | To |
|---|---|
| DHT11 VCC / data / GND | 5 V / pin 2 / GND, with 10 kΩ between VCC and data |
| DS1302 VCC / GND | 5 V / GND |
| DS1302 CLK / DAT / RST | pins 5 / 4 / 3 |

## Software

Boards in the Arduino IDE: "ESP32 Wrover Module", with PSRAM on "Enabled", and
"Arduino Uno". Libraries: OneWire and DallasTemperature (ESP32); DHT sensor
library, by Adafruit, and Rtc by Makuna (Uno). The `station_test` sketch needs a
local `credentials.h` file with the password of the network that the board
creates; copy
[`credentials.h.example`](firmware/station_test/credentials.h.example), choose
the password and keep `credentials.h` out of Git.

On the computer: Python 3 with `ultralytics`, `opencv-python`, `numpy`, `scipy`
and `matplotlib` (list in `analysis/requirements.txt`).

| Firmware (`firmware/`) | What it does |
|---|---|
| `dht11_rtc_sensor` | DHT11 and DS1302 on the Uno, producing the CSV with date and time |
| `station_test` | Camera and DS18B20 on the ESP32: the board creates the network `beehive-g4` and serves the photos and the temperature |

The `station_test` sketch is the bench test version of the station. It has no
card, no DS3231 and no AHT20, and it creates its own Wi-Fi network, unlike the
station described in the article, which records to the card without a network.

| Analysis (`analysis/`) | What it does |
|---|---|
| `window_counts.py` | Runs the detector on a video or a folder of photos and summarizes each window |
| `architecture_figure.py` | Method diagram used in the article |

## Model

**Detector.** YOLO11n from the
[Beehaviour](https://github.com/jordicalsinabaldoma/beehavior-upc) project (UPC,
2026), with one class, "bee", a 640-pixel input and a minimum confidence of 0.40.
The authors trained it on 1,756 frames of the Sledevič and Matuzevičius dataset
and left three hives out of the training. On those three, they report a
precision of 0.81 to 0.90 and a recall of 0.80 to 0.91 per frame.

**Dataset.** Sledevič and Matuzevičius, *Labeled dataset for bee detection and
direction estimation on entrance to beehive*, Data in Brief, vol. 52, 2024,
[doi:10.1016/j.dib.2024.110060](https://doi.org/10.1016/j.dib.2024.110060). It has
7,200 frames of 8 hives in Lithuania, filmed with a phone 30 cm from the landing
board, at 1920 × 1080 and 50 frames per second, with the bees labelled by hand.

**What we do with it.** From Beehaviour we use only the detection. Their tracking
and entry and exit counting stay out: they themselves report that this counting
is off by 30% to 75% on the low side when there are many bees on the board.
Instead, `window_counts.py` reduces the video to the frame rate of the station
and computes, for each window:

- **visible bees**: median, minimum and maximum number of bees per frame;
- **turnover** (experimental): how many bees appear in and disappear from the
  image, linking the detections of neighboring frames by the distance between
  centers. A bee only counts as appeared after being seen in two frames, and as
  disappeared after being absent for two frames.

## Results so far

Beehaviour sample clip: 15 s of hive `20230711b`, which was left out of the
training, at 1280 × 720, the same resolution as the station. Windows of 5 s. Full
output in `results/sample_windows.txt`.

| Window | Visible at 25 frames/s | at 10 frames/s | at 5 frames/s |
|---|---|---|---|
| 0 to 5 s | 33 | 33 | 34 |
| 5 to 10 s | 32 | 32 | 31 |
| 10 to 15 s | 24 | 24 | 25 |

The count of visible bees barely changes with the frame rate, which suggests that
10 frames per second are enough for it. It has not been compared with the ground
truth yet.

The turnover does not work yet: it gave 1,530 to 5,088 per minute, with about 30
bees in the image, and it grows with the frame rate. When the detector loses a
bee in one frame and finds it in the next, the script records a disappearance and
an appearance that did not happen. The fix depends on the hand-labelled
trajectories of the full dataset.

In the frame of `results/sample_detections.jpg`, the detector finds the bees
spread over the board and the grass, but it misses most of those crowded at the
slot, misses one bee on the pale wood and marks one bee with three overlapping
boxes.

## How to use

### Analysis on the computer

In the repository root, once:

```
python3 -m venv .venv
.venv/bin/pip install -r analysis/requirements.txt
mkdir -p analysis/models
curl -L -o analysis/models/bee11n.pt \
  https://github.com/jordicalsinabaldoma/beehavior-upc/raw/master/models/bee11n.pt
```

The weights (21 MB) are not in the repository. Then:

```
.venv/bin/python analysis/window_counts.py video.mp4 --fps 10 --window 5 --csv output.csv
```

The sample clip is `media/entrada_cenital_muestra.mp4` in the Beehaviour
repository. The full dataset is on
[Mendeley](https://doi.org/10.17632/8gb9r2yhfc.6). To run the detector on photos
instead of a video, put the JPEG files in a folder with the milliseconds since
the start of the window as the file name (for example `0000.jpg`, `0100.jpg`) and
pass the folder instead of the video.

### Testing the camera and the DS18B20

1. Connect the DS18B20 to GPIO 13, with the 4.7 kΩ resistor to 3.3 V.
2. Create `credentials.h` from the example, upload `firmware/station_test` to the
   ESP32 and open the serial monitor at 115200. The temperature shows up every
   3 s.
3. Connect the computer to the network `beehive-g4`, with the password from
   `credentials.h`, and open `http://192.168.4.1`.
4. Play a video from the dataset on a phone or monitor, with the camera pointed
   at the screen.

## Customizations

What was developed beyond the standard use of the libraries, the examples and the
ready-made model:

- **Pin allocation of the ESP32-WROVER-DEV.** The camera leaves seven pins free,
  and GPIO 12 prevents boot if it has a pull-up. The lab DS1302 would use three
  pins, and a second DHT11 would have nowhere to connect, because its protocol
  has no address. The solution was to put the DS3231 and the AHT20 on the same
  I2C bus and the DS18B20 on 1-Wire, leaving one spare pin.
- **Sealed interior sensor.** The DS18B20 measures only temperature and can be
  covered entirely, with no terminal exposed to propolis. A humidity sensor needs
  contact with the air. Humidity is now measured only outside.
- **Camera pin map.** The Espressif examples default to the AI-Thinker board. The
  WROVER-DEV uses the WROVER-KIT map, and with the wrong one the camera does not
  start.
- **Test firmware without an external network.** The board creates its own Wi-Fi
  network, because the college network requires a browser login. The photo is
  taken at the time of the request, with the newest frame. The 750 ms DS18B20
  conversion runs without blocking the server.
- **DS1302 clock on the bench.** The lab module is not I2C; it uses the Rtc by
  Makuna library with `ThreeWire`, and the sketch sets the time from the compile
  date.
- **Counting per window instead of tracking.** From Beehaviour we use only the
  detector. Their entry and exit counting was replaced by the median of visible
  bees in the window, which does not depend on following each bee.
- **Station frame rate.** The script reduces the dataset videos, recorded at 50
  frames per second, to the rate of the station, to evaluate the detector under
  the conditions in which it will capture.
- **Photos as input.** The script reads a folder of photos with the time in
  milliseconds in the name.
- **Experimental turnover.** Linking between neighboring frames with confirmation
  in two frames and a tolerance of one absent frame. It does not work yet, as
  described above.

## Limitations

- There is no hive. The results come from public videos filmed with a phone, and
  the station's camera has not been tested yet.
- The count has not been compared with the ground truth.
- The detector fails on crowds at the slot and can mark the same bee more than
  once.
- The turnover does not work yet.
- Without the card, the DS3231 and the AHT20, the station does not record
  anything by itself yet.
- Power comes from a power bank; the solar panel and the battery were left for a
  future version.

## Credits and licenses

The code of this repository is under the MIT license (see [`LICENSE`](LICENSE)).
The parts below keep their own licenses.

- Detector: the `bee11n.pt` weights of the Beehaviour project (J. Calsina,
  L. Santamaria, G. Biosca and V. Abelló, UPC), under AGPL-3.0. The scripts also
  use Ultralytics, which is AGPL-3.0 too. The weights are not in the repository.
- Images and labels: the dataset of Sledevič and Matuzevičius, under CC BY 4.0.
  The frame in `results/sample_detections.jpg` and panel (b) of
  `assets/prototype-and-detections.jpg` come from this dataset.
- Counting method with image and time record, also used by M. Rovai in the
  tutorial [Counting objects with YOLO](https://mjrovai.github.io/EdgeML_Made_Ease_ebook/raspi/counting_objects_yolo/counting_objects_yolo.html).

## Repository layout

| Folder | Contents |
|---|---|
| `firmware/` | Uno sketch and the ESP32 test sketch |
| `analysis/` | Window counting and the figure of the article |
| `results/` | Detector output on the sample clip |
| `assets/` | The figures of the article |
| `paper/` | Article (`.tex`) and `refs.bib` |
| `docs/` | Design decisions |

## Documents

| File | Contents |
|---|---|
| `paper/beehive-monitoring.tex` | Article, in English, in the SBrT template |
| `paper/refs.bib` | References of the article and the repository entry |
| `docs/design-decisions.md` | Decisions taken, with the reason, and what is still open |

The `.tex` uses the paths of the Overleaf project (`assets/` in the same folder as
the file). To compile from the repository, copy that folder into `paper/` or
adjust the paths.
