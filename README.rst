.. image:: https://requires.io/github/Dennis-van-Gils/project-Humidistat/requirements.svg?branch=main
    :target: https://requires.io/github/Dennis-van-Gils/project-Humidistat/requirements/?branch=main
    :alt: Requirements Status
.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/psf/black
.. image:: https://img.shields.io/badge/License-MIT-purple.svg
    :target: https://github.com/Dennis-van-Gils/project-Humidistat/blob/master/LICENSE.txt

Humidistat 
==========
*A Physics of Fluids project.*

Placeholder...

- Github: https://github.com/Dennis-van-Gils/project-Humidistat

.. image:: https://raw.githubusercontent.com/Dennis-van-Gils/project-Humidistat/master/screenshot.png

.. image:: https://raw.githubusercontent.com/Dennis-van-Gils/project-Humidistat/master/docs/control_bands_explained.png

Hardware
========
* Adafruit #3857: Adafruit Feather M4 Express - Featuring ATSAMD51 Cortex M4
* Pimoroni PIM472: BME280 Breakout - Temperature, Pressure, Humidity Sensor
* ...

Instructions
============
Download the `latest release <https://github.com/Dennis-van-Gils/project-Humidistat/releases/latest>`_
and unpack to a folder onto your drive.

Flashing the firmware
---------------------

Double click the reset button of the Feather while plugged into your PC. This
will mount a drive called `FEATHERBOOT`. Copy
`src_mcu/_build_Feather_M4/CURRENT.UF2 <https://github.com/Dennis-van-Gils/project-Humidistat/raw/main/src_mcu/_build_Feather_M4/CURRENT.UF2>`_
onto the Featherboot drive. It will restart automatically with the new firmware.

Running the application
-----------------------


Prerequisites
~~~~~~~~~~~~~

| Python 3.8
| Preferred distribution: Anaconda full or Miniconda

    * `Anaconda <https://www.anaconda.com>`_
    * `Miniconda <https://docs.conda.io/en/latest/miniconda.html>`_

Open `Anaconda Prompt` and navigate to the unpacked folder. Run the following to
install the necessary packages:

::

   cd src_python
   conda update -n base -c defaults conda
   conda create -n humi -c conda-forge  --force -y python=3.8.10
   conda activate humi
   pip install -r requirements.txt

Now you can run the graphical user interface of the humidistat.
In Anaconda prompt:

::

   conda activate humi
   ipython main.py


LED status lights
=================

The RGB LED of the Feather M4 will indicate its status:

* Blue : We're setting up
* Green: All okay and idling

Every read out, the LED will flash brightly turquoise.
