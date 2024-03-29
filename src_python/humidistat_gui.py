#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""humidistat_gui.py

Manages the graphical user interface
"""
__author__ = "Dennis van Gils"
__authoremail__ = "vangils.dennis@gmail.com"
__url__ = "https://github.com/Dennis-van-Gils/project-Humidistat"
__date__ = "28-07-2022"
__version__ = "1.1"
# pylint: disable=bare-except, broad-except, unnecessary-lambda

from pathlib import Path
from configparser import ConfigParser

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import QDateTime
from PyQt5.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpacerItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import pyqtgraph as pg
import dvg_monkeypatch_pyqtgraph  # pylint: disable=unused-import

import dvg_pyqt_controls as controls
from dvg_debug_functions import dprint, tprint, print_fancy_traceback as pft
from dvg_pyqt_filelogger import FileLogger
from dvg_pyqtgraph_threadsafe import (
    HistoryChartCurve,
    LegendSelect,
    PlotManager,
)

from dvg_devices.Arduino_protocol_serial import Arduino
from humidistat_qdev import Humidistat_qdev, ControlMode, ControlBand


# Constants
UPDATE_INTERVAL_WALL_CLOCK = 50  # 50 [ms]
CHART_HISTORY_TIME = 7200  # Maximum history length of charts [s]
DEFAULT_CONFIG_FILE = "./config/humidistat_default_config.ini"

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
    pi.vb.setLimits(xMax=0.01)

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


class MainWindow(QWidget):
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

        self.setWindowTitle("Humidistat")
        self.setGeometry(350, 60, 1200, 900)
        self.setStyleSheet(
            controls.SS_TEXTBOX_READ_ONLY
            + controls.SS_GROUP
            + controls.SS_HOVER
        )

        # Textbox widths for fitting N characters using the current font
        ex8 = 8 + 8 * QtGui.QFontMetrics(QtGui.QFont()).averageCharWidth()
        ex10 = 8 + 10 * QtGui.QFontMetrics(QtGui.QFont()).averageCharWidth()

        # -------------------------
        #   Top frame
        # -------------------------

        # Left box
        self.qlbl_DAQ_rate = QLabel("DAQ: nan Hz")
        self.qlbl_DAQ_rate.setStyleSheet("QLabel {min-width: 7em}")
        self.qlbl_update_counter = QLabel("0")
        self.qlbl_recording_time = QLabel()

        vbox_left = QVBoxLayout()
        vbox_left.addWidget(self.qlbl_DAQ_rate, stretch=0)
        vbox_left.addWidget(self.qlbl_update_counter, stretch=0)
        vbox_left.addWidget(self.qlbl_recording_time, stretch=0)
        vbox_left.addStretch(1)

        # Middle box
        self.qlbl_title = QLabel(
            "Humidistat",
            font=QtGui.QFont("Palatino", 14, weight=QtGui.QFont.Bold),
        )
        self.qlbl_title.setAlignment(QtCore.Qt.AlignCenter)
        self.qlbl_cur_date_time = QLabel("00-00-0000    00:00:00")
        self.qlbl_cur_date_time.setAlignment(QtCore.Qt.AlignCenter)
        self.qpbt_record = controls.create_Toggle_button(
            "Click to start recording to file"
        )
        self.qpbt_record.clicked.connect(
            lambda state: self.logger.record(state)
        )

        vbox_middle = QVBoxLayout()
        vbox_middle.addWidget(self.qlbl_title)
        vbox_middle.addWidget(self.qlbl_cur_date_time)
        vbox_middle.addWidget(self.qpbt_record)

        # Right box
        p = {"alignment": QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter}
        self.qpbt_exit = QPushButton("Exit", minimumHeight=30)
        self.qpbt_exit.clicked.connect(self.close)
        self.qlbl_GitHub = QLabel(
            '<a href="%s">Documentation</a>' % __url__, **p
        )
        self.qlbl_GitHub.setTextFormat(QtCore.Qt.RichText)
        self.qlbl_GitHub.setTextInteractionFlags(
            QtCore.Qt.TextBrowserInteraction
        )
        self.qlbl_GitHub.setOpenExternalLinks(True)

        vbox_right = QVBoxLayout(spacing=4)
        vbox_right.addWidget(self.qpbt_exit, stretch=0)
        vbox_right.addStretch(1)
        vbox_right.addWidget(QLabel(__author__, **p))
        vbox_right.addWidget(self.qlbl_GitHub)
        vbox_right.addWidget(QLabel("v%s" % __version__, **p))

        # Round up top frame
        hbox_top = QHBoxLayout()
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
        )  # TODO: Fix this wrong calculation. `_DAQ_interval_ms` is not the
        # correct variable anymore. DAQ interval is rather determined on the
        # Arduino side.
        PEN_01 = pg.mkPen(controls.COLOR_PEN_TURQUOISE, width=3)
        PEN_02 = pg.mkPen(controls.COLOR_PEN_YELLOW, width=3)
        PEN_03 = pg.mkPen(controls.COLOR_PEN_PINK, width=3)
        PEN_04 = pg.mkPen(
            controls.COLOR_PEN_PINK, width=1, style=QtCore.Qt.DotLine
        )

        self.curve_setpoint = HistoryChartCurve(  # Setpoint
            capacity=capacity,
            linked_curve=self.pi_humi.plot(pen=PEN_03, name=""),
        )
        self.curve_deadband_HI = HistoryChartCurve(  # Dead-band HI
            capacity=capacity,
            linked_curve=self.pi_humi.plot(pen=PEN_04, name=""),
        )
        self.curve_deadband_LO = HistoryChartCurve(  # Dead-band LO
            capacity=capacity,
            linked_curve=self.pi_humi.plot(pen=PEN_04, name=""),
        )
        self.curve_humi_1 = HistoryChartCurve(  # Sensor 1: Humidity
            capacity=capacity,
            linked_curve=self.pi_humi.plot(pen=PEN_01, name="H"),
        )
        self.curve_temp_1 = HistoryChartCurve(  # Sensor 1: Temperature
            capacity=capacity,
            linked_curve=self.pi_temp.plot(pen=PEN_01, name="T"),
        )
        self.curve_pres_1 = HistoryChartCurve(  # Sensor 1: Pressure
            capacity=capacity,
            linked_curve=self.pi_pres.plot(pen=PEN_01, name="P"),
        )
        self.curve_humi_2 = HistoryChartCurve(  # Sensor 2: Humidity
            capacity=capacity,
            linked_curve=self.pi_humi.plot(pen=PEN_02, name="H"),
        )
        self.curve_temp_2 = HistoryChartCurve(  # Sensor 2: Temperature
            capacity=capacity,
            linked_curve=self.pi_temp.plot(pen=PEN_02, name="T"),
        )
        self.curve_pres_2 = HistoryChartCurve(  # Sensor 2: Pressure
            capacity=capacity,
            linked_curve=self.pi_pres.plot(pen=PEN_02, name="P"),
        )

        self.curves_setpoint = [
            self.curve_setpoint,
            self.curve_deadband_HI,
            self.curve_deadband_LO,
        ]
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
        self.curves = self.curves_setpoint + self.curves_1 + self.curves_2

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
        self.qlin_humi_1 = QLineEdit(**p)
        self.qlin_temp_1 = QLineEdit(**p)
        self.qlin_pres_1 = QLineEdit(**p)
        self.qlin_humi_2 = QLineEdit(**p)
        self.qlin_temp_2 = QLineEdit(**p)
        self.qlin_pres_2 = QLineEdit(**p)

        # fmt: off
        legend_1.grid.setHorizontalSpacing(6)
        legend_1.grid.addWidget(self.qlin_humi_1  , 0, 2)
        legend_1.grid.addWidget(QLabel("± 3 % RH"), 0, 3)
        legend_1.grid.addWidget(self.qlin_temp_1  , 1, 2)
        legend_1.grid.addWidget(QLabel("± 0.5 °C"), 1, 3)
        legend_1.grid.addWidget(self.qlin_pres_1  , 2, 2)
        legend_1.grid.addWidget(QLabel("± 1 mbar"), 2, 3)
        legend_1.grid.setColumnStretch(0, 0)
        legend_1.grid.setColumnStretch(1, 0)

        legend_2.grid.setHorizontalSpacing(6)
        legend_2.grid.addWidget(self.qlin_humi_2  , 0, 2)
        legend_2.grid.addWidget(QLabel("± 3 % RH"), 0, 3)
        legend_2.grid.addWidget(self.qlin_temp_2  , 1, 2)
        legend_2.grid.addWidget(QLabel("± 0.5 °C"), 1, 3)
        legend_2.grid.addWidget(self.qlin_pres_2  , 2, 2)
        legend_2.grid.addWidget(QLabel("± 1 mbar"), 2, 3)
        legend_2.grid.setColumnStretch(0, 0)
        legend_2.grid.setColumnStretch(1, 0)
        # fmt: on

        vbox = QVBoxLayout(spacing=4)
        vbox.addWidget(QLabel("<b>Sensor #1</b>"))
        vbox.addLayout(legend_1.grid)
        vbox.addSpacing(6)
        vbox.addWidget(QLabel("<b>Sensor #2</b>"))
        vbox.addLayout(legend_2.grid)

        qgrp_readings = QGroupBox("Readings")
        qgrp_readings.setLayout(vbox)

        #  Group 'Log comments'
        # -------------------------

        self.qtxt_comments = QTextEdit()
        self.qtxt_comments.setMinimumHeight(60)
        grid = QGridLayout()
        grid.addWidget(self.qtxt_comments, 0, 0)

        qgrp_comments = QGroupBox("Log comments")
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
                    "button_label": "03:00",
                    "x_axis_label": "sec",
                    "x_axis_divisor": 1,
                    "x_axis_range": (-180, 0),
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

        qgrp_charts = QGroupBox("Charts")
        qgrp_charts.setLayout(self.plot_manager.grid)

        #  Group 'Control'
        # -------------------------

        p = {"maximumWidth": ex10 / 2, "alignment": QtCore.Qt.AlignRight}
        self.qlin_setpoint = QLineEdit(**p)
        self.qlin_control_band = QLineEdit(
            readOnly=True, maximumWidth=80, alignment=QtCore.Qt.AlignHCenter
        )
        self.qpbt_control_mode = controls.create_Toggle_button("Manual control")
        self.qpbt_valve_1 = controls.create_Toggle_button(maximumWidth=80)
        self.qpbt_valve_2 = controls.create_Toggle_button(maximumWidth=80)
        self.qpbt_pump = controls.create_Toggle_button(maximumWidth=80)
        self.qpbt_burst_incr_RH = QPushButton("RH ▲ burst")
        self.qpbt_burst_decr_RH = QPushButton("RH ▼ burst")
        self.qpbt_reconnect = QPushButton("Reconnect sensors")

        self.qlin_setpoint.editingFinished.connect(self.process_qlin_setpoint)
        self.qpbt_control_mode.clicked.connect(self.process_qpbt_control_mode)
        self.qpbt_valve_1.clicked.connect(
            lambda: ard_qdev.set_valve_1(not state.valve_1)
        )
        self.qpbt_valve_2.clicked.connect(
            lambda: ard_qdev.set_valve_2(not state.valve_2)
        )
        self.qpbt_pump.clicked.connect(
            lambda: ard_qdev.set_pump(not state.pump)
        )
        self.qpbt_burst_incr_RH.clicked.connect(ard_qdev.burst_incr_RH)
        self.qpbt_burst_decr_RH.clicked.connect(ard_qdev.burst_decr_RH)
        self.qpbt_reconnect.clicked.connect(ard_qdev.reconnect_BME280_sensors)

        legend_setpoint = LegendSelect(
            linked_curves=[self.curve_setpoint], hide_toggle_button=True
        )

        # Show/hide dead-band curves when clicking setpoint checkbox
        def curves_deadband_setVisible(flag: bool):
            self.curve_deadband_HI.setVisible(flag)
            self.curve_deadband_LO.setVisible(flag)

        legend_setpoint.chkbs[0].clicked.connect(
            lambda checked: curves_deadband_setVisible(checked)
        )

        # fmt: off
        i = 0
        grid = QGridLayout(spacing=4)
        grid.addWidget(QLabel("Setpoint:")       , i, 0)
        grid.addWidget(self.qlin_setpoint        , i, 1)
        grid.addWidget(QLabel("% RH")            , i, 2)         ; i+=1
        grid.addLayout(legend_setpoint.grid      , i, 1, 1, 2)   ; i+=1
        grid.addWidget(QLabel("Band:")           , i, 0)
        grid.addWidget(self.qlin_control_band    , i, 1, 1, 2)   ; i+=1
        grid.addItem(QSpacerItem(0, 10)          , i, 0)         ; i+=1
        grid.addWidget(QLabel("<b>Actuators</b>"), i, 0, 1, 3)   ; i+=1
        grid.addWidget(self.qpbt_control_mode    , i, 0, 1, 3)   ; i+=1
        grid.addWidget(QLabel("valve 1")         , i, 0)
        grid.addWidget(self.qpbt_valve_1         , i, 1, 1, 2)   ; i+=1
        grid.addWidget(QLabel("valve 2")         , i, 0)
        grid.addWidget(self.qpbt_valve_2         , i, 1, 1, 2)   ; i+=1
        grid.addWidget(QLabel("pump")            , i, 0)
        grid.addWidget(self.qpbt_pump            , i, 1, 1, 2)   ; i+=1
        grid.addItem(QSpacerItem(0, 6)           , i, 0)         ; i+=1
        grid.addWidget(self.qpbt_burst_incr_RH   , i, 0, 1, 3)   ; i+=1
        grid.addWidget(self.qpbt_burst_decr_RH   , i, 0, 1, 3)   ; i+=1
        grid.addItem(QSpacerItem(0, 6)           , i, 0)         ; i+=1
        grid.addWidget(QLabel("<b>Troubleshoot</b>"), i, 0, 1, 3); i+=1
        grid.addWidget(self.qpbt_reconnect       , i, 0, 1, 3)   ; i+=1
        # fmt: on

        qgrp_control = QGroupBox("Control")
        qgrp_control.setLayout(grid)

        #  Group 'Configuration'
        # -------------------------

        # fmt: off
        p = {"maximumWidth": ex10}
        self.qchk_incr_ENA_valve_1 = QCheckBox("valve 1", **p)
        self.qchk_incr_ENA_valve_2 = QCheckBox("valve 2", **p)
        self.qchk_incr_ENA_pump    = QCheckBox("pump"   , **p)
        self.qchk_decr_ENA_valve_1 = QCheckBox("valve 1", **p)
        self.qchk_decr_ENA_valve_2 = QCheckBox("valve 2", **p)
        self.qchk_decr_ENA_pump    = QCheckBox("pump"   , **p)
        self.qrbt_act_on_sensor_1  = QRadioButton("sensor 1")
        self.qrbt_act_on_sensor_2  = QRadioButton("sensor 2")
        # fmt: on

        self.qchk_incr_ENA_valve_1.clicked.connect(
            self.process_qchk_incr_ENA_valve_1
        )
        self.qchk_decr_ENA_valve_1.clicked.connect(
            self.process_qchk_decr_ENA_valve_1
        )
        self.qchk_incr_ENA_valve_2.clicked.connect(
            self.process_qchk_incr_ENA_valve_2
        )
        self.qchk_decr_ENA_valve_2.clicked.connect(
            self.process_qchk_decr_ENA_valve_2
        )
        self.qchk_incr_ENA_pump.clicked.connect(self.process_qchk_incr_ENA_pump)
        self.qchk_decr_ENA_pump.clicked.connect(self.process_qchk_decr_ENA_pump)
        self.qrbt_act_on_sensor_1.clicked.connect(
            self.process_qrbt_act_on_sensor_1
        )
        self.qrbt_act_on_sensor_2.clicked.connect(
            self.process_qrbt_act_on_sensor_2
        )

        p = {"maximumWidth": ex8, "alignment": QtCore.Qt.AlignRight}
        self.qlin_fineband_dHI = QLineEdit(**p)
        self.qlin_fineband_dLO = QLineEdit(**p)
        self.qlin_deadband_dHI = QLineEdit(**p)
        self.qlin_deadband_dLO = QLineEdit(**p)
        self.qlin_burst_update_period = QLineEdit(**p)
        self.qlin_burst_incr_RH_length = QLineEdit(**p)
        self.qlin_burst_decr_RH_length = QLineEdit(**p)

        self.qlin_fineband_dHI.editingFinished.connect(
            self.process_qlin_fineband_dHI
        )
        self.qlin_fineband_dLO.editingFinished.connect(
            self.process_qlin_fineband_dLO
        )
        self.qlin_deadband_dHI.editingFinished.connect(
            self.process_qlin_deadband_dHI
        )
        self.qlin_deadband_dLO.editingFinished.connect(
            self.process_qlin_deadband_dLO
        )
        self.qlin_burst_update_period.editingFinished.connect(
            self.process_qlin_burst_update_period
        )
        self.qlin_burst_incr_RH_length.editingFinished.connect(
            self.process_qlin_burst_incr_RH_length
        )
        self.qlin_burst_decr_RH_length.editingFinished.connect(
            self.process_qlin_burst_decr_RH_length
        )

        self.qpbt_load_config = QPushButton("Load", maximumWidth=ex8)
        self.qpbt_save_config = QPushButton("Save", maximumWidth=ex8)
        self.qpbt_dflt_config = QPushButton(
            "Save as default", maximumWidth=ex8 * 2
        )
        self.qpbt_load_config.clicked.connect(
            lambda: self.load_config_from_file(from_default=False)
        )
        self.qpbt_save_config.clicked.connect(
            lambda: self.save_config_to_file(as_default=False)
        )
        self.qpbt_dflt_config.clicked.connect(
            lambda: self.save_config_to_file(as_default=True)
        )

        grid3 = QGridLayout(spacing=4)
        grid3.addWidget(QLabel("<b>Configuration</b>"), 0, 0, 1, 3)
        grid3.addWidget(self.qpbt_load_config, 1, 0)
        grid3.addWidget(self.qpbt_save_config, 1, 1)
        grid3.addWidget(self.qpbt_dflt_config, 1, 2)

        # fmt: off
        i = 0
        grid2 = QGridLayout(spacing=4)
        grid2.addWidget(QLabel("<b>Control bandwidths</b>"), i, 0, 1, 3); i+=1
        grid2.addWidget(QLabel("Fine-band:")               , i, 0)
        grid2.addWidget(self.qlin_fineband_dLO             , i, 1)
        grid2.addWidget(self.qlin_fineband_dHI             , i, 2)
        grid2.addWidget(QLabel("% RH")                     , i, 3)      ; i+=1
        grid2.addWidget(QLabel("Dead-band:")               , i, 0)
        grid2.addWidget(self.qlin_deadband_dLO             , i, 1)
        grid2.addWidget(self.qlin_deadband_dHI             , i, 2)
        grid2.addWidget(QLabel("% RH")                     , i, 3)      ; i+=1
        grid2.addItem(QSpacerItem(0, 6)                    , i, 0)      ; i+=1
        grid2.addWidget(QLabel("<b>Fine-band bursts</b>")  , i, 0, 1, 3); i+=1
        grid2.addWidget(QLabel("Update period:")           , i, 0, 1, 2)
        grid2.addWidget(self.qlin_burst_update_period      , i, 2)
        grid2.addWidget(QLabel("s")                        , i, 3)      ; i+=1
        grid2.addWidget(QLabel("RH ▲ burst length:")       , i, 0, 1, 2)
        grid2.addWidget(self.qlin_burst_incr_RH_length     , i, 2)
        grid2.addWidget(QLabel("ms")                       , i, 3)      ; i+=1
        grid2.addWidget(QLabel("RH ▼ burst length:")       , i, 0, 1, 2)
        grid2.addWidget(self.qlin_burst_decr_RH_length     , i, 2)
        grid2.addWidget(QLabel("ms")                       , i, 3)      ; i+=1

        i = 0
        grid = QGridLayout(spacing=4)
        grid.addWidget(QLabel("<b>Assign actuators</b>")   , i, 0, 1, 3); i+=1
        grid.addWidget(QLabel("RH ▲:")                     , i, 0)
        grid.addWidget(self.qchk_incr_ENA_valve_1          , i, 1)
        grid.addWidget(QLabel("RH ▼:")                     , i, 2)
        grid.addWidget(self.qchk_decr_ENA_valve_1          , i, 3)      ; i+=1
        grid.addWidget(self.qchk_incr_ENA_valve_2          , i, 1)
        grid.addWidget(self.qchk_decr_ENA_valve_2          , i, 3)      ; i+=1
        grid.addWidget(self.qchk_incr_ENA_pump             , i, 1)
        grid.addWidget(self.qchk_decr_ENA_pump             , i, 3)      ; i+=1
        grid.addItem(QSpacerItem(0, 6)                     , i, 0)      ; i+=1
        grid.addWidget(QLabel("Act on:")                   , i, 0)
        grid.addWidget(self.qrbt_act_on_sensor_1           , i, 1, 1, 2); i+=1
        grid.addWidget(self.qrbt_act_on_sensor_2           , i, 1, 1, 2); i+=1
        grid.addItem(QSpacerItem(0, 4)                     , i, 0)      ; i+=1
        grid.addLayout(grid2                               , i, 0, 1, 4); i+=1
        grid.addItem(QSpacerItem(0, 4)                     , i, 0)      ; i+=1
        grid.addLayout(grid3                               , i, 0, 1, 4)
        # fmt: on

        qgrp_config = QGroupBox("Configuration")
        qgrp_config.setLayout(grid)

        #  Round up bottom frame
        # -------------------------

        hbox1 = QHBoxLayout()
        hbox1.addWidget(qgrp_control, alignment=QtCore.Qt.AlignLeft)
        hbox1.addWidget(qgrp_config, alignment=QtCore.Qt.AlignLeft)

        hbox2 = QHBoxLayout()
        hbox2.addWidget(qgrp_readings, alignment=QtCore.Qt.AlignLeft)
        hbox2.addWidget(qgrp_charts, alignment=QtCore.Qt.AlignLeft)

        vbox = QVBoxLayout()
        vbox.addLayout(hbox1)
        vbox.addLayout(hbox2)
        vbox.addWidget(qgrp_comments)

        grid_bot = QGridLayout()
        grid_bot.addWidget(self.gw, 0, 0)
        grid_bot.addLayout(vbox, 0, 1)
        grid_bot.setColumnStretch(0, 1)
        grid_bot.setColumnStretch(1, 0)

        # -------------------------
        #   Round up full window
        # -------------------------

        vbox = QVBoxLayout(self)
        vbox.addLayout(hbox_top, stretch=0)
        vbox.addSpacerItem(QSpacerItem(0, 10))
        vbox.addLayout(grid_bot, stretch=1)

        self.populate_configuration()

        # -------------------------
        #   Wall clock timer
        # -------------------------

        self.timer_wall_clock = QtCore.QTimer()
        self.timer_wall_clock.timeout.connect(self.update_wall_clock)
        self.timer_wall_clock.start(UPDATE_INTERVAL_WALL_CLOCK)

        # -------------------------
        #   Connect external signals
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

        self.qlbl_update_counter.setText("%i" % ard_qdev.update_counter_DAQ)
        self.qlbl_DAQ_rate.setText(
            "DAQ: %.1f Hz" % ard_qdev.obtained_DAQ_rate_Hz
        )
        if self.logger.is_recording():
            self.qlbl_recording_time.setText(
                "REC: %s" % self.logger.pretty_elapsed()
            )
        else:
            self.qlbl_recording_time.setText("")

        self.qlin_humi_1.setText("%.1f" % state.humi_1)
        self.qlin_temp_1.setText("%.1f" % state.temp_1)
        self.qlin_pres_1.setText("%.0f" % state.pres_1)
        self.qlin_humi_2.setText("%.1f" % state.humi_2)
        self.qlin_temp_2.setText("%.1f" % state.temp_2)
        self.qlin_pres_2.setText("%.0f" % state.pres_2)

        if state.control_band == ControlBand.Coarse:
            self.qlin_control_band.setText("COARSE")
        elif state.control_band == ControlBand.Fine:
            self.qlin_control_band.setText("FINE")
        elif state.control_band == ControlBand.Dead:
            self.qlin_control_band.setText("DEAD")

        self.qpbt_valve_1.setChecked(state.valve_1)
        self.qpbt_valve_1.setText("ON" if state.valve_1 else "OFF")
        self.qpbt_valve_2.setChecked(state.valve_2)
        self.qpbt_valve_2.setText("ON" if state.valve_2 else "OFF")
        self.qpbt_pump.setChecked(state.pump)
        self.qpbt_pump.setText("ON" if state.pump else "OFF")

        if DEBUG:
            tprint("update_charts")

        for curve in self.curves:
            curve.update()

    @QtCore.pyqtSlot()
    def populate_configuration(self):
        # Shorthands
        state = self.ard_qdev.state
        config = self.ard_qdev.config

        self.qlin_setpoint.setText("%u" % state.setpoint)

        self.qchk_incr_ENA_valve_1.setChecked(config.actors_incr_RH.ENA_valve_1)
        self.qchk_incr_ENA_valve_2.setChecked(config.actors_incr_RH.ENA_valve_2)
        self.qchk_incr_ENA_pump.setChecked(config.actors_incr_RH.ENA_pump)

        self.qchk_decr_ENA_valve_1.setChecked(config.actors_decr_RH.ENA_valve_1)
        self.qchk_decr_ENA_valve_2.setChecked(config.actors_decr_RH.ENA_valve_2)
        self.qchk_decr_ENA_pump.setChecked(config.actors_decr_RH.ENA_pump)

        self.qrbt_act_on_sensor_1.setChecked(config.act_on_sensor_no == 1)
        self.qrbt_act_on_sensor_2.setChecked(config.act_on_sensor_no == 2)

        self.qlin_fineband_dHI.setText("%+.1f" % config.fineband_dHI)
        self.qlin_fineband_dLO.setText("%+.1f" % config.fineband_dLO)
        self.qlin_deadband_dHI.setText("%+.1f" % config.deadband_dHI)
        self.qlin_deadband_dLO.setText("%+.1f" % config.deadband_dLO)
        self.qlin_burst_update_period.setText("%u" % config.burst_update_period)
        self.qlin_burst_incr_RH_length.setText(
            "%u" % config.burst_incr_RH_length
        )
        self.qlin_burst_decr_RH_length.setText(
            "%u" % config.burst_decr_RH_length
        )

    # --------------------------------------------------------------------------
    #   Handle controls
    # --------------------------------------------------------------------------

    @QtCore.pyqtSlot()
    def process_qlin_setpoint(self):
        try:
            val = int(self.qlin_setpoint.text())
        except ValueError:
            val = self.ard_qdev.state.setpoint

        val = max(val, 0)
        val = min(val, 100)
        self.qlin_setpoint.setText("%u" % val)
        self.ard_qdev.state.setpoint = val

    @QtCore.pyqtSlot()
    def process_qpbt_control_mode(self):
        if self.qpbt_control_mode.isChecked():
            # Switch to auto control
            self.qpbt_control_mode.setText("Auto control")
            self.ard_qdev.state.control_mode = ControlMode.Auto
        else:
            # Switch to manual control
            # Will automatically turn off all actuators
            self.qpbt_control_mode.setText("Manual control")
            self.ard_qdev.state.control_mode = ControlMode.Manual
            self.ard_qdev.set_actuators(False, False, False)

        flag = self.ard_qdev.state.control_mode == ControlMode.Manual
        self.qpbt_valve_1.setEnabled(flag)
        self.qpbt_valve_2.setEnabled(flag)
        self.qpbt_pump.setEnabled(flag)
        self.qpbt_burst_incr_RH.setEnabled(flag)
        self.qpbt_burst_decr_RH.setEnabled(flag)

    @QtCore.pyqtSlot(bool)
    def process_qchk_incr_ENA_valve_1(self, checked: bool):
        self.ard_qdev.config.actors_incr_RH.ENA_valve_1 = checked

    @QtCore.pyqtSlot(bool)
    def process_qchk_incr_ENA_valve_2(self, checked: bool):
        self.ard_qdev.config.actors_incr_RH.ENA_valve_2 = checked

    @QtCore.pyqtSlot(bool)
    def process_qchk_incr_ENA_pump(self, checked: bool):
        self.ard_qdev.config.actors_incr_RH.ENA_pump = checked

    @QtCore.pyqtSlot(bool)
    def process_qchk_decr_ENA_valve_1(self, checked: bool):
        self.ard_qdev.config.actors_decr_RH.ENA_valve_1 = checked

    @QtCore.pyqtSlot(bool)
    def process_qchk_decr_ENA_valve_2(self, checked: bool):
        self.ard_qdev.config.actors_decr_RH.ENA_valve_2 = checked

    @QtCore.pyqtSlot(bool)
    def process_qchk_decr_ENA_pump(self, checked: bool):
        self.ard_qdev.config.actors_decr_RH.ENA_pump = checked

    @QtCore.pyqtSlot(bool)
    def process_qrbt_act_on_sensor_1(self, checked: bool):
        self.ard_qdev.config.act_on_sensor_no = 1 if checked else 2

    @QtCore.pyqtSlot(bool)
    def process_qrbt_act_on_sensor_2(self, checked: bool):
        self.ard_qdev.config.act_on_sensor_no = 2 if checked else 1

    @QtCore.pyqtSlot()
    def process_qlin_fineband_dLO(self):
        try:
            val = float(self.qlin_fineband_dLO.text())
        except ValueError:
            val = self.ard_qdev.config.fineband_dLO

        val = -(abs(val))
        self.qlin_fineband_dLO.setText("%+.1f" % val)
        self.ard_qdev.config.fineband_dLO = val

    @QtCore.pyqtSlot()
    def process_qlin_fineband_dHI(self):
        try:
            val = float(self.qlin_fineband_dHI.text())
        except ValueError:
            val = self.ard_qdev.config.fineband_dHI

        val = max(val, 0)
        self.qlin_fineband_dHI.setText("%+.1f" % val)
        self.ard_qdev.config.fineband_dHI = val

    @QtCore.pyqtSlot()
    def process_qlin_deadband_dLO(self):
        try:
            val = float(self.qlin_deadband_dLO.text())
        except ValueError:
            val = self.ard_qdev.config.deadband_dLO

        val = -(abs(val))
        self.qlin_deadband_dLO.setText("%+.1f" % val)
        self.ard_qdev.config.deadband_dLO = val

    @QtCore.pyqtSlot()
    def process_qlin_deadband_dHI(self):
        try:
            val = float(self.qlin_deadband_dHI.text())
        except ValueError:
            val = self.ard_qdev.config.deadband_dHI

        val = max(val, 0)
        self.qlin_deadband_dHI.setText("%+.1f" % val)
        self.ard_qdev.config.deadband_dHI = val

    @QtCore.pyqtSlot()
    def process_qlin_burst_update_period(self):
        try:
            val = int(self.qlin_burst_update_period.text())
        except ValueError:
            val = self.ard_qdev.config.burst_update_period

        val = max(val, 1)
        self.qlin_burst_update_period.setText("%u" % val)
        self.ard_qdev.config.burst_update_period = val

    @QtCore.pyqtSlot()
    def process_qlin_burst_incr_RH_length(self):
        try:
            val = int(self.qlin_burst_incr_RH_length.text())
        except ValueError:
            val = self.ard_qdev.config.burst_incr_RH_length

        val = max(val, 500)
        self.qlin_burst_incr_RH_length.setText("%u" % val)
        self.ard_qdev.config.burst_incr_RH_length = val

    @QtCore.pyqtSlot()
    def process_qlin_burst_decr_RH_length(self):
        try:
            val = int(self.qlin_burst_decr_RH_length.text())
        except ValueError:
            val = self.ard_qdev.config.burst_decr_RH_length

        val = max(val, 500)
        self.qlin_burst_decr_RH_length.setText("%u" % val)
        self.ard_qdev.config.burst_decr_RH_length = val

    # --------------------------------------------------------------------------
    #   Configuration files
    # --------------------------------------------------------------------------

    def save_config_to_file(self, as_default: bool = True):
        config = self.ard_qdev.config  # Shorthand

        cp = ConfigParser()
        cp.optionxform = lambda option: option  # Preserve letter case

        descr = "Humidistat"
        cp.add_section(descr)
        tmp = config.actors_incr_RH
        cp.set(descr, "actors_incr_RH_ENA_valve_1", str(tmp.ENA_valve_1))
        cp.set(descr, "actors_incr_RH_ENA_valve_2", str(tmp.ENA_valve_2))
        cp.set(descr, "actors_incr_RH_ENA_pump", str(tmp.ENA_pump))
        tmp = config.actors_decr_RH
        cp.set(descr, "actors_decr_RH_ENA_valve_1", str(tmp.ENA_valve_1))
        cp.set(descr, "actors_decr_RH_ENA_valve_2", str(tmp.ENA_valve_2))
        cp.set(descr, "actors_decr_RH_ENA_pump", str(tmp.ENA_pump))
        cp.set(descr, "act_on_sensor_no", str(config.act_on_sensor_no))
        cp.set(descr, "fineband_dHI", str(config.fineband_dHI))
        cp.set(descr, "fineband_dLO", str(config.fineband_dLO))
        cp.set(descr, "deadband_dHI", str(config.deadband_dHI))
        cp.set(descr, "deadband_dLO", str(config.deadband_dLO))
        cp.set(descr, "burst_update_period", str(config.burst_update_period))
        cp.set(descr, "burst_incr_RH_length", str(config.burst_incr_RH_length))
        cp.set(descr, "burst_decr_RH_length", str(config.burst_decr_RH_length))

        if as_default:
            fn = DEFAULT_CONFIG_FILE
        else:  # Ask user for filename
            suggested_name = (
                "humidistat_config_%s.ini"
                % QDateTime.currentDateTime().toString("yyMMdd_HHmmss")
            )
            options = QFileDialog.Options()
            # options |= QFileDialog.DontUseNativeDialog
            fn, _ = QFileDialog.getSaveFileName(
                self,
                caption="Save Humidistat configuration to file",
                directory=suggested_name,
                filter="Configuration files (*.ini);;All Files (*)",
                options=options,
            )
            if not fn:
                return

        fn = Path(fn)
        try:
            with open(fn, "w") as f:
                cp.write(f)
        except Exception as err:  # pylint: disable=broad-except
            dprint("ERROR: Failed to write configuration to file")
            pft(err)
        else:
            dprint("Succesfully saved configuration file: %s" % fn)

    def load_config_from_file(self, from_default=True):
        config = self.ard_qdev.config  # Shorthand

        if from_default:
            fn = DEFAULT_CONFIG_FILE
        else:  # Ask user for filename
            options = QFileDialog.Options()
            # options |= QFileDialog.DontUseNativeDialog
            fn, _ = QFileDialog.getOpenFileName(
                self,
                caption="Load Humidistat configuration from file",
                directory="",
                filter="Configuration files (*.ini);;All Files (*)",
                options=options,
            )
            if not fn:
                return

        fn = Path(fn)
        cp = ConfigParser()
        try:
            cp.read(fn)
        except Exception as err:  # pylint: disable=broad-except
            dprint("ERROR: Failed to load configuration from file")
            pft(err)
            return

        try:
            descr = "Humidistat"
            config.actors_incr_RH.ENA_valve_1 = cp.getboolean(
                descr, "actors_incr_RH_ENA_valve_1"
            )
            config.actors_incr_RH.ENA_valve_2 = cp.getboolean(
                descr, "actors_incr_RH_ENA_valve_2"
            )
            config.actors_incr_RH.ENA_pump = cp.getboolean(
                descr, "actors_incr_RH_ENA_pump"
            )
            config.actors_decr_RH.ENA_valve_1 = cp.getboolean(
                descr, "actors_decr_RH_ENA_valve_1"
            )
            config.actors_decr_RH.ENA_valve_2 = cp.getboolean(
                descr, "actors_decr_RH_ENA_valve_2"
            )
            config.actors_decr_RH.ENA_pump = cp.getboolean(
                descr, "actors_decr_RH_ENA_pump"
            )
            config.act_on_sensor_no = cp.getint(descr, "act_on_sensor_no")
            config.fineband_dHI = cp.getfloat(descr, "fineband_dHI")
            config.fineband_dLO = cp.getfloat(descr, "fineband_dLO")
            config.deadband_dHI = cp.getfloat(descr, "deadband_dHI")
            config.deadband_dLO = cp.getfloat(descr, "deadband_dLO")
            config.burst_update_period = cp.getint(descr, "burst_update_period")
            config.burst_incr_RH_length = cp.getint(
                descr, "burst_incr_RH_length"
            )
            config.burst_decr_RH_length = cp.getint(
                descr, "burst_decr_RH_length"
            )
        except Exception as err:  # pylint: disable=broad-except
            dprint("ERROR: Failed to load configuration from file")
            pft(err)
        else:
            dprint("Succesfully loaded configuration file: %s" % fn)
            self.populate_configuration()
