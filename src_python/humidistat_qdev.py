#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""humidistat_qdev.py

Manages multi-threaded communication with the Arduino
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/project-Humidistat"
__date__ = "22-01-2021"
__version__ = "1.0"

import numpy as np

from dvg_devices.Arduino_protocol_serial import Arduino
from dvg_qdeviceio import QDeviceIO


class Humidistat_qdev(QDeviceIO):
    class State(object):
        """Reflects the actual readings, parsed into separate variables, of the
        Arduino. There should only be one instance of the State class.
        """

        def __init__(self):
            self.time = np.nan  # [s]
            self.valve_1 = False
            self.valve_2 = False
            self.pump = False
            self.temp_1 = np.nan  # ['C]
            self.temp_2 = np.nan  # ['C]
            self.humi_1 = np.nan  # [% RH]
            self.humi_2 = np.nan  # [% RH]
            self.pres_1 = np.nan  # [mbar]
            self.pres_2 = np.nan  # [mbar]

    class Config(object):
        """"""

        def __init__(self):
            pass

    # --------------------------------------------------------------------------
    #   Humidistat_qdev
    # --------------------------------------------------------------------------

    def __init__(
        self,
        dev: Arduino,
        DAQ_function=None,
        DAQ_interval_ms=1000,
        debug=False,
        **kwargs,
    ):
        super().__init__(dev, **kwargs)  # Pass kwargs onto QtCore.QObject()

        self.state = self.State()
        self.config = self.Config()

        self.create_worker_DAQ(
            DAQ_function=DAQ_function,
            DAQ_interval_ms=DAQ_interval_ms,
            critical_not_alive_count=3,
            debug=debug,
        )
        self.create_worker_jobs(debug=debug)

    # --------------------------------------------------------------------------
    #   Arduino communication functions
    # --------------------------------------------------------------------------

    def turn_valve_1_off(self):
        self.send(self.dev.write, "v10")

    def turn_valve_1_on(self):
        self.send(self.dev.write, "v11")

    def turn_valve_2_off(self):
        self.send(self.dev.write, "v20")

    def turn_valve_2_on(self):
        self.send(self.dev.write, "v21")

    def turn_pump_off(self):
        self.send(self.dev.write, "p0")

    def turn_pump_on(self):
        self.send(self.dev.write, "p1")
