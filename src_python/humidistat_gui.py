#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""humidistat_gui.py

Manages the graphical user interface
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/project-Humidistat"
__date__ = "22-01-2021"
__version__ = "1.0"
# pylint: disable=bare-except, broad-except, unnecessary-lambda

from PyQt5 import QtCore, QtGui
from PyQt5 import QtWidgets as QtWid
from PyQt5.QtCore import QDateTime
import pyqtgraph as pg
import dvg_monkeypatch_pyqtgraph  # pylint: disable=unused-import

import dvg_pyqt_controls as controls
from dvg_debug_functions import tprint
from dvg_pyqt_filelogger import FileLogger
from dvg_pyqtgraph_threadsafe import (
    HistoryChartCurve,
    LegendSelect,
    PlotManager,
)

from dvg_devices.Arduino_protocol_serial import Arduino
from humidistat_qdev import Humidistat_qdev


# Constants
UPDATE_INTERVAL_WALL_CLOCK = 50  # 50 [ms]
CHART_HISTORY_TIME = 7200  # Maximum history length of charts [s]

# Show debug info in terminal? Warning: Slow! Do not leave on unintentionally.
DEBUG = False

# Try OpenGL support
TRY_USING_OPENGL = True
if TRY_USING_OPENGL:
    try:
        import OpenGL.GL as gl  # pylint: disable=unused-import
    except:
        print("OpenGL acceleration: Disabled")
        print("To install: `conda install pyopengl` or `pip install pyopengl`")
    else:
        print("OpenGL acceleration: Enabled")
        pg.setConfigOptions(useOpenGL=True)
        pg.setConfigOptions(antialias=True)
        pg.setConfigOptions(enableExperimental=True)

# Default settings for graphs
# pg.setConfigOptions(leftButtonPan=False)
pg.setConfigOption("background", controls.COLOR_GRAPH_BG)
pg.setConfigOption("foreground", controls.COLOR_GRAPH_FG)


# ------------------------------------------------------------------------------
#   Custom plotting styles
# ------------------------------------------------------------------------------


class CustomAxis(pg.AxisItem):
    """Aligns the top label of a `pyqtgraph.PlotItem` plot to the top-left
    corner
    """

    def resizeEvent(self, ev=None):
        if self.orientation == "top":
            self.label.setPos(QtCore.QPointF(0, 0))


def apply_PlotItem_style(
    pi: pg.PlotItem,
    title: str = "",
    bottom: str = "",
    left: str = "",
    right: str = "",
):
    """Apply our custom stylesheet to a `pyqtgraph.PlotItem` plot"""

    pi.setClipToView(True)
    pi.showGrid(x=1, y=1)
    pi.setMenuEnabled(True)
    pi.enableAutoRange(axis=pg.ViewBox.XAxis, enable=False)
    pi.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
    pi.setAutoVisible(y=True)
    pi.setRange(xRange=[-CHART_HISTORY_TIME, 0])

    p_title = {
        "color": controls.COLOR_GRAPH_FG.name(),
        "font-size": "12pt",
        "font-family": "Helvetica",
        "font-weight": "bold",
    }
    p_label = {
        "color": controls.COLOR_GRAPH_FG.name(),
        "font-size": "12pt",
        "font-family": "Helvetica",
    }
    pi.setLabel("bottom", bottom, **p_label)
    pi.setLabel("left", left, **p_label)
    pi.setLabel("top", title, **p_title)
    pi.setLabel("right", right, **p_label)

    # fmt: off
    font = QtGui.QFont()
    font.setPixelSize(16)
    pi.getAxis("bottom").setTickFont(font)
    pi.getAxis("left")  .setTickFont(font)
    pi.getAxis("top")   .setTickFont(font)
    pi.getAxis("right") .setTickFont(font)

    pi.getAxis("bottom").setStyle(tickTextOffset=10)
    pi.getAxis("left")  .setStyle(tickTextOffset=10)

    pi.getAxis("bottom").setHeight(60)
    pi.getAxis("left")  .setWidth(90)
    pi.getAxis("top")   .setHeight(40)
    pi.getAxis("right") .setWidth(16)

    pi.getAxis("top")  .setStyle(showValues=False)
    pi.getAxis("right").setStyle(showValues=False)
    # fmt: on


