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

from ctypes import alignment
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import QDateTime
from PyQt5.QtWidgets import (
    QCheckBox,
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
from dvg_debug_functions import tprint
from dvg_pyqt_filelogger import FileLogger
from dvg_pyqtgraph_threadsafe import (
    HistoryChartCurve,
    LegendSelect,
    PlotManager,
)

from dvg_devices.Arduino_protocol_serial import Arduino
from humidistat_qdev import Humidistat_qdev, ControlMode


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
        config = self.ard_qdev.config

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
        self.qlbl_update_counter = QLabel("0")
        self.qlbl_DAQ_rate = QLabel("DAQ: nan Hz")
        self.qlbl_DAQ_rate.setStyleSheet("QLabel {min-width: 7em}")

        vbox_left = QVBoxLayout()
        vbox_left.addWidget(self.qlbl_update_counter, stretch=0)
        vbox_left.addStretch(1)
        vbox_left.addWidget(self.qlbl_DAQ_rate, stretch=0)

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
        self.qpbt_exit = QPushButton("Exit")
        self.qpbt_exit.clicked.connect(self.close)
        self.qpbt_exit.setMinimumHeight(30)
        self.qlbl_recording_time = QLabel(alignment=QtCore.Qt.AlignRight)

        vbox_right = QVBoxLayout()
        vbox_right.addWidget(self.qpbt_exit, stretch=0)
        vbox_right.addStretch(1)
        vbox_right.addWidget(self.qlbl_recording_time, stretch=0)

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
        )
        PEN_01 = pg.mkPen(controls.COLOR_PEN_TURQUOISE, width=3)
        PEN_02 = pg.mkPen(controls.COLOR_PEN_YELLOW, width=3)
        PEN_03 = pg.mkPen(controls.COLOR_PEN_PINK, width=3)

        self.curve_humi_1 = HistoryChartCurve(
            capacity=capacity,
            linked_curve=self.pi_humi.plot(pen=PEN_01, name="H_1"),
        )
        self.curve_temp_1 = HistoryChartCurve(
            capacity=capacity,
            linked_curve=self.pi_temp.plot(pen=PEN_01, name="T_1"),
        )
        self.curve_pres_1 = HistoryChartCurve(
            capacity=capacity,
            linked_curve=self.pi_pres.plot(pen=PEN_01, name="P_1"),
        )
        self.curve_humi_2 = HistoryChartCurve(
            capacity=capacity,
            linked_curve=self.pi_humi.plot(pen=PEN_02, name="H_2"),
        )
        self.curve_temp_2 = HistoryChartCurve(
            capacity=capacity,
            linked_curve=self.pi_temp.plot(pen=PEN_02, name="T_2"),
        )
        self.curve_pres_2 = HistoryChartCurve(
            capacity=capacity,
            linked_curve=self.pi_pres.plot(pen=PEN_02, name="P_2"),
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
        self.qlin_setpoint = QLineEdit("50", **p)

        # Operating band: 'COARSE', 'FINE' or 'DEAD'
        self.qlin_band = QLineEdit(
            "COARSE",
            readOnly=True,
            maximumWidth=80,
            alignment=QtCore.Qt.AlignHCenter,
        )

        self.qpbt_control_mode = controls.create_Toggle_button("Manual control")
        self.qpbt_control_mode.clicked.connect(self.process_qpbt_control_mode)

        self.qpbt_valve_1 = controls.create_Toggle_button(maximumWidth=80)
        self.qpbt_valve_2 = controls.create_Toggle_button(maximumWidth=80)
        self.qpbt_pump = controls.create_Toggle_button(maximumWidth=80)

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

        self.qpbt_burst_incr = QPushButton("RH ▲ burst")
        self.qpbt_burst_decr = QPushButton("RH ▼ burst")
        self.qpbt_burst_incr.clicked.connect(ard_qdev.burst_valve_1)
        self.qpbt_burst_decr.clicked.connect(ard_qdev.burst_valve_2)

        # fmt: off
        i = 0
        grid = QGridLayout(spacing=4)
        grid.addWidget(QLabel("Setpoint:")   , i, 0)
        grid.addWidget(self.qlin_setpoint    , i, 1)
        grid.addWidget(QLabel("% RH")        , i, 2)      ; i +=1
        grid.addWidget(QLabel("Band:")       , i, 0)
        grid.addWidget(self.qlin_band        , i, 1, 1, 2); i +=1
        grid.addItem(QSpacerItem(0, 8)       , i, 0)      ; i +=1
        grid.addWidget(self.qpbt_control_mode, i, 0, 1, 3); i +=1
        grid.addWidget(QLabel("valve 1")     , i, 0)
        grid.addWidget(self.qpbt_valve_1     , i, 1, 1, 2); i +=1
        grid.addWidget(QLabel("valve 2")     , i, 0)
        grid.addWidget(self.qpbt_valve_2     , i, 1, 1, 2); i +=1
        grid.addWidget(QLabel("pump")        , i, 0)
        grid.addWidget(self.qpbt_pump        , i, 1, 1, 2); i +=1
        grid.addItem(QSpacerItem(0, 6)       , i, 0)      ; i +=1
        grid.addWidget(self.qpbt_burst_incr  , i, 0, 1, 3); i +=1
        grid.addWidget(self.qpbt_burst_decr  , i, 0, 1, 3); i +=1
        # fmt: on

        qgrp_control = QGroupBox("Control")
        qgrp_control.setLayout(grid)

        #  Group 'Config'
        # -------------------------

        # fmt: off
        p = {"maximumWidth": ex10}
        self.qchk_incr_RH_valve_1 = QCheckBox("valve 1", **p)
        self.qchk_incr_RH_valve_2 = QCheckBox("valve 2", **p)
        self.qchk_incr_RH_pump    = QCheckBox("pump"   , **p)
        self.qchk_decr_RH_valve_1 = QCheckBox("valve 1", **p)
        self.qchk_decr_RH_valve_2 = QCheckBox("valve 2", **p)
        self.qchk_decr_RH_pump    = QCheckBox("pump"   , **p)
        self.qrbt_act_on_sensor_1 = QRadioButton("sensor 1")
        self.qrbt_act_on_sensor_2 = QRadioButton("sensor 2")
        # fmt: on

        p = {"maximumWidth": ex8, "alignment": QtCore.Qt.AlignRight}
        self.qlin_fineband_delta_HI = QLineEdit("+2.0", **p)
        self.qlin_fineband_delta_LO = QLineEdit("-2.0", **p)
        self.qlin_deadband_delta_HI = QLineEdit("+0.5", **p)
        self.qlin_deadband_delta_LO = QLineEdit("-0.5", **p)
        self.qlin_burst_update_period = QLineEdit("10", **p)
        self.qlin_incr_RH_burst_duration = QLineEdit("500", **p)
        self.qlin_decr_RH_burst_duration = QLineEdit("1000", **p)

        # fmt: off
        i = 0
        grid2 = QGridLayout(spacing=4)
        grid2.addWidget(QLabel("<b>Control bandwidths</b>"), i, 0, 1, 3); i+=1
        grid2.addWidget(QLabel("Fine-band:")             , i, 0)
        grid2.addWidget(self.qlin_fineband_delta_LO      , i, 1)
        grid2.addWidget(self.qlin_fineband_delta_HI      , i, 2)
        grid2.addWidget(QLabel("% RH")                   , i, 3)      ; i+=1
        grid2.addWidget(QLabel("Dead-band:")             , i, 0)
        grid2.addWidget(self.qlin_deadband_delta_LO      , i, 1)
        grid2.addWidget(self.qlin_deadband_delta_HI      , i, 2)
        grid2.addWidget(QLabel("% RH")                   , i, 3)      ; i+=1
        grid2.addItem(QSpacerItem(0, 6)                  , i, 0)      ; i+=1
        grid2.addWidget(QLabel("<b>Fine-band bursts</b>"), i, 0, 1, 3); i+=1
        grid2.addWidget(QLabel("Update period:")         , i, 0, 1, 2)
        grid2.addWidget(self.qlin_burst_update_period    , i, 2)
        grid2.addWidget(QLabel("s")                      , i, 3)      ; i+=1
        grid2.addWidget(QLabel("RH ▲ burst length:")     , i, 0, 1, 2)
        grid2.addWidget(self.qlin_incr_RH_burst_duration , i, 2)
        grid2.addWidget(QLabel("ms")                     , i, 3)      ; i+=1
        grid2.addWidget(QLabel("RH ▼ burst length:")     , i, 0, 1, 2)
        grid2.addWidget(self.qlin_decr_RH_burst_duration , i, 2)
        grid2.addWidget(QLabel("ms")                     , i, 3)      ; i+=1

        i = 0
        grid = QGridLayout(spacing=4)
        grid.addWidget(QLabel("<b>Assign actuators</b>"), i, 0, 1, 3); i+=1
        grid.addWidget(QLabel("RH ▲:")                  , i, 0)
        grid.addWidget(self.qchk_incr_RH_valve_1        , i, 1)
        grid.addWidget(QLabel("RH ▼:")                  , i, 2)
        grid.addWidget(self.qchk_decr_RH_valve_1        , i, 3)      ; i+=1
        grid.addWidget(self.qchk_incr_RH_valve_2        , i, 1)
        grid.addWidget(self.qchk_decr_RH_valve_2        , i, 3)      ; i+=1
        grid.addWidget(self.qchk_incr_RH_pump           , i, 1)
        grid.addWidget(self.qchk_decr_RH_pump           , i, 3)      ; i+=1
        grid.addItem(QSpacerItem(0, 6)                  , i, 0)      ; i+=1
        grid.addWidget(QLabel("Act on:")                , i, 0)
        grid.addWidget(self.qrbt_act_on_sensor_1        , i, 1, 1, 2); i+=1
        grid.addWidget(self.qrbt_act_on_sensor_2        , i, 1, 1, 2); i+=1
        grid.addItem(QSpacerItem(0, 6)                  , i, 0)      ; i+=1
        grid.addLayout(grid2                            , i, 0, 1, 4)

        # fmt: on

        qgrp_config = QGroupBox("Configuration")
        qgrp_config.setLayout(grid)

        #  Round up bottom frame
        # -------------------------

        hbox1 = QHBoxLayout()
        hbox1.addWidget(
            qgrp_readings, alignment=QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop
        )
        hbox1.addWidget(
            qgrp_control, alignment=QtCore.Qt.AlignLeft  # | QtCore.Qt.AlignTop
        )

        hbox2 = QHBoxLayout()
        hbox2.addWidget(
            qgrp_charts, alignment=QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop
        )
        hbox2.addWidget(
            qgrp_config, alignment=(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        )

        vbox = QVBoxLayout()
        vbox.addWidget(qgrp_comments)
        vbox.addLayout(hbox1)
        vbox.addLayout(hbox2)

        # fmt: off
        grid_bot = QGridLayout()
        grid_bot.addWidget(self.gw, 0, 0)
        grid_bot.addLayout(vbox   , 0, 1)
        # fmt: on
        grid_bot.setColumnStretch(0, 1)
        grid_bot.setColumnStretch(1, 0)
        # grid_bot.setAlignment(qgrp_control, QtCore.Qt.AlignLeft)

        # -------------------------
        #   Round up full window
        # -------------------------

        vbox = QVBoxLayout(self)
        vbox.addLayout(hbox_top, stretch=0)
        vbox.addSpacerItem(QSpacerItem(0, 10))
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

        self.qlin_humi_1.setText("%.1f" % state.humi_1)
        self.qlin_temp_1.setText("%.1f" % state.temp_1)
        self.qlin_pres_1.setText("%.0f" % state.pres_1)
        self.qlin_humi_2.setText("%.1f" % state.humi_2)
        self.qlin_temp_2.setText("%.1f" % state.temp_2)
        self.qlin_pres_2.setText("%.0f" % state.pres_2)

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
    def process_qpbt_control_mode(self):
        if self.qpbt_control_mode.isChecked():
            # Switch to auto control
            self.qpbt_control_mode.setText("Auto control")
            self.ard_qdev.state.control_mode = ControlMode.Auto_Coarse
        else:
            # Switch to manual control
            self.qpbt_control_mode.setText("Manual control")
            self.ard_qdev.state.control_mode = ControlMode.Manual
            self.ard_qdev.turn_valve_1_off()
            self.ard_qdev.turn_valve_2_off()
            self.ard_qdev.turn_pump_off()

        flag = self.ard_qdev.state.control_mode == ControlMode.Manual
        self.qpbt_valve_1.setEnabled(flag)
        self.qpbt_valve_2.setEnabled(flag)
        self.qpbt_pump.setEnabled(flag)
        self.qpbt_burst_incr.setEnabled(flag)
        self.qpbt_burst_decr.setEnabled(flag)
