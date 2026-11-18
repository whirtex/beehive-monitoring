# Design decisions

Each decision holds until it is replaced here, with its reason.

## Scope

- The station measures the occupancy of the entrance (visible bees in each photo)
  and the temperature. It does not count entries and exits, does not follow a bee
  from one photo to the next and does not detect pollen, *Varroa*, the queen or
  swarming. Sound, vibration and weight are left out.
- **Occupancy, not traffic.** The visible bees also rise when they fan at the
  entrance in the heat: in the hand-labelled test videos, 22% and 12% of the bees
  are fanning. The count is read as occupancy of the landing board next to the
  temperature, not as foraging.
- **No entries and exits.** The professor suggested tracking each bee (MOT) to
  count entries and exits. With one photo every 10 s a bee crosses the entrance
  between photos, so photos cannot be linked. Tracking needs video, and filming
  all day draws more energy than the solar panel delivers.
- The group has no hive. The professor accepted the validation on public videos;
  the field installation is future work.

## Two modes

- **Mode 1, the main one and the only one built:** own power (solar panel and
  battery), everything on the microSD card, collected when the user wants.
- **Mode 2, not built:** with mains and a network at the site, the ESP32 sends
  each photo over Wi-Fi to a server running the same detector.

## Camera and schedule

- OV2640 camera on the ESP32-WROVER-DEV (the board has the PSRAM the camera
  needs), above and slightly in front of the entrance, blocking neither the
  entrance nor the ventilation.
- **The OV2640 works by day.** In a daylight test it showed detail of distant
  tiles and leaves and a 3 cm object sharp up close. In a dim room at night the
  photos come out dark, so the station photographs from 06:00 to 18:00.
- **800 x 600 (SVGA).** The detector reduces every image to 640 px; on the 3230
  labelled frames, 640 and 1280 px gave the same result (F1 0.823) and 800 px gave
  0.832. SVGA is the full-field mode of the OV2640, faster, with smaller photos.
- **Camera height:** about 25 cm above the landing board with the standard lens
  (about 66°), so a bee measures about 30 px at 800 px, as in the dataset.
- **One photo every 10 s, from 06:00 to 18:00.** It replaces the first schedule,
  10 s bursts at 10 frames per second every 5 min. On the hand-labelled recordings
  (`results/photo_schedule.txt`): the frame rate does not change the window
  median; against the median of each 5 min period of a 13 min recording, the 10 s
  burst missed by 3 bees and 30 photos, one every 10 s, by half a bee; on a 2 h
  YouTube video, the burst missed by 2 and the photos by half a bee. 5 s errs a
  little less than 10 s with twice the photos, 20 s already errs 1 and 60 s, 2; 10 s
  among these is a choice, not a result of the test.
- The count of each 5 min period is the median of its 30 photos. A period with
  fewer photos shows a failure of the station at that time.

## Sensors

- DS18B20 inside the hive, in the waterproof version with a stainless steel tip:
  it measures only temperature, so it can be fully sealed against propolis. It
  sits among the central frames, at the height of the brood nest, where the colony
  regulates the temperature.
- AHT20 outside, in the shade, near the entrance, on 3.3 V: on 5 V its I2C
  pull-ups would put 5 V on the ESP32 pins.
- Readings every 5 min, so a reading matches a count period.
- Before the installation, both sensors stay side by side for some hours, and the
  mean difference is subtracted in the analysis. On the bench they read 27.8 and
  27.6 °C.

## Board, card and clock

- **Common reader module, over SPI.** The 32 GB microSD card uses the most common
  reader module, over SPI on pins 14, 15, 2 and 0, powered from 5 V (the board VCC
  pin); on 3.3 V its regulator does not give the card enough and the card does not
  answer. The module's level shifter only passes signals one way, which rules out
  the 1-bit SD mode. The cost is pin 0, of the BOOT button, and a few mA drawn all
  the time by the module regulator. The reader holds pin 2 high, which blocks
  uploads: the wire from pin 2 comes out to upload.
- **DS3231, not the internal clock.** In deep sleep the ESP32 counts time on an
  on-chip oscillator, which gained 24 s per hour, almost 10 min per day
  (`results/clock_test.txt`), and resets at every power loss. The DS3231 has its
  own battery and errs about one minute per year, according to the maker.
- `environment.csv` has one line every 5 min: date, time, inside temperature,
  outside temperature and humidity, and battery voltage. The battery column stays
  empty until the solar supply is built.
- At an estimated 30 kB per photo, the schedule writes about 130 MB per day, and a
  32 GB card lasts months.

## Power

- Designed for a panel of about 3 W, an 18650 battery and a 5 V boost regulator.
- **The solar supply is not built (agreed with the professor).** The station runs
  on USB; the consumption is estimated and the panel and battery are sized from
  it. Building the solar supply is future work.
- **The board sleeps between photos.** By the estimate of `analysis/autonomy.py`:
  asleep between photos, about 3.3 Wh per day, and the battery holds almost 3 days
  without sun; never asleep, about 16 Wh, more than the panel restores. The bench
  measured 0.6 s awake per photo; the currents are still to be measured.
- **Charge controller with a battery temperature input.** In a box in the sun the
  battery can pass 45 °C, above the charge limit of a lithium cell.
- **PETG or ASA box, in the shade, ventilated.** PLA softens around 55 to 60 °C.

## Detector and evaluation

- Detector: YOLO11n of the Beehaviour project (UPC, AGPL-3.0), trained on the
  Sledevič and Matuzevičius dataset with three hives left out. Only the detection
  is used, with a minimum confidence of 0.40.
- Evaluation on the three held-out hives (`results/label_evaluation.txt`):
  precision, recall and F1 per box (IoU 0.5), and mean error, bias, relative error
  and agreement of the count per frame.
- **Agreement instead of r².** The r² of the correlation does not see the bias:
  on hive 20230609b, r² 0.82 and agreement (R² against y = x) 0.38.
- **No correction of the count.** A linear correction fitted on two hives made the
  error worse on the third in all three combinations: the bias depends on the
  scene, and correcting it would need labelled images of the installed hive.
- **Alternative method: background subtraction**, the method of Tu et al., written
  by the group (`results/background_subtraction.txt`): F1 0.31 against 0.88.

## Open items

While an item is here, the article claims nothing about it.

- Measure the current in each state of the board and run `analysis/autonomy.py`
  with the measured values.
- Photograph the labelled frames with the OV2640 to measure the loss caused by the
  camera.
- Define the passage of the DS18B20 cable and the sealing of the box.
- Install the station at a real hive.
