#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Humidistat

A humidity controller for fluid dynamics research
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/project-Humidistat"
__date__ = "28-07-2022"
__version__ = "1.1"
# pylint: disable=bare-except, broad-except

import sys
import time

from PyQt5 import QtCore
from PyQt5 import QtWidgets as QtWid
from PyQt5.QtCore import QDateTime

from dvg_pyqt_filelogger import FileLogger
from dvg_debug_functions import dprint, print_fancy_traceback as pft

from dvg_devices.Arduino_protocol_serial import Arduino
from humidistat_qdev import Humidistat_qdev, ControlMode, ControlBand
from humidistat_gui import MainWindow

# Show debug info in terminal?
DEBUG = False

# ------------------------------------------------------------------------------
#   current_date_time_strings
# ------------------------------------------------------------------------------


def current_date_time_strings():
    cur_date_time = QDateTime.currentDateTime()
    return (
        cur_date_time.toString("dd-MM-yyyy"),  # Date
        cur_date_time.toString("HH:mm:ss"),  # Time
    )


# ------------------------------------------------------------------------------
#   Program termination routines
# ------------------------------------------------------------------------------


def stop_running():
    app.processEvents()
    ard_qdev.quit()
    logger.close()


@QtCore.pyqtSlot()
def notify_connection_lost():
    stop_running()

    window.qlbl_title.setText("! ! !    LOST CONNECTION    ! ! !")
    str_cur_date, str_cur_time = current_date_time_strings()
    str_msg = "%s %s\nLost connection to Arduino." % (
        str_cur_date,
        str_cur_time,
    )
    print("\nCRITICAL ERROR @ %s" % str_msg)
    reply = QtWid.QMessageBox.warning(
        window, "CRITICAL ERROR", str_msg, QtWid.QMessageBox.Ok
    )

    if reply == QtWid.QMessageBox.Ok:
        pass  # Leave the GUI open for read-only inspection by the user


@QtCore.pyqtSlot()
def about_to_quit():
    print("\nAbout to quit")
    stop_running()
    ard.close()


# ------------------------------------------------------------------------------
#   Arduino data-acquisition update function
# ------------------------------------------------------------------------------


def DAQ_function() -> bool:
    # WARNING: Do not change the GUI directly from out of this function as it
    # will be running in a separate and different thread to the main/GUI thread.

    # Shorthands
    state = ard_qdev.state
    config = ard_qdev.config

    # Date-time keeping
    str_cur_date, str_cur_time = current_date_time_strings()

    # Listen to the Arduino for sensor readings send out over serial
    success, reply = ard.readline()
    dprint(reply)

    if not (success):
        dprint(
            "'%s' reports IOError @ %s %s"
            % (ard.name, str_cur_date, str_cur_time)
        )
        return False

    # Parse readings into separate state variables
    try:
        (
            state.time,
            state.valve_1,
            state.valve_2,
            state.pump,
            state.humi_1,
            state.humi_2,
            state.temp_1,
            state.temp_2,
            state.pres_1,
            state.pres_2,
        ) = list(
            map(float, reply.split("\t"))
        )  # Parse all as float to allow for "nan" values in the reply string
        state.valve_1 = bool(state.valve_1)
        state.valve_2 = bool(state.valve_2)
        state.pump = bool(state.pump)
        state.time /= 1000  # Arduino time, [msec] to [s]
        state.pres_1 /= 100  # [Pa] to [mbar]
        state.pres_2 /= 100  # [Pa] to [mbar]
    except Exception as err:
        pft(err)
        dprint(
            "'%s' reports IOError @ %s %s"
            % (ard.name, str_cur_date, str_cur_time)
        )
        return False

    # We will use PC time instead
    state.time = time.perf_counter()

    # Measurement bandwidth control mechanism
    humi = state.humi_1 if config.act_on_sensor_no == 1 else state.humi_2
    humi_err = humi - state.setpoint

    if (humi_err > config.deadband_dLO) & (humi_err < config.deadband_dHI):
        state.control_band = ControlBand.Dead
        if state.control_band != state.control_band_prev:
            dprint("Control band: DEAD")
    elif (humi_err > config.fineband_dLO) & (humi_err < config.fineband_dHI):
        state.control_band = ControlBand.Fine
        if state.control_band != state.control_band_prev:
            dprint("Control band: FINE")
    else:
        state.control_band = ControlBand.Coarse
        if state.control_band != state.control_band_prev:
            dprint("Control band: COARSE")

    if state.control_mode == ControlMode.Auto:
        if state.control_band == ControlBand.Coarse:
            if humi < state.setpoint:
                ard_qdev.set_actuators(
                    config.actors_incr_RH.ENA_valve_1,
                    config.actors_incr_RH.ENA_valve_2,
                    config.actors_incr_RH.ENA_pump,
                )
            else:
                ard_qdev.set_actuators(
                    config.actors_decr_RH.ENA_valve_1,
                    config.actors_decr_RH.ENA_valve_2,
                    config.actors_decr_RH.ENA_pump,
                )

        elif state.control_band == ControlBand.Fine:
            if state.control_band != state.control_band_prev:
                # Restart burst timer as soon as we enter the fine-band and
                # ensure we turn off all actuators
                state.t_burst = time.perf_counter()
                ard_qdev.set_actuators(False, False, False)

            if time.perf_counter() - state.t_burst > config.burst_update_period:
                # Burst timer fired
                if humi < state.setpoint:
                    ard_qdev.burst_incr_RH()
                else:
                    ard_qdev.burst_decr_RH()

                state.t_burst = time.perf_counter()

        else:
            # Dead-band: Turn off all actuators
            ard_qdev.set_actuators(False, False, False)

    state.control_band_prev = state.control_band

    # Add readings to chart histories
    window.curve_humi_1.appendData(state.time, state.humi_1)
    window.curve_temp_1.appendData(state.time, state.temp_1)
    window.curve_pres_1.appendData(state.time, state.pres_1)
    window.curve_humi_2.appendData(state.time, state.humi_2)
    window.curve_temp_2.appendData(state.time, state.temp_2)
    window.curve_pres_2.appendData(state.time, state.pres_2)
    window.curve_setpoint.appendData(state.time, state.setpoint)
    window.curve_deadband_HI.appendData(
        state.time, state.setpoint + config.deadband_dHI
    )
    window.curve_deadband_LO.appendData(
        state.time, state.setpoint + config.deadband_dLO
    )

    # Logging to file
    logger.update(mode="w")

    # Return success
    return True


