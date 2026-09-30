"""Offline GUI only: no MAVLink connection, SITL launch or evidence writes."""
import bisect
import sys
import time
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets
import numpy as np
import pyqtgraph as pg

from .data import discover_runs, load_replay

ROOT = Path(__file__).resolve().parents[1]
COLORS = ["#48d5be", "#68aaff", "#ffbe64", "#de90ed", "#fa839c", "#b5d66f"]
PHASE_NAMES = {"approach": "进入", "observe": "观察", "return": "返回"}
EVENT_NAMES = {
    "connected": "已连接", "armed_confirmed": "已解锁", "takeoff_command_sent": "起飞",
    "airborne_ready": "起飞就绪", "phase_start_sent": "开始阶段", "phase_auto_confirmed": "AUTO 确认",
    "phase_finished": "航点完成", "task_target_verified": "到位确认", "landing_started": "降落",
    "landed_confirmed": "已落地", "run_failed": "运行失败", "phase_release_scheduled": "调度下一阶段",
}


class LoadWorker(QtCore.QThread):
    loaded = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            self.loaded.emit(load_replay(self.path))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def result_word(value):
    return "通过" if value is True else "未通过" if value is False else "未知 / 未提供"


def configure_application(app):
    # Qt's offscreen Windows plugin may expose no system font families. Load an
    # existing local font for render verification; never download/install fonts.
    if not QtGui.QFontDatabase().families():
        font = Path("C:/Windows/Fonts/msyh.ttc")
        if font.exists():
            QtGui.QFontDatabase.addApplicationFont(str(font))
    app.setFont(QtGui.QFont("Microsoft YaHei UI", 9))
    pg.setConfigOptions(antialias=True)


class ReplayWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SwarmTaskSim · 离线回放与计划预览")
        self.resize(1440, 920)
        self.setMinimumSize(1040, 700)
        self.data = None
        self.worker = None
        self.playing = False
        self.current_t = 0.0
        self.graphics = {}
        self.arrays = {}
        self.event_times = []
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.last_tick = time.perf_counter()
        self._build()
        self.refresh_runs()
        self.set_transport_enabled(False)

    def _build(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #111c2d; color: #e2eaf5; font-size: 13px; }
            QPushButton { background: #24344c; border: 1px solid #3a4a62; border-radius: 5px; padding: 7px 12px; }
            QPushButton:hover { background: #344967; } QPushButton:disabled { color: #6c7a8b; border-color: #283447; }
            QPushButton#primary { background: #167e70; border-color: #299987; }
            QComboBox, QDoubleSpinBox { background: #1b2a40; border: 1px solid #3a4a62; padding: 5px; }
            QListWidget, QPlainTextEdit, QTableWidget { background: #17253a; border: 1px solid #2e3e55; }
            QHeaderView::section { background: #24344c; padding: 6px; border: none; }
            QTabBar::tab { background: #24344c; padding: 8px 14px; } QTabBar::tab:selected { background: #36516c; }
            QSlider::groove:horizontal { height: 5px; background: #344760; }
            QSlider::handle:horizontal { width: 13px; margin: -5px 0; border-radius: 6px; background: #48d5be; }
            QToolTip { background: #263c55; color: white; border: none; }
        """)
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(18, 14, 18, 12)
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("SwarmTaskSim  /  REPLAY")
        title.setStyleSheet("font-size: 23px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch()
        tag = QtWidgets.QLabel("离线查看 · 本机数据 · 不连接飞控")
        tag.setStyleSheet("color: #70dcc7;")
        header.addWidget(tag)
        layout.addLayout(header)
        toolbar = QtWidgets.QHBoxLayout()
        self.open_plan = QtWidgets.QPushButton("打开任务 / 场景")
        self.open_run = QtWidgets.QPushButton("打开运行目录")
        self.demo = QtWidgets.QPushButton("三机示例")
        self.open_plan.clicked.connect(self.pick_plan)
        self.open_run.clicked.connect(self.pick_run)
        self.demo.clicked.connect(self.load_demo)
        self.runs = QtWidgets.QComboBox()
        self.runs.setMinimumWidth(240)
        self.runs.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.runs.setToolTip("当前工程已有记录；也可以打开其他已结束的运行目录")
        self.load_selected = QtWidgets.QPushButton("加载记录")
        self.load_selected.clicked.connect(lambda: self.load_path(self.runs.currentData()) if self.runs.currentData() else None)
        self.refresh = QtWidgets.QPushButton("刷新列表")
        self.refresh.clicked.connect(self.refresh_runs)
        for widget in (self.open_plan, self.open_run, self.demo, self.runs, self.load_selected, self.refresh):
            toolbar.addWidget(widget, 1 if widget is self.runs else 0)
        self.load_controls = [self.open_plan, self.open_run, self.demo, self.runs, self.load_selected, self.refresh]
        layout.addLayout(toolbar)
        self.source = QtWidgets.QLabel("打开任务可预览计划；打开历史运行可回放实际轨迹。")
        self.source.setTextFormat(QtCore.Qt.PlainText)
        self.source.setWordWrap(True)
        self.source.setStyleSheet("color: #a4b7cd; padding: 4px 0;")
        layout.addWidget(self.source)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 10, 0)
        layers = QtWidgets.QHBoxLayout()
        self.plan_check = QtWidgets.QCheckBox("计划虚线")
        self.partition_check = QtWidgets.QCheckBox("责任分区")
        self.trail_check = QtWidgets.QCheckBox("历史尾迹")
        self.full_check = QtWidgets.QCheckBox("显示全程轨迹")
        for box in (self.plan_check, self.partition_check, self.trail_check, self.full_check):
            box.setChecked(box is not self.full_check)
            box.toggled.connect(self.redraw)
            layers.addWidget(box)
        layers.addStretch()
        fit = QtWidgets.QPushButton("适应全图")
        fit.clicked.connect(self.fit_view)
        layers.addWidget(fit)
        left_layout.addLayout(layers)
        graphs = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.map = pg.PlotWidget(background="#0d1726")
        self.map.setLabel("bottom", "东 East", units="m")
        self.map.setLabel("left", "北 North", units="m")
        self.map.setAspectLocked(True)
        self.map.showGrid(x=True, y=True, alpha=0.14)
        self.map.setTitle("俯视轨迹 · ENU 局部坐标", color="#c6d8ec", size="13pt")
        self.map.setMenuEnabled(False)
        self.map.getPlotItem().hideButtons()
        graphs.addWidget(self.map)
        self.height = pg.PlotWidget(background="#0d1726")
        self.height.setLabel("bottom", "运行时间", units="s")
        self.height.setLabel("left", "高度 Up", units="m")
        self.height.setTitle("全程高度曲线 · 竖线为当前回放位置", color="#a4b7cd", size="10pt")
        self.height.showGrid(x=True, y=True, alpha=0.14)
        self.height.setMenuEnabled(False)
        self.height.getPlotItem().hideButtons()
        graphs.addWidget(self.height)
        graphs.setSizes([560, 180])
        left_layout.addWidget(graphs, 1)
        note = QtWidgets.QLabel("颜色对应飞机  ·  淡色矩形是责任区，不是已覆盖区域  ·  轨迹缺口不补线")
        note.setStyleSheet("color: #90a4bd; font-size: 12px;")
        left_layout.addWidget(note)
        splitter.addWidget(left)
        side = QtWidgets.QWidget()
        side.setMinimumWidth(310)
        side_layout = QtWidgets.QVBoxLayout(side)
        side_layout.setContentsMargins(4, 0, 0, 0)
        self.state = QtWidgets.QLabel("尚未加载")
        self.state.setStyleSheet("font-size: 17px; font-weight: 600; color: #70dcc7;")
        self.state.setWordWrap(True)
        side_layout.addWidget(self.state)
        self.agent_list = QtWidgets.QListWidget()
        self.agent_list.setMaximumHeight(145)
        self.agent_list.itemChanged.connect(self.redraw)
        side_layout.addWidget(self.agent_list)
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["飞机", "位置状态", "高度 m", "速度 m/s"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.table.setMaximumHeight(225)
        side_layout.addWidget(self.table)
        tabs = QtWidgets.QTabWidget()
        self.details = QtWidgets.QPlainTextEdit()
        self.details.setReadOnly(True)
        self.event_list = QtWidgets.QListWidget()
        self.event_list.setToolTip("双击事件跳转；记录表示执行事件，不代表轨迹推断出的行为")
        self.event_list.itemDoubleClicked.connect(lambda item: self.seek(item.data(QtCore.Qt.UserRole)))
        tabs.addTab(self.details, "任务 / 结果")
        tabs.addTab(self.event_list, "执行事件")
        side_layout.addWidget(tabs, 1)
        splitter.addWidget(side)
        splitter.setSizes([1030, 360])
        layout.addWidget(splitter, 1)
        transport = QtWidgets.QHBoxLayout()
        self.play = QtWidgets.QPushButton("播放")
        self.play.setObjectName("primary")
        self.play.clicked.connect(self.toggle_play)
        self.rewind = QtWidgets.QPushButton("回到开头")
        self.rewind.clicked.connect(lambda: self.seek(0.0))
        self.mission = QtWidgets.QPushButton("任务开始")
        self.mission.clicked.connect(lambda: self.seek(self.data.mission_start) if self.data else None)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setRange(0, 10000)
        self.slider.sliderPressed.connect(lambda: self.set_playing(False))
        self.slider.valueChanged.connect(self.slider_changed)
        self.time_box = QtWidgets.QDoubleSpinBox()
        self.time_box.setDecimals(2)
        self.time_box.setSuffix(" s")
        self.time_box.setFixedWidth(113)
        self.time_box.valueChanged.connect(self.seek)
        self.duration_label = QtWidgets.QLabel("/ 0.00 s")
        self.speed = QtWidgets.QComboBox()
        for multiplier in (0.25, 0.5, 1, 2, 4, 8):
            self.speed.addItem(f"{multiplier}×", multiplier)
        self.speed.setCurrentIndex(2)
        self.speed.setToolTip("只改变回放速度，不改变记录中的时间或位置")
        for w in (self.play, self.rewind, self.mission, self.slider, self.time_box, self.duration_label, self.speed):
            transport.addWidget(w, 1 if w is self.slider else 0)
        layout.addLayout(transport)
        self.statusBar().showMessage("就绪")

    def refresh_runs(self):
        self.runs.clear()
        for path in discover_runs(ROOT):
            self.runs.addItem(path.name, str(path))
        self.load_selected.setEnabled(self.runs.count() > 0)

    def pick_plan(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "打开任务或执行场景", str(ROOT / "missions"), "JSON (*.json)")
        if path:
            self.load_path(path)

    def pick_run(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择包含 metadata.json 和 samples.csv 的运行目录", str(ROOT / "verification"))
        if path:
            self.load_path(path)

    def load_demo(self):
        preferred = ROOT / "verification/v03_integration_20260930/runs/recon_shared_demo_3uav_20260930T152031Z_08eff45d"
        self.load_path(preferred if preferred.exists() else ROOT / "missions/recon_shared_3uav.json")

    def load_path(self, path):
        if self.worker and self.worker.isRunning():
            return
        self.set_playing(False)
        for widget in self.load_controls:
            widget.setEnabled(False)
        self.statusBar().showMessage("正在读取记录……")
        self.worker = LoadWorker(path, self)
        self.worker.loaded.connect(self.apply_data)
        self.worker.failed.connect(self.load_error)
        self.worker.finished.connect(self.load_finished)
        self.worker.start()

    def load_error(self, error):
        self.statusBar().showMessage("加载失败；此前显示的数据保持不变")
        QtWidgets.QMessageBox.warning(self, "无法加载", error)

    def load_finished(self):
        self.worker.deleteLater()
        self.worker = None
        for widget in self.load_controls:
            widget.setEnabled(True)
        self.load_selected.setEnabled(self.runs.count() > 0)

    def apply_data(self, replay):
        self.set_playing(False)
        self.data = replay
        self.current_t = 0.0
        selected = self.runs.findData(str(replay.path))
        self.runs.setCurrentIndex(selected)
        self.source.setText(str(replay.path))
        self.map.clear()
        self.height.clear()
        self.graphics.clear()
        self.arrays.clear()
        self.agent_list.blockSignals(True)
        self.agent_list.clear()
        self.table.setRowCount(len(replay.agent_ids))
        scene = replay.scene
        partitions = {p["id"]: p for p in scene.get("planning", {}).get("region_partitions", [])}
        assignments = scene.get("planning", {}).get("agent_to_partition", {})
        for row, vehicle in enumerate(scene["vehicles"]):
            agent = vehicle["id"]
            color = COLORS[row % len(COLORS)]
            item = QtWidgets.QListWidgetItem(f"{agent}   ·   {assignments.get(agent, '独立路线')}")
            item.setForeground(QtGui.QColor(color))
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked)
            self.agent_list.addItem(item)
            for col in range(4):
                self.table.setItem(row, col, QtWidgets.QTableWidgetItem(agent if col == 0 else "—"))
            self.table.item(row, 0).setForeground(QtGui.QColor(color))
            route = [(vehicle["east_m"], vehicle["north_m"])] + [
                (p["targets"][agent]["east_m"], p["targets"][agent]["north_m"]) for p in scene["phases"]]
            plan = self.map.plot([p[0] for p in route], [p[1] for p in route],
                                 pen=pg.mkPen(color, width=1.4, style=QtCore.Qt.DashLine))
            start = self.map.plot([vehicle["east_m"]], [vehicle["north_m"]], pen=None,
                                  symbol="s", symbolSize=8, symbolBrush="#142438", symbolPen=color)
            trail = self.map.plot([], [], pen=pg.mkPen(color, width=2.4), connect="finite")
            marker = self.map.plot([], [], pen=None, symbol="o", symbolSize=13, symbolBrush=color, symbolPen="#f0f6ff")
            label = pg.TextItem(agent, color=color, anchor=(0, 1))
            self.map.addItem(label)
            partition = None
            if assignments.get(agent) in partitions:
                p = partitions[assignments[agent]]
                partition = QtWidgets.QGraphicsRectItem(p["min_east_m"], p["min_north_m"], p["width_m"], p["height_m"])
                fill = QtGui.QColor(color)
                fill.setAlpha(20)
                partition.setBrush(fill)
                partition.setPen(pg.mkPen(color, width=1))
                partition.setZValue(-5)
                self.map.addItem(partition)
            track = replay.tracks.get(agent)
            arrays = tuple(np.asarray(a, dtype=float) for a in track.plot_points(replay.max_gap)) if track else tuple(np.array([]) for _ in range(4))
            self.arrays[agent] = arrays
            altitude = self.height.plot(arrays[0], arrays[3], pen=pg.mkPen(color, width=1.7), connect="finite")
            self.graphics[agent] = dict(plan=plan, start=start, trail=trail, marker=marker, label=label, partition=partition, altitude=altitude)
        self.agent_list.blockSignals(False)
        self.cursor = pg.InfiniteLine(0, angle=90, pen=pg.mkPen("#f1f5fc", width=1.5))
        self.height.addItem(self.cursor)
        self.event_list.clear()
        self.event_times = [e["t"] for e in replay.events]
        for event in replay.events:
            item = QtWidgets.QListWidgetItem(f"{event['t']:7.2f}s  {event.get('agent_id') or '群'}  {EVENT_NAMES.get(event['event'], event['event'])} {event.get('phase', '')}")
            item.setData(QtCore.Qt.UserRole, event["t"])
            item.setToolTip(str(event))
            self.event_list.addItem(item)
        self.time_box.setRange(0, replay.duration)
        self.duration_label.setText(f"/ {replay.duration:.2f} s")
        self.show_details()
        self.set_transport_enabled(replay.is_run and any(t.samples for t in replay.tracks.values()) and replay.duration > 0)
        self.seek(0.0)
        self.fit_view()
        self.statusBar().showMessage(f"已加载 · {len(replay.agent_ids)} 架 · {'历史 FCU 观测（非 SIM 真值）' if replay.is_run else '仅计划预览，未执行仿真'}" + (f" · {len(replay.warnings)} 条提示，见任务 / 结果" if replay.warnings else ""))

    def show_details(self):
        d = self.data
        task = d.scene.get("task_spec", {})
        mission = task.get("mission", {})
        text = [f"场景：{d.scene['scenario_id']}", f"飞机：{len(d.agent_ids)} 架", f"执行阶段：{len(d.scene['phases'])}"]
        if mission:
            text += ["任务：共享区域观察", f"要求覆盖：{mission['coverage_required']:.0%}", f"要求返回：{'是' if mission['return_required'] else '否'}"]
        if d.is_run:
            text += ["", f"记录状态：{d.metadata.get('status', '未知')}", "位置来源：samples.csv / FCU 估计", "时间：从运行启动起的主机相对秒", "显示：最近有效样本；不插值补缺口"]
            if d.metadata.get("error"):
                text += [f"运行错误：{d.metadata['error']}"]
            if d.analysis_name:
                text += ["", "已保存的最终分析（不是当前时刻结果）", f"SIM 任务：{result_word(d.labels.get('mission_success'))}", f"FCU 任务：{result_word(d.labels.get('mission_success_observation'))}", f"默认资格：{result_word(d.quality.get('benchmark_eligible'))}", f"严格资格：{result_word(d.quality.get('strict_benchmark_eligible'))}", f"分析目录：{d.analysis_name}", "此界面未重算结果、未执行证据哈希审计。"]
        else:
            text += ["", "只展示规划目标，没有实际飞行证据。", "虚线路径不表示实际飞行时间或覆盖结果。"]
        if d.warnings:
            text += ["", "读取提示："] + d.warnings
        self.details.setPlainText("\n".join(text))

    def set_transport_enabled(self, enabled):
        for widget in (self.play, self.rewind, self.mission, self.slider, self.time_box, self.speed):
            widget.setEnabled(enabled)

    def set_playing(self, value):
        self.playing = bool(value)
        self.last_tick = time.perf_counter()
        self.play.setText("暂停" if self.playing else "播放")

    def toggle_play(self):
        if not self.data or not self.play.isEnabled():
            return
        if not self.playing and self.current_t >= self.data.duration:
            self.seek(0.0)
        self.set_playing(not self.playing)

    def tick(self):
        now = time.perf_counter()
        dt = now - self.last_tick
        self.last_tick = now
        if self.playing and self.data:
            self.seek(self.current_t + dt * self.speed.currentData())

    def slider_changed(self, value):
        if self.data:
            self.seek(self.data.duration * value / 10000)

    def seek(self, t):
        if not self.data:
            return
        self.current_t = min(self.data.duration, max(0.0, float(t)))
        if self.current_t >= self.data.duration:
            self.set_playing(False)
        self.slider.blockSignals(True)
        self.slider.setValue(round(self.current_t / self.data.duration * 10000) if self.data.duration else 0)
        self.slider.blockSignals(False)
        self.time_box.blockSignals(True)
        self.time_box.setValue(self.current_t)
        self.time_box.blockSignals(False)
        self.redraw()

    def redraw(self, *_):
        if not self.data or not self.graphics:
            return
        d, t = self.data, self.current_t
        for row, agent in enumerate(d.agent_ids):
            visible = self.agent_list.item(row).checkState() == QtCore.Qt.Checked
            g = self.graphics[agent]
            g["plan"].setVisible(visible and self.plan_check.isChecked())
            g["start"].setVisible(visible)
            if g["partition"]:
                g["partition"].setVisible(visible and self.partition_check.isChecked())
            a = self.arrays[agent]
            end = len(a[0]) if self.full_check.isChecked() else np.searchsorted(a[0], t, side="right")
            g["trail"].setData(a[1][:end], a[2][:end], connect="finite")
            g["trail"].setVisible(visible and self.trail_check.isChecked())
            g["altitude"].setVisible(visible)
            sample = d.tracks[agent].at(t, d.max_gap) if agent in d.tracks else None
            if sample:
                g["marker"].setData([sample.xyz[0]], [sample.xyz[1]])
                g["label"].setPos(sample.xyz[0] + 0.6, sample.xyz[1] + 0.6)
                state = "已解锁" if sample.armed == "1" else "有效"
                values = [state, f"{sample.xyz[2]:.2f}", f"{sample.speed:.2f}" if sample.speed is not None else "—"]
                tooltip = f"样本 t={sample.t:.3f}s；模式编号 {sample.mode or '未知'}"
            else:
                values = ["缺失 / 过期" if d.is_run else "计划", "—", "—"]
                tooltip = "当前位置没有有效记录，不使用过去位置或计划位置冒充。"
            g["marker"].setVisible(visible and sample is not None)
            g["label"].setVisible(visible and sample is not None)
            for col, value in enumerate(values, 1):
                self.table.item(row, col).setText(value)
                self.table.item(row, col).setToolTip(tooltip)
        self.cursor.setValue(t)
        index = bisect.bisect_right(self.event_times, t) - 1
        if index >= 0:
            event = d.events[index]
            phase = event.get("phase", "")
            semantic = d.scene.get("semantic_plan", {}).get("execution_phases", {}).get(phase, {}).get("semantic_phase", "")
            self.state.setText(f"{PHASE_NAMES.get(semantic, EVENT_NAMES.get(event['event'], event['event']))}  {phase}")
            self.event_list.setCurrentRow(index)
        else:
            self.state.setText("历史回放 · 准备阶段" if d.is_run else "计划预览 · 尚未执行")
            self.event_list.setCurrentRow(-1)

    def fit_view(self):
        if not self.data:
            return
        points = [(v["east_m"], v["north_m"]) for v in self.data.scene["vehicles"]]
        points += [(target["east_m"], target["north_m"]) for phase in self.data.scene["phases"] for target in phase["targets"].values()]
        for region in self.data.scene.get("planning", {}).get("region_partitions", []):
            points += [(region["min_east_m"], region["min_north_m"]), (region["min_east_m"] + region["width_m"], region["min_north_m"] + region["height_m"])]
        for a in self.arrays.values():
            valid = np.isfinite(a[1]) & np.isfinite(a[2])
            if valid.any():
                points += [(float(a[1][valid].min()), float(a[2][valid].min())), (float(a[1][valid].max()), float(a[2][valid].max()))]
        xs, ys = zip(*points)
        self.map.setRange(xRange=(min(xs) - 3, max(xs) + 3), yRange=(min(ys) - 3, max(ys) + 3), padding=0.04)
        self.height.enableAutoRange()
        if self.data.duration:
            self.height.setXRange(0, self.data.duration, padding=0.015)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.statusBar().showMessage("正在读取文件，请读取结束后关闭。")
            event.ignore()
            return
        self.timer.stop()
        event.accept()


def launch(path=None):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    configure_application(app)
    window = ReplayWindow()
    window.show()
    QtCore.QTimer.singleShot(0, lambda: window.load_path(path) if path else window.load_demo())
    return app.exec_()
