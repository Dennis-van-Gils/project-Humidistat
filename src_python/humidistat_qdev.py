#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""humidistat_qdev.py

Manages multi-threaded communication with the Arduino
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/project-Humidistat"
__date__ = "25-01-2021"
__version__ = "1.0"

from enum import Enum
import numpy as np

from dvg_devices.Arduino_protocol_serial import Arduino
from dvg_qdeviceio import QDeviceIO


class ControlMode(Enum):
    Manual = 0
    Auto = 1


class ControlBand(Enum):
    Coarse = 0
    Fine = 1
    Dead = 2


class ActuatorManager:
    """Holds which actuators to enable to either increase or decrease the
    humidity. Hence, two instances of this class should be created."""

    def __init__(
        self, valve_1: bool = False, valve_2: bool = False, pump: bool = False
    ):
        self.ENA_valve_1 = valve_1
        self.ENA_valve_2 = valve_2
        self.ENA_pump = pump


class Humidistat_qdev(QDeviceIO):
    class State(object):
        def __init__(self):
            # Actual readings of the Arduino
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

            # Control
            self.setpoint = 50  # [% RH]
            self.control_mode = ControlMode.Manual
            self.control_band = ControlBand.Coarse
            self.control_band_prev = ControlBand.Coarse
            self.t_burst = 0  # [s], timestamp at start of burst period

    class Config(object):
        def __init__(self):
            # fmt: off
            # Actuators
            self.actuators_incr = ActuatorManager(True, False, True)
            self.actuators_decr = ActuatorManager(False, True, True)
            self.act_on_sensor_no = 2  # [1 or 2]

            # Bandwidths
            self.fineband_dHI = +2     # [% RH]
            self.fineband_dLO = -2     # [% RH]
            self.deadband_dHI = +0.5   # [% RH]
            self.deadband_dLO = -0.5   # [% RH]

            # Fine 'burst' control mode
            self.burst_update_period = 10     # [s]
            self.burst_incr_RH_length = 500   # [ms]
            self.burst_decr_RH_length = 1000  # [ms]
            # fmt: on

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

    def set_valve_1(self, flag: bool):
        if not self.state.valve_1 == flag:
            self.send(self.dev.write, "v1%u" % flag)

    def set_valve_2(self, flag: bool):
        if not self.state.valve_2 == flag:
            self.send(self.dev.write, "v2%u" % flag)

    def set_pump(self, flag: bool):
        if not self.state.pump == flag:
            self.send(self.dev.write, "p%u" % flag)

    def burst_incr_RH(self):
        command = "b%u%u%u%u" % (
            self.config.actuators_incr.ENA_valve_1,
            self.config.actuators_incr.ENA_valve_2,
            self.config.actuators_incr.ENA_pump,
            self.config.burst_incr_RH_length,
        )
        self.send(self.dev.write, command)

    def burst_decr_RH(self):
        command = "b%u%u%u%u" % (
            self.config.actuators_decr.ENA_valve_1,
            self.config.actuators_decr.ENA_valve_2,
            self.config.actuators_decr.ENA_pump,
            self.config.burst_decr_RH_length,
        )
        self.send(self.dev.write, command)
