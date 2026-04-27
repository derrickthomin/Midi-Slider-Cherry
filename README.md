# LumaFader 68

The LumaFader 68 is a compact MIDI controller featuring four long-throw faders, capable of controlling up to 68 parameters in your DAW or synthesizer (via mini TRS). It's ideal for both live performance and recording automation.

## Demo

[![LumaFader 68 Demo](https://img.youtube.com/vi/-r_8dHA1_Gs/0.jpg)](https://youtu.be/-r_8dHA1_Gs?si=00uZ8pCUi5EYb8bo)

*Click the image above to watch a demonstration on YouTube.*  

## Links

*   **Web Config Utility:** [Open Web Config](https://derrickthomin.github.io/Midi-Slider-Cherry/) — configure your LumaFader from the browser (Chrome/Edge, requires Web Serial)
*   **Project Writeup:** [www.djbajablast.com/post/lumafader68](https://www.djbajablast.com/post/lumafader68)
*   **Buy:** [Etsy - DJBB LumaFader 68](https://www.etsy.com/listing/1872693350/djbb-lumafader-68-midi-controller-rgb)

---

## What's New (April 2026)

- **Multi-channel output** - send CC messages to multiple MIDI channels simultaneously using the `|` separator
- **Aftertouch support** - channel pressure (aftertouch) messages now supported
- **Web Config Utility** - configure settings directly from the browser via Web Serial (Chrome/Edge)

---

## Configuration

Use the [Web Config Utility](https://derrickthomin.github.io/Midi-Slider-Cherry/) to configure your LumaFader (Chrome/Edge, requires Web Serial). You can also edit `settings.json` directly -- see the user manual for details on the JSON structure.

<img width="500" height="" alt="Web Settings Interface" src="https://github.com/user-attachments/assets/b8ba807f-c97e-4158-9761-0b9c1cd95882" />

### Channel Inheritance

Each slider's MIDI channel is resolved by inheritance. If a bank's channel is left empty, it falls back to the page channel. If the page channel is empty, it falls back to the global channel.

```
Bank Channel → Page Channel → Global Channel
```

By default, all page/bank channels are empty, so everything uses `GLOBAL_CHANNEL`.

### Multi-Channel Output

Any channel field can target multiple MIDI channels at once using the `|` separator (e.g. `"1|2|3"`). This sends the same CC or aftertouch message to all specified channels simultaneously.

For example you can set `GLOBAL_CHANNEL`1` to `"1|2|3|4"`

---

## Updating Firmware

### What You Need

- This repository (download it from this page)
- A USB-C data cable connected to the LumaFader

### Locate the Boot Button

The boot button is on the bottom PCB. See the image below for where it is located. I usually just stick a screwdriver through the hole in the case for the USB and use that to press the button. Alternaltivly you can take the top panel off with an m3 hex key.

<img width="450" height="1246" alt="Show Boot Button" src="https://github.com/user-attachments/assets/2fdeeb8c-3297-4982-aabe-627f1dcd7ce0" />

### Steps

1. **Enter boot mode:** Hold the **BOOT** button on the Pico, then plug in the USB cable (or tap RESET while holding BOOT). Release the button. A drive called **RPI-RP2** should appear on your computer.

2. **Flash nuke:** Drag `uf2 current/flash_nuke.uf2` onto the **RPI-RP2** drive. The device will reboot and reappear as **RPI-RP2** after a few seconds.

3. **Install CircuitPython:** Drag `uf2 current/adafruit-circuitpython-raspberry_pi_pico-en_US-8.2.6.uf2` onto the **RPI-RP2** drive. The device will reboot and reappear as a drive called **CIRCUITPY**.

4. **Copy source files:** Copy the entire contents of the `src/` folder onto the **CIRCUITPY** drive. This includes all `.py` files, `settings.json`, and the `lib/` folder. Overwrite if prompted.

5. **Done.** Unplug the LumaFader and plug it back in.