# ------------------------------------------------------------------------------
#   MainWindow
# ------------------------------------------------------------------------------


class MainWindow(QtWid.QWidget):
    def __init__(
        self,
        ard: Arduino,
        ard_qdev: Humidistat_qdev,
        logger: FileLogger,
        parent=None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)

        self.ard = ard
        self.ard_qdev = ard_qdev
        self.logger = logger

        # Shorthands
        state = self.ard_qdev.state
        config = self.ard_qdev.config

        self.setWindowTitle("Humidistat")
        self.setGeometry(350, 60, 1200, 900)
        self.setStyleSheet(
            controls.SS_TEXTBOX_READ_ONLY
            + controls.SS_GROUP_RECT
            + controls.SS_HOVER
        )

        # -------------------------
        #   Top frame
        # -------------------------

        # Left box
        self.qlbl_update_counter = QtWid.QLabel("0")
        self.qlbl_DAQ_rate = QtWid.QLabel("DAQ: nan Hz")
        self.qlbl_DAQ_rate.setStyleSheet("QLabel {min-width: 7em}")

        vbox_left = QtWid.QVBoxLayout()
        vbox_left.addWidget(self.qlbl_update_counter, stretch=0)
        vbox_left.addStretch(1)
        vbox_left.addWidget(self.qlbl_DAQ_rate, stretch=0)

        # Middle box
        self.qlbl_title = QtWid.QLabel(
            "Humidistat",
            font=QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Bold),
        )
        self.qlbl_title.setAlignment(QtCore.Qt.AlignCenter)
        self.qlbl_cur_date_time = QtWid.QLabel("00-00-0000    00:00:00")
        self.qlbl_cur_date_time.setAlignment(QtCore.Qt.AlignCenter)
        self.qpbt_record = controls.create_Toggle_button(
            "Click to start recording to file"
        )
        self.qpbt_record.clicked.connect(
            lambda state: self.logger.record(state)
        )

        vbox_middle = QtWid.QVBoxLayout()
        vbox_middle.addWidget(self.qlbl_title)
        vbox_middle.addWidget(self.qlbl_cur_date_time)
        vbox_middle.addWidget(self.qpbt_record)

        # Right box
        self.qpbt_exit = QtWid.QPushButton("Exit")
        self.qpbt_exit.clicked.connect(self.close)
        self.qpbt_exit.setMinimumHeight(30)
        self.qlbl_recording_time = QtWid.QLabel(alignment=QtCore.Qt.AlignRight)

        vbox_right = QtWid.QVBoxLayout()
        vbox_right.addWidget(self.qpbt_exit, stretch=0)
        vbox_right.addStretch(1)
        vbox_right.addWidget(self.qlbl_recording_time, stretch=0)

        # Round up top frame
        hbox_top = QtWid.QHBoxLayout()
        hbox_top.addLayout(vbox_left, stretch=0)
        hbox_top.addStretch(1)
        hbox_top.addLayout(vbox_middle, stretch=0)
        hbox_top.addStretch(1)
        hbox_top.addLayout(vbox_right, stretch=0)

        # -------------------------
        #   Bottom frame
        # -------------------------

        #  Charts
        # -------------------------

        self.gw = pg.GraphicsLayoutWidget()

        # Plots
        self.pi_humi = self.gw.addPlot(
            row=0, col=0, axisItems={"top": CustomAxis(orientation="top")}
        )
        self.pi_temp = self.gw.addPlot(
            row=1, col=0, axisItems={"top": CustomAxis(orientation="top")}
        )
        self.pi_pres = self.gw.addPlot(
            row=2, col=0, axisItems={"top": CustomAxis(orientation="top")}
        )
        apply_PlotItem_style(self.pi_humi, title="Humidity", left="% RH")
        apply_PlotItem_style(self.pi_temp, title="Temperature", left="°C")
        apply_PlotItem_style(self.pi_pres, title="Pressure", left="mbar")
        self.plots = [self.pi_temp, self.pi_humi, self.pi_pres]

        # Thread-safe curves
        capacity = round(
            CHART_HISTORY_TIME * 1e3 / ard_qdev.worker_DAQ._DAQ_interval_ms
        )
        PEN_01 = pg.mkPen(controls.COLOR_PEN_TURQUOISE, width=3)
        PEN_02 = pg.mkPen(controls.COLOR_PEN_YELLOW, width=3)
        PEN_03 = pg.mkPen(controls.COLOR_PEN_PINK, width=3)

        self.curve_humi_1 = HistoryChartCurve(
            capacity=capacity,
            linked_curve=self.pi_humi.plot(pen=PEN_01, name="H"),
        )
        self.curve_temp_1 = HistoryChartCurve(
            capacity=capacity,
            linked_curve=self.pi_temp.plot(pen=PEN_01, name="T"),
        )
        self.curve_pres_1 = HistoryChartCurve(
            capacity=capacity,
            linked_curve=self.pi_pres.plot(pen=PEN_01, name="P"),
        )
        self.curve_humi_2 = HistoryChartCurve(
            capacity=capacity,
            linked_curve=self.pi_humi.plot(pen=PEN_02, name="H"),
        )
        self.curve_temp_2 = HistoryChartCurve(
            capacity=capacity,
            linked_curve=self.pi_temp.plot(pen=PEN_02, name="T"),
        )
        self.curve_pres_2 = HistoryChartCurve(
            capacity=capacity,
            linked_curve=self.pi_pres.plot(pen=PEN_02, name="P"),
        )

        self.curves_1 = [
            self.curve_humi_1,
            self.curve_temp_1,
            self.curve_pres_1,
        ]
        self.curves_2 = [
            self.curve_humi_2,
            self.curve_temp_2,
            self.curve_pres_2,
        ]
        self.curves = self.curves_1 + self.curves_2

        #  Group `Readings`
        # -------------------------

        legend_1 = LegendSelect(linked_curves=self.curves_1)
        legend_2 = LegendSelect(linked_curves=self.curves_2)
        legend_1.qpbt_toggle.clicked.connect(
            lambda: QtCore.QCoreApplication.processEvents()  # Force redraw
        )
        legend_2.qpbt_toggle.clicked.connect(
            lambda: QtCore.QCoreApplication.processEvents()  # Force redraw
        )

        p = {
            "readOnly": True,
            "alignment": QtCore.Qt.AlignRight,
            "maximumWidth": 54,
        }
        self.qlin_humi_1 = QtWid.QLineEdit(**p)
        self.qlin_temp_1 = QtWid.QLineEdit(**p)
        self.qlin_pres_1 = QtWid.QLineEdit(**p)
        self.qlin_humi_2 = QtWid.QLineEdit(**p)
        self.qlin_temp_2 = QtWid.QLineEdit(**p)
        self.qlin_pres_2 = QtWid.QLineEdit(**p)

        # fmt: off
        legend_1.grid.setHorizontalSpacing(6)
        legend_1.grid.addWidget(self.qlin_humi_1         , 0, 2)
        legend_1.grid.addWidget(QtWid.QLabel("± 3 % RH") , 0, 3)
        legend_1.grid.addWidget(self.qlin_temp_1         , 1, 2)
        legend_1.grid.addWidget(QtWid.QLabel("± 0.5 °C") , 1, 3)
        legend_1.grid.addWidget(self.qlin_pres_1         , 2, 2)
        legend_1.grid.addWidget(QtWid.QLabel("± 1 mbar") , 2, 3)
        legend_1.grid.setColumnStretch(0, 0)
        legend_1.grid.setColumnStretch(1, 0)

        legend_2.grid.setHorizontalSpacing(6)
        legend_2.grid.addWidget(self.qlin_humi_2         , 0, 2)
        legend_2.grid.addWidget(QtWid.QLabel("± 3 % RH") , 0, 3)
        legend_2.grid.addWidget(self.qlin_temp_2         , 1, 2)
        legend_2.grid.addWidget(QtWid.QLabel("± 0.5 °C") , 1, 3)
        legend_2.grid.addWidget(self.qlin_pres_2         , 2, 2)
        legend_2.grid.addWidget(QtWid.QLabel("± 1 mbar") , 2, 3)
        legend_2.grid.setColumnStretch(0, 0)
        legend_2.grid.setColumnStretch(1, 0)
        # fmt: on

        vbox = QtWid.QVBoxLayout()
        vbox.addWidget(QtWid.QLabel("Sensor #1"))
        vbox.addLayout(legend_1.grid)
        vbox.addWidget(QtWid.QLabel("Sensor #2"))
        vbox.addLayout(legend_2.grid)

        qgrp_readings = QtWid.QGroupBox("Readings")
        qgrp_readings.setLayout(vbox)

        #  Group 'Log comments'
        # -------------------------

        self.qtxt_comments = QtWid.QTextEdit()
        grid = QtWid.QGridLayout()
        grid.addWidget(self.qtxt_comments, 0, 0)

        qgrp_comments = QtWid.QGroupBox("Log comments")
        qgrp_comments.setLayout(grid)

        #  Group 'Charts'
        # -------------------------

        self.plot_manager = PlotManager(parent=self)
        self.plot_manager.add_autorange_buttons(linked_plots=self.plots)
        self.plot_manager.add_preset_buttons(
            linked_plots=self.plots,
            linked_curves=self.curves,
            presets=[
                {
                    "button_label": "01:00",
                    "x_axis_label": "sec",
                    "x_axis_divisor": 1,
                    "x_axis_range": (-60, 0),
                },
                {
                    "button_label": "10:00",
                    "x_axis_label": "min",
                    "x_axis_divisor": 60,
                    "x_axis_range": (-10, 0),
                },
                {
                    "button_label": "30:00",
                    "x_axis_label": "min",
                    "x_axis_divisor": 60,
                    "x_axis_range": (-30, 0),
                },
                {
                    "button_label": "60:00",
                    "x_axis_label": "min",
                    "x_axis_divisor": 60,
                    "x_axis_range": (-60, 0),
                },
                {
                    "button_label": "120:00",
                    "x_axis_label": "min",
                    "x_axis_divisor": 60,
                    "x_axis_range": (-120, 0),
                },
            ],
        )
        self.plot_manager.add_clear_button(linked_curves=self.curves)
        self.plot_manager.perform_preset(1)

        qgrp_chart = QtWid.QGroupBox("Charts")
        qgrp_chart.setLayout(self.plot_manager.grid)

        #  Group 'Control'
        # -------------------------

        self.qpbt_valve_1 = controls.create_Toggle_button("valve 1")
        self.qpbt_valve_2 = controls.create_Toggle_button("valve 2")
        self.qpbt_pump = controls.create_Toggle_button("pump")

        self.qpbt_valve_1.clicked.connect(
            lambda: ard_qdev.turn_valve_1_off()
            if state.valve_1
            else ard_qdev.turn_valve_1_on()
        )
        self.qpbt_valve_2.clicked.connect(
            lambda: ard_qdev.turn_valve_2_off()
            if state.valve_2
            else ard_qdev.turn_valve_2_on()
        )
        self.qpbt_pump.clicked.connect(
            lambda: ard_qdev.turn_pump_off()
            if state.pump
            else ard_qdev.turn_pump_on()
        )

        grid = QtWid.QGridLayout()
        grid.addWidget(self.qpbt_valve_1, 0, 0)
        grid.addWidget(self.qpbt_valve_2, 1, 0)
        grid.addWidget(self.qpbt_pump, 2, 0)

        qgrp_control = QtWid.QGroupBox("Control")
        qgrp_control.setLayout(grid)

        #  Round up bottom frame
        # -------------------------

        # fmt: off
        grid_bot = QtWid.QGridLayout()
        grid_bot.addWidget(self.gw      , 0, 0, 3, 1)
        grid_bot.addWidget(qgrp_comments, 0, 1, 1, 2)
        grid_bot.addWidget(qgrp_readings, 1, 1)
        grid_bot.addWidget(qgrp_chart   , 2, 1)
        grid_bot.addWidget(qgrp_control , 1, 2)
        # fmt: on
        grid_bot.setColumnStretch(0, 1)
        grid_bot.setColumnStretch(1, 0)
        grid_bot.setColumnStretch(2, 0)
        grid_bot.setAlignment(qgrp_chart, QtCore.Qt.AlignLeft)
        grid_bot.setAlignment(qgrp_control, QtCore.Qt.AlignTop)

        # -------------------------
        #   Round up full window
        # -------------------------

        vbox = QtWid.QVBoxLayout(self)
        vbox.addLayout(hbox_top, stretch=0)
        vbox.addSpacerItem(QtWid.QSpacerItem(0, 10))
        vbox.addLayout(grid_bot, stretch=1)

        # -------------------------
        #   Wall clock timer
        # -------------------------

        self.timer_wall_clock = QtCore.QTimer()
        self.timer_wall_clock.timeout.connect(self.update_wall_clock)
        self.timer_wall_clock.start(UPDATE_INTERVAL_WALL_CLOCK)

        # -------------------------
        #   Connect signals
        # -------------------------

        self.ard_qdev.signal_DAQ_updated.connect(self.update_GUI)

        self.logger.signal_recording_started.connect(
            lambda filepath: self.qpbt_record.setText(
                "Recording to file: %s" % filepath
            )
        )
        self.logger.signal_recording_stopped.connect(
            lambda: self.qpbt_record.setText("Click to start recording to file")
        )

    # --------------------------------------------------------------------------
    #   Handle controls
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def update_wall_clock(self):
        cur_date_time = QDateTime.currentDateTime()
        self.qlbl_cur_date_time.setText(
            "%s    %s"
            % (
                cur_date_time.toString("dd-MM-yyyy"),
                cur_date_time.toString("HH:mm:ss"),
            )
        )

    @QtCore.pyqtSlot()
    def update_GUI(self):
        # Shorthands
        ard_qdev = self.ard_qdev
        state = self.ard_qdev.state
        config = self.ard_qdev.config

        self.qlbl_update_counter.setText("%i" % ard_qdev.update_counter_DAQ)
        self.qlbl_DAQ_rate.setText(
            "DAQ: %.1f Hz" % ard_qdev.obtained_DAQ_rate_Hz
        )
        if self.logger.is_recording():
            self.qlbl_recording_time.setText(self.logger.pretty_elapsed())

        self.qlin_humi_1.setText("%.0f" % state.humi_1)
        self.qlin_temp_1.setText("%.1f" % state.temp_1)
        self.qlin_pres_1.setText("%.0f" % state.pres_1)
        self.qlin_humi_2.setText("%.0f" % state.humi_2)
        self.qlin_temp_2.setText("%.1f" % state.temp_2)
        self.qlin_pres_2.setText("%.0f" % state.pres_2)

        self.qpbt_valve_1.setChecked(state.valve_1)
        self.qpbt_valve_2.setChecked(state.valve_2)
        self.qpbt_pump.setChecked(state.pump)

        if DEBUG:
            tprint("update_charts")

        for curve in self.curves:
            curve.update()
