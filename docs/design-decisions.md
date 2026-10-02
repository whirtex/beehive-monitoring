# Design decisions

The main decisions of the beehive station, grouped by topic. Open items are at
the end. While an item is open, the article should not claim anything about it.

## Scope of the first version

- One camera watches the hive entrance.
- Two environmental sensors: one for temperature inside the hive and one for
  temperature and humidity outside.
- An acoustic sensor may come in a later stage. Vibration and weight sensors are
  out of the first version.
- The AI only detects and counts the bees visible in the images. The system
  estimates the activity of the bees at the entrance.
- The system must not claim that it identifies individual entries and exits,
  disease, a missing queen or swarming.

## Environmental sensors

- **Inside the hive, a DS18B20 in a TO-92 package; outside, near the entrance and
  in the shade, an AHT20.** Decision of 27 September 2026. The DS18B20 replaces
  the AHT20 at the interior point for three reasons:
  - it is the smallest sensor available and fits inside the hive without
    bothering the bees;
  - it measures only temperature, so it can be sealed completely. Bees cover any
    foreign object in the hive with propolis, and a humidity sensor needs contact
    with the air to work;
  - it uses the 1-Wire protocol, with a single pin, and the group already has
    five units, bought for the predictive maintenance project and unused since
    temperature left that project.
- The swap has a cost: the system no longer measures the humidity inside. Humidity
  is measured only outside.
- The interior sensor is sealed with heat-shrink tubing or epoxy, with no exposed
  leads, and it is powered and read through a three-wire cable that goes to the
  electronics mounted outside.
- The lab DHT11 does not go into the station. It stays on the Arduino Uno, on the
  bench.
- The sensors read every 3 minutes. Because the two sensors differ, they sit side
  by side for a few hours before installation, and the mean temperature
  difference between them is subtracted in the analysis.

## Camera

- Mounted outside the hive, above and slightly in front of the entrance, pointed
  at where the bees come in and go out, on a firm mount with rain protection. It
  must not block the entrance or interfere with the ventilation.
- Initial resolution of 1280 × 720. It works on a preset schedule, from 07:00 to
  17:00.
- Two configurations will be tested, each for 3 days: 5 seconds of capture at 10
  frames per second every 5 minutes, and 10 seconds at 10 frames per second every
  5 minutes. They will be compared on the quality of the count, the space used on
  the card and the energy use.
- Images are saved as a sequence of JPEG files, not as H.264 or H.265 video. The
  original images are kept during the tests, so the analysis can be redone.

## Board and storage

- The board is an **ESP32-WROVER-DEV v1.6**, with an ESP32-WROVER-E module, and a
  separate **OV2640** camera on the flat connector. It has micro-USB and an
  embedded CH340C converter, so it uploads firmware straight over the cable. The
  module has the PSRAM that the camera needs at 1280 × 720.
- The board **has no microSD slot**, so a separate reader module is wired to the
  header pins. The card is a 32 GB microSD from a reliable brand.
- The central board receives the data of both sensors and writes the images and
  the measurements to the same card. The data is collected about once a week.
- Images go into folders by date, with the time in the file name. Measurements go
  into a CSV with date, time, interior temperature, exterior temperature,
  exterior humidity and, if possible, the battery level.
- **The station clock is a DS3231** on the same I2C bus as the exterior sensor,
  so the date and time hold even without Wi-Fi. The lab DS1302 takes three pins,
  and the board has no free pins for it and for both sensors. The DS1302 stays on
  the Arduino Uno, on the bench.

## Communication and analysis

- The system does not depend on Wi-Fi. Images and environmental data stay on the
  card, which is copied once a week and taken to a computer for analysis. LoRa is
  not needed in the first version.
- The images are analyzed afterwards, away from the hive. An existing AI model is
  tested first; if it is not good enough on the project images, a model is
  created or tuned with the group's own images.
- The AI counts the bees visible in each image or observation window. It does not
  try to follow the same bee between windows, because the camera is off between
  captures.

## Model and validation without a hive

Decisions of 27 September 2026. The group has no access to a hive, and the
professor accepted validation with public videos.

- **Bees and ground truth.** The videos and labels of the dataset of Sledevič and
  Matuzevičius (Data in Brief, 2024, CC BY 4.0): 7,200 frames of 8 real hives,
  filmed from above the landing board, at 30 cm, with a phone, at 1920 × 1080 and
  50 frames per second.
- **Detector.** The YOLO11n of the Beehaviour project (UPC, 2026, AGPL-3.0),
  trained on that dataset with the three test hives left out of the training. It
  is credited in a footnote of the article and in the README, because it is not an
  academic publication.
- **Measure 1: visible bees per window.** The median of the number of bees
  detected in the frames of the window.
- **Measure 2: turnover per minute.** How many bees appear in and disappear from
  the field of view inside the window, linking the detections of neighboring
  frames. It is not a count of entries and exits of the hive. It helps tell bees
  resting on the board from bees passing by.
- **Central experiment.** Play the videos on a monitor, film them with the OV2640
  and compare the count on the original frames and on the filmed ones, against the
  same ground truth.
- **Installation on a real hive is future work.**
- **References.** The article keeps ten academic references. Sledevič and
  Matuzevičius (2024) and Sledevič et al. (PLOS ONE, 2025) come in. Uthoff et al.,
  which only justified leaving out audio, and Tashakkori et al., whose role as a
  network counterpoint Henry et al. already fills, go out.

## Power

- The prototype runs on a power bank or a phone charger, with no solar panel. The
  panel of about 3 W, the 18650 battery with BMS protection, the charge controller
  and the boost converter are left for a future version of the station. The
  article must not claim that the prototype runs autonomously.
- The consumption will be measured with the lab multimeter, in series with the
  supply, in each state of the board.
- The electronics sit in a sealed plastic jar, with holes for the lens and for
  the cable of the interior sensor.

## Open decisions

### Image analysis

- Download the full dataset (7.8 GB) and measure the count error against the
  ground truth, only on the three hives left out of the detector training.
- Tune the turnover measure against the hand-labelled trajectories. The first
  untuned test, on the 15 s Beehaviour clip, gave numbers that make no sense:
  about 200 bees appearing in 5 s with some 30 in the image, and values that
  change with the frame rate. Detection misses from one frame to the next count
  as appearances.
- Choose the metrics to report. Count error and R² are the direct candidates,
  following Tu et al. MOTA and MOTP do not apply, because they measure tracking.
- Define the final criterion to consider the count adequate.

### Hardware and power

- Buy the remaining parts, after the first assessment (AP1).
- Confirm that the 32 GB card works with the board and in which format it has to
  be.
- Confirm that the board records 1280 × 720 at 10 frames per second to the card in
  1-bit mode.
- Measure the real consumption of the board, the camera, the card and the sensors
  in the two capture configurations.
- Measure the temperature difference between the DS18B20 and the AHT20 with the two
  side by side.

### Installation on the hive

- Define the sealing of the DS18B20, the installation point inside the hive, the
  cable passage and the sealing.
- Confirm the hive, the place and the conditions in which the tests will run.

### Wi-Fi variant

- Decide whether to develop a second version of the station, with Wi-Fi
  transmission, for apiaries where the hive is near a network. The offline version
  stays the main one.