# ------------------------------------------------------------------------------
#   File logger
# ------------------------------------------------------------------------------


def write_header_to_log():
    str_cur_date, str_cur_time = current_date_time_strings()
    logger.write("[HEADER]\n")
    logger.write(str_cur_date + "\n")
    logger.write(str_cur_time + "\n")
    logger.write(window.qtxt_comments.toPlainText())
    logger.write("\n\n[DATA]\n")
    logger.write(
        "[s]\t"
        "[0/1]\t[0/1]\t[0/1]\t"
        "[??3 pct]\t[??0.5 ??C]\t[??1 mbar]\t"
        "[??3 pct]\t[??0.5 ??C]\t[??1 mbar]\n"
    )
    logger.write(
        "time\t"
        "valve_1\tvalve_2\tpump\t"
        "humi_1\ttemp_1\tpres_1\t"
        "humi_2\ttemp_2\tpres_2\n"
    )


def write_data_to_log():
    state = ard_qdev.state  # Shorthand
    logger.write(
        "%.3f\t%u\t%u\t%u\t%.2f\t%.2f\t%.1f\t%.2f\t%.2f\t%.1f\n"
        % (
            logger.elapsed(),
            state.valve_1,
            state.valve_2,
            state.pump,
            state.humi_1,
            state.temp_1,
            state.pres_1,
            state.humi_2,
            state.temp_2,
            state.pres_2,
        )
    )


# ------------------------------------------------------------------------------
#   Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":

    # Connect to Arduino
    ard = Arduino(name="Ard", connect_to_specific_ID="Humidistat v1")
    ard.serial_settings["baudrate"] = 115200
    ard.auto_connect(filepath_last_known_port="config/port_Arduino.txt")

    if not (ard.is_alive):
        print("\nCheck connection and try resetting the Arduino.\n")
        # print("Exiting...\n")
        # sys.exit(0)

    # Set up multi-threaded communication: Creates workers and threads
    ard_qdev = Humidistat_qdev(
        dev=ard,
        DAQ_function=DAQ_function,
        debug=DEBUG,
    )
    ard_qdev.signal_connection_lost.connect(notify_connection_lost)

    # File logger
    logger = FileLogger(
        write_header_function=write_header_to_log,
        write_data_function=write_data_to_log,
    )

    # Create application and main window
    QtCore.QThread.currentThread().setObjectName("MAIN")  # For DEBUG info
    app = QtWid.QApplication(sys.argv)
    app.aboutToQuit.connect(about_to_quit)
    window = MainWindow(ard, ard_qdev, logger)

    # Start threads
    ard_qdev.start()  # NOTE: The DAQ worker thread starts up in a paused state
    ard_qdev.unpause_DAQ()  # Start listening continuously to the Arduino

    # Load default Humidistat configuration from file
    window.load_config_from_file(from_default=True)

    # Start the main GUI event loop
    window.show()
    sys.exit(app.exec_())
