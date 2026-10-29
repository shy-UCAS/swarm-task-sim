"""Qt display only. All episode validation and scene loading use viz_episodes."""
from pathlib import Path
import sys
import time

import numpy as np
from PyQt5 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from scripts import viz_episodes as source

INTENTS = {"reconnaissance": "侦察", "patrol": "巡逻", "rapid_passage": "快速通过"}


def word(value):
    return "是" if value is True else "否" if value is False else "—"


def catalogue(folder):
    records = []
    for path in source.discover_episodes(folder):
        record = dict(path=path, identity=path.name, intent=None, family=None,
                      pattern=None, success=None, quality=None, error=None)
        try:
            # Listing metadata is a preview, not an accepted/validated episode.
            manifest = source.read_json(path / "manifest.json")
            record.update(identity=manifest.get("run_id") or path.name,
                          intent=manifest.get("intent"), family=manifest.get("family_id"),
                          pattern=manifest.get("flight_pattern"), success=manifest.get("mission_success"),
                          quality=manifest.get("episode_quality_eligible"))
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        records.append(record)
    return records


class Reader(QtCore.QThread):
    ready = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, operation, path, parent):
        super().__init__(parent)
        self.operation, self.path = operation, path

    def run(self):
        try:
            self.ready.emit(self.operation(self.path))
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class EpisodePlayer(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Episode 轨迹播放器 · 离线只读")
        self.resize(1500, 900)
        self.reader = None
        self.records, self.rows, self.graphics = [], {}, {}
        self.item = None
        self.times = np.empty(0)
        self.xy = np.empty((0, 0, 2))
        self.mask = np.empty((0, 0), dtype=bool)
        self.current_t = 0.0
        self.frame = -1
        self.playing = False
        self.anchor_clock = time.perf_counter()
        self.anchor_t = 0.0
        self.max_gap = float("inf")
        self._build()
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.set_transport(False)

    def _build(self):
        self.open_action = self.menuBar().addMenu("文件").addAction("打开文件夹…")
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self.pick_folder)
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        layout = QtWidgets.QVBoxLayout(root)
        self.info = QtWidgets.QLabel("打开文件夹后，双击左侧 episode 加载")
        self.info.setTextFormat(QtCore.Qt.PlainText)
        self.info.setWordWrap(True)
        self.info.setStyleSheet("font-size: 15px; padding: 8px;")
        layout.addWidget(self.info)
        splitter = QtWidgets.QSplitter()
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        self.source_label = QtWidgets.QLabel("尚未导入数据")
        self.source_label.setTextFormat(QtCore.Qt.PlainText)
        self.source_label.setWordWrap(True)
        left_layout.addWidget(self.source_label)
        self.intent_filter = QtWidgets.QComboBox()
        self.family_filter = QtWidgets.QComboBox()
        for label, box in (("意图", self.intent_filter), ("Family", self.family_filter)):
            row = QtWidgets.QHBoxLayout()
            row.addWidget(QtWidgets.QLabel(label))
            row.addWidget(box, 1)
            box.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
            box.addItem("全部", None)
            box.currentIndexChanged.connect(self.filter_rows)
            left_layout.addLayout(row)
        self.list = QtWidgets.QTreeWidget()
        self.list.setHeaderLabels(["Episode", "意图", "计划飞法", "成功", "质量"])
        self.list.setRootIsDecorated(False)
        self.list.setUniformRowHeights(True)
        self.list.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.list.itemDoubleClicked.connect(self.load_row)
        for index, width in enumerate((220, 75, 165, 50, 50)):
            self.list.setColumnWidth(index, width)
        left_layout.addWidget(self.list, 1)
        self.count = QtWidgets.QLabel()
        left_layout.addWidget(self.count)
        splitter.addWidget(left)
        center = QtWidgets.QWidget()
        center_layout = QtWidgets.QVBoxLayout(center)
        self.map = pg.PlotWidget(background="w")
        self.map.setLabel("bottom", "East", units="m")
        self.map.setLabel("left", "North", units="m")
        self.map.setAspectLocked(True)
        self.map.setMenuEnabled(False)
        self.map.getPlotItem().hideButtons()
        self.map.showGrid(x=True, y=True, alpha=.15)
        center_layout.addWidget(self.map, 1)
        bottom = QtWidgets.QHBoxLayout()
        bottom.addWidget(QtWidgets.QLabel("灰色：目标区  ·  虚线：世界边界  ·  浅线：全程观测  ·  实线：最近 10 秒"))
        fit = QtWidgets.QPushButton("适应全图")
        fit.clicked.connect(self.fit_view)
        bottom.addWidget(fit)
        center_layout.addLayout(bottom)
        splitter.addWidget(center)
        splitter.setSizes([570, 900])
        layout.addWidget(splitter, 1)
        controls = QtWidgets.QHBoxLayout()
        self.play = QtWidgets.QPushButton("播放")
        self.play.clicked.connect(self.toggle_play)
        self.previous = QtWidgets.QPushButton("上一帧")
        self.previous.clicked.connect(lambda: self.step(-1))
        self.next = QtWidgets.QPushButton("下一帧")
        self.next.clicked.connect(lambda: self.step(1))
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.sliderPressed.connect(lambda: self.set_playing(False))
        self.slider.valueChanged.connect(self.slider_changed)
        self.speed = QtWidgets.QComboBox()
        for value in (1, 5, 20):
            self.speed.addItem(f"{value}×", value)
        self.speed.currentIndexChanged.connect(self.change_speed)
        self.clock = QtWidgets.QLabel("0.00 / 0.00 s")
        self.clock.setMinimumWidth(155)
        for widget in (self.play, self.previous, self.next, self.slider, self.speed, self.clock):
            controls.addWidget(widget, 1 if widget is self.slider else 0)
        layout.addLayout(controls)
        self.statusBar().showMessage("只读模型观测；加载前保留全部哈希及版本校验")

    def pick_folder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "选择 episode、示例、数据集或批次目录")
        if folder:
            self.open_source(Path(folder))

    def start_reader(self, operation, path, ready, failed):
        if self.reader is not None:
            return
        self.set_playing(False)
        self.open_action.setEnabled(False)
        self.list.setEnabled(False)
        self.set_transport(False)
        self.reader = Reader(operation, path, self)
        self.reader.ready.connect(ready)
        self.reader.failed.connect(failed)
        self.reader.finished.connect(self.reader_finished)
        self.statusBar().showMessage("正在读取……")
        self.reader.start()

    def reader_finished(self):
        self.reader.deleteLater()
        self.reader = None
        self.open_action.setEnabled(True)
        self.list.setEnabled(True)
        self.set_transport(bool(len(self.times)))

    def open_source(self, folder):
        folder = Path(folder).resolve()
        self.start_reader(catalogue, folder, lambda records: self.apply_catalogue(folder, records),
                          lambda reason: self.error_dialog("无法导入目录", reason))

    def apply_catalogue(self, folder, records):
        self.records = records
        self.rows.clear()
        self.list.clear()
        self.item = None
        self.times = np.empty(0)
        self.graphics.clear()
        self.map.clear()
        self.current_t, self.frame = 0.0, -1
        self.slider.setRange(0, 0)
        self.clock.setText("0.00 / 0.00 s")
        self.info.setText("双击 episode 加载；列表元数据将在加载时核验")
        self.info.setStyleSheet("font-size: 15px; padding: 8px;")
        self.source_label.setText(str(folder))
        for record in records:
            row = QtWidgets.QTreeWidgetItem([record["identity"], INTENTS.get(record["intent"], record["intent"]) or "—",
                                            record["pattern"] or "—", word(record["success"]), word(record["quality"])])
            row.setData(0, QtCore.Qt.UserRole, record)
            self.list.addTopLevelItem(row)
            self.rows[record["path"]] = row
            self.decorate_row(row)
        for box, key in ((self.intent_filter, "intent"), (self.family_filter, "family")):
            box.blockSignals(True)
            box.clear()
            box.addItem("全部", None)
            for value in sorted({r[key] for r in records if r[key]}):
                box.addItem(INTENTS.get(value, value) if key == "intent" else value, value)
            box.blockSignals(False)
        self.filter_rows()
        self.statusBar().showMessage(f"已导入 {len(records)} 个 episode；双击后执行加载器校验")

    def decorate_row(self, row):
        record = row.data(0, QtCore.Qt.UserRole)
        color = "#888888" if record["error"] else "#202020"
        hint = record["error"] or f"{record['path']}\nfamily={record['family'] or '—'}\n双击加载并校验"
        for column in range(5):
            row.setForeground(column, QtGui.QBrush(QtGui.QColor(color)))
            row.setToolTip(column, hint)

    def filter_rows(self, *_):
        visible = 0
        for row in self.rows.values():
            record = row.data(0, QtCore.Qt.UserRole)
            match = all(box.currentData() is None or box.currentData() == record[key]
                        for box, key in ((self.intent_filter, "intent"), (self.family_filter, "family")))
            row.setHidden(not match)
            visible += int(match)
        self.count.setText(f"显示 {visible} / {len(self.rows)} 个；灰色表示加载失败")

    def load_row(self, row, _column=0):
        record = row.data(0, QtCore.Qt.UserRole)
        self.start_reader(source.load_plot_episode, record["path"],
                          lambda item: self.loaded(row, item), lambda reason: self.load_failed(row, reason))

    def loaded(self, row, item):
        try:
            self.apply_episode(item)
        except Exception as exc:
            self.load_failed(row, f"{type(exc).__name__}: {exc}")
            return
        record = row.data(0, QtCore.Qt.UserRole)
        record["error"] = None
        row.setData(0, QtCore.Qt.UserRole, record)
        self.decorate_row(row)
        self.statusBar().showMessage("加载完成；按观测采样帧显示，不插值；拖动或逐帧操作会暂停")

    def load_failed(self, row, reason):
        record = row.data(0, QtCore.Qt.UserRole)
        record["error"] = reason
        row.setData(0, QtCore.Qt.UserRole, record)
        self.decorate_row(row)
        self.error_dialog(f"无法加载 {record['identity']}", reason)

    def error_dialog(self, title, reason):
        self.statusBar().showMessage("加载失败；可继续选择其他 episode")
        QtWidgets.QMessageBox.warning(self, title, reason)

    def apply_episode(self, item):
        data = item["data"]
        times = np.asarray(data["t_s"], dtype=float)
        mask = np.asarray(data["mask"], dtype=bool).reshape(len(times), len(data["agent_ids"]))
        xy = np.asarray(data["x"], dtype=float).reshape(len(times), len(data["agent_ids"]), 6)[:, :, :2].copy()
        xy[~mask] = np.nan
        self.set_playing(False)
        self.item, self.times, self.mask, self.xy = item, times, mask, xy
        context = data["metadata"].get("evaluation_context") or {}
        self.max_gap = context.get("execution", {}).get("max_gap_s", context.get("max_gap_s", float("inf")))
        self.graphics.clear()
        self.map.clear()
        box = source.rectangle(item["corners"])
        region = QtWidgets.QGraphicsRectItem(*box)
        region.setBrush(QtGui.QColor(210, 210, 210, 100))
        region.setPen(pg.mkPen("#888888"))
        region.setZValue(-5)
        self.map.addItem(region)
        world = item["world"]
        if "east_bounds_m" in world and "north_bounds_m" in world:
            east, north = world["east_bounds_m"], world["north_bounds_m"]
            boundary = QtWidgets.QGraphicsRectItem(east[0], north[0], east[1] - east[0], north[1] - north[0])
            boundary.setPen(pg.mkPen("#999999", style=QtCore.Qt.DashLine))
            self.map.addItem(boundary)
        for index, agent in enumerate(data["agent_ids"]):
            color = source.COLORS[index % len(source.COLORS)]
            faint = QtGui.QColor(color)
            faint.setAlpha(60)
            self.map.plot(xy[:, index, 0], xy[:, index, 1], pen=pg.mkPen(faint, width=1.3), connect="finite")
            tail = self.map.plot([], [], pen=pg.mkPen(color, width=2.5), connect="finite")
            marker = self.map.plot([], [], pen=None, symbol="o", symbolSize=13,
                                   symbolBrush=color, symbolPen="w")
            label = pg.TextItem(agent, color=color, anchor=(0, 1.2))
            self.map.addItem(label)
            self.graphics[agent] = dict(tail=tail, marker=marker, label=label)
        labels, meta = data["targets"], data["metadata"]
        intent = labels.get("requested_intent") or labels.get("assigned_intent")
        success = labels.get("mission_success", meta.get("mission_success"))
        quality = meta.get("episode_quality_eligible")
        self.info.setText(f"{meta.get('run_id') or item['path'].name}  |  意图：{INTENTS.get(intent, intent) or '—'}  |  "
                          f"计划飞法：{meta.get('flight_pattern') or '—'}  |  任务成功：{word(success)}  |  质量合格：{word(quality)}")
        failed = success is False or quality is False or labels.get("run_status") == "failed"
        self.info.setStyleSheet(f"font-size: 15px; padding: 8px; color: {'#b22222' if failed else '#202020'};")
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, len(times) - 1))
        self.slider.blockSignals(False)
        self.set_transport(bool(len(times)))
        self.seek(float(times[0]) if len(times) else 0.0)
        self.fit_view()

    def set_transport(self, enabled):
        for widget in (self.play, self.previous, self.next, self.slider, self.speed):
            widget.setEnabled(enabled)

    def set_playing(self, value):
        self.playing = bool(value and len(self.times))
        self.anchor_clock, self.anchor_t = time.perf_counter(), self.current_t
        self.play.setText("暂停" if self.playing else "播放")

    def toggle_play(self):
        if not len(self.times):
            return
        if not self.playing and self.current_t >= self.times[-1]:
            self.seek(float(self.times[0]))
        self.set_playing(not self.playing)

    def change_speed(self, *_):
        self.anchor_clock, self.anchor_t = time.perf_counter(), self.current_t

    def tick(self, now=None):
        if self.playing:
            elapsed = (time.perf_counter() if now is None else now) - self.anchor_clock
            self.seek(self.anchor_t + elapsed * self.speed.currentData())

    def slider_changed(self, frame):
        self.set_playing(False)
        if len(self.times):
            self.seek(float(self.times[frame]))

    def step(self, delta):
        self.set_playing(False)
        if len(self.times):
            frame = max(0, min(len(self.times) - 1, self.frame + delta))
            self.seek(float(self.times[frame]))

    def seek(self, stamp):
        if not len(self.times):
            self.current_t, self.frame = 0.0, -1
            self.clock.setText("0.00 / 0.00 s · 无观测帧")
        else:
            self.current_t = min(float(self.times[-1]), max(float(self.times[0]), stamp))
            self.frame = int(np.searchsorted(self.times, self.current_t, side="right")) - 1
            if self.current_t >= self.times[-1]:
                self.set_playing(False)
            self.slider.blockSignals(True)
            self.slider.setValue(self.frame)
            self.slider.blockSignals(False)
            self.clock.setText(f"{self.current_t:.2f} / {self.times[-1]:.2f} s")
        begin = int(np.searchsorted(self.times, self.current_t - 10, side="left"))
        for index, graphics in enumerate(self.graphics.values()):
            points = self.xy[begin:self.frame + 1, index]
            graphics["tail"].setData(points[:, 0], points[:, 1], connect="finite")
            visible = (self.frame >= 0 and self.mask[self.frame, index]
                       and self.current_t - self.times[self.frame] <= self.max_gap)
            graphics["marker"].setVisible(bool(visible))
            graphics["label"].setVisible(bool(visible))
            if visible:
                east, north = self.xy[self.frame, index]
                graphics["marker"].setData([east], [north])
                graphics["label"].setPos(east, north)

    def fit_view(self):
        if self.item is not None:
            self.map.autoRange(padding=.05)

    def closeEvent(self, event):
        if self.reader is not None:
            self.statusBar().showMessage("正在读取文件，请读取完成后关闭")
            event.ignore()
            return
        self.timer.stop()
        event.accept()


def launch(folder=None):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    if not QtGui.QFontDatabase().families():
        font = Path("C:/Windows/Fonts/msyh.ttc")
        if font.is_file():
            QtGui.QFontDatabase.addApplicationFont(str(font))
    app.setFont(QtGui.QFont("Microsoft YaHei UI", 9))
    pg.setConfigOptions(antialias=True)
    window = EpisodePlayer()
    window.show()
    if folder is not None:
        QtCore.QTimer.singleShot(0, lambda: window.open_source(folder))
    return app.exec_()
